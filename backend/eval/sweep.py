"""Quét tham số RRF (trọng số nguồn) và ⑤ (số phim giữ, λ của MMR) trên bộ câu hỏi — không gọi LLM."""
import json, sys
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from app import config
from app.embedder import embed
from app.engine import filters as F
from app.engine import retrieve as R
from app.engine.pipeline import load_movies
from eval.engine_eval import ndcg10, to_filters

qs = json.loads((Path(__file__).parent / "questions_resolved.json").read_text(encoding="utf-8"))
sys.stdout.reconfigure(encoding="utf-8")
with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
    register_vector(conn)
    vecs = embed([q["q"] for q in qs])
    ctx = []
    for q, v in zip(qs, vecs):
        ref = load_movies(conn, [q["ref"]])[0] if q.get("ref") else None
        where, params, *_ = F.apply(conn, to_filters(q.get("filters")), [q["ref"]] if q.get("ref") else [])
        src = {"dense_query": R.dense(conn, where, params, v), "keyword": R.keyword(conn, where, params, q["q"])}
        if ref:
            src["dense_ref"] = R.dense(conn, where, params, ref["dense"])
            src["crew"] = R.crew(conn, where, params, ref)
        ctx.append((q, src))
    print("| trọng số (query, keyword, ref, crew) | R@100 | nDCG@10 |\n|---|---|---|")
    best = None
    for w in [(1, 0, 0, 0), (1, .7, 1, .5), (1, .3, 1, .3), (1, .3, 2, .5), (1, .5, 2, .5), (1, .3, 3, .5), (1, .3, 2, 1), (1, 0, 2, .5)]:
        W = dict(zip(["dense_query", "keyword", "dense_ref", "crew"], w))
        r100 = nd = 0
        for q, src in ctx:
            s = R.rrf(src, W)
            ranked = sorted(s, key=s.get, reverse=True)[:100]
            rel = set(q["expect_ids"])
            r100 += len(rel & set(ranked)) / len(rel)
            nd += ndcg10(ranked, rel)
        print(f"| {w} | {r100 / len(ctx):.3f} | {nd / len(ctx):.3f} |")
        if not best or nd > best[1]:
            best = (W, nd)
    W = best[0]
    print(f"\nTốt nhất: {W}\n\n| ⑤ giữ n phim | λ MMR | phim đáp án còn lại |\n|---|---|---|")
    for n, lam in [(40, .7), (40, .9), (50, .7), (60, .7), (60, .9)]:
        tot = 0
        for q, src in ctx:
            s = R.rrf(src, W)
            ranked = sorted(s, key=s.get, reverse=True)[:100]
            pool = R.diversify(conn, ranked, n=n, lam=lam)
            tot += len(set(q["expect_ids"]) & set(pool)) / len(q["expect_ids"])
        print(f"| {n} | {lam} | {tot / len(ctx):.3f} |")
