# CineMind — Lộ trình phát triển tiếp

> Cập nhật 2026-10-27. Trạng thái hiện tại: `docs/PROGRESS.md` · thiết kế: `docs/engine-design.md` · bằng chứng: `docs/steps/`.
> Ký hiệu: 🔴 nên làm trước · 🟠 nên làm · 🟢 tuỳ chọn · 💰 tốn tiền LLM · 👤 cần user / khách quyết.

## 0. Đang chờ quyết định
| # | Việc | Ai quyết | Ghi chú |
|---|---|---|---|
| 0.1 👤 | Repo public hay private trong lúc khách chưa bảo vệ đồ án | User + khách | Hiện **public**. Rủi ro: khách bị phát hiện trùng lặp / không muốn công khai |
| 0.2 👤 | Đề tài có bắt buộc **đăng nhập thật + phân quyền** không, cần vai trò nào | Khách | Xem mục 2.1 |
| 0.3 ✅ | Hồ sơ 1.300 series châu Á (27/10: ~2,5 USD key Medium + ~0,6 USD embed) | — | Có hồ sơ: CN 921 · KR 591 · HK 95 · TH 75 · TW 42 |
| 0.4 ✅ | Đã đổi key: `LLM_API_KEY` = nhóm Medium (gpt) · `AUX_API_KEY` = key cũ (embedding + Jev) | — | Medium nhanh (~150 hồ sơ/phút, gần như không lỗi) nhưng ~0,19 cent/hồ sơ (×2,4 nhóm Cheap) |

## 1. Giao được cho khách (🔴)
| # | Việc | Ước lượng | Cách làm |
|---|---|---|---|
| 1.1 | **Xuất database** để khách khỏi tự viết lại 11k hồ sơ (~20 USD) | 30 phút | `docker exec cinemind-db pg_dump -U cinemind -Fc cinemind > cinemind.dump` (~200–300 MB) → GitHub Release / Drive; thêm `etl/restore.md` + lệnh `pg_restore` vào README |
| 1.2 | **Đóng gói Docker cả bộ** (DB + API + frontend build) | 1 giờ | `backend/Dockerfile` (uvicorn), `frontend` build tĩnh do FastAPI phục vụ hoặc nginx; compose 1 lệnh `docker compose up` |
| 1.3 | Hướng dẫn cho khách A–Z (cài Docker, WARP, điền key, nạp dump, chạy) | 30 phút | 1 file `docs/HUONG-DAN-KHACH.md`, ảnh chụp từng bước |
| 1.4 | Ghi nguồn TMDB trong giao diện (điều khoản TMDB bắt buộc) | 10 phút | Footer: "This product uses the TMDB API but is not endorsed or certified by TMDB" + logo |

## 2. Tính năng còn thiếu
| # | Việc | Ước lượng | Ghi chú |
|---|---|---|---|
| 2.1 🟠👤 | **Đăng nhập thật**: bảng `users` (email, bcrypt, role), JWT, lưu My List + lịch sử chat trên server, API cần đăng nhập thì kiểm tra token | 2–3 giờ | Hiện là giả: localStorage, không mật khẩu, API mở. Tham khảo HotelChatbot (đã có RBAC + bcrypt + session) |
| 2.2 🟠 | **Giới hạn lượt gọi** (rate limit theo IP / user) | 30 phút | Bắt buộc trước khi public demo — mỗi câu tốn ~2 cent |
| 2.3 🟠 | **Cache câu trả lời** (câu + filter giống nhau → trả ngay) | 30 phút | Bảng `answer_cache` hoặc Redis, hết hạn 1–7 ngày; chip gợi ý được bấm nhiều nhất → lợi nhất |
| 2.4 🟢 | Trang admin: số câu hỏi/ngày, chi phí, độ trễ, câu hỏi không ra kết quả | 2 giờ | Cần log từng câu (`_debug` đã có timing/model/attempt) |
| 2.5 🟢 | Job tự cập nhật phim mới + trending hằng ngày | 1 giờ | `etl/*.py` đã chạy lại được; cần WARP/DNS trên máy chạy job |

## 3. Chất lượng engine
| # | Việc | Ước lượng | Ghi chú |
|---|---|---|---|
| 3.0 ✅ | **Jev loại phim sai yêu cầu cứng + không ép đủ 10** (ca: "phim thời Dân Quốc từ 2023" ra 6/10 phim cổ trang, lý do bịa) | 2 giờ | Kế hoạch chi tiết: `docs/plans/09-jev-loai-phim.md` (chỉ ở máy, gitignore) |
| 3.1 🔴 | **"giống X nhưng …"** và pha trộn nhiều phim (yếu nhất: 36% rất hợp) | 1–2 giờ | Ý tưởng: phần "nhưng" (ngắn hơn, ít bạo lực, nhẹ hơn) đưa vào Jev như 1 câu hỏi `noul` riêng + phạt mạnh; "ngắn hơn X" → filter `runtime_max = runtime(X)`; pha trộn → dùng trung bình vector các phim tham chiếu |
| 3.2 🟠 | Cập nhật bộ đánh giá 40 câu: thêm series vào đáp án | 30 phút | Hiện kho có series nên nDCG theo bộ cũ bị thấp giả |
| 3.3 🟠💰 | Viết hồ sơ phần còn lại (~7.700 phim lẻ · ~13.000 series) | — | ~0,17 cent/phim; ưu tiên phim từ 1975 + series đang hot (popularity) |
| 3.4 🟢 | Điểm Jev hay bão hoà 98–100% với câu rộng ("phim mafia") | 30 phút | Thêm mức chấm (6 thay vì 4) hoặc chuẩn hoá điểm trong từng câu trả lời |
| 3.5 🟢 | Tên phim tiếng Việt không chuẩn ("Lang **Gia** Bảng" vs TMDB "Lang **Nha** Bảng") | 1 giờ | Bảng tên gọi khác do user/LLM bổ sung; hoặc khớp gần theo từng từ |
| 3.6 🟢 | Nhận diện tên chậm ~1,2 s | 30 phút | Bỏ điều kiện `EXISTS unnest(alt_titles)` khỏi WHERE (quét cả bảng) hoặc tách bảng `titles` có index trigram |

## 4. Tốc độ & chi phí
| # | Việc | Hiệu quả dự kiến |
|---|---|---|
| 4.1 🟠👤 | Provider chính chủ (OpenAI / Anthropic) thay `shopaikey` | −2 s/câu, gần hết lỗi 429/503 |
| 4.2 🟢 | Rút ngắn phần viết ở ⑦ (lý do ≤ 12 từ, hoặc chỉ viết cho 5 phim đầu, 5 phim sau viết khi cuộn tới) | −2 đến −3 s |
| 4.3 🟢 | Chạy ① song song với ② cho câu có dạng "giống X" rõ ràng (regex nhận tên trước) | −1 s |

## 5. Đã thử — KHÔNG làm lại (trừ khi có số liệu mới)
MMR ở ⑤ · nguồn keyword full-text · deepseek-v4-flash cho ① · gpt-5.4-mini cho ① · qwen3-rerank · Jev chấm 60 phim ·
để LLM tự chọn tỉ lệ "giống phim X ↔ chủ đề" · cốt truyện Wikipedia khi embed (+1–2%, code `etl/fetch_plots.py` còn giữ).
Bằng chứng: `docs/steps/02, 03, 07, 08`.
