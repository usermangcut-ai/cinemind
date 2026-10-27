"""Đánh giá engine trên bộ câu hỏi.

--core : bước ③④⑤ không LLM (filter lấy từ đáp án, phim tham chiếu từ q.ref) — so dense-only vs RRF nhiều nguồn.
--full : chạy nguyên pipeline ask() (①→⑦, có gọi LLM) — đo kết quả cuối + độ trễ + vi phạm filter.
Chạy:  .venv/Scripts/python -m eval.engine_eval --core | --full [--sample]
"""
import json, statistics, sys, time
from pathlib import Path

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from app import config
from app.embedder import embed
from app.engine import filters as F
from app.engine.pipeline import ask, load_movies
from app.engine.retrieve import dense, diversify, retrieve

HERE = Path(__file__).parent


def to_filters(f):
    return [{"field": k, "value": v} for k, v in (f or {}).items()]


def ndcg10(ranked, rel):
    dcg = sum(1 / np.log2(i + 2) for i, m in enumerate(ranked[:10]) if m in rel)
    idcg = sum(1 / np.log2(i + 2) for i in range(min(10, len(rel))))
    return dcg / idcg if idcg else 0.0


def core(conn, qs):
    vecs = embed([q["q"] for q in qs])
    rows = []
    for q, v in zip(qs, vecs):
        rel = set(q["expect_ids"])
        ref = load_movies(conn, [q["ref"]])[0] if q.get("ref") else None
        where, params, *_ = F.apply(conn, to_filters(q.get("filters")), [q["ref"]] if q.get("ref") else [])
        d = dense(conn, where, params, ref["dense"] if ref else v, 100)
        ranked, _ = retrieve(conn, where, params, v, q["q"], ref)
        pool = diversify(conn, ranked, n=40)
        rows.append({"type": q["type"], "dense_r100": len(rel & set(d)) / len(rel),
                     "rrf_r100": len(rel & set(ranked)) / len(rel), "pool40": len(rel & set(pool)) / len(rel),
                     "dense_ndcg": ndcg10(d, rel), "rrf_ndcg": ndcg10(ranked, rel)})
    print("| Nhóm | n | dense-only R@100 | RRF R@100 | sau ⑤ (40 phim vào rerank) | dense nDCG@10 | RRF nDCG@10 |")
    print("|---|---|---|---|---|---|---|")
    for t in ["mood", "similar", "filter", "vi_title", None]:
        sel = [r for r in rows if t is None or r["type"] == t]
        avg = lambda k: sum(r[k] for r in sel) / len(sel)
        print(f"| {t or '**tất cả**'} | {len(sel)} | {avg('dense_r100'):.3f} | {avg('rrf_r100'):.3f} | {avg('pool40'):.3f} | "
              f"{avg('dense_ndcg'):.3f} | {avg('rrf_ndcg'):.3f} |")


def violates(m, f):
    for x in f:
        k, v = x["field"], x["value"]
        if k == "countries" and not set(v) & set(m["countries"]): return True
        if k == "genres" and not set(v) & set(m["genres"]): return True
        if k == "exclude_genres" and set(v) & set(m["genres"]): return True
        if k == "runtime_max" and (m["runtime"] or 0) > v: return True
        if k == "year_min" and (m["year"] or 0) < v: return True
        if k == "year_max" and (m["year"] or 9999) > v: return True
        if k == "person" and v not in m["director"] + m["cast_top"] + m["writers"]: return True
    return False


def full(conn, qs):
    rows, title = [], {}
    for q in qs:
        t = time.time()
        res = ask(conn, {"text": q["q"]})
        secs = time.time() - t
        ids = [m["id"] for m in res.get("movies", [])]
        rel = set(q["expect_ids"])
        ms = {m["id"]: m for m in load_movies(conn, ids)}
        title.update({i: f"{m['title']} ({m['year']})" for i, m in ms.items()})
        applied = [f for f in res.get("filters", []) if not f.get("relaxed")]
        viol = sum(violates(ms[i], applied) for i in ids if i in ms)
        rows.append({"id": q["id"], "type": q["type"], "q": q["q"], "secs": secs, "hit10": len(rel & set(ids)),
                     "ndcg": ndcg10(ids, rel), "viol": viol, "n": len(ids), "ids": ids, "rel": rel,
                     "filters": [f["label"] for f in res.get("filters", [])], "clarify": bool(res.get("clarify")),
                     "timing": res.get("_debug", {}).get("timing", {}), "engine": (res.get("_debug", {}).get("rank") or {}).get("engine")})
        print(f"{q['id']}: {secs:.1f}s hit {rows[-1]['hit10']}/{min(10, len(rel))} viol {viol}", file=sys.stderr, flush=True)
    secs = sorted(r["secs"] for r in rows)
    print(f"Câu hỏi: {len(rows)} | nDCG@10 TB: {statistics.mean(r['ndcg'] for r in rows):.3f} | "
          f"có ≥1 phim đáp án trong top 10: {sum(r['hit10'] > 0 for r in rows)}/{len(rows)} | "
          f"phim vi phạm filter: {sum(r['viol'] for r in rows)} | hỏi lại (clarify): {sum(r['clarify'] for r in rows)}")
    print(f"Độ trễ p50 {secs[len(secs) // 2]:.1f}s · p95 {secs[int(len(secs) * .95) - 1]:.1f}s · max {secs[-1]:.1f}s")
    parts = {k: statistics.mean(r["timing"].get(k, 0) for r in rows if r["timing"]) for k in ("parse", "embed", "retrieve", "rank")}
    print("Thời gian TB từng bước: " + " · ".join(f"{k} {v:.2f}s" for k, v in parts.items()))
    print("\n| id | câu hỏi | filter | top 5 (✓ = đáp án) | nDCG@10 | s |\n|---|---|---|---|---|---|")
    for r in rows:
        top = ", ".join(("✓" if i in r["rel"] else "") + title.get(i, str(i)) for i in r["ids"][:5])
        print(f"| {r['id']} | {r['q']} | {'; '.join(r['filters'])} | {top} | {r['ndcg']:.2f} | {r['secs']:.1f} |")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    qs = json.loads((HERE / "questions_resolved.json").read_text(encoding="utf-8"))
    if "--sample" in sys.argv:  # 10 câu đại diện cho đủ 4 nhóm, đỡ tốn tiền
        pick = {"mood-01", "mood-03", "mood-11", "mood-19", "sim-01", "sim-03", "flt-01", "flt-03", "flt-05", "vi-02"}
        qs = [q for q in qs if q["id"] in pick]
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        register_vector(conn)
        (full if "--full" in sys.argv else core)(conn, qs)
