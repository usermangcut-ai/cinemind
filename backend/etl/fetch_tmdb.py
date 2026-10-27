"""Kéo chi tiết phim từ TMDB API → data/raw/tmdb/movies.jsonl (chạy lại được, bỏ qua id đã có).

Danh sách id = TMDB discover phim vote ≥ 200 (chia theo giai đoạn vì discover giới hạn 500 trang)
             ∪ TMDB discover phim Việt vote ≥ 10.
Máy phải bật Cloudflare WARP / DNS 1.1.1.1 (nhà mạng chặn api.themoviedb.org).

Chạy:  .venv/Scripts/python etl/fetch_tmdb.py [--limit N]
"""
import argparse, asyncio, json, os, sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
API = "https://api.themoviedb.org/3"
HEADERS = {"Authorization": f"Bearer {os.environ['TMDB_READ_TOKEN']}"}
OUT = ROOT / "data/raw/tmdb/movies.jsonl"
APPEND = "credits,keywords,translations,release_dates,alternative_titles"

MIN_VOTES, MIN_VOTES_VI = 200, 10
PERIODS = [(None, "1979-12-31"), ("1980-01-01", "1999-12-31"), ("2000-01-01", "2009-12-31"),
           ("2010-01-01", "2016-12-31"), ("2017-01-01", None)]
CONCURRENCY = 25


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


async def discover_ids(client, **filters):
    ids, page, pages = set(), 1, 1
    while page <= min(pages, 500):
        data = await get(client, "/discover/movie", page=page, sort_by="vote_count.desc", include_adult="false", **filters)
        if not data:
            break
        ids |= {m["id"] for m in data["results"]}
        pages = data["total_pages"]
        page += 1
    return ids


async def main(limit):
    done = set()
    if OUT.exists():
        done = {json.loads(l)["id"] for l in OUT.open(encoding="utf-8")}

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        ids = set()
        for start, end in PERIODS:
            f = {"vote_count.gte": MIN_VOTES}
            if start: f["primary_release_date.gte"] = start
            if end: f["primary_release_date.lte"] = end
            got = await discover_ids(client, **f)
            print(f"discover {start or '…'} → {end or 'nay'}: {len(got)}")
            ids |= got
        vi = await discover_ids(client, with_original_language="vi", **{"vote_count.gte": MIN_VOTES_VI})
        print(f"phim Việt: {len(vi)}")
        ids |= vi
        todo = sorted(ids - done)
        if limit:
            todo = todo[:limit]
        print(f"tổng: {len(ids)} | đã có: {len(done)} | cần kéo: {len(todo)}")

        sem, n, miss = asyncio.Semaphore(CONCURRENCY), 0, 0
        with OUT.open("a", encoding="utf-8") as f:
            async def one(mid):
                nonlocal n, miss
                async with sem:
                    data = await get(client, f"/movie/{mid}", append_to_response=APPEND)
                if data is None:
                    miss += 1
                    return
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
                n += 1
                if n % 500 == 0:
                    print(f"  {n}/{len(todo)}", flush=True)
            await asyncio.gather(*(one(m) for m in todo))
    print(f"xong: ghi {n}, lỗi/không tồn tại {miss} → {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(ap.parse_args().limit))
