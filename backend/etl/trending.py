"""Cập nhật bảng trending (Top 10 tuần / ngày→tháng) từ TMDB /trending. Cần bật WARP.

TMDB chỉ có trending "day" và "week"; cột "Tháng" trên UI dùng top phim nhiều vote phát hành trong 60 ngày gần đây.
Chỉ giữ phim đã có trong DB và đã có profile.
Chạy:  .venv/Scripts/python etl/trending.py
"""
import os, sys
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main():
    h = {"Authorization": f"Bearer {os.environ['TMDB_READ_TOKEN']}"}
    week = []
    for page in (1, 2, 3):
        r = httpx.get("https://api.themoviedb.org/3/trending/movie/week", params={"page": page}, headers=h, timeout=20)
        r.raise_for_status()
        week += [m["id"] for m in r.json()["results"]]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        have = {r[0] for r in conn.execute("SELECT id FROM movies WHERE profile IS NOT NULL AND id = ANY(%s)", (week,))}
        week = [m for m in week if m in have][:10]
        month = [r[0] for r in conn.execute(
            "SELECT id FROM movies WHERE profile IS NOT NULL AND kind = 'movie' AND release_date >= now() - interval '60 days' "
            "ORDER BY vote_count DESC LIMIT 10")]
        # kho có hồ sơ còn nhỏ → bù cho đủ 10: tuần theo popularity, tháng theo phim mới (24 tháng) nhiều vote
        week += [r[0] for r in conn.execute(
            "SELECT id FROM movies WHERE profile IS NOT NULL AND kind = 'movie' AND NOT (id = ANY(%s)) ORDER BY popularity DESC LIMIT %s",
            (week, 10 - len(week)))]
        month += [r[0] for r in conn.execute(
            "SELECT id FROM movies WHERE profile IS NOT NULL AND kind = 'movie' AND NOT (id = ANY(%s)) AND release_date >= now() - interval '24 months' "
            "ORDER BY vote_count DESC LIMIT %s", (month, 10 - len(month)))]
        conn.execute("DELETE FROM trending")
        for period, ids in (("week", week), ("month", month)):
            for rank, mid in enumerate(ids, 1):
                conn.execute("INSERT INTO trending VALUES (%s, %s, %s)", (period, rank, mid))
    print(f"week: {len(week)} phim | month: {len(month)} phim")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
