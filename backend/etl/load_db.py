"""Nạp data/raw/tmdb/movies.jsonl (+ IMDb ratings) vào bảng movies. Chạy lại được (upsert).

Không ghi đè profile / dense / sparse đã có.
Chạy:  .venv/Scripts/python etl/load_db.py
"""
import gzip, json, os, sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
SRC = ROOT / "data/raw/tmdb/movies.jsonl"
RATINGS = ROOT / "data/raw/imdb/title.ratings.tsv.gz"

WRITING_JOBS = {"Screenplay", "Writer", "Story", "Novel", "Author"}
KEY_CREW_JOBS = {"Original Music Composer", "Director of Photography"}

COLS = ["id", "imdb_id", "title", "original_title", "title_vi", "overview_vi", "alt_titles", "year", "release_date",
        "runtime", "original_language", "genres", "countries", "keywords", "director", "writers", "cast_top",
        "crew_key", "collection_id", "collection", "certification", "tagline", "overview", "vote_average",
        "vote_count", "imdb_rating", "imdb_votes", "popularity", "poster_path", "backdrop_path"]


def uniq(xs, n=None):
    out = list(dict.fromkeys(x for x in xs if x))
    return out[:n] if n else out


def imdb_ratings(wanted):
    out = {}
    with gzip.open(RATINGS, "rt", encoding="utf-8") as f:
        next(f)
        for line in f:
            tconst, rating, votes = line.rstrip("\n").split("\t")
            if tconst in wanted:
                out[tconst] = (float(rating), int(votes))
    return out


def to_row(m, ratings):
    vi = next((t["data"] for t in m["translations"]["translations"] if t["iso_639_1"] == "vi"), {})
    crew = m["credits"]["crew"]
    us = next((r for r in m["release_dates"]["results"] if r["iso_3166_1"] == "US"), None)
    cert = next((d["certification"] for d in (us or {}).get("release_dates", []) if d["certification"]), None)
    coll = m.get("belongs_to_collection") or {}
    rating = ratings.get(m.get("imdb_id"), (None, None))
    rd = m.get("release_date") or None
    return {
        "id": m["id"],
        "imdb_id": m.get("imdb_id"),
        "title": m["title"],
        "original_title": m.get("original_title"),
        "title_vi": vi.get("title") or None,
        "overview_vi": vi.get("overview") or None,
        "alt_titles": uniq((t["title"] for t in m["alternative_titles"]["titles"]), 20),
        "year": int(rd[:4]) if rd else None,
        "release_date": rd,
        "runtime": m.get("runtime") or None,
        "original_language": m.get("original_language"),
        "genres": [g["name"] for g in m["genres"]],
        "countries": [c["iso_3166_1"] for c in m["production_countries"]],
        "keywords": [k["name"] for k in m["keywords"]["keywords"]],
        "director": uniq(c["name"] for c in crew if c["job"] == "Director"),
        "writers": uniq((c["name"] for c in crew if c["job"] in WRITING_JOBS), 5),
        "cast_top": [c["name"] for c in sorted(m["credits"]["cast"], key=lambda c: c["order"])[:5]],
        "crew_key": uniq(c["name"] for c in crew if c["job"] in KEY_CREW_JOBS),
        "collection_id": coll.get("id"),
        "collection": coll.get("name"),
        "certification": cert,
        "tagline": m.get("tagline") or None,
        "overview": m.get("overview") or None,
        "vote_average": m.get("vote_average"),
        "vote_count": m.get("vote_count"),
        "imdb_rating": rating[0],
        "imdb_votes": rating[1],
        "popularity": m.get("popularity"),
        "poster_path": m.get("poster_path"),
        "backdrop_path": m.get("backdrop_path"),
    }


def main():
    movies = {}
    for line in SRC.open(encoding="utf-8"):
        m = json.loads(line)
        movies[m["id"]] = m  # trùng id → giữ bản sau
    ratings = imdb_ratings({m.get("imdb_id") for m in movies.values()})
    rows = [to_row(m, ratings) for m in movies.values()]

    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLS if c != "id") + ", updated_at = now()"
    sql = f"INSERT INTO movies ({', '.join(COLS)}) VALUES ({', '.join('%(' + c + ')s' for c in COLS)}) " \
          f"ON CONFLICT (id) DO UPDATE SET {sets}"
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        total, vi_title, rated = conn.execute(
            "SELECT count(*), count(title_vi), count(imdb_rating) FROM movies").fetchone()
    print(f"nạp {len(rows)} phim | DB: {total} phim, {vi_title} có tên tiếng Việt, {rated} có điểm IMDb")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
