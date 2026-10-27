# Bước 4 — LLM ① phân tích câu hỏi · ⑦ viết câu trả lời

> Trạng thái: ✅ · Code: `backend/app/engine/parse.py`, `filters.validate()`, `app/llm.py` · Đánh giá: `eval/parse_eval.py`.

## 1. ① Phân tích câu hỏi
LLM trả JSON `{intent, movie_refs, add_filters[{field, value, evidence}], remove_filters, soft{text, prefer_runtime}}`.
- Filter được **giữ theo cuộc chat**: frontend gửi lại chip đang có, LLM chỉ trả phần *thêm* / *gỡ*.
- **4 lớp chống bịa** (`filters.validate`, chạy bằng code): field phải nằm trong danh sách · giá trị đúng enum/giới hạn (19 thể loại TMDB, mã ISO, năm 1900–nay, 30–300 phút) · `evidence` phải là chuỗi con thật của câu user (so sau khi bỏ dấu) · kiểm tra mâu thuẫn → `clarify`.

### Đánh giá — 49 câu (40 câu bộ đánh giá + 9 câu bẫy)
Lần 1 (prompt ban đầu):
```
Câu có filter: 8/10 khớp chính xác
Câu không có filter: 8/39 bị sinh filter thừa
- ❌ "phim zombie, đại dịch, sinh tồn" → genres: ["Drama"]            (suy diễn bừa)
- ❌ "phim trinh thám phá án…"          → genres: [Mystery, Crime, Thriller]  (+ lỗi: SQL bắt phải có ĐỦ 3)
- ❌ "phim hành động… không phải siêu anh hùng" → exclude_genres: [Science Fiction]
- ❌ "phim kiểu Hố đen tử thần"          → không nhận ra là tên phim
```
Sửa: (1) `genres` đổi sang "có ít nhất 1"; (2) prompt: chỉ thành filter thể loại khi user **gọi đúng tên thể loại**, chủ đề (zombie, mafia, siêu anh hùng…) đưa vào `soft`; (3) prompt: tên phim có thể là tên tiếng Việt, "kiểu X / như X" = similar;
(4) sửa lại nhãn đáp án cho nhất quán với quy tắc (vd "phim hài…", "phim chiến tranh…" gọi đúng tên thể loại → filter là đúng).

Lần cuối:
```
Câu có filter: 17/17 khớp chính xác
Câu không có filter: 0/32 bị sinh filter thừa (sau lớp chống bịa)
Intent đúng: 15/15
✅ "phim cũ cũ mà hay, đừng dài quá"        → không filter (mơ hồ → soft)
✅ "tối nay buồn quá, gợi ý phim gì nhẹ nhàng đi" → không filter
✅ "phim giống Interstellar nhưng ngắn hơn"  → similar, refs [Interstellar]
✅ "phim Hàn dưới 2 tiếng từ 2018"           → {countries [KR], runtime_max 120, year_min 2018}
✅ "phim thập niên 90 không có bạo lực"      → {year_min 1990, year_max 1999}
✅ "so sánh Parasite và Joker"               → compare, refs [Parasite, Joker]
✅ "Arrival kể về gì vậy"                    → about
✅ "chào bạn"                                → chitchat
```
Khi chạy cả pipeline vẫn gặp 1 lỗi: *"từ 2020 trở lại đây"* bị hiểu thành `year_max 2020` (lúc provider xoay sang model dự phòng) → đã thêm ví dụ rõ vào prompt.

## 2. ⑦ Viết câu trả lời
Gộp chung 1 lần gọi với ⑥ khi chưa có Jev (xem `05-rerank.md`). Riêng `compare` / `about` có prompt riêng (`rank.compare()`, `rank.about()`).

## 3. Provider không ổn định
`api.shopaikey.com` trả 429 / 503 "No available channel" theo đợt, có lần treo 80–95 s.
`app/llm.py`: timeout 25 s / lần, thử lại tối đa 4 lần, **mỗi lần xoay model**: `gpt-4.1-mini → gpt-5.4-mini → gemini-3.5-flash`.
