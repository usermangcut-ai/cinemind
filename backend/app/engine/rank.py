"""⑥ Rerank + ⑦ viết câu trả lời.

- RERANK=jev (mặc định khi gọi được): Jev chấm từng phim song song qua provider (`{LLM_BASE_URL}/systemone`)
  hoặc TypeSafe gốc nếu có TYPESAFE_API_KEY → top 10 → LLM chỉ viết text/reason/chips.
- Jev lỗi hoặc RERANK=llm: 1 lần gọi LLM vừa chấm vừa viết (gộp ⑥+⑦).
- "Đội ngũ" tính bằng CODE từ cast/crew thật (không để AI đoán); chỉ có khi có phim tham chiếu.
Mọi id LLM trả về đều bị lọc theo danh sách ứng viên → không thể bịa phim.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from app import config, llm

W_REF = {"Nội dung": 0.5, "Chủ đề": 0.4, "Đội ngũ": 0.1}
W_NOREF = {"Nội dung": 0.55, "Chủ đề": 0.45}


def final_score(parts, violation=0.0):
    w = W_REF if "Đội ngũ" in parts else W_NOREF
    # chỉ phạt khi chắc là vi phạm (Jev hay trả 0.3–0.4 cho điều kiện đã được filter lo rồi)
    penalty = violation if (violation or 0) >= 0.6 else 0.0
    return round(100 * sum(w[k] * parts[k] for k in w) * (1 - penalty))


def crew_score(ref, m):
    """Trùng người thật giữa 2 phim: đạo diễn nặng nhất, rồi biên kịch, diễn viên, nhạc/quay phim, cùng series."""
    if not ref:
        return None
    same = lambda a, b: len(set(a or []) & set(b or []))
    s = (0.6 * min(1, same(ref["director"], m["director"])) + 0.25 * min(1, same(ref["writers"], m["writers"]))
         + 0.15 * min(2, same(ref["cast_top"], m["cast_top"])) + 0.1 * min(1, same(ref["crew_key"], m["crew_key"]))
         + (0.3 if ref.get("collection_id") and ref["collection_id"] == m.get("collection_id") else 0))
    return round(min(1.0, s), 2)


def _parts(nd, cd, ref, m):
    parts = {"Nội dung": nd, "Chủ đề": cd}
    dn = crew_score(ref, m)
    if dn is not None:
        parts["Đội ngũ"] = dn
    return parts


def _card(m, profile_lines=4, overview=0):
    prof = "; ".join((m.get("profile") or "").split("\n")[:profile_lines])
    if overview and m.get("overview"):  # thời đại, bối cảnh, kiểu nhân vật thường chỉ nằm trong tóm tắt
        prof += " · Tóm tắt: " + m["overview"][:overview]
    vi = f" / {m['title_vi']}" if m.get("title_vi") else ""
    kind = "Series · " if m.get("kind") == "tv" else ""
    return (f"[{m['id']}] {kind}{m['title']}{vi} ({m['year']}) · {', '.join(m['genres'])} · {m['runtime'] or '?'}' · "
            f"ĐD: {', '.join(m['director'][:2])} · {prof}")


# ---------- Jev ----------
JEV_LEVELS = ["Không liên quan", "Hơi liên quan", "Khá khớp", "Rất khớp"]
DROP_AT = 0.6  # cùng ngưỡng "chắc chắn" với vi_pham


def _jev_one(client, url, query, ref, m):
    state = {"yeu_cau": query, "phim": _card(m, 8, overview=400)}
    if ref:
        state["phim_tham_chieu"] = _card(ref, 8)
    body = {"model": "jev-latest", "state": state, "questions": {
        "noi_dung": {"type": "score", "instructions": "Cốt truyện/ý tưởng của phim khớp yêu cầu của user tới đâu?", "criteria": JEV_LEVELS},
        "chu_de": {"type": "score", "instructions": "Chủ đề, tâm trạng, không khí của phim khớp yêu cầu tới đâu?", "criteria": JEV_LEVELS},
        "vi_pham": {"type": "noul", "instructions": "User có nói rõ KHÔNG muốn điều gì (vd không kinh dị, không buồn) mà phim này lại có không? Nếu user không nói điều gì không muốn → false."},
        "sai_yeu_cau": {"type": "noul", "instructions": "User có nêu rõ điều kiện BẮT BUỘC về phim (thời đại, bối cảnh, nơi chốn, kiểu nhân vật chính, nghề nghiệp, đối tượng câu chuyện…) mà phim này KHÔNG đáp ứng không? Chỉ true khi thông tin phim cho thấy rõ là trái điều kiện. User chỉ nêu cảm giác, chủ đề chung, hoặc chỉ muốn giống một phim khác → false."}}}
    for attempt in range(3):
        try:
            r = client.post(url, json=body)
            r.raise_for_status()
            a = r.json()["answers"]
            top = len(JEV_LEVELS) - 1
            parts = _parts(a["noi_dung"]["score"] / top, a["chu_de"]["score"] / top, ref, m)
            return m["id"], parts, a["vi_pham"]["noul"], a["sai_yeu_cau"]["noul"]
        except (httpx.HTTPError, KeyError):
            time.sleep(0.5 * (attempt + 1))
    return m["id"], None, None, None


def jev_rerank(query, ref, movies):
    if config.TYPESAFE_API_KEY:
        url, key = "https://api.typesafe.ai/v1/systemone", config.TYPESAFE_API_KEY
    else:
        url, key = config.LLM_BASE_URL.rstrip("/") + "/systemone", config.AUX_API_KEY
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=15) as client,             ThreadPoolExecutor(config.JEV_CONCURRENCY) as pool:
        res = list(pool.map(lambda m: _jev_one(client, url, query, ref, m), movies))
    ok = {mid: {"parts": parts, "score": final_score(parts, vp), "drop": (off or 0) >= DROP_AT}
          for mid, parts, vp, off in res if parts}
    if len(ok) < len(movies) * 0.7:
        raise httpx.HTTPError(f"Jev lỗi quá nhiều ({len(movies) - len(ok)}/{len(movies)})")
    return ok


# ---------- qwen3-rerank (cross-encoder, 1 request cho cả danh sách) ----------
def qwen_rerank(query, ref, movies):
    q = query + (f" (giống phim {ref['title']}: {(ref.get('profile') or ref.get('overview') or '')[:300]})" if ref else "")
    docs = [_card(m, 8) + " · " + (m.get("overview") or "")[:300] for m in movies]
    with httpx.Client(timeout=30) as c:
        r = c.post(config.LLM_BASE_URL.rstrip("/") + "/rerank", headers={"Authorization": f"Bearer {config.AUX_API_KEY}"},
                   json={"model": "qwen3-rerank", "query": q, "documents": docs, "top_n": len(docs)})
        r.raise_for_status()
    out = {}
    for x in r.json()["results"]:
        m = movies[x["index"]]
        rel = float(x["relevance_score"])
        parts = _parts(rel, rel, ref, m)  # qwen chỉ cho 1 điểm → dùng chung cho Nội dung & Chủ đề
        out[m["id"]] = {"parts": parts, "score": final_score(parts)}
    return out


# ---------- LLM ----------
RANK_SYSTEM = """Bạn là chuyên gia tư vấn phim, trả lời tiếng Việt, giọng thân thiện ngắn gọn.
Nhiệm vụ: chọn tối đa 10 phim HỢP NHẤT với yêu cầu từ danh sách ứng viên (CHỈ dùng id có trong danh sách), chấm điểm và viết lý do.
Trả JSON:
{
 "text": "1 câu mở đầu ngắn, có thể **in đậm** ý chính; nếu filter bị nới thì nói rõ",
 "picks": [{"id": 123, "nd": 0-10, "cd": 0-10, "vp": 0-1, "reason": "≤ 20 từ: vì sao hợp, cụ thể"}],
 "chips": ["2-3 câu user có thể BẤM để hỏi tiếp, viết như lời user, ≤ 8 từ, vd: 'Phim giống Arrival', 'Chỉ phim dưới 2 tiếng', 'Có phim Hàn nào không?'"]
}
nd = cốt truyện/ý tưởng khớp yêu cầu; cd = chủ đề/tâm trạng/không khí khớp;
vp = mức độ phim trái điều user nói KHÔNG muốn (0 = không vi phạm). Điều kiện đã được hệ thống NỚI (xem Ghi chú) KHÔNG tính là vi phạm.
Sắp picks theo độ hợp giảm dần."""

EXPLAIN_SYSTEM = """Bạn là chuyên gia tư vấn phim, trả lời tiếng Việt, giọng thân thiện ngắn gọn.
Các phim dưới đây ĐÃ được chọn và chấm điểm. Viết lời giới thiệu và lý do cho từng phim, giữ nguyên thứ tự.
Lý do CHỈ nêu điều có thật trong thông tin phim; không gán điều kiện của user cho phim khi thông tin phim không thể hiện điều đó.
Phim chỉ khớp một phần thì nói rõ phần khớp. Danh sách có thể ít hơn 10 phim; nếu Ghi chú nói kho ít phim đúng yêu cầu thì câu mở đầu nói thật điều đó.
Trả JSON: {"text": "1-2 câu mở đầu", "reasons": {"<id dạng số, vd 4977>": "≤ 20 từ vì sao hợp"} — ĐỦ lý do cho MỌI phim,
 "chips": ["2-3 câu user có thể BẤM để hỏi tiếp, viết như lời user, ≤ 8 từ"]}"""


def _context(query, ref, notes):
    msg = f"Yêu cầu của user: {query}"
    if ref:
        msg += f"\nPhim tham chiếu: {_card(ref, 8)}"
        if not ref.get("profile"):
            msg += ("\n(Phim tham chiếu chỉ có tóm tắt ngắn: " + (ref.get("overview") or "")[:400]
                    + ". KHÔNG khẳng định chi tiết về phim tham chiếu ngoài thông tin này.)")
    if notes:
        msg += "\nGhi chú: " + " ".join(notes)
    return msg


def llm_rank_and_explain(query, ref, movies, notes):
    cands = "\n".join(_card(m) for m in movies)
    out, usage = llm.chat([{"role": "system", "content": RANK_SYSTEM},
                           {"role": "user", "content": _context(query, ref, notes) + "\n\nỨng viên:\n" + cands}],
                          json_mode=True, temperature=0.3, max_tokens=900)
    by, picks = {m["id"]: m for m in movies}, []
    valid = set(by)
    for p in out.get("picks", []):
        try:
            mid = int(p["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if mid not in valid or any(x["id"] == mid for x in picks):
            continue
        parts = _parts(_clip(p.get("nd")) / 10, _clip(p.get("cd")) / 10, ref, by[mid])
        picks.append({"id": mid, "reason": p.get("reason", ""),
                      "sim": {"score": final_score(parts, _clip(p.get("vp"), 1)), "parts": parts}})
    picks.sort(key=lambda p: -p["sim"]["score"])
    picks = top_unique(picks, {m["id"]: m.get("collection_id") for m in movies})
    return out.get("text", ""), picks, out.get("chips", [])[:3], usage


def llm_explain(query, ref, ranked, notes):
    """Sau Jev: chỉ viết chữ cho top 10 đã chấm."""
    cands = "\n".join(_card(m) for m, _ in ranked)
    out, usage = llm.chat([{"role": "system", "content": EXPLAIN_SYSTEM},
                       {"role": "user", "content": _context(query, ref, notes) + "\n\nPhim:\n" + cands}],
                      json_mode=True, temperature=0.3, max_tokens=1000)
    reasons = {str(k).strip("[]"): v for k, v in (out.get("reasons") or {}).items()}
    picks = [{"id": m["id"], "reason": reasons.get(str(m["id"])) or _fallback_reason(m), "sim": s} for m, s in ranked]
    return out.get("text", ""), picks, out.get("chips", [])[:3], usage


def _fallback_reason(m):
    for line in (m.get("profile") or "").split(chr(10)):
        if line.startswith("Tâm trạng:"):
            return line.split(":", 1)[1].strip().capitalize() + "."
    return ""


def top_unique(items, coll, n=10):
    """items đã xếp theo điểm → n phần tử đầu, mỗi collection (phần 1/2/3) 1 phim."""
    seen, out = set(), []
    for it in items:
        k = coll.get(it[0] if isinstance(it, tuple) else it["id"])
        if k and k in seen:
            continue
        seen.add(k)
        out.append(it)
        if len(out) >= n:
            break
    return out


def _clip(v, hi=10):
    try:
        return max(0.0, min(float(v), hi))
    except (TypeError, ValueError):
        return 0.0


def rank(query, ref, movies, notes, preview=None):
    """Trả (text, picks[top10], chips, engine_name)."""
    if config.RERANK in ("jev", "qwen"):
        try:
            f = jev_rerank if config.RERANK == "jev" else qwen_rerank
            scores = f(query, ref, movies[:config.JEV_TOP])  # movies đã xếp theo RRF/MMR
            by = {m["id"]: m for m in movies}
            coll = {m["id"]: m.get("collection_id") for m in movies}
            ranked = sorted(scores.items(), key=lambda kv: -kv[1]["score"])
            kept = [kv for kv in ranked if not kv[1].get("drop") and kv[1]["score"] >= config.MIN_SCORE]
            dropped = [mid for mid, s in ranked if s.get("drop") or s["score"] < config.MIN_SCORE]
            if len(kept) < config.MIN_KEEP:  # kho quá ít phim đúng → vẫn đưa vài phim gần nhất, nói thật
                kept = ranked[:config.MIN_KEEP]
                notes = list(notes or []) + ["Kho có rất ít phim đáp ứng hết điều kiện của user; đây là các phim gần nhất, hãy nói thật điều đó."]
            elif len(kept) < 10:
                notes = list(notes or []) + [f"Chỉ có {len(kept)} phim đúng yêu cầu (các phim khác đã bị loại vì không khớp)."]
            top = top_unique(kept, coll)
            if preview:  # đã có thứ tự + điểm → cho UI hiện thẻ phim trước khi LLM viết xong lý do
                preview([{"id": mid, "reason": "", "sim": s} for mid, s in top])
            t = time.time()
            try:
                text, picks, chips, usage = llm_explain(query, ref, [(by[mid], s) for mid, s in top], notes)
            except llm.LLMError:  # provider lỗi ở bước viết → vẫn giữ thứ tự + điểm của Jev
                text, chips, usage = "Đây là những phim hợp nhất với yêu cầu của bạn:", [], {}
                picks = [{"id": mid, "reason": _fallback_reason(by[mid]), "sim": s} for mid, s in top]
            return text, picks, chips, {"engine": config.RERANK, "explain_s": round(time.time() - t, 2), "dropped": dropped,
                                        "explain_model": usage.get("_model"), "explain_attempt": usage.get("_attempt")}
        except (httpx.HTTPError, KeyError):
            pass  # Jev lỗi → rơi xuống dự phòng
    text, picks, chips, usage = llm_rank_and_explain(query, ref, movies, notes)
    return text, picks, chips, {"engine": "llm", "model": usage.get("_model"), "attempt": usage.get("_attempt")}


COMPARE_SYSTEM = """Bạn so sánh 2-3 phim cho người xem Việt. Trả JSON:
{"text": "1 câu mở đầu", "verdict": "2-3 câu kết luận: nên chọn phim nào trong trường hợp nào, có **in đậm** tên phim",
 "chips": ["2-3 câu user có thể BẤM để hỏi tiếp, viết như lời user, ≤ 8 từ, vd 'Tìm phim giống cả hai'"]}"""

ABOUT_SYSTEM = """Bạn giới thiệu 1 phim cho người xem Việt, dựa trên dữ liệu được cung cấp (không bịa giải thưởng/số liệu).
Trả JSON: {"text": "3-4 câu: phim nói về gì (không spoil), cảm giác khi xem, hợp với ai; **in đậm** tên phim",
 "reason": "1 câu ngắn vì sao đáng xem", "chips": ["2-3 câu user có thể BẤM để hỏi tiếp, ≤ 8 từ, vd 'Phim giống Arrival'"]}"""


def compare(movies):
    out, _ = llm.chat([{"role": "system", "content": COMPARE_SYSTEM},
                       {"role": "user", "content": "\n".join(_card(m, 8) for m in movies)}],
                      json_mode=True, temperature=0.3, max_tokens=600)
    return out


def about(m):
    out, _ = llm.chat([{"role": "system", "content": ABOUT_SYSTEM},
                       {"role": "user", "content": _card(m, 8) + f"\nTóm tắt: {m.get('overview') or ''}"}],
                      json_mode=True, temperature=0.3, max_tokens=500)
    return out
