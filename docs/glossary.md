# Giải thích các trường & thuật ngữ

> Đọc kèm `engine-design.md`. Mỗi mục: **là gì** → **ví dụ** → **dùng để làm gì**.
> Ví dụ xuyên suốt: user gõ *"Tìm phim kiểu Hố đen tử thần, từ 2015 trở lại đây, đừng dài quá, không kinh dị"*.

---

## A. Thuật ngữ chung

| Thuật ngữ | Hiểu nôm na | Ví dụ |
|---|---|---|
| **Offline** | Việc làm sẵn trước, user không phải chờ | Kéo 10k phim về, viết hồ sơ, tính vector — làm 1 lần |
| **Online** | Việc làm ngay khi user hỏi | 7 bước ① → ⑦, phải xong trong vài giây |
| **LLM** | Model AI viết/hiểu chữ (Claude) | Đọc câu user → hiểu "Hố đen tử thần" là tên phim |
| **Embedding / vector** | Biến 1 đoạn chữ thành dãy số; 2 đoạn ý nghĩa giống nhau → dãy số gần nhau | "phim buồn về gia đình" và "drama gia đình cảm động" → 2 vector rất gần |
| **Dense vector** | Vector "hiểu ý nghĩa" (3072 con số với gemini-embedding-001) | Bắt được "vũ trụ" ≈ "không gian" ≈ "space" |
| **Full-text search** | Tìm "khớp từ khoá" trong Postgres (cột `fts`), bỏ dấu trước khi so | Bắt được đúng chữ "Nolan", "zombie" |
| **gemini-embedding-001** | Model tạo embedding (đã chọn sau khi so với bge-m3, text-embedding-3-large), hiểu cả tiếng Việt lẫn tiếng Anh | "phim giống Ký sinh trùng" → hiểu là phim Parasite chứ không phải con ký sinh trùng |
| **pgvector** | Phần mở rộng cho Postgres để lưu và tìm vector | `ORDER BY dense <=> vector_cau_hoi LIMIT 200` |
| **pg_trgm** | Phần mở rộng Postgres để tìm chữ gần giống (chịu được gõ sai) | "intersteller" → "Interstellar" |
| **Retrieval** | Bước "vớt" ứng viên: từ hàng nghìn phim lấy ra vài trăm phim có khả năng hợp | 4.200 → 100 |
| **Rerank** | Bước "chấm kỹ" lại số ít ứng viên để xếp thứ tự cuối | 40 → 10 |
| **RRF** | Cách gộp nhiều bảng xếp hạng thành 1, chỉ dựa vào thứ hạng | Phim nào nhiều nguồn cùng xếp cao → lên đầu |
| **MMR** | Cách chọn danh sách vừa hợp vừa *khác nhau*, tránh 10 phim na ná | Không trả 5 phim "phi hành gia kẹt ngoài vũ trụ" |
| **Collection** | Nhóm phim cùng series trên TMDB | Dune, Dune: Part Two → chỉ giữ 1 |
| **Jev** | Model của TypeSafe AI, không viết chữ, chỉ chấm điểm / chọn / trả lời có-không kèm xác suất. Gọi qua chính provider LLM (`/v1/systemone`) | Chấm "Arrival khớp yêu cầu: Rất khớp (xác suất 0.97)" |
| **Series / `kind`** | Phim bộ TV, lưu chung bảng với `kind='tv'`, id âm. Có hồ sơ mới được gợi ý; không có hồ sơ vẫn nhận diện được tên | "giống Breaking Bad" → Better Call Saul, Ozark |
| **Phim tham chiếu** | Phim user nhắc tới để so ("giống X") — khác với phim được gợi ý ra | X = Peaky Blinders |
| **Stream** | Trả kết quả dần: các bước → 10 thẻ phim (chưa có lý do) → câu trả lời đầy đủ | Thẻ phim hiện sau ~6 s, xong sau ~11 s |
| **Hallucination (bịa)** | AI tự nghĩ ra thứ không có | User không nói năm mà LLM tự thêm "từ 2015" |
| **Chip** | Nhãn nhỏ bo tròn bấm được trên UI | `( Từ 2015 ✕ )` |
| **Human-in-the-loop** | Cho người dùng can thiệp/sửa quyết định của máy | Bấm ✕ để gỡ filter sai |

---

## B. Bảng `movies` trong DB (mỗi dòng = 1 phim)

