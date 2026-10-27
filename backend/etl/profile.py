"""Viết "hồ sơ phim" bằng LLM cho các phim chưa có profile, ưu tiên phim nhiều vote.

Mỗi lần gọi ghi token vào data/profile_usage.jsonl để tính chi phí.
Chạy:  .venv/Scripts/python etl/profile.py --top 5000 --ids eval/questions_resolved.json
"""
import argparse, asyncio, json, os, random, sys, time
from pathlib import Path

import httpx
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.llm import parse_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
USAGE = ROOT / "data/profile_usage.jsonl"
CONCURRENCY = 10
# provider hay trả 429 theo đợt → mỗi lần thử lại xoay sang model dự phòng
FALLBACK_MODELS = ["gpt-5.4-mini", "gemini-3.5-flash"]

SYSTEM = """Bạn là biên tập viên phim, viết "hồ sơ cảm nhận" cho hệ thống gợi ý phim tiếng Việt.
Hồ sơ KHÔNG kể cốt truyện (cốt truyện đã có ở phần tóm tắt). Hồ sơ trả lời: xem phim này CẢM THẤY thế nào, hợp với ai.
Trả về JSON đúng các khoá sau, mọi giá trị bằng tiếng Việt, ngắn gọn:
{
 "tam_trang": "2-4 tính từ cảm xúc khi xem, vd: u buồn, ám ảnh, ấm áp, hồi hộp, sảng khoái",
 "nhip_phim": "chậm / vừa / nhanh + 1 cụm mô tả, vd: chậm rãi, nhiều khoảng lặng",
 "chu_de": "3-5 chủ đề sâu, vd: tình cha con, cái giá của tham vọng, cô đơn, giai cấp",
 "tong": "tông tổng thể, vd: u tối nghiêm túc / hài hước nhẹ nhàng / lãng mạn day dứt",
 "kieu_ket": "kiểu kết KHÔNG spoil, vd: mở, gây tranh cãi, có hậu, buồn, twist bất ngờ",
 "phong_cach": "điểm đặc trưng về cách làm phim, vd: hình ảnh hoành tráng, thoại nhiều, nhạc nổi bật",
 "hop_voi": "hợp người xem nào / dịp nào, vd: người thích xoắn não, xem một mình đêm khuya, cả gia đình",
 "tu_khoa": ["6-10 cụm từ người Việt hay gõ khi tìm phim kiểu này, vd: phim xoắn não, phim chữa lành, phim cười thả ga"]
}
Không bịa giải thưởng hay số liệu. Không nhắc tên nhân vật."""

FIELDS = [("tam_trang", "Tâm trạng"), ("nhip_phim", "Nhịp phim"), ("chu_de", "Chủ đề"), ("tong", "Tông"),
          ("kieu_ket", "Kiểu kết"), ("phong_cach", "Phong cách"), ("hop_voi", "Hợp với")]


def to_profile(d):
    lines = [f"{label}: {d[k]}" for k, label in FIELDS if d.get(k)]
    if d.get("tu_khoa"):
        kw = d["tu_khoa"] if isinstance(d["tu_khoa"], list) else [d["tu_khoa"]]
        lines.append("Hay được tìm: " + ", ".join(kw))
    return "\n".join(lines)


def prompt(m):
    parts = [
        ("Series truyền hình. " if m["id"] < 0 else "") + f"Tên: {m['title']} ({m['year']})" + (f" — tên Việt: {m['title_vi']}" if m["title_vi"] else ""),
        f"Thể loại: {', '.join(m['genres'])}",
        (f"Thời lượng: {m['runtime']} phút" + ("/tập" if m["id"] < 0 else "")) if m["runtime"] else "",
        f"Đạo diễn: {', '.join(m['director'])}" if m["director"] else "",
        f"Diễn viên: {', '.join(m['cast_top'])}" if m["cast_top"] else "",
        f"Từ khoá: {', '.join(m['keywords'][:25])}" if m["keywords"] else "",
        f"Tagline: {m['tagline']}" if m["tagline"] else "",
        f"Tóm tắt: {m['overview']}" if m["overview"] else "",
    ]
    return "\n".join(p for p in parts if p)


