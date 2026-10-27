"""Độ tương đồng giữa 2 phim — KHÔNG gọi LLM (dùng cho drawer "Phim tương tự" và bảng so sánh).

Nội dung = cosine vector (gemini) quy về 0–1 · Chủ đề = trùng thể loại + từ khoá · Đội ngũ = trùng người thật.
"""
import numpy as np

from app.engine.rank import crew_score

W = {"Nội dung": 0.7, "Chủ đề": 0.2, "Đội ngũ": 0.1}  # vector đáng tin nhất; từ khoá TMDB nhiễu

# đo trên kho: 2 phim ngẫu nhiên cos ~0.61 · 10 phim gần nhất ~0.73–0.80 · gần như cùng series ~0.9
COS_LO, COS_HI = 0.6, 0.85


def _clip(x):
    return float(max(0.0, min(1.0, x)))


def pair_sim(a, b):
    va, vb = np.asarray(a["dense"], dtype=np.float32), np.asarray(b["dense"], dtype=np.float32)
    cos = float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-9))
    ta = {x.lower() for x in a["genres"] + a["keywords"]}
    tb = {x.lower() for x in b["genres"] + b["keywords"]}
    jac = len(ta & tb) / (len(ta | tb) or 1)
    parts = {"Nội dung": round(_clip((cos - COS_LO) / (COS_HI - COS_LO)), 2), "Chủ đề": round(_clip(jac * 4), 2),
             "Đội ngũ": crew_score(a, b)}
    return {"score": round(100 * sum(W[k] * parts[k] for k in W)), "parts": parts}


def similar(conn, ref, n=4):
    """Phim gần nhất với ref (đã có hồ sơ), mỗi collection 1 phim, xếp theo điểm tương đồng."""
    from app.engine.pipeline import load_movies
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM movies WHERE profile IS NOT NULL AND dense IS NOT NULL AND id <> %(id)s "
        "ORDER BY dense <=> (SELECT dense FROM movies WHERE id = %(id)s) LIMIT 30", {"id": ref["id"]})]
    out, seen = [], set()
    for m in sorted(load_movies(conn, ids), key=lambda m: -pair_sim(ref, m)["score"]):
        if m.get("collection_id") and m["collection_id"] in seen:
            continue
        seen.add(m.get("collection_id"))
        out.append({"id": m["id"], "sim": pair_sim(ref, m)})
        if len(out) >= n:
            break
    return out