| Trường | Là gì | Ví dụ (Arrival) | Dùng ở đâu |
|---|---|---|---|
| `id` | Mã phim trên TMDB — "chứng minh thư" của phim | `329865` | Mọi nơi; frontend dùng để hiện poster, My List |
| `imdb_id` | Mã phim trên IMDb | `tt2543164` | Nối sang để lấy điểm IMDb |
| `title` | Tên gốc | `Arrival` | Hiển thị, tìm tên |
| `title_vi` / `overview_vi` | Tên / tóm tắt tiếng Việt (TMDB translations) | `Cuộc Đổ Bộ Bí Ẩn` | Tìm khi user gõ tên Việt, hiển thị |
| `alt_titles` | Các tên khác (tên phụ, tên ở nước khác) | `["Story of Your Life"]` | Tìm tên ② |
| `year` | Năm phát hành | `2016` | Filter năm ③ |
| `runtime` | Thời lượng (phút) | `116` | Filter thời lượng ③, ưu tiên "ngắn" ④ |
| `genres` | Thể loại (19 loại cố định của TMDB) | `["Drama","Science Fiction","Mystery"]` | Filter ③, keyword ④ |
| `countries` | Quốc gia sản xuất (mã 2 chữ ISO) | `["US"]` | Filter "phim Hàn" = `KR` |
| `keywords` | Từ khoá TMDB gắn cho phim | `["alien","linguistics","time"]` | Keyword ④, so trùng chủ đề |
| `director` | Đạo diễn (mảng, có phim 2 đạo diễn) | `["Denis Villeneuve"]` | Nguồn "Đội ngũ" ④, filter `person` |
| `cast_top` | 5 diễn viên chính | `["Amy Adams","Jeremy Renner",…]` | Nguồn "Đội ngũ" ④ |
| `writers` | Biên kịch | `["Eric Heisserer"]` | Nguồn "Đội ngũ" ④ |
| `crew_key` | Nhạc, quay phim | `["Jóhann Jóhannsson","Bradford Young"]` | Nguồn "Đội ngũ" ④ |
| `collection_id` / `collection` | Mã + tên series trên TMDB (rỗng nếu phim lẻ) | `null` (Dune → `726871`, "Dune Collection") | Gộp series ⑤ |
| `overview` | Tóm tắt cốt truyện (TMDB viết) | "A linguist works with the military to…" | Đầu vào để LLM viết `profile` |
| `profile` | **Hồ sơ phim do LLM viết** — tâm trạng, nhịp, chủ đề, hợp với ai | "Sci-fi trầm, chậm, giàu cảm xúc…" | Tạo `dense`; Jev ⑥ và LLM ⑦ đọc |
| `imdb_rating` / `imdb_votes` | Điểm và số lượt vote IMDb (file ratings tải hằng ngày) | `7.9` / `850000` | Cộng nhẹ cho phim chất lượng ④ |
| `vote_average` | Điểm TMDB | `7.6` | Dự phòng khi thiếu điểm IMDb |
| `original_title` / `original_language` | Tên & ngôn ngữ gốc | `Hai Phượng` / `vi` | Tìm tên ②, lọc phim Việt |
| `tagline` / `backdrop_path` | Câu slogan / ảnh nền | `Why are they here?` | Hiển thị, đầu vào hồ sơ phim |
| `vote_count` | Số lượt vote TMDB | `18500` | Chọn phạm vi phim (`≥ 200`), loại phim quá vô danh |
| `certification` | Độ tuổi (Mỹ) | `PG-13` | Filter "cho trẻ em" |
| `popularity` | Độ hot hiện tại theo TMDB | `45.2` | Bảng Top tuần/tháng |
| `poster_path` | Đường dẫn ảnh poster | `/x2FJs….jpg` | Frontend hiện ảnh |
| `dense` | Vector ý nghĩa (3072 số, kiểu `halfvec`) tạo từ tên + hồ sơ + tóm tắt + từ khoá + đạo diễn | `[0.021, -0.113, …]` | Tìm theo ý nghĩa ④ |
| `fts` | Chỉ mục full-text (tên, hồ sơ, từ khoá, tóm tắt — đã bỏ dấu) | `'interstellar':1A 'vu':12B …` | Nguồn keyword ④ |
| `updated_at` | Lần cập nhật cuối | `2026-10-26` | Job đồng bộ biết phim nào cần làm lại |

Bảng **`trending`**: `period` (`week`/`month`) · `rank` (1–10) · `movie_id` → dùng cho cột Top 10 bên phải màn hình chat.

---

## C. JSON bước ① — LLM phân tích câu hỏi

