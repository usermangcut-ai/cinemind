# CineMind backend

Thiết kế: `../docs/engine-design.md` · thuật ngữ: `../docs/glossary.md` · nhật ký + bằng chứng từng bước: `../docs/steps/` · tiến độ: `../docs/PROGRESS.md`.

## Cài & chạy
```bash
cp .env.example .env                     # điền TMDB_READ_TOKEN, LLM_API_KEY (TYPESAFE_API_KEY nếu có Jev)
docker compose up -d                     # Postgres 16 + pgvector (Docker Desktop phải mở)
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```
Frontend (thư mục gốc): `npm run dev` → http://localhost:5173/chat.

## Nạp dữ liệu (lần đầu)
Nhà mạng VN chặn `api.themoviedb.org` → **bật Cloudflare WARP** (hoặc DNS 1.1.1.1) khi chạy `fetch_tmdb.py` / `trending.py`.
```bash
.venv/Scripts/python etl/fetch_tmdb.py                     # ~15k phim, ~12 phút
.venv/Scripts/python etl/load_db.py                        # nạp DB + điểm IMDb (data/raw/imdb/title.ratings.tsv.gz)
.venv/Scripts/python etl/fetch_tmdb_tv.py && .venv/Scripts/python etl/load_tv.py   # series TV (~12.8k)
.venv/Scripts/python etl/profile.py --kind movie --min-year 1975 --limit 5000   # hồ sơ bằng LLM, ~0.17 cent/phim, chạy lại được
.venv/Scripts/python etl/profile.py --kind tv --limit 3000
.venv/Scripts/python -m etl.embed && .venv/Scripts/python -m etl.embed --tv    # vector gemini-embedding-001
.venv/Scripts/python etl/trending.py                       # Top 10 tuần/tháng
```

## Thư mục
```
app/
  main.py            FastAPI: /api/ask, /api/ask/stream, /api/similar, /api/pair, /api/movies, /api/trending, /api/health
  config.py          đọc .env
  llm.py             gọi LLM (OpenAI-compatible) + xoay model dự phòng khi provider lỗi
  embedder.py        embedding (API hoặc bge-m3 local) + công thức đoạn văn đại diện phim
  engine/
    pipeline.py      ghép 7 bước → output ask()
    parse.py         ① phân tích câu hỏi
    titles.py        ② nhận diện tên phim
    filters.py       ③ filter cứng, chống bịa, nới lọc
    retrieve.py      ④ nhiều nguồn + RRF, ⑤ collection + MMR
    rank.py          ⑥ rerank (Jev / LLM) + ⑦ viết câu trả lời, compare, about, điểm "Đội ngũ"
    similar.py       độ tương đồng 2 phim không dùng LLM (drawer, bảng so sánh)
etl/                 fetch_tmdb · load_db · fetch_tmdb_tv · load_tv · profile · embed · trending
eval/                questions.json (40 câu) · resolve · embed_bakeoff · sweep · parse_eval · engine_eval · bench_llm · model_bakeoff
db/schema.sql        schema (chạy tự động khi tạo container)
data/                (gitignore) dữ liệu thô, cache vector, log, kết quả đánh giá
```

## Model đang dùng (`.env`)
| Biến | Giá trị | Vì sao |
|---|---|---|
| `EMBED_MODEL` | gemini-embedding-001 | thắng bài so sánh (`docs/steps/02-embedding.md`) |
| `LLM_MODEL_PARSE` | gpt-4.1-mini | ① nhanh, rẻ, chính xác gần ngang deepseek |
| `LLM_MODEL_ONLINE` | gpt-4.1-mini | ⑦ viết lý do, so sánh, giới thiệu |
| `LLM_MODEL_OFFLINE` | gpt-4.1-mini | viết hồ sơ phim |
| `RERANK` / `JEV_TOP` | jev / 25 | ⑥ Jev qua provider (`/v1/systemone`), `llm` để tắt |
