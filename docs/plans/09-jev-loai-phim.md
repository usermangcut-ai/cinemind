# Kế hoạch 09 — Jev loại phim sai yêu cầu + không ép đủ 10 phim

> Viết 2026-10-27 trưa, làm ở phiên sau. Đọc `CLAUDE.md` trước (cách user làm việc, bẫy môi trường).
> User đã duyệt hướng này. **Không chia subagent.** Xong ghi `docs/steps/09-jev-loai-phim.md` (input/output thật) + cập nhật `docs/PROGRESS.md`, `CLAUDE.md`.

## 1. Lỗi cần sửa (ca thật)
Câu: *"T muốn tìm phim với nam nhân vật ở thời kỳ dân quốc trung quốc từ 2023 trở đi"* → 10 kết quả, chỉ ~4 đúng.
| Đúng (Dân Quốc) | Sai |
|---|---|
| War of Faith · Archives: The Nanyang Mystery · In the Name of the Brother · A Love Never Lost | A League of Nobleman, Legend of the Magnate, The Wanted Detective, Destined, White Cat Legend (cổ trang phong kiến) · Blossoms Shanghai (thập niên 1990) |

Nguyên nhân:
1. Kho chỉ có ~5–8 bộ đúng → pipeline **luôn ép đủ 10**, lấp bằng phim "gần vector".
2. Bước ⑦ (gpt-4.1-mini) **bịa lý do cho khớp** ("Tình yêu, trưởng thành trong thời dân quốc" cho Destined — phim cổ trang). Lỗi nặng nhất vì đánh lừa người dùng.
3. Bước ① **bỏ sót filter nước** ("trung quốc" → không ra `countries=CN`, chỉ có `year_min=2023`).
4. Jev không thấy thông tin thời đại: `_card()` (`app/engine/rank.py:47`) chỉ gửi tên/năm/thể loại/đạo diễn + 8 dòng hồ sơ, **không có `overview`** — mà thời đại/bối cảnh thường chỉ nằm trong overview.

## 2. Quy tắc bắt buộc (user chốt)
- **Không fix cứng case nào** trong prompt/code: không viết "Dân Quốc", "Trung Quốc → CN", "cổ trang" vào prompt. Chỉ viết **quy tắc chung** (vd "mọi tên nước/khu vực trong câu đều thành filter `countries`").
- **Không thêm mục "bối cảnh" vào hồ sơ phim** — user bác (không bao quát được mọi kiểu yêu cầu).
- **Không đổi model ⑦**. Có thể thử model ① (mục 4.5).
- Đo trước — sửa — đo sau; báo bảng số liệu.

## 3. Thiết kế
```
⑥ Jev chấm 40 phim (mỗi phim 1 request, như cũ) + thêm 1 câu noul "sai_yeu_cau"
   → phim sai_yeu_cau = true: LOẠI hẳn (không chỉ trừ điểm)
   → còn < MIN_KEEP (3): giữ 3 phim điểm cao nhất, notes thêm "kho ít phim đúng yêu cầu"
   → top_unique (gộp series) → tối đa 10, có thể ÍT HƠN 10
⑦ gpt-4.1-mini chỉ viết cho các phim được giữ; ít phim thì nói thật; cấm gán đặc điểm phim không có
```
Vì sao Jev chứ không phải ⑦: Jev chấm **từng phim độc lập**, không bị áp lực đủ 10; chạy **trước** preview nên UI không hiện rồi mất; thêm câu hỏi vào cùng request → không thêm lượt gọi.

## 4. Các bước
### 4.1 Đo mốc (trước khi sửa)
```bash
cd backend && docker compose up -d
.venv/Scripts/python -m eval.parse_eval                # mốc bước ① (rẻ, < 10 cent)
.venv/Scripts/python -m eval.eval100 run && .venv/Scripts/python -m eval.eval100 judge && .venv/Scripts/python -m eval.eval100 report
```
- Lưu kết quả mốc ra file riêng (đổi tên output trước khi chạy lại) để so sánh.
- **Hỏi user chọn**: eval 100 câu đầy đủ (~2 USD/lần, ~4 USD tổng) hay bản rút gọn (~1 USD). User chưa chọn.
- Thêm vào `eval/questions100.json` (hoặc file riêng) ~10 câu nhóm mới **"điều kiện bối cảnh/thời đại/kiểu nhân vật"**, đa dạng, không chỉ Dân Quốc: vd phim Thế chiến 2 từ 2015, series Hàn thời Joseon, phim Mỹ thập niên 80 về tuổi teen, phim nữ chính là bác sĩ, phim Nhật thời Edo, phim lấy bối cảnh vũ trụ không phải siêu anh hùng… Kèm 1 câu nguyên văn ca lỗi ở mục 1.

### 4.2 Jev: thêm câu loại phim — `app/engine/rank.py`
- `_jev_one`: thêm vào `questions`:
  ```python
  "sai_yeu_cau": {"type": "noul", "instructions": "User có nêu rõ điều kiện BẮT BUỘC về phim (thời đại, bối cảnh, nơi chốn, nước, loại phim, kiểu nhân vật chính, nghề nghiệp…) mà phim này KHÔNG đáp ứng không? Chỉ trả true khi chắc chắn phim trái điều kiện. Nếu user chỉ nêu cảm giác, chủ đề chung, hoặc chỉ muốn giống một phim khác → false."}
  ```
  (câu chữ có thể chỉnh, nhưng giữ dạng quy tắc chung — không ví dụ cụ thể kiểu Dân Quốc.)
