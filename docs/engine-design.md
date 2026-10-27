# CineMind — Thiết kế Engine gợi ý phim

> Trạng thái: **đã chốt flow** (2026-10-26) · **đã build & chạy** (2026-10-27, xem `steps/` và `PROGRESS.md`). Tài liệu này là nguồn chuẩn cho phần backend/engine.
> Frontend nối vào qua hàm `ask()` trong `frontend/src/lib/ai.js` (xem §5).

---

## 1. Tổng quan

```
                ┌──────────────────────── OFFLINE (1 lần + đồng bộ hằng ngày) ────────────────────────┐
                │  TMDB API ─► chuẩn hoá ─► LLM viết "hồ sơ phim" ─► gemini-embedding ─► Postgres+pgvector │
                └──────────────────────────────────────────────────────────────────────────────────────┘
                                                        │
 User ─► ① Phân tích ─► ② Nhận diện tên phim ─► ③ Filter cứng ─► ④ Retrieval + RRF ─► ⑤ Đa dạng hoá ─► ⑥ Rerank (Jev) ─► ⑦ Viết câu trả lời ─► ask()
          (LLM)            (pg_trgm)              (SQL)            (top 100)            (40)            (top 10, 0–100)      (LLM)
```

Khung pipeline theo mô hình chuẩn của các hệ gợi ý production
(`hydrate → sources → filter → score → select`, xem `xai-org/x-algorithm`, NVIDIA Merlin "4 tầng"),
cộng thêm 2 bước LLM ở đầu (hiểu ngôn ngữ tự nhiên) và cuối (giải thích).

**Nguyên tắc đã chốt**
1. **Filter là cổng lọc, không cộng điểm.** Chỉ lọc cứng các ý user nói rõ; ý mơ hồ đi vào phần chấm điểm.
2. **LLM không được bịa phim.** Mọi phim trả ra phải có ID trong DB; LLM chỉ chọn trong danh sách ứng viên.
3. **Không chặn user để xác nhận.** Trả kết quả trước, user sửa bằng chip filter; chỉ hỏi lại trong 3 trường hợp (§4.8).
4. **Có đo lường.** Mọi thay đổi trọng số/prompt phải chạy lại bộ câu hỏi đánh giá (§7).

---

## 2. Offline — dữ liệu

### 2.1 Nguồn (chốt 2026-10-26)
| Nguồn | Lấy gì | Ghi chú |
|---|---|---|
| **TMDB API** (chính) | `/discover/movie` lấy danh sách id; `/movie/{id}?append_to_response=credits,keywords,translations,release_dates,alternative_titles` lấy chi tiết: title, **tên + overview tiếng Việt**, genres, keywords, runtime, quốc gia, đạo diễn/biên kịch/cast/nhạc/quay phim, collection, độ tuổi, poster, vote, popularity | Nhà mạng chặn DNS `api.themoviedb.org` → máy chạy job **phải bật Cloudflare WARP** (hoặc DNS `1.1.1.1`). Thương mại cần thoả thuận với TMDB → báo khách |
| IMDb `title.ratings.tsv.gz` | `imdb_rating`, `imdb_votes` theo `imdb_id` | Tải hằng ngày, 8 MB, phi thương mại |
| `image.tmdb.org` | poster theo `poster_path` | Không bị chặn |

Đã thử và **loại**: dump Kaggle `asaniczka/…` và HF `HenryWaltson/…` — nội dung đóng băng ở 09/2023 (xem `steps/00-setup.md`).

Phạm vi: phim `vote_count ≥ 200` (**~15.1k phim**, discover chia 5 giai đoạn vì giới hạn 500 trang/truy vấn) + phim Việt `vote_count ≥ 10` (51 phim).

### 2.2 Làm giàu bằng LLM — "hồ sơ phim"
Mỗi phim, LLM (`gpt-4.1-mini` qua provider OpenAI-compatible, cấu hình `LLM_MODEL_OFFLINE`) viết 1 đoạn ~80–120 từ
mô tả những thứ overview không có: tâm trạng, nhịp phim, chủ đề sâu, tông, kiểu kết, hợp với ai.

