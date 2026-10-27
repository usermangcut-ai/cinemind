"""Nạp data/raw/tmdb/tv.jsonl vào bảng movies với kind='tv', id = -tmdb_tv_id (tránh trùng id phim).
Series chỉ dùng làm phim tham chiếu; ③ filter luôn có kind='movie' nên series không bao giờ ra kết quả.
Chạy:  .venv/Scripts/python etl/load_tv.py
"""
import json, os, sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl.load_db import COLS, uniq  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
SRC = ROOT / "data/raw/tmdb/tv.jsonl"


# Thể loại TV của TMDB khác bộ thể loại phim → quy về thể loại phim để filter "phim hành động" khớp cả series
TV_GENRES = {"Action & Adventure": ["Action", "Adventure"], "Sci-Fi & Fantasy": ["Science Fiction", "Fantasy"],
             "War & Politics": ["War"], "Kids": ["Family"], "Soap": ["Drama"], "Reality": [], "Talk": [], "News": []}


def tv_genres(names):
    out = []
    for g in names:
        out += TV_GENRES.get(g, [g])
    return list(dict.fromkeys(out))


def to_row(t):
    vi = next((x["data"] for x in t["translations"]["translations"] if x["iso_639_1"] == "vi"), {})
    ag = t.get("aggregate_credits") or {}
    cast = sorted(ag.get("cast", []), key=lambda c: -(c.get("total_episode_count") or 0))
    music = [c["name"] for c in ag.get("crew", []) if any(j["job"] == "Original Music Composer" for j in c.get("jobs", []))]
    fd = t.get("first_air_date") or None
    return {
        "id": -t["id"], "imdb_id": None, "title": t["name"], "original_title": t.get("original_name"),
        "title_vi": vi.get("name") or None, "overview_vi": vi.get("overview") or None,
        "alt_titles": uniq((a["title"] for a in (t.get("alternative_titles") or {}).get("results", [])), 20),
        "year": int(fd[:4]) if fd else None, "release_date": fd,
        # episode_run_time hay rỗng → lấy thời lượng tập gần nhất / sắp chiếu
        "runtime": ((t.get("episode_run_time") or [None])[0] or (t.get("last_episode_to_air") or {}).get("runtime")
                    or (t.get("next_episode_to_air") or {}).get("runtime")),
        "original_language": t.get("original_language"),
        "genres": tv_genres(g["name"] for g in t["genres"]), "countries": t.get("origin_country") or [],
        "keywords": [k["name"] for k in (t.get("keywords") or {}).get("results", [])],
        "director": [c["name"] for c in t.get("created_by", [])], "writers": [],
        "cast_top": [c["name"] for c in cast[:5]], "crew_key": uniq(music, 3),
        "collection_id": None, "collection": None, "certification": None,
        "tagline": t.get("tagline") or None, "overview": t.get("overview") or None,
        "vote_average": t.get("vote_average"), "vote_count": t.get("vote_count"),
        "imdb_rating": None, "imdb_votes": None, "popularity": t.get("popularity"),
        "poster_path": t.get("poster_path"), "backdrop_path": t.get("backdrop_path"),
    }


def main():
    rows = {}
    for line in SRC.open(encoding="utf-8"):
        t = json.loads(line)
        rows[t["id"]] = to_row(t)
    cols = COLS + ["kind"]
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
    sql = f"INSERT INTO movies ({', '.join(cols)}) VALUES ({', '.join('%(' + c + ')s' for c in cols)}) ON CONFLICT (id) DO UPDATE SET {sets}"
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, [{**r, "kind": "tv"} for r in rows.values()])
        n, vi = conn.execute("SELECT count(*), count(title_vi) FROM movies WHERE kind = 'tv'").fetchone()
    print(f"nạp {len(rows)} series | DB: {n} series, {vi} có tên tiếng Việt")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