- Trả thêm cờ này ra; `jev_rerank` trả `{"parts", "score", "drop": bool}`.
- Kiểm tra kiểu giá trị `noul` Jev trả (xác suất 0–1 hay bool — `vi_pham` hiện xử lý như số, xem `final_score`: phạt khi ≥ 0.6). Dùng cùng ngưỡng 0.6 cho `drop`.
- `_card` cho Jev: thêm `overview` (~300 ký tự đầu). Có thể thêm tham số để không ảnh hưởng chỗ khác dùng `_card` (⑦, qwen).

### 4.3 Lọc sau Jev — `app/engine/rank.py` (hàm gọi Jev, ~dòng 205–220)
- Bỏ các phim `drop` trước `top_unique`. Còn < `MIN_KEEP` (3, đưa vào `config.py`) → lấy lại 3 phim điểm cao nhất kể cả bị drop, và thêm note cho ⑦: "kho có ít phim đúng hết điều kiện; nói thật với user".
- Ghi vào `_debug`: số phim bị Jev loại + id, để eval/xem log.
- Frontend: kiểm tra UI chịu được < 10 phim (preview + final) — `frontend/src/lib/ai.js` và trang chat.

### 4.4 Prompt ⑦ — `RANK_SYSTEM` / prompt của `llm_explain` (`app/engine/rank.py:111+`)
- "Chọn tối đa 10" → chỉ viết cho danh sách được đưa; **không cần đủ 10**.
- Thêm quy tắc chung: lý do chỉ nêu đặc điểm có thật trong thông tin phim; không gán điều kiện của user cho phim nếu thông tin phim không thể hiện; phim không khớp phần nào thì nói rõ phần đó.
- Danh sách ít hơn yêu cầu → câu mở đầu nói thật ("Chỉ tìm được N bộ đúng…").

### 4.5 Bước ① bắt thiếu filter — `app/engine/parse.py`
- Sửa prompt theo **quy tắc chung** (mọi tên nước/khu vực/ngôn ngữ → `countries`/`languages` theo whitelist hiện có; năm/khoảng năm → year_*; …). Không liệt kê từng nước. Thêm câu kiểm thử vào `EXTRA` trong `eval/parse_eval.py` (vài nước khác nhau, viết thường, không dấu).
- Thử thêm **gpt-4.1 (bản đầy đủ)** cho ①: chạy `parse_eval` với `LLM_MODEL_PARSE=gpt-4.1` (rẻ). Hơn rõ (filter đúng ↑, filter bịa không ↑) mới đổi; không thì giữ gpt-4.1-mini. gpt-5.4-mini đã thử — kém (không thử lại).

### 4.6 Đo lại + báo cáo
- Chạy lại `parse_eval` + eval (cùng bộ câu như mốc).
- **Lưu ý chỉ số:** eval100 tính "Hợp / 10", "Rất hợp / 10" — khi trả < 10 phim phải tính **trên số phim thực trả** và báo thêm cột **số phim trả về trung bình** + **số câu trả < 5 phim**. Sửa `report()` trong `eval/eval100.py` nếu cần.
- Bảng so sánh trước/sau theo nhóm, đặc biệt: nhóm mới (bối cảnh), "phim rộng/cảm xúc" (không được bị loại oan), "giống X", "giống X nhưng…".
- Tiêu chí chốt: tỉ lệ không hợp ↓ rõ; nhóm câu rộng không bị trả ít phim vô lý; độ trễ p50 không tăng > 1 s.
- Nếu Jev loại oan nhiều ở câu rộng → chỉnh câu `sai_yeu_cau`, hoặc chỉ bật loại khi bước ① có `soft`/điều kiện cứng (đo lại).

### 4.7 Hoàn tất
- Chạy `.venv/Scripts/python -m eval.engine_eval --core` (không tốn tiền) để chắc không vỡ gì.
- Restart API, thử lại câu ở mục 1 qua `POST /api/ask` (body `{"text": "..."}`; test bằng Python httpx, không dùng curl).
- Ghi `docs/steps/09-jev-loai-phim.md`, cập nhật PROGRESS / ROADMAP / CLAUDE.md. Commit (author `usermangcut-ai` + noreply, kèm dòng attribution) + push. Không push `.env`, `CLAUDE.md`, `AGENTS.md`, `backend/data`.

## 5. Chi phí ước tính (báo user trước khi chạy)
| Việc | Tiền |
|---|---|
| parse_eval × 2–3 lần (kể cả thử gpt-4.1) | < 0,1 USD |
| eval100 × 2 (trước/sau) | ~4 USD (rút gọn ~1 USD) |
| Jev thêm 1 câu hỏi | ~0 (cùng request) |
Key: `LLM_API_KEY` (nhóm Medium, gpt) · `AUX_API_KEY` (key cũ, embedding + Jev; đã dùng ~57,8 USD, hạn mức 70 sau khi user nạp thêm 10).
