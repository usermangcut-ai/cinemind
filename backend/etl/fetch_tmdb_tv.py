"""Kéo series TV phổ biến từ TMDB → data/raw/tmdb/tv.jsonl. Series chỉ dùng làm PHIM THAM CHIẾU
("giống Breaking Bad / Squid Game") — không được gợi ý ra kết quả (engine chỉ gợi ý phim lẻ).
Cần bật WARP. Chạy:  .venv/Scripts/python etl/fetch_tmdb_tv.py
"""
import asyncio, json, os, sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
API = "https://api.themoviedb.org/3"
HEADERS = {"Authorization": f"Bearer {os.environ['TMDB_READ_TOKEN']}"}
OUT = ROOT / "data/raw/tmdb/tv.jsonl"
MIN_VOTES = 20
PERIODS = [(None, "2009-12-31"), ("2010-01-01", "2017-12-31"), ("2018-01-01", None)]
ASIA, ASIA_MIN_VOTES = ["CN", "TW", "HK", "KR", "TH", "VN"], 3


async def get(client, path, **params):
    for attempt in range(5):
        try:
            r = await client.get(f"{API}{path}", params=params)
            if r.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except (httpx.TransportError, httpx.HTTPStatusError):
            await asyncio.sleep(2 ** attempt)
    return None


async def main():
    done = {json.loads(l)["id"] for l in OUT.open(encoding="utf-8")} if OUT.exists() else set()
    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        ids = set()
        # series châu Á: người dùng TMDB ít vote → lấy theo quốc gia, ngưỡng vote thấp, xếp theo độ hot
        for cc in ASIA:
            page, pages = 1, 1
            while page <= min(pages, 100):
                d = await get(client, "/discover/tv", page=page, with_origin_country=cc, sort_by="popularity.desc",
                              **{"vote_count.gte": ASIA_MIN_VOTES})
                if not d:
                    break
                ids |= {x["id"] for x in d["results"]}
                pages, page = d["total_pages"], page + 1
            print(f"discover tv {cc}: tổng {len(ids)}", flush=True)
        for start, end in PERIODS:
            f = {"vote_count.gte": MIN_VOTES, "sort_by": "vote_count.desc"}
            if start: f["first_air_date.gte"] = start
            if end: f["first_air_date.lte"] = end
            page, pages = 1, 1
            while page <= min(pages, 500):
                d = await get(client, "/discover/tv", page=page, **f)
                if not d:
                    break
                ids |= {x["id"] for x in d["results"]}
                pages, page = d["total_pages"], page + 1
            print(f"discover tv {start or '…'} → {end or 'nay'}: tổng {len(ids)}", flush=True)
        todo = sorted(ids - done)
        print(f"cần kéo: {len(todo)}", flush=True)
        sem, n = asyncio.Semaphore(25), 0
        with OUT.open("a", encoding="utf-8") as f:
            async def one(tid):
                nonlocal n
                async with sem:
                    d = await get(client, f"/tv/{tid}", append_to_response="keywords,translations,aggregate_credits,alternative_titles")
                if d:
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
                    n += 1
            await asyncio.gather(*(one(t) for t in todo))
    print(f"xong: ghi {n} series → {OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