```
Input : title, year, genres, keywords, overview, tagline, director, cast
Output: "Sci-fi trầm, chậm, giàu cảm xúc. Trọng tâm là tình mẫu tử và thời gian phi tuyến.
         Ít hành động, nhiều suy ngẫm. Hợp người thích khoa học nghiêm túc + kết thúc gây ám ảnh."
```
Chạy 1 lần/phim (song song nhiều request), chỉ chạy lại khi dữ liệu nguồn đổi.

### 2.3 Embedding
**`gemini-embedding-001`** (3072 chiều, qua provider) — thắng bge-m3 và text-embedding-3-large trong bài so sánh (`steps/02-embedding.md`).
Đoạn văn embed cho mỗi phim: tên + tên Việt + thể loại + hồ sơ + tóm tắt + từ khoá + đạo diễn (`app/embedder.py::movie_text`).
Không dùng sparse vector; nguồn keyword ở ④ dùng full-text Postgres (cột `fts`).

### 2.4 Schema (Postgres 16 + pgvector 0.8.7, pg_trgm, unaccent)
File chuẩn: `backend/db/schema.sql` (chạy tự động khi container khởi tạo lần đầu). Các cột chính:

| Cột | Nguồn |
|---|---|
| `id`, `imdb_id`, `title`, `original_title`, `title_vi`, `overview_vi`, `alt_titles`, `release_date`/`year`, `runtime`, `original_language`, `genres`, `countries` (ISO), `keywords`, `director[]`, `writers[]`, `cast_top[]`, `crew_key[]`, `collection_id`/`collection`, `certification`, `tagline`, `overview`, `vote_average`, `vote_count`, `popularity`, `poster_path`, `backdrop_path` | TMDB API |
| `imdb_rating`, `imdb_votes` | IMDb ratings |
| `profile` | LLM |
| `dense halfvec(3072)` | gemini-embedding-001 |
| `fts tsvector` | full-text (tên, hồ sơ, từ khoá, tóm tắt) cho nguồn keyword |

Index: HNSW trên `dense`, GIN trên `genres`/`countries`, trigram trên `lower(title)`/`lower(title_vi)`.
Bảng `trending(period, rank, movie_id)` cho cột Top 10.
Khi query vector kèm WHERE: bật `SET hnsw.iterative_scan = relaxed_order` để không bị hụt kết quả.

### 2.5 Đồng bộ
Job định kỳ (bật WARP): discover phim mới / đổi dữ liệu → làm giàu + embed lại; IMDb ratings tải lại;
trending tuần/tháng từ `/trending/movie/{week|day}` cho cột Top 10.

---

## 3. Online — 7 bước (tóm tắt)

| # | Bước | Input | Output | Công cụ |
|---|---|---|---|---|
| ① | Phân tích câu hỏi | text user + filter đang giữ | JSON `{intent, filters[], soft, movie_refs}` đã validate | gpt-4.1-mini + JSON schema |
| ② | Nhận diện tên phim | `movie_refs` | `movie_id` + độ tin cậy | pg_trgm |
| ③ | Filter cứng | `filters` | tập phim hợp lệ (WHERE) | SQL |
| ④ | Retrieval + RRF | soft, refs, tập hợp lệ | top 100 | pgvector + RRF |
| ⑤ | Đa dạng hoá | top 100 | 40 | gộp collection + MMR |
| ⑥ | Rerank | 40 phim đầu RRF (bỏ MMR, steps/08) + câu hỏi | top 10 + điểm 0–100 | **Jev qua provider** (`/v1/systemone`); dự phòng: LLM gộp với ⑦ |
| ⑦ | Viết câu trả lời | top 10 + điểm + profile | shape `ask()` | gpt-4.1-mini |

Bỏ qua ① khi input đến từ nút UI (`similar` / `compare` / `about`) vì đã có ID.

---

## 4. Online — chi tiết từng bước

Ví dụ xuyên suốt: **"Tìm phim kiểu Hố đen tử thần, từ 2015 trở lại đây, đừng dài quá, không kinh dị"**

