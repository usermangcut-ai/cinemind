# Bước 1 — Dữ liệu

> Trạng thái: ✅ xong phần kéo + nạp DB + hồ sơ phim cho **3.789 phim** (dừng vì chạm ngân sách, xem §4–5).
> Script: `backend/etl/fetch_tmdb.py` → `etl/load_db.py` → `etl/profile.py`.

## 1. Kéo từ TMDB (`fetch_tmdb.py`, cần bật WARP)
```
discover … → 1979-12-31: 1533
discover 1980-01-01 → 1999-12-31: 2665
discover 2000-01-01 → 2009-12-31: 3040
discover 2010-01-01 → 2016-12-31: 3383
discover 2017-01-01 → nay: 4481
phim Việt: 51
tổng: 15151 | đã có: 3 | cần kéo: 15148
xong: ghi 15148, lỗi/không tồn tại 0 → data/raw/tmdb/movies.jsonl   (845 MB, ~12 phút)
```
Mỗi phim gọi 1 request `/movie/{id}?append_to_response=credits,keywords,translations,release_dates,alternative_titles`.

## 2. Nạp DB (`load_db.py`, 38 giây)
```
nạp 15151 phim | DB: 15151 phim, 7095 có tên tiếng Việt, 15134 có điểm IMDb
```
| Trường | Có dữ liệu |
|---|---|
| tổng phim | 15.151 (năm 1888 → phát hành mới nhất 2026-10-09) |
| `title_vi` | 7.095 |
| `overview_vi` | 6.193 |
| `collection_id` | 3.483 |
| `certification` (US) | 12.194 |
| `imdb_rating` | 15.134 |
| phim 2024+ | 800 |

Mẫu 1 dòng (Arrival):
```
id 329865 | Arrival | Cuộc Đổ Bộ Bí Ẩn | 2016 | 116' | {Drama, Science Fiction, Mystery} | {US}
director {Denis Villeneuve} | cast {Amy Adams, Jeremy Renner, Forest Whitaker}
crew_key {Jóhann Jóhannsson, Bradford Young} | PG-13 | IMDb 7.9 | 20.088 vote
```

## 3. Hồ sơ phim (`profile.py`)

### Lần 1 — prompt văn xuôi → ❌ hỏng
`gpt-4.1-mini` bỏ qua yêu cầu và **kể lại cốt truyện**:
> *The Dark Knight:* "Bộ phim kể về cuộc chiến không ngừng nghỉ của một chiến binh bóng tối chống lại tội phạm trong thành phố Gotham. Cùng với sự hỗ trợ của một cảnh sát trưởng…"

### Lần 2 — ép JSON có 8 trường → ✅
Prompt yêu cầu JSON `{tam_trang, nhip_phim, chu_de, tong, kieu_ket, phong_cach, hop_voi, tu_khoa[]}`, code ghép lại thành văn bản:
```
## Parasite / Ký Sinh Trùng (2019)
Tâm trạng: căng thẳng, châm biếm, bất ngờ, sâu sắc
Nhịp phim: vừa phải, xen kẽ cao trào và khoảnh khắc lặng
Chủ đề: bất bình đẳng xã hội, đấu tranh giai cấp, mưu mẹo sinh tồn, gia đình, sự giả tạo
Tông: u tối pha trộn hài hước châm biếm
Kiểu kết: mở, gây suy ngẫm
Phong cách: hình ảnh sắc nét, kịch bản chặt chẽ, nhịp phim linh hoạt, diễn xuất chân thực
Hợp với: người thích phim xã hội, phim tâm lý, xem cùng bạn bè để thảo luận
Hay được tìm: phim xã hội, phim châm biếm, phim tâm lý, phim Hàn Quốc, phim gia đình, phim kịch tính, phim xoắn não…

## Furie / Hai Phượng (2019)
Tâm trạng: kịch tính, căng thẳng, mãnh liệt, cảm động
Nhịp phim: nhanh, dồn dập và liên tục cao trào
Chủ đề: tình mẫu tử, công lý, bạo lực, đấu tranh sinh tồn, tội phạm
Kiểu kết: có hậu, thỏa mãn
Hay được tìm: phim hành động Việt Nam, phim võ thuật, phim bắt cóc, phim tình mẫu tử…
```

### Sự cố provider
- Chạy 20 request song song → provider trả **429** và **503 "No available channel for model gpt-4.1-mini"** theo đợt, tốc độ rơi xuống ~15 phim/phút.
- Sửa: song song 10, backoff có jitter, mỗi lần thử lại **xoay sang model dự phòng** (`gpt-5.4-mini`, `gemini-3.5-flash`). Tốc độ lên ~110–130 phim/phút.
- Cùng cơ chế dự phòng được thêm vào `app/llm.py` cho phần online.

## 4. Chi phí thật & quyết định dừng
| | |
|---|---|
| Token trung bình / phim | ~610 vào + ~260 ra |
| Model thực dùng | gpt-4.1-mini 1.293 phim · gpt-5.4-mini 167 phim (dự phòng) |
| Chi phí đo trên provider | `total_usage` 2.985 → 3.151 cent cho ~1.500 hồ sơ ≈ **0,1 cent / phim** |
| Ước tính 5k phim | ~5 USD · 15k phim ~15 USD |
| Hạn mức provider | 40 USD/tháng, đã dùng ~31,5 USD (gồm project khác) |

→ **Dừng ở 1.537 phim** (≈1.400 phim nhiều vote nhất + 51 phim Việt + mọi phim trong bộ đánh giá)
để giữ tiền cho embedding và chạy thử online. Khi nạp thêm tiền:
```bash
.venv/Scripts/python etl/profile.py --top 5000      # chạy tiếp, bỏ qua phim đã có hồ sơ
.venv/Scripts/python -m etl.embed                    # embed phần mới
```

## 5. Đợt 2 — dùng nốt ngân sách (đêm 27/10)
Sau khi engine chạy ổn trên 1.537 phim, chạy tiếp `profile.py --top 4500` kèm **script canh ngân sách**
(đọc `total_usage` mỗi 90 s, tự dừng khi ≥ 38,5 USD để chừa tiền test):
```
00:41 usage=3508 … 01:05 usage=3841 · 01:07 usage=3860 → STOP at 3860
hồ sơ: 3.789 phim · embed: "xong: 3789 phim có vector (gemini-embedding-001, 3072 chiều)"
total_usage sau embed: 3.891,6 cent (≈ 38,9 / 40 USD)
```
→ còn ~1,1 USD để thử online. Phim chưa có hồ sơ: 11.362 (chạy tiếp được bất cứ lúc nào, script bỏ qua phim đã có).
