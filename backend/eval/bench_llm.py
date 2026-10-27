"""Đo tốc độ + chất lượng các model cho bước ① và ⑥+⑦ với prompt thật."""
import json, sys, time
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from app import config, llm
from app.embedder import embed
from app.engine import filters as F
from app.engine import rank as RK
from app.engine.parse import SYSTEM as PARSE_SYSTEM
from app.engine.pipeline import load_movies
from app.engine.retrieve import diversify, retrieve
from eval.engine_eval import ndcg10

sys.stdout.reconfigure(encoding="utf-8")
qs = [q for q in json.loads((Path(__file__).parent / "questions_resolved.json").read_text(encoding="utf-8"))
      if q["id"] in ("mood-01", "mood-03", "sim-03", "flt-03", "mood-11", "vi-04")]
models = sys.argv[1:] or ["gpt-4.1-mini", "gemini-3.1-flash-lite", "gemini-3.5-flash", "gpt-5.4-mini", "gpt-4.1-nano"]
with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
    register_vector(conn)
    ctx = []
    for q, v in zip(qs, embed([q["q"] for q in qs])):
        ref = load_movies(conn, [q["ref"]])[0] if q.get("ref") else None
        where, params, *_ = F.apply(conn, [{"field": k, "value": x} for k, x in (q.get("filters") or {}).items()],
                                    [q["ref"]] if q.get("ref") else [])
        ranked, _ = retrieve(conn, where, params, v, q["q"], ref)
        ctx.append((q, ref, load_movies(conn, diversify(conn, ranked, n=40))))
    print("| model | ① parse s | ⑥+⑦ rank s | nDCG@10 | lỗi |\n|---|---|---|---|---|")
    for m in models:
        llm.FALLBACK_MODELS[:] = []  # đo đúng model, không xoay
        ps, rs, nd, err = [], [], [], 0
        for q, ref, movies in ctx:
            try:
                t = time.time()
                llm.chat([{"role": "system", "content": PARSE_SYSTEM}, {"role": "user", "content": "Câu user: " + q["q"]}],
                         model=m, json_mode=True, temperature=0, max_tokens=500)
                ps.append(time.time() - t)
                config.LLM_MODEL_ONLINE = m
                t = time.time()
                _, picks, _, _ = RK.llm_rank_and_explain(q["q"], ref, movies, [])
                rs.append(time.time() - t)
                nd.append(ndcg10([p["id"] for p in picks], set(q["expect_ids"])))
            except Exception:
                err += 1
        avg = lambda x: sum(x) / len(x) if x else float("nan")
        print(f"| {m} | {avg(ps):.1f} | {avg(rs):.1f} | {avg(nd):.3f} | {err} |", flush=True)