async def write_profile(client, m):
    models = [os.environ["LLM_MODEL_OFFLINE"], *FALLBACK_MODELS]
    body = {"temperature": 0.4, "max_tokens": 500,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt(m)}]}
    for attempt in range(7):
        try:
            t = time.time()
            body["model"] = models[attempt % len(models)]
            r = await client.post("/chat/completions", json=body)
            r.raise_for_status()
            data = r.json()
            d = parse_json(data["choices"][0]["message"]["content"])
            return to_profile(d), {"model": body["model"], **data.get("usage", {})}, time.time() - t
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            print(f"  lỗi id={m['id']} lần {attempt + 1}: {type(e).__name__} {code or ''}", flush=True)
            if code in (401, 402, 403):
                raise SystemExit("provider từ chối (hết tiền / key lỗi) → dừng")
            await asyncio.sleep(min(30, 2 * 2 ** attempt) * (0.5 + random.random()))
    return None, {}, 0


async def main(top, extra_ids, kind="movie", min_year=0, limit=0):
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        cur = conn.cursor(row_factory=dict_row)
        todo = cur.execute(
            "SELECT id, title, title_vi, year, genres, runtime, director, cast_top, keywords, tagline, overview "
            "FROM movies WHERE profile IS NULL AND kind = %s AND (id = ANY(%s) OR id IN "
            "(SELECT id FROM movies WHERE kind = %s ORDER BY vote_count DESC NULLS LAST LIMIT %s) OR original_language = 'vi') "
            "ORDER BY vote_count DESC NULLS LAST", (kind, extra_ids, kind, top)).fetchall()
        # ưu tiên phim mới: bỏ phim trước min_year (trừ phim bắt buộc trong extra_ids)
        todo = [m for m in todo if m["id"] in extra_ids or (m["year"] or 0) >= min_year]
        if limit:
            todo = todo[:limit]
        print(f"cần viết: {len(todo)}")

        sem, done, fail = asyncio.Semaphore(CONCURRENCY), 0, 0
        headers = {"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"}
        async with httpx.AsyncClient(base_url=os.environ["LLM_BASE_URL"], headers=headers, timeout=httpx.Timeout(45, connect=10)) as client:
            with USAGE.open("a", encoding="utf-8") as log:
                async def one(m):
                    nonlocal done, fail
                    async with sem:
                        text, usage, secs = await write_profile(client, m)
                    if not text:
                        fail += 1
                        return
                    conn.execute("UPDATE movies SET profile = %s, updated_at = now() WHERE id = %s", (text, m["id"]))
                    conn.commit()
                    log.write(json.dumps({"id": m["id"], "secs": round(secs, 2), **usage}) + "\n")
                    done += 1
                    if done % 100 == 0:
                        print(f"  {done}/{len(todo)}", flush=True)
                await asyncio.gather(*(one(m) for m in todo))
    print(f"xong: {done} | lỗi: {fail}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50, help="N phim nhiều vote nhất (phim Việt luôn được thêm)")
    ap.add_argument("--min-year", type=int, default=0, help="bỏ qua phim cũ hơn năm này")
    ap.add_argument("--limit", type=int, default=0, help="viết tối đa N hồ sơ lần này")
    ap.add_argument("--kind", default="movie", choices=["movie", "tv"], help="movie = phim lẻ, tv = series")
    ap.add_argument("--ids", help="file JSON danh sách id bắt buộc có (vd eval/questions_resolved.json)")
    a = ap.parse_args()
    extra = []
    if a.ids:
        for q in json.loads(Path(a.ids).read_text(encoding="utf-8")):
            extra += q.get("expect_ids", []) + ([q["ref"]] if q.get("ref") else [])
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(a.top, extra, a.kind, a.min_year, a.limit))
