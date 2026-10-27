"""Đánh giá bước ① (phân tích câu hỏi) + lớp chống bịa filter.

- Câu có filters kỳ vọng → so khớp field/value sau validate.
- Câu không có filter → mọi filter còn lại sau validate = "filter bịa".
Chạy:  .venv/Scripts/python -m eval.parse_eval
"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.engine.filters import validate
from app.engine.parse import parse

HERE = Path(__file__).parent
EXTRA = [  # câu bẫy: mơ hồ, không được sinh filter cứng
    {"id": "trap-01", "q": "phim cũ cũ mà hay, đừng dài quá", "filters": {}},
    {"id": "trap-02", "q": "tối nay buồn quá, gợi ý phim gì nhẹ nhàng đi", "filters": {}},
    {"id": "trap-03", "q": "phim giống Interstellar nhưng ngắn hơn", "filters": {}, "allow_extra": ["runtime_max"]},
    {"id": "trap-04", "q": "phim hay nhất mọi thời đại", "filters": {}},
    {"id": "trap-05", "q": "phim Hàn dưới 2 tiếng từ 2018", "filters": {"countries": ["KR"], "runtime_max": 120, "year_min": 2018}},
    {"id": "trap-06", "q": "phim thập niên 90 không có bạo lực", "filters": {"year_min": 1990, "year_max": 1999}},
    {"id": "trap-07", "q": "so sánh Parasite và Joker", "filters": {}, "intent": "compare"},
    {"id": "trap-08", "q": "Arrival kể về gì vậy", "filters": {}, "intent": "about"},
    {"id": "trap-09", "q": "chào bạn", "filters": {}, "intent": "chitchat"},
]


def one(q):
    p, _ = parse(q["q"])
    kept, dropped = validate(p["add_filters"], q["q"])
    got = {f["field"]: f["value"] for f in kept}
    exp = q.get("filters") or {}
    norm = lambda v: sorted(v) if isinstance(v, list) else v
    missing = [k for k in exp if norm(got.get(k)) != norm(exp[k])]
    extra = [k for k in got if k not in exp and k not in q.get("allow_extra", [])]
    return {"id": q["id"], "q": q["q"], "intent": p["intent"], "want_intent": q.get("intent"),
            "refs": p["movie_refs"], "got": got, "missing": missing, "extra": extra,
            "dropped": [(d[0].get("field"), d[1]) for d in dropped]}


def main():
    qs = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    qs = [{"id": q["id"], "q": q["q"], "filters": q.get("filters", {}), "allow_extra": q.get("allow_extra", []),
           "intent": "similar" if q["type"] in ("similar", "vi_title") else None} for q in qs] + EXTRA
    with ThreadPoolExecutor(6) as pool:
        res = list(pool.map(one, qs))
    with_f = [r for r in res if any(q["id"] == r["id"] and q["filters"] for q in qs)]
    no_f = [r for r in res if r not in with_f]
    exact = sum(not r["missing"] and not r["extra"] for r in with_f)
    halluc = sum(bool(r["extra"]) for r in no_f)
    intent_ok = [r for r in res if r["want_intent"]]
    print(f"Câu có filter: {exact}/{len(with_f)} khớp chính xác")
    print(f"Câu không có filter: {halluc}/{len(no_f)} bị sinh filter thừa (sau lớp chống bịa)")
    print(f"Intent đúng: {sum(r['intent'] == r['want_intent'] for r in intent_ok)}/{len(intent_ok)}")
    print(f"Lớp chống bịa đã chặn: {sum(len(r['dropped']) for r in res)} filter")
    for r in res:
        bad = r["missing"] or r["extra"] or (r["want_intent"] and r["intent"] != r["want_intent"])
        if bad or r["dropped"] or r["id"].startswith("trap"):
            print(f"- {'❌' if bad else '✅'} {r['id']} \"{r['q']}\" → intent={r['intent']} refs={r['refs']} "
                  f"filters={json.dumps(r['got'], ensure_ascii=False)}"
                  + (f" thiếu/sai={r['missing']}" if r["missing"] else "") + (f" thừa={r['extra']}" if r["extra"] else "")
                  + (f" bị chặn={r['dropped']}" if r["dropped"] else ""))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
