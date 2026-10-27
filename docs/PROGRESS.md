# Tiến độ CineMind engine

> Phiên mới: đọc **`CLAUDE.md`** ở gốc repo (bàn giao đầy đủ: bối cảnh, bẫy, quyết định đã chốt, việc chờ user) rồi file này.
> Quy tắc: không chia subagent; hết tiền LLM thì dừng phần LLM nhưng vẫn làm các bước khác; xong bước nào ghi `docs/steps/NN-*.md` kèm input/output thật.

## Checklist
- [x] 0. Chuẩn bị môi trường → `steps/00-setup.md`
- [x] 1. Dữ liệu TMDB → `steps/01-data.md`
- [x] 2. Chọn embedding: gemini-embedding-001 → `steps/02-embedding.md`
- [x] 3. Engine lõi ③④⑤ + bộ 40 câu đánh giá → `steps/03-engine-core.md`
- [x] 4. LLM ① + ⑦, chống bịa filter → `steps/04-llm.md`
- [x] 5. Rerank ⑥ → `steps/05-rerank.md`
- [x] 6. FastAPI + nối frontend → `steps/06-api-frontend.md`
- [x] 7. Jev qua provider, series TV, sửa hallucination, frontend thật + stream → `steps/07-series-jev-frontend.md`
- [x] 8. Bỏ MMR, Jev chấm 40, bộ 100 câu kiểu người dùng thật + giám khảo LLM → `steps/08-eval100.md`
- [x] 9. Jev loại phim sai yêu cầu cứng (thời đại, bối cảnh, kiểu nhân vật) + Jev xem overview + ⑦ hết bịa lý do → `steps/09-jev-loai-phim.md`

## Trạng thái hiện tại
| | |
|---|---|
| Được gợi ý (có hồ sơ + vector) | **7.494 phim lẻ + 5.037 series = 12.531** (series châu Á: CN 921 · KR 591 · HK 95 · TH 75 · TW 42) |
| Nhận diện được tên | 15.151 phim lẻ + 16.559 series (gồm ~5k series châu Á kéo thêm 27/10) |
| Flow | ① gpt-4.1-mini → ② tên phim/series → ③ filter (chống bịa 4 lớp + từ khoá thể loại/loại phim) → ④ RRF → ⑤ top 40 RRF → ⑥ Jev (40, loại phim `sai_yeu_cau`) → gộp series → ⑦ gpt-4.1-mini |
| Không tìm thấy phim | nói thật / hỏi lại |
| Chất lượng (100 câu, giám khảo LLM) | **98% phim hợp · 78% rất hợp · 100% câu có phim rất hợp trong top 3** (steps/09; trước: 95% · 65%) · yếu nhất: pha trộn nhiều phim, "giống X nhưng…" |
| Tốc độ | thẻ phim hiện ~6 s, xong ~11 s (stream); provider đôi lúc treo tới 30–90 s |
| Giá | ~2 cent / câu hỏi (Jev chấm 40 phim) |
| Ngân sách provider | ~55,7 / 60 USD |

## Việc còn lại (chi tiết + cách làm: [`ROADMAP.md`](ROADMAP.md))
| # | Việc | Cần user? |
|---|---|---|
| −1 | **Chờ user:** đăng nhập/phân quyền thật có cần không | **Có** |
| 0 | "giống X **nhưng** <khác>" và pha trộn nhiều phim: áp phần "nhưng" mạnh hơn (ngắn hơn, ít bạo lực…) | Không |
| 1 | Cache câu trả lời (câu trùng → 0 s, 0 đồng) | Không |
| 1b | **Xuất DB cho khách** (`pg_dump` ~200–300 MB nén → GitHub Release / Drive + lệnh `pg_restore`) — không có thì khách phải tự viết lại 11k hồ sơ (~20 USD, vài tiếng) | Không |
| 2 | Đóng gói Docker (API + frontend + DB + file dump dữ liệu) | Không |
| 3 | ~~Push git~~ ✅ https://github.com/usermangcut-ai/cinemind (private) | — |
| 4 | Đổi key sang nhóm "OpenAI Medium" (provider khuyên, đỡ lỗi 503) | **Có** |
| 5 | Job tự cập nhật phim mới / trending | Không |
| 6 | Hồ sơ cho phần còn lại (~7.700 phim lẻ, ~11.500 series) | Ngân sách (~0,17 cent/phim) |

## Lệnh hay dùng
```bash
cd backend
docker compose up -d                                       # DB (Docker Desktop phải mở)
.venv/Scripts/python -m uvicorn app.main:app --port 8000    # API
cd ../frontend && npm install && npm run dev               # frontend → http://localhost:5173/chat

# dữ liệu (bật WARP khi gọi TMDB)
.venv/Scripts/python etl/fetch_tmdb.py  && .venv/Scripts/python etl/load_db.py      # phim lẻ
.venv/Scripts/python etl/fetch_tmdb_tv.py && .venv/Scripts/python etl/load_tv.py    # series
.venv/Scripts/python etl/profile.py --kind movie --min-year 1975 --limit 500        # hồ sơ (tốn tiền)
.venv/Scripts/python etl/profile.py --kind tv --limit 500
.venv/Scripts/python -m etl.embed          # vector phim lẻ có hồ sơ
.venv/Scripts/python -m etl.embed --tv     # vector series (series mới có hồ sơ: set dense = NULL trước)
.venv/Scripts/python etl/trending.py       # Top 10

# đánh giá
.venv/Scripts/python -m eval.engine_eval --core            # không tốn tiền
.venv/Scripts/python -m eval.engine_eval --full --sample   # 10 câu, ~10–25 cent
.venv/Scripts/python -m eval.parse_eval                    # bước ①, ~3 cent
```