### 4.1 ① Phân tích câu hỏi
LLM trả JSON theo schema cố định:
```json
{
  "intent": "similar",                       // search | similar | compare | about | chitchat
  "movie_refs": ["Hố đen tử thần"],
  "filters": [
    { "field": "year_min",       "value": 2015,      "evidence": "từ 2015 trở lại đây" },
    { "field": "exclude_genres", "value": ["Horror"], "evidence": "không kinh dị" }
  ],
  "soft": { "text": "không khí giống phim tham chiếu", "prefer_runtime": "short" }
}
```
**Chống bịa filter (4 lớp, đều bằng code):**
1. **Schema + enum** — `genres` ∈ 19 thể loại TMDB, `countries` ∈ mã ISO 3166-1; field ngoài danh sách bị từ chối.
2. **Evidence** — mỗi filter phải kèm đoạn trích nguyên văn; code kiểm tra `evidence` có trong câu user (so sánh sau khi bỏ dấu, lowercase). Không có → bỏ filter.
3. **Validate giá trị** — năm ∈ [1900, năm hiện tại], `year_min ≤ year_max`, runtime ∈ [30, 300]…
4. **Chip + nới lọc** — user thấy và gỡ được (§4.8).

**Field filter cho phép:** `year_min`, `year_max`, `runtime_max`, `runtime_min`, `genres` (gồm), `exclude_genres`, `countries`, `exclude_countries`, `certification_max`, `person` (đạo diễn/diễn viên).

**Quy tắc cứng/mềm:** chỉ là filter khi user nói rõ giá trị ("từ 2015", "dưới 2 tiếng", "phim Hàn").
Ý mơ hồ ("cũ cũ", "đừng dài quá", "nhẹ nhàng") → `soft`.

Filter được **giữ theo cuộc hội thoại**: câu sau ("thế còn phim Hàn?") kế thừa filter cũ + thêm mới. LLM nhận filter hiện tại trong input để biết thêm/bỏ.

### 4.2 ② Nhận diện tên phim
```
"Hố đen tử thần" → pg_trgm trên title / title_vi / alt_titles → { id: 157336, "Interstellar", conf: 0.98 }
```
- `conf < 0.6` hoặc ≥ 2 ứng viên sát nhau (vd "Dune" 1984/2021) → hỏi lại (§4.8).
- Phim tham chiếu bị loại khỏi kết quả.

### 4.3 ③ Filter cứng
```sql
WHERE year >= 2015 AND NOT (genres && ARRAY['Horror'])
  AND vote_count >= 500 AND id <> 157336
```
**Nới lọc:** nếu còn < 5 phim → bỏ dần filter theo thứ tự ưu tiên thấp → cao
(`genres` → `runtime` → `year` → `countries`), ghi lại để báo user:
*"Không có phim Hàn nào dưới 90 phút khớp, mình mở rộng lên 110 phút."*
Còn 0 phim sau khi nới hết → hỏi lại (§4.8).

### 4.4 ④ Retrieval + RRF
Các nguồn ứng viên, mỗi nguồn lấy top 200 trong tập đã lọc:

| Nguồn | Truy vấn | Khi nào | Trọng số (chỉnh bằng `eval/sweep.py`) |
|---|---|---|---|
| Dense câu hỏi | embed(câu gốc) vs `dense` — embed song song với ① | luôn | 1.0 |
| Keyword | full-text (`fts`) với từ của câu gốc + `soft.text` | luôn | **0** (tắt — kho 3.789 phim làm giảm nDCG, xem steps/03) |
| Dense phim tham chiếu | `dense` của phim ref | có `movie_refs` | **2.0** |
| Đội ngũ | trùng director/writers/cast_top/crew_key với phim ref | có `movie_refs` | 0.5 |

**Gộp bằng RRF có trọng số** (chỉ dùng thứ hạng, không cần chuẩn hoá thang điểm):
```
RRF(phim) = Σ  w_i / (60 + hạng_i(phim))        // phim không có trong nguồn i → 0
```
Cộng thêm nhẹ: `+ 0.002 · chuẩn hoá(imdb_rating, vote_count)` để tránh phim quá vô danh;
`soft.prefer_runtime` cộng/trừ nhẹ tương tự. Lấy **top 100**.

> RRF không cần xếp đúng thứ tự — chỉ cần đưa đủ phim tốt vào top 100. Điểm hiển thị do ⑥ quyết định.

