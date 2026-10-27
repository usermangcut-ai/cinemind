"""Đánh giá 100 câu hỏi kiểu người dùng thật — chấm bằng LLM giám khảo (model khác với model của engine).

Bước 1 (run):   chạy engine cho từng câu → data/eval100/results.jsonl (chạy lại được, bỏ qua câu đã có)
Bước 2 (judge): giám khảo chấm từng phim trong top 10: 2 = rất hợp · 1 = tạm hợp · 0 = không hợp → judged.jsonl
Bước 3 (report): bảng tổng hợp theo nhóm → data/eval100/report.md
Chạy:  .venv/Scripts/python -m eval.eval100 run | judge | report
"""
import json, statistics as st, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app import config, llm
from app.engine.pipeline import ask

HERE = Path(__file__).parent
OUT = config.ROOT / "data/eval100"
OUT.mkdir(parents=True, exist_ok=True)
RES, JUD = OUT / "results.jsonl", OUT / "judged.jsonl"
JUDGE_MODEL = "claude-haiku-4-5-20251001"


def load(p):
    return {json.loads(l)["id"]: json.loads(l) for l in p.open(encoding="utf-8")} if p.exists() else {}


def run_one(q):
    for attempt in range(3):
        try:
            return _run_one(q)
        except Exception as e:  # noqa: BLE001 — provider lỗi tạm thời → thử lại cả câu
            print(f"  {q['id']} lỗi lần {attempt + 1}: {type(e).__name__}", flush=True)
            time.sleep(20)
    return None


def _run_one(q):
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        register_vector(conn)
        filters = []
        if q.get("prev"):
            first = ask(conn, {"text": q["prev"]})
            filters = [f for f in first.get("filters", []) if not f.get("relaxed")]
        t = time.time()
        r = ask(conn, {"text": q["q"], "filters": filters} if filters else {"text": q["q"]})
        secs = time.time() - t
    return {"id": q["id"], "group": q["group"], "q": q["q"], "prev": q.get("prev"), "secs": round(secs, 2),
            "ids": [m["id"] for m in r.get("movies", [])], "scores": [m.get("sim", {}).get("score") for m in r.get("movies", [])],
            "filters": [f["label"] for f in r.get("filters", [])], "clarify": bool(r.get("clarify")),
            "steps": r.get("steps"), "text": r.get("text"), "debug": r.get("_debug", {})}


def run():
    qs = json.loads((HERE / "questions100.json").read_text(encoding="utf-8"))
    done = load(RES)
    todo = [q for q in qs if q["id"] not in done]
    print(f"cần chạy: {len(todo)}/{len(qs)}", flush=True)
    with RES.open("a", encoding="utf-8") as f, ThreadPoolExecutor(2) as pool:
        for r in pool.map(run_one, todo):
            if r is None:
                continue
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  {r['id']}: {r['secs']}s · {len(r['ids'])} phim", flush=True)


JUDGE = """Bạn là giám khảo đánh giá hệ thống gợi ý phim. Với yêu cầu của user và danh sách phim hệ thống trả về,
chấm TỪNG phim: 2 = rất hợp yêu cầu, 1 = tạm hợp / hợp một phần, 0 = không hợp. Dựa trên hiểu biết của bạn về phim
và thông tin kèm theo. Nếu user có điều kiện rõ (năm, quốc gia, thể loại, thời lượng, phim lẻ/series, loại trừ) mà phim vi phạm → 0.
Trả JSON: {"scores": {"<id>": 0|1|2}, "note": "1 câu nhận xét chung về chất lượng danh sách"}"""


