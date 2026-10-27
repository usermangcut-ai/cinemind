"""So sánh model embedding trên bộ câu hỏi đánh giá — chỉ dense retrieval, không RRF/rerank.

Kho phim = mọi phim đã có profile. Vector mỗi model cache ở data/emb/<model>.npz.
Chạy:  .venv/Scripts/python -m eval.embed_bakeoff gemini-embedding-001 text-embedding-3-large bge-m3
"""
import json, sys, time
from pathlib import Path

import numpy as np
import psycopg
from psycopg.rows import dict_row

from app import config
from app.embedder import embed, movie_text

HERE = Path(__file__).parent
EMB = config.ROOT / "data/emb"
SHOW = ["mood-01", "mood-03", "sim-03", "flt-03", "vi-02"]


def corpus():
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT id, title, title_vi, year, genres, profile, overview, keywords, director, countries, runtime "
            "FROM movies WHERE profile IS NOT NULL ORDER BY id").fetchall()


def vectors(model, movies):
    path = EMB / f"{model}.npz"
    ids = np.array([m["id"] for m in movies])
    if path.exists():
        z = np.load(path)
        if np.array_equal(z["ids"], ids):
            return z["vecs"], 0.0
    t = time.time()
    vecs = embed([movie_text(m) for m in movies], model)
    np.savez(path, ids=ids, vecs=vecs)
    return vecs, time.time() - t


def mask_for(f, movies):
    def ok(m):
        if "countries" in f and not set(f["countries"]) & set(m["countries"]): return False
        if "genres" in f and not set(f["genres"]) <= set(m["genres"]): return False
        if "exclude_genres" in f and set(f["exclude_genres"]) & set(m["genres"]): return False
        if "runtime_max" in f and not (m["runtime"] and m["runtime"] <= f["runtime_max"]): return False
        if "year_min" in f and not (m["year"] and m["year"] >= f["year_min"]): return False
        if "year_max" in f and not (m["year"] and m["year"] <= f["year_max"]): return False
        if "person" in f and f["person"] not in m["director"]: return False
        return True
    return np.array([ok(m) for m in movies])


def ndcg10(ranked, rel):
    dcg = sum(1 / np.log2(i + 2) for i, mid in enumerate(ranked[:10]) if mid in rel)
    idcg = sum(1 / np.log2(i + 2) for i in range(min(10, len(rel))))
    return dcg / idcg if idcg else 0.0


def run(model, movies, qs):
    vecs, build_s = vectors(model, movies)
    ids = np.array([m["id"] for m in movies])
    pos = {mid: i for i, mid in enumerate(ids)}
    t = time.time()
    qv = embed([q["q"] for q in qs], model)
    q_ms = (time.time() - t) / len(qs) * 1000
    rows, tops = [], {}
    for q, v in zip(qs, qv):
        rel = {i for i in q["expect_ids"] if i in pos}
        if not rel:
            continue
        for mode in ("text", "ref") if q.get("ref") in pos else ("text",):
            qvec = vecs[pos[q["ref"]]] if mode == "ref" else v
            scores = vecs @ qvec
            if q.get("filters"):
                scores = np.where(mask_for(q["filters"], movies), scores, -9)
            if q.get("ref") in pos:
                scores[pos[q["ref"]]] = -9
            ranked = list(ids[np.argsort(-scores)[:100]])
            rows.append({"id": q["id"], "type": q["type"], "mode": mode,
                         "r100": len(rel & set(ranked)) / len(rel), "r10": len(rel & set(ranked[:10])) / len(rel),
                         "ndcg10": ndcg10(ranked, rel)})
            if q["id"] in SHOW and mode == "text":
                tops[q["id"]] = ranked[:10]
    return rows, tops, build_s, q_ms


def main(models):
    movies = corpus()
    qs = json.loads((HERE / "questions_resolved.json").read_text(encoding="utf-8"))
    title = {m["id"]: f"{m['title']} ({m['year']})" for m in movies}
    print(f"kho: {len(movies)} phim | {len(qs)} câu hỏi\n")
    report = {}
    for model in models:
        rows, tops, build_s, q_ms = run(model, movies, qs)
        report[model] = {"rows": rows, "tops": tops, "build_s": build_s, "q_ms": q_ms}

    def avg(rows, key, **flt):
        sel = [r[key] for r in rows if all(r[k] == v for k, v in flt.items())]
        return sum(sel) / len(sel) if sel else float("nan")

    print("| Model | Recall@100 | Recall@10 | nDCG@10 | tâm trạng R@100 | giống phim (text) R@100 | giống phim (vector phim gốc) R@100 | có filter R@100 | tên Việt (text) R@100 | ms/câu hỏi |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for model, r in report.items():
        rows = r["rows"]
        print(f"| {model} | {avg(rows, 'r100', mode='text'):.3f} | {avg(rows, 'r10', mode='text'):.3f} | "
              f"{avg(rows, 'ndcg10', mode='text'):.3f} | {avg(rows, 'r100', type='mood'):.3f} | "
              f"{avg(rows, 'r100', type='similar', mode='text'):.3f} | {avg(rows, 'r100', mode='ref'):.3f} | "
              f"{avg(rows, 'r100', type='filter'):.3f} | {avg(rows, 'r100', type='vi_title', mode='text'):.3f} | {r['q_ms']:.0f} |")
    for qid in SHOW:
        q = next(q for q in qs if q["id"] == qid)
        print(f"\n**{qid}: \"{q['q']}\"** (✓ = có trong đáp án)\n")
        print("| # | " + " | ".join(report) + " |\n|---|" + "---|" * len(report))
        for i in range(10):
            cells = []
            for r in report.values():
                mid = r["tops"].get(qid, [None] * 10)[i]
                cells.append(("✓ " if mid in q["expect_ids"] else "") + title.get(mid, "—"))
            print(f"| {i + 1} | " + " | ".join(cells) + " |")
    (EMB / "bakeoff.json").write_text(json.dumps({m: r["rows"] for m, r in report.items()}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:] or ["gemini-embedding-001", "text-embedding-3-large", "bge-m3"])