### 4.5 ⑤ Đa dạng hoá
1. Gộp theo `collection_id`: mỗi collection giữ 1 phim điểm cao nhất.
2. MMR (λ = 0.7) trên `dense` → chọn **40** phim (30 → mất thêm 6% phim đúng, xem `steps/03-engine-core.md`).

### 4.6 ⑥ Rerank — Jev
Mỗi phim 1 request, chạy song song (~40 request):
```json
{
  "model": "jev-latest",
  "state": { "query": "<câu hỏi>", "ref": "Interstellar: <profile>", "movie": "Arrival: <profile + metadata>" },
  "questions": {
    "noi_dung": { "type": "score", "instructions": "Cốt truyện/ý tưởng khớp yêu cầu tới đâu?", "criteria": ["Không liên quan", "…", "Rất khớp"] },
    "chu_de":   { "type": "score", "instructions": "Chủ đề, không khí khớp tới đâu?",          "criteria": ["…"] },
    "doi_ngu":  { "type": "score", "instructions": "Đạo diễn/diễn viên/phong cách làm phim khớp tới đâu?", "criteria": ["…"] },
    "vi_pham":  { "type": "noul",  "instructions": "Phim có điểm nào trái với điều user không muốn?" }
  }
}
```
Điểm cuối:
```
parts = { 'Nội dung': noi_dung/10, 'Chủ đề': chu_de/10, 'Đội ngũ': doi_ngu/10 }
score = round(100 · (0.5·Nội dung + 0.35·Chủ đề + 0.15·Đội ngũ) · (1 − vi_pham))
```
Lấy **top 10**. Trọng số chỉnh bằng bộ đánh giá (§7).

Thực tế dùng 4 mức (0–3) thay vì 0–10, chia cho 3 để ra 0–1.

**Dự phòng (đang chạy vì chưa có key Jev):** `gpt-5.4-mini` chấm 3 tiêu chí + vi phạm cho cả 40 phim **và viết luôn text/reason/chips trong cùng 1 lần gọi** (gộp ⑥+⑦, đỡ 1 lượt ~3–5 s).

### 4.7 ⑦ Viết câu trả lời
Khi có Jev: LLM nhận top 10 đã chấm → viết `text` + `reason` + `chips`. Khi chưa có: gộp với ⑥ (trên).
`chips` là câu **user bấm để hỏi tiếp** ("Phim giống Arrival", "Chỉ phim dưới 2 tiếng"), không phải câu hỏi ngược lại user.
Ràng buộc: chỉ được nhắc phim có trong danh sách; code kiểm tra mọi `id` trả về ∈ top 10.

### 4.8 Human-in-the-loop
**Mặc định không chặn**: trả kết quả ngay, filter hiển thị thành **chip** trên đầu câu trả lời:
```
Đang lọc:  ( Từ 2015 ✕ )  ( Không kinh dị ✕ )
```
- ✕ → frontend gửi `{type: 'refilter', query, filters}` → chạy lại từ ③ (không gọi lại ①).
- Filter giữ qua các lượt chat; user thêm điều kiện bằng cách gõ tiếp ("thế còn phim Hàn?"). Nút "+ Thêm" **chưa làm** (gõ tự nhiên đã đủ).

**Chỉ hỏi lại trước khi chạy** trong 3 trường hợp (phát hiện bằng code):

| Trường hợp | Điều kiện | Hỏi |
|---|---|---|
| Tên phim mơ hồ | conf < 0.6 hoặc ≥ 2 ứng viên sát nhau | `[Dune (1984)] [Dune (2021)]` |
| Không còn phim | 0 phim sau khi nới hết | "Bỏ 'trước 1990' nhé?" `[Bỏ] [Đổi câu khác]` |
| Filter mâu thuẫn | rule: `year_min > year_max`, genres ∩ exclude_genres ≠ ∅, … | hỏi giữ filter nào |

---

## 5. Hợp đồng `ask()` (frontend ↔ engine)