```json
{
  "intent": "similar",
  "movie_refs": ["Hố đen tử thần"],
  "filters": [
    { "field": "year_min", "value": 2015, "evidence": "từ 2015 trở lại đây" },
    { "field": "exclude_genres", "value": ["Horror"], "evidence": "không kinh dị" }
  ],
  "soft": { "text": "không khí giống phim tham chiếu", "prefer_runtime": "short" }
}
```

| Trường | Là gì | Ví dụ |
|---|---|---|
| `intent` | User đang muốn **làm gì** | `search` — tìm theo mô tả ("phim buồn về gia đình")<br>`similar` — tìm phim giống phim X<br>`compare` — so sánh 2–3 phim<br>`about` — hỏi thông tin 1 phim ("Arrival kể về gì?")<br>`chitchat` — không phải hỏi phim ("chào bạn") |
| `movie_refs` | Tên phim user **nhắc tới** (chép nguyên chữ user gõ, chưa tra ID) | `["Hố đen tử thần"]` → bước ② tra ra Interstellar |
| `filters` | Các **điều kiện cứng** — phim nào không thoả là bị loại hẳn | xem bảng dưới |
| `filters[].field` | Lọc theo cái gì | `year_min` |
| `filters[].value` | Giá trị lọc | `2015` |
| `filters[].evidence` | **Câu trích nguyên văn** từ lời user làm bằng chứng cho filter này. Code kiểm tra đoạn này có thật trong câu user không → không có thì bỏ filter (chống bịa) | `"từ 2015 trở lại đây"` |
| `soft` | Các **mong muốn mềm** — không loại phim, chỉ cộng/trừ điểm | |
| `soft.text` | Mô tả "gu" của user, sẽ được embed để tìm theo ý nghĩa | `"không khí giống phim tham chiếu"`, `"buồn, chậm, ám ảnh"` |
| `soft.prefer_runtime` | Thích phim ngắn/dài (mơ hồ, không có số) | `"short"` khi user nói "đừng dài quá" |

**Các `field` filter cho phép:**

| field | Nghĩa | User nói | value |
|---|---|---|---|
| `year_min` / `year_max` | Từ năm / đến năm | "từ 2015", "trước 2000" | `2015` / `1999` |
| `runtime_min` / `runtime_max` | Thời lượng tối thiểu / tối đa (phút) | "dưới 2 tiếng" | `runtime_max: 120` |
| `genres` | Phải có thể loại | "phim hoạt hình" | `["Animation"]` |
| `exclude_genres` | Không được có thể loại | "không kinh dị" | `["Horror"]` |
| `countries` / `exclude_countries` | Phải / không được thuộc quốc gia | "phim Hàn" | `["KR"]` |
| `certification_max` | Độ tuổi tối đa | "cho trẻ em xem" | `"PG"` |
| `person` | Có đạo diễn/diễn viên | "phim của Nolan" | `"Christopher Nolan"` |

**Cứng hay mềm?** Có con số / tên cụ thể → `filters`. Mơ hồ → `soft`.
"dưới 2 tiếng" → filter `runtime_max: 120` · "đừng dài quá" → `soft.prefer_runtime: "short"`.

---

## D. Bước ② — nhận diện tên phim

```json
{ "Hố đen tử thần": { "id": 157336, "title": "Interstellar", "match": "title_vi", "conf": 0.98 } }
```
| Trường | Là gì |
|---|---|
| `id` | Mã phim tìm được |
| `title` | Tên gốc của phim đó |
| `match` | Khớp ở cột nào (`title`, `title_vi`, `alt_titles`) |
| `conf` | Độ chắc chắn 0–1. Dưới 0.6, hoặc có 2 phim sát điểm nhau (Dune 1984/2021) → hỏi lại user |

---

## E. Bước ④ — các nguồn & điểm RRF

| Nguồn | Hỏi DB câu gì | Có khi nào |
|---|---|---|
| Dense câu hỏi | "Phim nào có *ý nghĩa* gần câu user nhất?" | Luôn có |
| Keyword | "Phim nào có *từ khoá* trùng câu user?" (full-text) | Luôn có |
| Dense phim tham chiếu | "Phim nào *giống Interstellar* nhất?" | Khi user nhắc tên phim |
| Đội ngũ | "Phim nào chung đạo diễn/diễn viên/nhạc sĩ với Interstellar?" | Khi user nhắc tên phim |

- **Hạng** = vị trí của phim trong bảng của từng nguồn (1, 2, 3…).
- **Trọng số `w`** = nguồn nào được tin hơn. Đang dùng: câu hỏi 1.0 · keyword 0.3 · phim tham chiếu 2.0 · đội ngũ 0.5 (chọn bằng `eval/sweep.py`).
- **Điểm RRF** = cộng `w / (60 + hạng)` qua các nguồn. Chỉ dùng để chọn top 100, **không** hiện lên UI.