def judge_one(r, conn):
    if not r["ids"]:
        return {**r, "grades": [], "note": "không có kết quả" + (" (hỏi lại)" if r["clarify"] else "")}
    rows = {m["id"]: m for m in conn.execute(
        "SELECT id, kind, title, year, genres, countries, runtime, director, overview, profile FROM movies WHERE id = ANY(%s)",
        (r["ids"],)).fetchall()}
    lines = []
    for mid in r["ids"]:
        m = rows[mid]
        prof = "; ".join((m["profile"] or "").splitlines()[:3])
        lines.append(f"[{mid}] {'Series' if m['kind'] == 'tv' else 'Phim'} · {m['title']} ({m['year']}) · {', '.join(m['genres'])} · "
                     f"{', '.join(m['countries'])} · {m['runtime'] or '?'}' · ĐD {', '.join(m['director'][:2])} · {(m['overview'] or '')[:200]} · {prof}")
    req = (f"(Câu trước: \"{r['prev']}\") " if r["prev"] else "") + f"Yêu cầu: \"{r['q']}\""
    out, usage = llm.chat([{"role": "system", "content": JUDGE}, {"role": "user", "content": req + "\n\n" + "\n".join(lines)}],
                          model=JUDGE_MODEL, json_mode=True, temperature=0, max_tokens=800)
    sc = {str(k).strip("[]"): v for k, v in (out.get("scores") or {}).items()}
    return {**r, "grades": [int(sc.get(str(mid), 0)) for mid in r["ids"]], "note": out.get("note", ""),
            "judge_model": usage.get("_model")}


def judge():
    res, done = load(RES), load(JUD)
    todo = [r for k, r in res.items() if k not in done]
    print(f"cần chấm: {len(todo)}", flush=True)
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn, JUD.open("a", encoding="utf-8") as f:
        for r in todo:
            f.write(json.dumps(judge_one(r, conn), ensure_ascii=False) + "\n")
            f.flush()


def ndcg(g):
    dcg = sum(x / np.log2(i + 2) for i, x in enumerate(g))
    ideal = sum(x / np.log2(i + 2) for i, x in enumerate(sorted(g, reverse=True)))
    return dcg / ideal if ideal else 0.0


def report():
    js = list(load(JUD).values())
    qs = json.loads((HERE / "questions100.json").read_text(encoding="utf-8"))
    order = list(dict.fromkeys(q["group"] for q in qs))
    def stats(rs):
        rs_ok = [r for r in rs if r["grades"]]
        p = [sum(x >= 1 for x in r["grades"]) / len(r["grades"]) for r in rs_ok]
        good = [sum(x == 2 for x in r["grades"]) / len(r["grades"]) for r in rs_ok]
        top3 = [max(r["grades"][:3]) == 2 for r in rs_ok]
        return (len(rs), st.mean(p) if p else 0, st.mean(good) if good else 0, st.mean(top3) if top3 else 0,
                st.mean([ndcg(r["grades"]) for r in rs_ok]) if rs_ok else 0, st.median([r["secs"] for r in rs]))
    lines = ["| Nhóm | n | Hợp (≥1) / 10 | Rất hợp (=2) / 10 | Top 3 có phim rất hợp | Thứ tự (nDCG) | p50 (s) |", "|---|---|---|---|---|---|---|"]
    for g in order + ["**Tổng**"]:
        rs = js if g == "**Tổng**" else [r for r in js if r["group"] == g]
        if not rs:
            continue
        n, p, good, t3, nd, med = stats(rs)
        lines.append(f"| {g} | {n} | {p:.0%} | {good:.0%} | {t3:.0%} | {nd:.2f} | {med:.1f} |")
    secs = sorted(r["secs"] for r in js)
    lines.append(f"\nĐộ trễ: p50 {secs[len(secs) // 2]:.1f} s · p90 {secs[int(len(secs) * .9)]:.1f} s · max {secs[-1]:.1f} s · "
                 f"không có kết quả / hỏi lại: {sum(not r['grades'] for r in js)}")
    lines.append("\n## 10 câu kém nhất\n| id | câu hỏi | hợp | nhận xét của giám khảo |\n|---|---|---|---|")
    for r in sorted([r for r in js if r["grades"]], key=lambda r: sum(r["grades"]))[:10]:
        lines.append(f"| {r['id']} | {r['q']} | {sum(x >= 1 for x in r['grades'])}/10 | {r['note']} |")
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"run": run, "judge": judge, "report": report}[sys.argv[1]]()