Giữ shape cũ, **thêm `filters` và `clarify`**:
```js
// input
{ text, filters? }                                // filters = chip hiện tại của cuộc chat
| { type: 'similar', ids: [id], filters? } | { type: 'compare', ids } | { type: 'about', id }
| { type: 'refilter', query, filters }            // gỡ chip / chọn ở clarify → chạy lại từ ③

// output
{
  steps: string[],                                 // hiện trong khối "Đang suy luận"
  text: string,                                    // hỗ trợ **in đậm**
  movies?: [{ id, reason, sim?: { score: 0–100, parts: { 'Nội dung', 'Chủ đề', 'Đội ngũ': 0–1 } } }],
  compare?: number[],
  verdict?: string,
  chips?: string[],                                // câu hỏi gợi ý tiếp
  filters?: [{ field, value, label, evidence, relaxed?: boolean }],   // MỚI — chip "Đang lọc"
  clarify?: { question, options: string[], inputs: object[] },        // MỚI — inputs[i] = input gửi lại khi bấm options[i]
  query?: { text, soft, ref_ids },                                     // MỚI — để gửi lại khi refilter
  catalog: { [id]: movie }                                             // dữ liệu phim để frontend hiển thị (poster, tên…)
}
```
Ví dụ output đầy đủ:
```json
{
  "steps": ["Nhận diện: Hố đen tử thần → Interstellar", "Lọc: từ 2015, bỏ kinh dị (4.200 phim)", "Tìm 100 phim gần nhất", "Chấm lại 40 phim"],
  "text": "Đây là những phim có **không khí sci-fi trầm, giàu cảm xúc** như Interstellar:",
  "movies": [
    { "id": 329865, "reason": "Cùng chủ đề thời gian và tình cảm gia đình, nhịp chậm, kết ám ảnh.",
      "sim": { "score": 72, "parts": { "Nội dung": 0.78, "Chủ đề": 0.91, "Đội ngũ": 0.30 } } }
  ],
  "filters": [
    { "field": "year_min", "value": 2015, "label": "Từ 2015", "evidence": "từ 2015 trở lại đây" },
    { "field": "exclude_genres", "value": ["Horror"], "label": "Không kinh dị", "evidence": "không kinh dị" }
  ],
  "chips": ["Có phim nào của Nolan không?", "So sánh Arrival và Ad Astra"]
}
```

---

## 6. Tech stack (đã dùng thật)

| Tầng | Chọn | Ghi chú |
|---|---|---|
| Nguồn dữ liệu | TMDB API (qua Cloudflare WARP) + IMDb `title.ratings` | nhà mạng chặn DNS TMDB |
| Backend | Python 3.12 + FastAPI (`app/main.py`) | |
| DB + vector | Postgres 16 + pgvector 0.8.7 (Docker) | `halfvec(3072)` + HNSW |
| Keyword | Postgres full-text (`fts`, bỏ dấu bằng `f_unaccent`) | |
| Tìm tên mờ | pg_trgm | |
| Embedding | gemini-embedding-001 (provider) | bge-m3 bị loại (chậm + kém) |
| LLM ① | gpt-4.1-mini | deepseek-v4-flash chính xác hơn chút nhưng chậm ×2–3, đắt ×15 (model reasoning); gpt-5.4-mini hay sót filter |
| LLM ⑦ (viết lý do), compare, about | gpt-4.1-mini | gpt-5.4-mini bị provider báo khan nguồn |
| LLM offline (hồ sơ phim) | gpt-4.1-mini (+ dự phòng gpt-5.4-mini, gemini-3.5-flash) | |
| Rerank ⑥ | **Jev qua provider** (`{LLM_BASE_URL}/systemone`, cùng key) — 25 phim ~2 s, ~0,7 cent | `TYPESAFE_API_KEY` nếu dùng TypeSafe gốc · `RERANK=llm` để tắt |
| Provider | `api.shopaikey.com` (OpenAI-compatible) | hay lỗi 429/503 → `app/llm.py` xoay model dự phòng |
| Cache / job | chưa làm (chạy tay `etl/*.py`) | |

Giai đoạn 2: Gorse / LightFM làm thêm 1 nguồn ứng viên ở ④, cá nhân hoá theo My List.

---

## 7. Đánh giá

