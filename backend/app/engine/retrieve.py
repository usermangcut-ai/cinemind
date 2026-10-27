"""④ Retrieval nhiều nguồn + RRF có trọng số, ⑤ gộp collection + MMR."""
import numpy as np
from pgvector import HalfVector

from app.engine.filters import norm

K = 60
PER_SOURCE = 200
# chỉnh theo eval/sweep.py: kho 1.537 phim keyword 0.3 tốt nhất; kho 3.789 phim keyword làm GIẢM nDCG (0.386 → 0.409 khi tắt)
WEIGHTS = {"dense_query": 1.0, "keyword": 0.0, "dense_ref": 2.0, "crew": 0.5}
STOP = set("phim bo cho toi minh ban muon xem tim kiem gi nao co khong va voi ve cua la mot nhung cac nhu kieu "
           "giong hay nhat rat qua thi ma de duoc nay do day the nhe nha oi a voi lai con hon".split())


def _ids(rows):
    return [r[0] for r in rows]


def dense(conn, where, params, vec, n=PER_SOURCE):
    conn.execute("SET hnsw.iterative_scan = relaxed_order")
    return _ids(conn.execute(
        f"SELECT id FROM movies WHERE dense IS NOT NULL AND {where} ORDER BY dense <=> %(v)s LIMIT {n}",
        {**params, "v": HalfVector(vec)}).fetchall())


def keyword(conn, where, params, text, n=PER_SOURCE):
    words = [w for w in norm(text).replace("-", " ").split() if w not in STOP and len(w) > 1]
    if not words:
        return []
    tsq = " | ".join(dict.fromkeys(w.replace("'", "") for w in words))
    return _ids(conn.execute(
        f"""SELECT id FROM movies WHERE dense IS NOT NULL AND {where} AND fts @@ to_tsquery('simple', %(tsq)s)
            ORDER BY ts_rank_cd(fts, to_tsquery('simple', %(tsq)s)) DESC LIMIT {n}""",
        {**params, "tsq": tsq}).fetchall())


def crew(conn, where, params, ref, n=PER_SOURCE):
    people = list(dict.fromkeys(ref["director"] + ref["writers"] + ref["cast_top"] + ref["crew_key"]))
    if not people:
        return []
    return _ids(conn.execute(
        f"""SELECT id FROM movies WHERE dense IS NOT NULL AND {where} AND
              (director && %(p)s::text[] OR writers && %(p)s::text[] OR cast_top && %(p)s::text[] OR crew_key && %(p)s::text[])
            ORDER BY 3 * cardinality(ARRAY(SELECT unnest(director) INTERSECT SELECT unnest(%(d)s::text[])))
                   + cardinality(ARRAY(SELECT unnest(cast_top || writers || crew_key) INTERSECT SELECT unnest(%(p)s::text[]))) DESC,
                     vote_count DESC
            LIMIT {n}""", {**params, "p": people, "d": ref["director"]}).fetchall())


def rrf(sources, weights=WEIGHTS):
    score = {}
    for name, ids in sources.items():
        for rank, mid in enumerate(ids, 1):
            score[mid] = score.get(mid, 0.0) + weights[name] / (K + rank)
    return score


def retrieve(conn, where, params, query_vec, query_text, ref=None, prefer_runtime=None, top=100):
    sources = {"dense_query": dense(conn, where, params, query_vec)}
    if WEIGHTS["keyword"]:
        sources["keyword"] = keyword(conn, where, params, query_text)
    if ref:
        sources["dense_ref"] = dense(conn, where, params, ref["dense"])
        sources["crew"] = crew(conn, where, params, ref)
    score = rrf(sources)
    if not score:
        return [], {k: len(v) for k, v in sources.items()}
    # cộng nhẹ: chất lượng (điểm IMDb/TMDB) + ưu tiên thời lượng mơ hồ ("đừng dài quá")
    meta = {r[0]: r[1:] for r in conn.execute(
        "SELECT id, coalesce(imdb_rating, vote_average), runtime FROM movies WHERE id = ANY(%s)", (list(score),))}
    for mid, (rating, runtime) in meta.items():
        score[mid] += 0.002 * ((rating or 6) - 6) / 3
        if prefer_runtime and runtime:
            score[mid] += 0.002 * (1 if (runtime <= 120) == (prefer_runtime == "short") else -1)
    ranked = sorted(score, key=score.get, reverse=True)[:top]
    return ranked, {k: len(v) for k, v in sources.items()}


def diversify(conn, ranked, n=40, lam=0.7):
    """⑤ Mỗi collection giữ 1 phim (thứ hạng cao nhất) rồi MMR trên vector dense."""
    if not ranked:
        return []
    rows = conn.execute("SELECT id, collection_id, dense FROM movies WHERE id = ANY(%s)", (ranked,)).fetchall()
    info = {r[0]: r for r in rows}
    seen, kept = set(), []
    for mid in ranked:
        coll = info[mid][1]
        if coll and coll in seen:
            continue
        seen.add(coll)
        kept.append(mid)
    vec = np.array([info[m][2].to_numpy() for m in kept], dtype=np.float32)
    rel = np.linspace(1.0, 0.5, len(kept))  # độ liên quan theo thứ hạng RRF
    chosen, rest = [0], list(range(1, len(kept)))
    while rest and len(chosen) < n:
        sim = vec[rest] @ vec[chosen].T
        mmr = lam * rel[rest] - (1 - lam) * sim.max(axis=1)
        pick = rest[int(np.argmax(mmr))]
        chosen.append(pick)
        rest.remove(pick)
    return [kept[i] for i in chosen]
