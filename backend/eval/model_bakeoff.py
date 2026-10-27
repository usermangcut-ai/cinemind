"""So model LLM cho từng tác vụ: ① phân tích (49 câu) + ⑥⑦ chấm & viết (6 câu, 40 ứng viên thật).
Giá đo thật = chênh lệch total_usage của provider trước/sau mỗi model.
Chạy:  .venv/Scripts/python -m eval.model_bakeoff gpt-4.1-mini deepseek-v4-flash ...
"""
import json, statistics as st, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
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
from eval.parse_eval import EXTRA

HERE = Path(__file__).parent
llm.FALLBACK_MODELS[:] = []  # đo đúng model, không xoay


def usage():
    r = httpx.get(config.LLM_BASE_URL.rstrip("/") + "/dashboard/billing/usage?start_date=2026-10-01&end_date=2026-11-30",
                  headers={"Authorization": f"Bearer {config.LLM_API_KEY}"}, timeout=20)
    return r.json()["total_usage"]


def parse_one(model, q):
    t = time.time()
    try:
        out, _ = llm.chat([{"role": "system", "content": PARSE_SYSTEM}, {"role": "user", "content": "Câu user: " + q["q"]}],
                          model=model, json_mode=True, temperature=0, max_tokens=500)
    except Exception:
        return None
    secs = time.time() - t
    kept, _ = F.validate(out.get("add_filters", []), q["q"])
    got = {f["field"]: f["value"] for f in kept}
    exp = q.get("filters") or {}
    nv = lambda v: sorted(v) if isinstance(v, list) else v
    ok_f = all(nv(got.get(k)) == nv(exp[k]) for k in exp) and all(k in exp or k in q.get("allow_extra", []) for k in got)
    ok_i = q.get("intent") is None or out.get("intent") == q["intent"]
    ok_r = not q.get("need_ref") or bool(out.get("movie_refs"))
    return secs, ok_f and ok_i and ok_r


def main(models):
    qs = json.loads((HERE / "questions_resolved.json").read_text(encoding="utf-8"))
    pq = [{"q": q["q"], "filters": q.get("filters", {}), "allow_extra": q.get("allow_extra", []),
           "intent": "similar" if q["type"] in ("similar", "vi_title") else None,
           "need_ref": q["type"] in ("similar", "vi_title")} for q in qs] + EXTRA
    rq = [q for q in qs if q["id"] in ("mood-01", "mood-03", "sim-03", "flt-03", "mood-11", "vi-04")]
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        register_vector(conn)
        ctx = []
        for q, v in zip(rq, embed([q["q"] for q in rq])):
            ref = load_movies(conn, [q["ref"]])[0] if q.get("ref") else None
            where, params, *_ = F.apply(conn, [{"field": k, "value": x} for k, x in (q.get("filters") or {}).items()],
                                        [q["ref"]] if q.get("ref") else [])
            ranked, _ = retrieve(conn, where, params, v, q["q"], ref)
            ctx.append((q, ref, load_movies(conn, diversify(conn, ranked, n=40))))
    print("| model | ① đúng (49 câu) | ① p50 s | ⑥⑦ nDCG@10 | ⑥⑦ p50 s | lỗi | cent (cả bộ test) |")
    print("|---|---|---|---|---|---|---|", flush=True)
    for m in models:
        u0 = usage()
        with ThreadPoolExecutor(6) as pool:
            pres = list(pool.map(lambda q: parse_one(m, q), pq))
        okp = [r for r in pres if r]
        config.LLM_MODEL_ONLINE = m
        rs, nd, err = [], [], sum(r is None for r in pres)
        for q, ref, movies in ctx:
            try:
                t = time.time()
                _, picks, _, _ = RK.llm_rank_and_explain(q["q"], ref, movies, [])
                rs.append(time.time() - t)
                nd.append(ndcg10([p["id"] for p in picks], set(q["expect_ids"])))
            except Exception:
                err += 1
        time.sleep(3)
        cost = usage() - u0
        med = lambda x: f"{st.median(x):.1f}" if x else "—"
        print(f"| {m} | {sum(r[1] for r in okp)}/{len(pq)} | {med([r[0] for r in okp])} | "
              f"{st.mean(nd):.3f} | {med(rs)} | {err} | {cost:.2f} |" if nd else
              f"| {m} | {sum(r[1] for r in okp)}/{len(pq)} | {med([r[0] for r in okp])} | — | — | {err} | {cost:.2f} |", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
