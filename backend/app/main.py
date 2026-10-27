"""FastAPI cho frontend.  Chạy: .venv/Scripts/uvicorn app.main:app --port 8000"""
import hashlib
import json
import queue
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector
from pydantic import BaseModel

from app import config
from app.engine.filters import GENRE_VI
from app.engine.pipeline import ask as run_ask, load_movies
from app.engine.similar import pair_sim, similar

IMG = "https://image.tmdb.org/t/p/w500"


def _configure(conn):
    register_vector(conn)
    conn.autocommit = True


pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=8, configure=_configure, open=True)
app = FastAPI(title="CineMind API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class AskIn(BaseModel):
    text: str | None = None
    type: str | None = None
    ids: list[int] | None = None
    id: int | None = None
    filters: list[dict] | None = None
    query: dict | None = None


def _profile_field(profile, name):
    for line in (profile or "").split("\n"):
        if line.startswith(name + ":"):
            return line.split(":", 1)[1].strip()
    return ""


def catalog(conn, ids):
    """Dữ liệu phim theo đúng shape frontend đang dùng (src/data/movies.js)."""
    if not ids:
        return {}
    cur = conn.cursor(row_factory=dict_row)
    rows = cur.execute(
        "SELECT id, kind, title, title_vi, year, director, cast_top, genres, runtime, imdb_rating, vote_average, "
        "poster_path, backdrop_path, profile, keywords, overview, overview_vi FROM movies WHERE id = ANY(%s)", (list(ids),)).fetchall()
    out = {}
    for r in rows:
        mood = _profile_field(r["profile"], "Tâm trạng")
        out[r["id"]] = {
            "id": r["id"], "kind": r["kind"], "title": r["title"], "title_vi": r["title_vi"], "year": r["year"],
            "director": ", ".join(r["director"][:2]), "cast": r["cast_top"][:3],
            "genres": [GENRE_VI.get(g, g) for g in r["genres"]], "runtime": r["runtime"] or 0,
            "rating": round(r["imdb_rating"] or r["vote_average"] or 0, 1),
            "poster": IMG + r["poster_path"] if r["poster_path"] else None,
            "mood": mood[:1].upper() + mood[1:] if mood else "",
            "keywords": r["keywords"][:6], "overview": r["overview_vi"] or r["overview"] or "",
            "backdrop": "https://image.tmdb.org/t/p/w780" + r["backdrop_path"] if r["backdrop_path"] else None,
            "profile": [line.split(": ", 1) for line in (r["profile"] or "").splitlines() if ": " in line],
            "hue": int(hashlib.md5(str(r["id"]).encode()).hexdigest(), 16) % 360,
        }
    return out


@app.post("/api/ask")
def api_ask(body: AskIn):
    with pool.connection() as conn:
        res = run_ask(conn, body.model_dump(exclude_none=True))
        ids = [m["id"] for m in res.get("movies", [])] + list(res.get("compare", []))
        res["catalog"] = catalog(conn, ids)
    return res


@app.post("/api/ask/stream")
def api_ask_stream(body: AskIn):
    """NDJSON: {"type":"steps","steps":[...]} · {"type":"preview","movies":[...],"catalog":{...}} · {"type":"final",...}"""
    q = queue.Queue()

    def work():
        try:
            with pool.connection() as conn:
                def emit(kind, data):
                    if kind == "steps":
                        q.put({"type": "steps", "steps": data})
                    elif kind == "preview":
                        q.put({"type": "preview", "movies": data, "catalog": catalog(conn, [m["id"] for m in data])})
                res = run_ask(conn, body.model_dump(exclude_none=True), emit)
                ids = [m["id"] for m in res.get("movies", [])] + list(res.get("compare", []))
                res["catalog"] = catalog(conn, ids)
                q.put({"type": "final", **res})
        except Exception as e:  # noqa: BLE001 — báo lỗi về UI thay vì treo stream
            q.put({"type": "error", "message": str(e)[:200]})
        q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def gen():
        while (item := q.get()) is not None:
            yield json.dumps(item, ensure_ascii=False) + chr(10)

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/movies")
def api_movies(ids: str):
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()][:100]
    except ValueError:
        raise HTTPException(400, "ids phải là danh sách số")
    with pool.connection() as conn:
        return catalog(conn, id_list)


@app.get("/api/similar")
def api_similar(id: int, n: int = 4):
    with pool.connection() as conn:
        ref = load_movies(conn, [id])
        if not ref or ref[0]["dense"] is None:
            return {"items": [], "catalog": {}}
        items = similar(conn, ref[0], min(n, 12))
        return {"items": items, "catalog": catalog(conn, [x["id"] for x in items])}


@app.get("/api/pair")
def api_pair(a: int, b: int):
    with pool.connection() as conn:
        ms = load_movies(conn, [a, b])
        if len(ms) < 2 or any(m["dense"] is None for m in ms):
            return {"sim": None, "catalog": {}}
        return {"sim": pair_sim(ms[0], ms[1]), "catalog": catalog(conn, [a, b])}


@app.get("/api/trending")
def api_trending():
    with pool.connection() as conn:
        rows = conn.execute("SELECT period, movie_id FROM trending ORDER BY period, rank").fetchall()
        if not rows:  # chưa chạy etl/trending.py → tạm lấy theo popularity
            week = [r[0] for r in conn.execute(
                "SELECT id FROM movies WHERE profile IS NOT NULL ORDER BY popularity DESC LIMIT 10")]
            month = [r[0] for r in conn.execute(
                "SELECT id FROM movies WHERE profile IS NOT NULL AND year >= extract(year FROM now()) - 2 "
                "ORDER BY vote_count DESC LIMIT 10")]
        else:
            week = [m for p, m in rows if p == "week"]
            month = [m for p, m in rows if p == "month"]
        return {"week": week, "month": month, "catalog": catalog(conn, week + month)}


@app.get("/api/health")
def health():
    with pool.connection() as conn:
        n, prof, emb = conn.execute("SELECT count(*), count(profile), count(dense) FROM movies").fetchone()
    return {"movies": n, "profiles": prof, "embedded": emb, "embed_model": config.EMBED_MODEL,
            "rerank": config.RERANK, "jev_top": config.JEV_TOP, "pool": config.POOL_N}
