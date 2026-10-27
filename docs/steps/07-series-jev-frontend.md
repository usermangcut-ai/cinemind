# Bước 7 — Jev, series TV, chống bịa, frontend thật

> Trạng thái: ✅ (27/10). Code: `app/engine/rank.py`, `filters.py`, `similar.py`, `pipeline.py`, `app/main.py`,
> `etl/fetch_tmdb_tv.py`, `etl/load_tv.py`, `src/lib/ai.js`, `src/store.jsx`, `src/components/*`.

## 1. Chọn model cho từng bước (đo giá thật = chênh `total_usage`)
| Bước | Model | Đo |
|---|---|---|
| ① phân tích | **gpt-4.1-mini** | 2,8 s · 0,06 cent/câu. deepseek-v4-flash: 6,1 s · 0,89 cent (model reasoning) — chính xác hơn rất ít |
| ⑥ chấm | **Jev qua provider** (`POST {LLM_BASE_URL}/systemone`, cùng key) | 40 phim: 2,0 s · 1,15 cent → giảm còn **25 phim** |
| ⑦ viết | **gpt-4.1-mini** | ~3–5 s |

So 10 câu, cùng kho 3.789 phim:
| | ① deepseek + ⑥ Jev + ⑦ gpt | gpt-4.1-mini cho tất cả |
|---|---|---|
| nDCG@10 | 0,466 | 0,414 |
| có phim đúng trong top 10 | 9/10 | 8/10 |
| p50 | 13,3 s | 11,2 s |
| giá/câu | 2,4 cent | 0,4 cent |
→ Chốt: ① gpt-4.1-mini (bỏ deepseek), ⑥ Jev 25 phim, ⑦ gpt-4.1-mini.

## 2. Series TV
```
fetch_tmdb_tv.py (vote ≥ 20): 12.805 series · 7m44s
load_tv.py: "nạp 12805 series | DB: 12805 series, 4476 có tên tiếng Việt"
```
Nhận diện tên (không tốn tiền):
```
Breaking Bad → Breaking Bad (2008)          Trò chơi con mực → Squid Game (2021)
High Tides → High Tides (2023)              Bóng ma Anh Quốc → Peaky Blinders (2013)
Trò chơi vương quyền → Game of Thrones      Dune / Interstellar → vẫn ra phim lẻ
```
Kết quả thật:
```
"phim giống Breaking Bad" → El Camino 98% · [Series] Better Call Saul 96% · [Series] Ozark 86% · [Series] Narcos: Mexico 82%
"phim lẻ giống Trò chơi con mực" (lọc Chỉ phim lẻ) → Battle Royale 86% · The Belko Experiment 84% · 13 Sins 82%
"phim bộ Hàn Quốc tâm lý hồi hộp" → Flower of Evil · Beyond Evil · Signal · Stranger · The 8 Show
```

## 3. Kho hồ sơ cuối
| | Trong DB | Có hồ sơ (được gợi ý) | Có vector |
|---|---|---|---|
| Phim lẻ | 15.151 | **7.494** (ưu tiên từ 1975, nhiều vote) | 7.494 |
| Series | 12.805 | **3.531** (nhiều vote trước) | 12.805 |

Hồ sơ ~0,17 cent/phim ở đợt này (provider báo nhóm OpenAI khan nguồn). Tổng đã dùng ~51 USD.
Các lệnh chạy dài đã bị Claude Code tắt 2 lần vì máy thiếu RAM → chạy lại theo đợt ≤ 10 phút; mọi script đều bỏ qua phần đã xong.

## 4. Sửa lỗi phát hiện khi test
| Lỗi | Sửa |
|---|---|
| "tìm phim tương tự High Tides" (series chưa có) → đoán theo nghĩa đen "thuỷ triều", lời mở đầu nói như thể biết phim | Bước "Không tìm thấy \"High Tides\"" + `clarify` nếu câu chỉ có tên; có mô tả thêm thì LLM buộc nói rõ chưa có phim |
| "Bóng ma Anh Quốc" không nhận ra (tên TMDB dài hơn) | thêm `word_similarity` × 0.9 (tên gõ nằm trọn trong tên dài) |
| Phim tham chiếu ngoài kho đã embed → không tìm được phim giống | tính vector tại chỗ từ dữ liệu TMDB |
| "tâm lý" → filter Chính kịch; "zombie" → Kinh dị | `GENRE_WORDS`: thể loại phải được gọi đúng tên |
| "phim nào … như Peaky Blinders" → tự thêm "Chỉ series" | `KIND_WORDS`: chỉ lọc khi user nói "phim bộ / series / phim lẻ" |
| Điểm "Đội ngũ" do LLM chấm bừa (Paprika 0,9 với Inception) | tính bằng code từ cast/crew thật |
| Jev chấm "vi phạm" 0,3–0,4 cho cả phim hợp → Paprika chỉ 53% | chỉ trừ khi ≥ 0,6 + hỏi rõ "user có nói KHÔNG muốn gì" |
| LLM bỏ trống lý do vài phim | tự điền từ "Tâm trạng" của hồ sơ |
| gemini bọc JSON trong ```json → 80 lần gọi hỏng | `llm.parse_json` bỏ rào |
| `requirements.txt` thiếu fastapi/uvicorn/psycopg-pool/numpy; ghi chú tiếng Việt làm pip Windows lỗi | sửa + kiểm tra trong venv sạch |
Đã thử và **bỏ**: để LLM ① tự chọn tỉ lệ "giống phim X ↔ đúng chủ đề" — cùng 1 câu lúc 0,35 lúc 0,8, kết quả dao động mạnh → giữ tỉ lệ cố định.

## 5. Frontend
| Chỗ | Trước | Giờ |
|---|---|---|
| Chat | đợi xong mới hiện, hiệu ứng bước giả | **stream** `/api/ask/stream`: bước thật → 10 thẻ phim (chưa có lý do, "đang viết lý do…") → đầy đủ |
| Drawer "Chi tiết" | phim tương tự từ 20 phim mock, "tóm tắt review" viết sẵn | `/api/similar` + mục **"AI cảm nhận về phim"** từ hồ sơ thật |
| Bảng so sánh | % tính bằng công thức mock | `pairs` từ engine |
| Landing | % mock | `/api/pair` |
| Chat mẫu / My List | 3 cuộc chat mẫu, dữ liệu mock | bỏ chat mẫu; My List & lịch sử nạp dữ liệu thật qua `/api/movies` |
| Chip | — | nhãn **"Hỏi tiếp:"**, nút **"+ Thêm"** điều kiện (điền sẵn ô nhập), nhãn **Series**, ẩn thời lượng khi thiếu |

Test UI thật (Edge headless, dev mode):
```
landing sim: 52%  ·  chat mẫu còn lại: 0
0.1s  khung suy luận: "Đang phân tích câu hỏi…"
6.0s  thẻ phim hiện (preview): El Camino, Better Call Saul, Ozark, Narcos: Mexico
11.1s xong, lý do #1: "Tiếp nối Breaking Bad, tập trung hồi sinh và chuộc lỗi nhân vật Jesse."
      chip: "Hỏi tiếp: Phim nào có nhiều hành động? · …"
drawer El Camino → tương tự: Breaking Bad 89% · Better Call Saul 60% · El Chapo 54% · Mayans M.C. 52%
      hồ sơ: Tâm trạng · Nhịp phim · Chủ đề · Tông · Kiểu kết · Phong cách · Hợp với
lỗi console / HTTP ≥ 400: []
```
Ảnh: `img/ui-5-landing.png`, `img/ui-6-preview.png`, `img/ui-7-drawer.png`.
