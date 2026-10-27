# Bước 0 — Chuẩn bị môi trường

> Trạng thái: ✅ xong (2026-10-26). Lệnh đã chạy + kết quả thật làm bằng chứng.

## 1. Máy
| Thứ | Kết quả |
|---|---|
| Python | 3.12.6, venv `backend/.venv`, thư viện `backend/requirements.txt` (pandas, psycopg, pgvector, python-dotenv, httpx) |
| Docker | 29.5.3 (Docker Desktop phải mở khi dùng DB) |
| RAM / GPU | 16 GB / không GPU → bge-m3 chạy CPU |
| Mạng | **Cloudflare WARP phải bật** khi gọi TMDB API (xem §3) |

## 2. `backend/.env` (gitignore, mẫu: `.env.example`)
| Biến | Giá trị / nguồn |
|---|---|
| `TMDB_READ_TOKEN` | token TMDB (themoviedb.org → Settings → API) |
| `LLM_BASE_URL`, `LLM_API_KEY` | provider `api.shopaikey.com` (OpenAI-compatible, 186 model gồm GPT / Claude / Gemini) |
| `LLM_MODEL_ONLINE`, `LLM_MODEL_OFFLINE` | `gpt-4.1-mini` |
| `TYPESAFE_API_KEY` | ⏸ Jev — lấy khi tới bước rerank |
| `DATABASE_URL` | `postgresql://cinemind:cinemind@localhost:5432/cinemind` |

### Độ trễ LLM qua provider (1 câu tiếng Việt, 2 lần/model)
| Model | Thời gian |
|---|---|
| **gpt-4.1-mini** ← chọn | 2.1s · 2.0s |
| gemini-3.5-flash | 3.4s · 3.0s |
| claude-haiku-4-5 | 4.8s · 3.8s |
| claude-haiku-5-5 | 5.9s · 5.4s |
| claude-sonnet-5-5 | 22.0s · 26.2s |

## 3. Mạng — TMDB bị nhà mạng chặn
```
Resolve-DnsName api.themoviedb.org                → 127.0.0.1      (DNS nhà mạng)
Resolve-DnsName api.themoviedb.org -Server 1.1.1.1 → 13.224.245.47 (IP thật)
```
Cách xử lý đã chọn: **Cloudflare WARP** (app 1.1.1.1, bật/tắt 1 click). Sau khi bật:
```
GET /3/movie/693134?language=vi-VN → "Hành Tinh Cát: Phần Hai" | Dune: Part Two | 2024-02-27 | vote 8834 | 167'
```
Dự phòng: đổi DNS sang `1.1.1.1, 8.8.8.8`.

## 4. Nguồn dữ liệu — đã thử và loại
| Nguồn | Vì sao loại |
|---|---|
| HF `HenryWaltson/TMDB-IMDB-Movies-Dataset` (435k phim) | Phim mới nhất 2023-09-29 |
| Kaggle `asaniczka/tmdb-movies-dataset-2023-930k-movies` (1.5M dòng, "updated daily") | Chỉ thêm ID mới, nội dung đóng băng 09/2023: `Dune: Part Two` vote 0, `Deadpool & Wolverine` vẫn tên "Deadpool 3" |
| IMDb `title.crew` / `title.principals` / `name.basics` (1.1 GB) | Thừa — TMDB credits đã có đạo diễn/cast |

Đã xoá toàn bộ khỏi máy. Chỉ giữ `data/raw/imdb/title.ratings.tsv.gz` (8 MB) cho `imdb_rating`.

## 5. Script kéo dữ liệu — `backend/etl/fetch_tmdb.py`
Chạy thử `--limit 3` (4 phút, phần lớn là quét discover):
```
discover … → 1979-12-31: 1533
discover 1980-01-01 → 1999-12-31: 2665
discover 2000-01-01 → 2009-12-31: 3040
discover 2010-01-01 → 2016-12-31: 3383
discover 2017-01-01 → nay: 4481
phim Việt: 51
tổng: 15151 | đã có: 0 | cần kéo: 3
xong: ghi 3, lỗi/không tồn tại 0 → data/raw/tmdb/movies.jsonl
```
Mẫu 1 bản ghi (Ariel, id 2): director `Aki Kaurismäki` · cast 5 người · keywords `prison, underdog, …` · certification US `NR`.

## 6. Database
`backend/docker-compose.yml` (`pgvector/pgvector:pg16`, volume `pgdata`) + `backend/db/schema.sql`.
```
docker compose up -d   → Container cinemind-db Started
\dx                    → vector 0.8.7 · pg_trgm 1.6 · unaccent 1.1
\dt                    → movies (35 cột) · trending
psycopg connect        → PostgreSQL 16.15
```

## 7. Cấu trúc
```
backend/
  .env / .env.example
  docker-compose.yml
  requirements.txt
  db/schema.sql
  etl/fetch_tmdb.py
  data/raw/imdb/title.ratings.tsv.gz
  data/raw/tmdb/movies.jsonl        ← bước 1 ghi vào đây
```
