# Bước 5 — ⑥ Rerank (+ ⑦ viết câu trả lời)

> Trạng thái: ✅ chạy bằng **LLM dự phòng** (`gpt-5.4-mini`). Code Jev đã viết sẵn, tự bật khi có `TYPESAFE_API_KEY`.
> Code: `backend/app/engine/rank.py` · Đo model: `eval/bench_llm.py`.

## 1. Cách làm
- **Có Jev** (`TYPESAFE_API_KEY` trong `.env`): mỗi phim 1 request song song (16 luồng), 3 câu `score` (Nội dung / Chủ đề / Đội ngũ, 4 mức) + 1 câu `noul` (vi phạm) → điểm → top 10 → LLM chỉ viết chữ cho 10 phim (`llm_explain`). Jev lỗi/timeout → tự rơi xuống dự phòng.
- **Chưa có Jev** (hiện tại): **1 lần gọi LLM vừa chấm vừa viết** cho 40 ứng viên (gộp ⑥+⑦ để đỡ một lượt gọi):
  `{"text", "picks": [{id, nd, cd, dn, vp, reason}], "chips"}`.
- Điểm hiển thị: `score = 100 × (0.5·Nội dung + 0.35·Chủ đề + 0.15·Đội ngũ) × (1 − vi_phạm)`.
- **Chống bịa phim**: mọi `id` LLM trả về được lọc theo danh sách 40 ứng viên; id lạ / trùng bị bỏ.

## 2. Chọn model (6 câu đại diện, 40 ứng viên thật mỗi câu, không xoay model dự phòng)
| model | ① parse (s) | ⑥+⑦ rank (s) | nDCG@10 | lỗi |
|---|---|---|---|---|
| gpt-4.1-mini | 2.4 | 11.3 | 0.396 | 0 |
| **gpt-5.4-mini** ← rank | 2.2 | **7.0** | 0.394 | 0 |
| gpt-4.1-nano | 2.7 | 5.1 | 0.275 | 0 |
| gemini-3.5-flash | 16.0 | 43.2 | 0.678 | 4/6 |
| gemini-3.1-flash-lite | 6.9 | — | — | 6/6 |

→ `gpt-5.4-mini` cho ⑥⑦ (chất lượng ngang 4.1-mini, nhanh hơn ~40%). gemini-3.5-flash chấm tốt nhất nhưng quá chậm/hay lỗi qua provider này.
→ Riêng ① giữ `gpt-4.1-mini`: thử 3 lần câu *"… từ 2015 trở lại đây, không kinh dị"*, gpt-5.4-mini **bỏ sót filter 1/3 lần**; gpt-4.1-mini đủ **5/5**.
Cấu hình: `LLM_MODEL_PARSE=gpt-4.1-mini`, `LLM_MODEL_ONLINE=gpt-5.4-mini`.

## 3. Lỗi phát hiện khi chạy thật & đã sửa
| Lỗi | Sửa |
|---|---|
| Khi filter bị nới (vd "phim Việt kinh dị trước 1990"), LLM coi đó là vi phạm → mọi phim **0%** | Prompt: điều kiện đã được hệ thống nới KHÔNG tính là vi phạm |
| Chip gợi ý là câu hỏi ngược lại user ("Bạn muốn phim thiên về hành động hay…?") | Prompt: chip phải là câu **user bấm để hỏi tiếp**, ≤ 8 từ ("Phim giống Arrival", "Chỉ phim dưới 2 tiếng") |
| Provider treo 80–95 s ở vài câu | Timeout 25 s/lần + xoay model dự phòng (`app/llm.py`) |
