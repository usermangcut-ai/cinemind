"""Ghép 7 bước → output đúng shape ask() của frontend.

Input:
  {text, filters?}                       câu hỏi tự nhiên (filters = chip đang giữ của cuộc chat)
  {type: 'similar', ids: [id]}           nút "Tương tự"
  {type: 'compare', ids: [..]}           so sánh 2-3 phim
  {type: 'about', id}                    hỏi về 1 phim
  {type: 'refilter', query, filters}     user gỡ chip / chọn ở clarify → chạy lại từ ③, KHÔNG gọi lại ①
Output thêm 2 trường so với bản mock: filters (chip), clarify ({question, options, inputs}),
và query (để frontend gửi lại khi refilter).
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor

from psycopg.rows import dict_row

from app import config, llm
from app.embedder import embed, movie_text
from app.engine import filters as F
from app.engine.parse import parse
from app.engine.rank import about, compare, rank
from app.engine.retrieve import STOP as STOP_WORDS, retrieve
from app.engine.titles import resolve

MOVIE_COLS = ("id, kind, title, title_vi, year, runtime, genres, countries, director, writers, cast_top, crew_key, "
              "keywords, profile, overview, overview_vi, tagline, imdb_rating, vote_average, poster_path, "
              "certification, collection_id")
NO_SOFT = {"text": "", "prefer_runtime": None}
_pool = ThreadPoolExecutor(4)
# Dự phòng khi ① không trả movie_refs: lấy cụm sau "giống/kiểu/như/tương tự" làm tên phim
REF_PATTERN = re.compile(r"(?:giống|kiểu|như|tương tự|na ná)\s+(?:phim\s+)?(.+?)(?=\s*(?:,|\.|\?|!|\bnhưng\b|\bmà\b|\bvà\b|$))", re.I)


def load_movies(conn, ids):
    cur = conn.cursor(row_factory=dict_row)
    rows = {r["id"]: r for r in cur.execute(f"SELECT {MOVIE_COLS}, dense FROM movies WHERE id = ANY(%s)", (list(ids),))}
    for r in rows.values():
        r["dense"] = r["dense"].to_numpy() if r["dense"] is not None else None
    return [rows[i] for i in ids if i in rows]


class Steps(list):
    """Danh sách bước suy luận; mỗi lần thêm bước thì báo ra ngoài (stream lên UI)."""
    def __init__(self, emit, items=()):
        super().__init__(items)
        self.emit = emit or (lambda *a: None)
        if items:
            self.emit("steps", list(self))

    def append(self, x):
        super().append(x)
        self.emit("steps", list(self))


def ask(conn, inp, emit=None):
    """emit(kind, data) — tuỳ chọn, để stream: ('steps', [...]) mỗi khi có bước mới, ('preview', movies) khi đã chấm xong."""
    t0, timing = time.time(), {}
    emit = emit or (lambda *a: None)
    kind = inp.get("type")
    if kind == "compare":
        return _compare(conn, inp["ids"])
    if kind == "about":
        return _about(conn, inp["id"])
    if kind == "similar":
        ms = load_movies(conn, inp["ids"][:1])
        if not ms:
            return {"steps": [], "text": "Mình không tìm thấy phim này trong kho dữ liệu.", "movies": []}
        q = {"text": f"phim giống {ms[0]['title']}", "soft": NO_SOFT, "ref_ids": [ms[0]["id"]]}
        return _recommend(conn, q, inp.get("filters") or [], [], Steps(emit, ["Đọc hồ sơ phim gốc"]), timing, t0, emit=emit)
    if kind == "refilter":
        q = inp.get("query") or {"text": "", "soft": NO_SOFT, "ref_ids": []}
        return _recommend(conn, q, inp.get("filters") or [], [], Steps(emit, ["Áp lại bộ lọc"]), timing, t0, emit=emit)

    text = (inp.get("text") or "").strip()
    current = inp.get("filters") or []
    qvec_future = _pool.submit(embed, [text])  # embed câu gốc song song với ① để đỡ ~1 s
    emit("steps", ["Đang phân tích câu hỏi…"])
    try:
        p, _ = parse(text, current)
    except llm.LLMError:
        p = {"intent": "search", "movie_refs": [], "add_filters": [], "remove_filters": [], "soft": {**NO_SOFT, "text": text}}
    timing["parse"] = time.time() - t0

    if p["intent"] == "chitchat":
        return {"steps": ["Phân tích câu hỏi"], "filters": _chips(current, []),
                "text": "Mình là trợ lý tìm phim 🎬 Bạn kể mình nghe tâm trạng tối nay, thể loại thích, hay một phim bạn từng mê nhé.",
                "chips": ["Phim nhẹ nhàng tối nay", "Phim giống Inception", "Phim Hàn Quốc hay"]}

    added, dropped = F.validate(p["add_filters"], text)
    active = F.merge(current, added, p["remove_filters"])
    steps = Steps(emit, ["Phân tích câu hỏi"])

    # ② nhận diện tên phim
    refs, missing = [], []
    names = list(p["movie_refs"][:3])
    if not names:
        m = REF_PATTERN.search(text)
        if m and (r := resolve(conn, m.group(1))) and "id" in r and r["conf"] >= 0.8:
            names = [m.group(1)]
    for name in names:
        r = resolve(conn, name)
        if r and "ambiguous" in r:
            opts = r["ambiguous"]
            return {"steps": steps, "text": f"Bạn đang nói tới phim **{name}** nào?", "filters": _chips(active, []),
                    "clarify": {"question": f"Bạn muốn nói tới bản nào của \"{name}\"?",
                                "options": [f"{o['title']} ({o['year']})" for o in opts],
                                "inputs": [{"text": text.replace(name, f"{o['title']} ({o['year']})"), "filters": active}
                                           for o in opts]}}
        if r:
            refs.append(r)
            steps.append(f"Nhận diện: {name} → {r['title']} ({r['year']})")
        else:
            missing.append(name)
            steps.append(f"Không tìm thấy \"{name}\" trong kho dữ liệu")

    # User nhắc tới phim mà kho không có → nói thật. Câu chỉ có mỗi tên phim (không mô tả gì thêm)
    # thì hỏi lại thay vì đoán theo nghĩa đen của tên.
    if missing and not refs:
        rest = REF_PATTERN.sub(" ", text)  # bỏ cụm "giống X" trước, rồi bỏ tên phim còn sót
        for name in missing:
            rest = re.sub(re.escape(name), " ", rest, flags=re.I)
        rest = F.norm(rest)
        rest_words = [w for w in rest.split() if w not in STOP_WORDS]
        who = ", ".join(f"**{n}**" for n in missing)
        if len(rest_words) < 2:
            return {"steps": steps, "filters": _chips(active, []),
                    "text": f"Mình chưa có {who} trong kho dữ liệu (có thể là series hoặc phim mới/ít người xem), "
                            "nên chưa biết phim nói về gì để tìm phim giống.",
                    "clarify": {"question": "Bạn kể ngắn phim đó nói về gì, không khí ra sao, mình sẽ tìm theo mô tả nhé?",
                                "options": [], "inputs": []},
                    "chips": ["Phim tội phạm u tối", "Phim tuổi trẻ mùa hè", "Phim giống Inception"]}
        p["_missing_note"] = (f"User nhắc tới {', '.join(missing)} nhưng phim này KHÔNG có trong dữ liệu. TUYỆT ĐỐI không nói như "
                              "thể biết phim đó. Câu mở đầu phải nói rõ chưa có phim này trong kho và gợi ý dưới đây chỉ dựa "
                              "theo phần mô tả còn lại trong câu hỏi.")

    if p["intent"] == "compare" and len(refs) >= 2:
        return _compare(conn, [r["id"] for r in refs])
    if p["intent"] == "about" and refs:
        return _about(conn, refs[0]["id"])

    pu = p.get("_usage") or {}
    q = {"text": text, "soft": p["soft"], "ref_ids": [r["id"] for r in refs],
         "notes": [p["_missing_note"]] if p.get("_missing_note") else [],
         "_parse_usage": {"model": pu.get("_model"), "attempt": pu.get("_attempt"),
                          "reasoning_tokens": (pu.get("completion_tokens_details") or {}).get("reasoning_tokens")}}
    if F.conflicts(active):
        a, b = F.conflicts(active)[0]
        keep_a = [f for f in active if f["field"] != b]
        keep_b = [f for f in active if f["field"] != a]
        la = next(F.label(f) for f in active if f["field"] == a)
        lb = next(F.label(f) for f in active if f["field"] == b)
        return {"steps": steps, "text": "Các điều kiện lọc đang mâu thuẫn nhau.", "filters": _chips(active, []),
                "query": q, "clarify": {"question": f"Giữ điều kiện nào: \"{la}\" hay \"{lb}\"?", "options": [la, lb],
                                        "inputs": [{"type": "refilter", "query": q, "filters": keep_a},
                                                   {"type": "refilter", "query": q, "filters": keep_b}]}}
    return _recommend(conn, q, active, dropped, steps, timing, t0, qvec_future, emit=emit)


def _recommend(conn, q, active, dropped, steps, timing, t0, qvec_future=None, emit=None):
    ref = load_movies(conn, q["ref_ids"][:1])[0] if q.get("ref_ids") else None
    if ref and ref["dense"] is None:  # phim tham chiếu nằm ngoài kho đã embed → tính vector tại chỗ từ dữ liệu TMDB
        ref["dense"] = embed([movie_text(ref)])[0]
    where, params, final, relaxed, n = F.apply(conn, active, q.get("ref_ids") or [])
    steps.append(f"Lọc: {', '.join(F.label(f) for f in final) or 'không có điều kiện'} (còn {n:,} phim)".replace(",", "."))
    if n == 0:
        last = final[-1] if final else None
        return {"steps": steps, "text": "Không có phim nào khớp tất cả điều kiện.", "query": q,
                "filters": _chips(final, relaxed),
                "clarify": {"question": f"Bỏ điều kiện \"{F.label(last)}\" nhé?" if last else "Bạn thử đổi câu hỏi nhé?",
                            "options": [f"Bỏ \"{F.label(last)}\""] if last else [],
                            "inputs": [{"type": "refilter", "query": q, "filters": final[:-1]}] if last else []}}

    soft = q.get("soft") or NO_SOFT
    t = time.time()
    qtext = q["text"]  # eval cho thấy embed câu gốc đủ tốt; soft.text dùng cho keyword + rerank
    qvec = (qvec_future.result() if qvec_future else embed([qtext]))[0]
    timing["embed"] = time.time() - t
    t = time.time()
    kw_text = " ".join(dict.fromkeys(x for x in [soft.get("text"), q["text"]] if x))
    ranked, sizes = retrieve(conn, where, params, qvec, kw_text, ref, soft.get("prefer_runtime"))
    # ⑤ lấy thẳng top RRF (đo: MMR làm mất phim đúng vì phim user muốn hay "na ná nhau"; xem steps/08)
    pool = ranked[:config.POOL_N]
    timing["retrieve"] = time.time() - t
    steps.append(f"Tìm {len(ranked)} phim gần nhất từ {len(sizes)} nguồn, chọn {len(pool)} phim sát nhất")

    notes = list(q.get("notes") or [])
    if relaxed:
        notes.append("Không đủ phim khớp hết điều kiện nên đã BỎ: " + ", ".join(F.label(f) for f in relaxed) + ".")
    t = time.time()
    try:
        cand = load_movies(conn, pool)
        text, picks, chips, rinfo = rank(q["text"], ref, cand, notes,
                                         preview=lambda ps: emit and emit("preview", ps))
    except llm.LLMError:
        text, chips, rinfo = "Đây là những phim gần nhất với yêu cầu của bạn:", [], {"engine": "none"}
        from app.engine.rank import _fallback_reason
        picks = [{"id": m["id"], "reason": _fallback_reason(m)} for m in cand[:10]]
    timing["rank"] = time.time() - t
    steps.append("Chấm lại & viết giải thích" + (" (Jev)" if rinfo["engine"] == "jev" else ""))
    timing["total"] = time.time() - t0
    return {"steps": steps, "text": text, "movies": picks, "chips": chips, "query": q,
            "filters": _chips(final, relaxed),
            "_debug": {"timing": {k: round(v, 2) for k, v in timing.items()}, "sources": sizes,
                       "dropped_filters": [{**d[0], "why": d[1]} for d in dropped], "rank": rinfo,
                       "parse": q.get("_parse_usage")}}


def _chips(active, relaxed):
    return [{**f, "label": F.label(f)} for f in active] + [{**f, "label": F.label(f), "relaxed": True} for f in relaxed]


def _compare(conn, ids):
    from app.engine.similar import pair_sim
    ms = load_movies(conn, ids[:3])
    out = compare(ms)
    pairs = [{"a": a["id"], "b": b["id"], "sim": pair_sim(a, b)} for i, a in enumerate(ms) for b in ms[i + 1:]
             if a["dense"] is not None and b["dense"] is not None]
    return {"steps": ["Tải hồ sơ các phim", "Đối chiếu nội dung, nhịp phim, đội ngũ", "Viết kết luận"],
            "text": out.get("text", ""), "compare": [m["id"] for m in ms], "pairs": pairs,
            "verdict": out.get("verdict", ""), "chips": out.get("chips", [])[:3]}


def _about(conn, mid):
    ms = load_movies(conn, [mid])
    if not ms:
        return {"steps": [], "text": "Mình không tìm thấy phim này.", "movies": []}
    out = about(ms[0])
    return {"steps": ["Truy xuất thông tin phim", "Viết giới thiệu"], "text": out.get("text", ""),
            "movies": [{"id": mid, "reason": out.get("reason", "")}], "chips": out.get("chips", [])[:3]}