- **Bộ câu hỏi vàng:** 40 câu (`backend/eval/questions.json`) + 9 câu bẫy cho bước ① (`eval/parse_eval.py`).
- **Chỉ số:**
  - Recall@100 sau ④ (phim "nên có" có lọt top 100 không)
  - nDCG@10 sau ⑥
  - Tỉ lệ vi phạm filter (phim "không được có" xuất hiện) — mục tiêu 0
  - Tỉ lệ filter bịa (filter không có trong câu user) — mục tiêu 0
  - Độ trễ p50 / p95 — mục tiêu p95 < 6 s
- Script: `eval/embed_bakeoff.py` (model embedding) · `eval/sweep.py` (trọng số RRF, ⑤) · `eval/parse_eval.py` (①) · `eval/engine_eval.py --core | --full` (toàn engine). Kết quả: `steps/02`–`06`.

---

## 7b. Bổ sung sau khi build (27/10)

**Series TV.** 12.805 series (TMDB `vote_count ≥ 20`) nằm chung bảng `movies` với `kind = 'tv'`, `id = −tmdb_tv_id`.
- Series nào cũng có vector (embed từ tóm tắt + từ khoá) → **nhận diện được tên** để làm phim tham chiếu ("giống Breaking Bad", "giống Trò chơi con mực").
- 3.531 series nhiều vote nhất có hồ sơ → **được gợi ý** như phim lẻ, UI gắn nhãn "Series", thời lượng ghi "/tập".
- Filter mới `kind` (`movie` | `tv`): chỉ khi user nói rõ "phim lẻ" / "phim bộ, series".

**Chỉ gợi ý phim đã có hồ sơ.** ③ luôn có `profile IS NOT NULL`. Phim/series chưa có hồ sơ vẫn nhận diện được tên (vector tính từ tóm tắt; nếu thiếu vector thì tính tại chỗ).

**Không tìm thấy phim tham chiếu.** Bước "Không tìm thấy \"X\"". Câu chỉ có tên phim → `clarify` hỏi user tả phim; câu có mô tả thêm → vẫn gợi ý theo mô tả nhưng LLM bị buộc nói rõ "chưa có X trong kho".

**Chống bịa filter — thêm 2 lớp bằng code** (`filters.validate`): thể loại chỉ giữ khi trích dẫn chứa đúng từ khoá thể loại (`GENRE_WORDS`: "tâm lý", "zombie" không còn thành Chính kịch / Kinh dị); `kind` chỉ giữ khi có "phim bộ / series / phim lẻ…".

**Điểm "Đội ngũ" tính bằng code** (`rank.crew_score`: trùng đạo diễn 0.6, biên kịch 0.25, diễn viên 0.15/người, nhạc/quay phim 0.1, cùng series 0.3), chỉ có khi có phim tham chiếu.
Điểm hiển thị: có phim tham chiếu `0.5·Nội dung + 0.4·Chủ đề + 0.1·Đội ngũ`, không có `0.55·Nội dung + 0.45·Chủ đề`; chỉ trừ điểm vi phạm khi Jev ≥ 0.6.

**Độ tương đồng giữa 2 phim (không LLM)** — `engine/similar.py`, dùng cho drawer "Phim tương tự", bảng so sánh, Landing:
Nội dung = cosine vector quy về 0–1 (0.6 → 0, 0.85 → 1) · Chủ đề = trùng thể loại + từ khoá · Đội ngũ = `crew_score` · điểm = 0.7 / 0.2 / 0.1.

**API**
| Endpoint | Dùng cho |
|---|---|
| `POST /api/ask` | trả lời 1 lần (hợp đồng §5 + `catalog`) |
| `POST /api/ask/stream` | NDJSON: `steps` (mỗi bước) → `preview` (10 phim + điểm, chưa có lý do) → `final` |
| `GET /api/similar?id=&n=` | phim tương tự (drawer) |
| `GET /api/pair?a=&b=` | điểm 2 phim (Landing) |
| `GET /api/movies?ids=` | dữ liệu phim (My List, lịch sử chat) |
| `GET /api/trending` · `GET /api/health` | Top 10 · tình trạng kho |

`catalog` mỗi phim có thêm `kind`, `backdrop`, `profile` (danh sách `[mục, nội dung]` của hồ sơ).

## 8. Việc còn mở → xem `PROGRESS.md`