---

## F. Bước ⑥ — Jev rerank

| Trường | Là gì |
|---|---|
| `state` | Thông tin cho Jev đọc: câu hỏi, phim tham chiếu, phim đang chấm |
| `questions` | Các câu hỏi Jev phải trả lời cho phim đó |
| `type: "score"` | Chấm điểm theo các mức định sẵn (ở đây 0–10), trả số có thể lẻ (7.8) |
| `type: "noul"` | Câu hỏi có/không, trả xác suất "có" (0–1) |
| `criteria` | Mô tả từng mức điểm, vd mức 0 = "không liên quan", mức 10 = "rất khớp" |
| `confidence` | Jev chắc chắn tới đâu về câu trả lời (0–1) |
| `noi_dung` | Cốt truyện/ý tưởng khớp yêu cầu tới đâu → `'Nội dung'` trên UI |
| `chu_de` | Chủ đề, không khí khớp tới đâu → `'Chủ đề'` trên UI |
| `doi_ngu` | Đạo diễn/diễn viên/phong cách khớp tới đâu → `'Đội ngũ'` trên UI |
| `vi_pham` | Xác suất phim trái ý user (vd user nói "không đáng sợ" mà phim khá rợn) → trừ điểm |

**Điểm cuối hiện trên UI:**
```
score = 100 × (0.5·Nội dung + 0.35·Chủ đề + 0.15·Đội ngũ) × (1 − vi_pham)
Arrival: 100 × (0.5·0.78 + 0.35·0.91 + 0.15·0.30) × (1 − 0.04) ≈ 72
```
*(Trọng số 0.5 / 0.35 / 0.15 là điểm xuất phát, sẽ chỉnh bằng bộ câu hỏi đánh giá.)*

---

## G. Output `ask()` — thứ frontend nhận về

| Trường | Là gì | Hiện ở đâu trên UI |
|---|---|---|
| `steps` | Danh sách các bước engine đã làm, viết cho người đọc | Khối "Đang suy luận" |
| `text` | Câu trả lời chính (hỗ trợ `**in đậm**`) | Bong bóng chat của AI |
| `movies` | Danh sách phim gợi ý | Hàng poster |
| `movies[].id` | Mã phim | Để lấy poster, tên, thêm vào My List |
| `movies[].reason` | 1 câu vì sao gợi ý phim này | Dưới mỗi poster |
| `movies[].sim.score` | Điểm phù hợp 0–100 | Badge "88%" |
| `movies[].sim.parts` | Điểm thành phần 0–1: Nội dung / Chủ đề / Đội ngũ | Thanh điểm chi tiết |
| `compare` | Các ID cần dựng bảng so sánh | Bảng so sánh (khi `intent = compare`) |
| `verdict` | Kết luận khi so sánh | Dưới bảng so sánh |
| `chips` | Câu hỏi gợi ý hỏi tiếp | Chip dưới câu trả lời |
| `filters` *(mới)* | Các filter đang áp dụng | Chip "Đang lọc" có ✕ |
| `filters[].label` | Chữ hiện trên chip | `Từ 2015` |
| `filters[].relaxed` | `true` nếu engine đã tự nới filter này vì quá ít phim | Chip hiện khác màu + ghi chú "đã nới" |
| `clarify` *(mới)* | Câu hỏi lại user — chỉ có trong 3 trường hợp đặc biệt | Câu hỏi + các nút chọn |
| `clarify.question` | Nội dung hỏi | "Bạn muốn Dune bản nào?" |
| `clarify.options` | Các lựa chọn | `["Dune (1984)", "Dune (2021)"]` |

---

## H. Chỉ số đánh giá

| Chỉ số | Hiểu nôm na |
|---|---|
| **Recall@100** | Trong các phim "nên có", bao nhiêu % lọt được vào top 100 sau bước ④. Thấp → retrieval đang bỏ sót |
| **nDCG@10** | Top 10 cuối có đúng phim hay **và** xếp phim hay lên đầu không (0–1, càng cao càng tốt) |
| **Tỉ lệ vi phạm filter** | Có phim nào trái filter lọt ra không (vd phim kinh dị khi user nói không) — phải = 0 |
| **Tỉ lệ filter bịa** | LLM có tự thêm filter user không nói không — phải = 0 |
| **p50 / p95 độ trễ** | 50% / 95% câu hỏi trả lời xong trong bao lâu. Mục tiêu p95 < 6 giây |
