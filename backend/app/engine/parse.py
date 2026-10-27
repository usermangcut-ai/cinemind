"""① LLM phân tích câu hỏi → JSON có cấu trúc. Validate ở filters.validate()."""
import json

from app import config, llm
from app.engine.filters import GENRES

SYSTEM = f"""Bạn phân tích câu hỏi tìm phim (tiếng Việt) thành JSON. Chỉ trả JSON, đúng schema:
{{
 "intent": "search | similar | compare | about | chitchat",
 "movie_refs": ["tên phim user nhắc tới, chép đúng chữ user gõ"],
 "add_filters": [{{"field": "...", "value": ..., "evidence": "đoạn trích NGUYÊN VĂN từ câu user"}}],
 "remove_filters": ["field user muốn bỏ trong các filter đang áp dụng"],
 "soft": {{"text": "mô tả gu/tâm trạng/chủ đề user muốn, viết lại tự nhiên bằng tiếng Việt", "prefer_runtime": "short | long | null"}}
}}
intent: search = tìm theo mô tả; similar = tìm phim giống phim X; compare = so sánh 2-3 phim; about = hỏi về 1 phim cụ thể; chitchat = CHỈ khi chào hỏi / chuyện không liên quan phim. Câu xin phim chung chung ("tối nay xem gì", "phim hay", "chán quá có phim gì không") = search.
Field filter cho phép (CHỈ dùng khi user nói RÕ RÀNG, có giá trị cụ thể):
- year_min, year_max (số năm) — "từ 2015", "từ 2020 trở lại đây", "sau 2015" (→ year_min); "trước 2000" (→ year_max 1999);
  "thập niên 90" (→ year_min 1990 + year_max 1999). "trở lại đây" = từ năm đó ĐẾN NAY → year_min, KHÔNG phải year_max.
- runtime_min, runtime_max (phút) — "dưới 2 tiếng" → runtime_max 120
- genres, exclude_genres (danh sách, CHỈ chọn trong: {", ".join(GENRES)}) — CHỈ khi user GỌI ĐÚNG TÊN thể loại
  ("phim hoạt hình", "phim kinh dị", "phim chiến tranh", "không phải phim hài"). 1 thể loại user gọi tên → 1 giá trị.
  KHÔNG suy diễn thể loại từ chủ đề/đối tượng: "zombie", "mafia", "siêu anh hùng", "tiểu sử nhà khoa học", "du hành thời gian" → đưa vào soft.
- countries, exclude_countries (mã ISO 2 chữ: KR Hàn, JP Nhật, US Mỹ, VN Việt Nam, CN Trung Quốc, IN Ấn Độ, FR Pháp, GB Anh, TH Thái…)
- certification_max ("G" | "PG" | "PG-13" | "R") — chỉ khi user nói rõ "cho trẻ em", "trẻ con xem được"
- person (tên đầy đủ đạo diễn/diễn viên, viết theo tên quốc tế, vd "Christopher Nolan")
- kind ("movie" | "tv") — CHỈ khi user nói rõ: "phim bộ", "series", "TV show" → "tv"; "phim lẻ", "phim chiếu rạp" → "movie"
Ý MƠ HỒ không phải filter, đưa vào soft: "phim cũ cũ", "đừng dài quá" (→ prefer_runtime short), "nhẹ nhàng", "hay".
Phim tham chiếu KHÔNG phải filter. Tên phim có thể là tên tiếng Việt ("Hố đen tử thần", "Ký sinh trùng", "Kẻ trộm giấc mơ")
→ vẫn đưa vào movie_refs. "giống X", "kiểu X", "như X", "tương tự X" → intent similar.
evidence phải là chuỗi con xuất hiện y nguyên trong câu user. Không chắc thì không thêm filter."""


def parse(text, current_filters=None):
    msg = f"Câu user: {text}"
    if current_filters:
        msg += "\nFilter đang áp dụng: " + json.dumps(
            [{"field": f["field"], "value": f["value"]} for f in current_filters], ensure_ascii=False)
    out, usage = llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": msg}],
                          model=config.LLM_MODEL_PARSE, json_mode=True, temperature=0, max_tokens=3000)  # đủ chỗ cho model reasoning
    out["_usage"] = usage
    out.setdefault("intent", "search")
    out.setdefault("movie_refs", [])
    out.setdefault("add_filters", [])
    out.setdefault("remove_filters", [])
    soft = out.get("soft") or {}
    out["soft"] = {"text": soft.get("text") or text,
                   "prefer_runtime": soft.get("prefer_runtime") if soft.get("prefer_runtime") in ("short", "long") else None}
    return out, usage
