# Bước 2 — Chọn model embedding

> Trạng thái: ✅ chốt **`gemini-embedding-001`** (3072 chiều, qua provider). Vector đã nạp vào `movies.dense` (halfvec, HNSW).
> Script: `backend/eval/embed_bakeoff.py` (so sánh) · `backend/etl/embed.py` (nạp DB).

## 1. Cách so sánh
- **Kho phim**: 1.537 phim đã có hồ sơ. Mỗi phim ghép thành 1 đoạn văn giống nhau cho mọi model (`app/embedder.py::movie_text`):
  tên + tên Việt + thể loại + hồ sơ + tóm tắt + từ khoá + đạo diễn.
- **Câu hỏi**: 40 câu trong `backend/eval/questions.json` (20 tâm trạng/chủ đề · 8 giống phim X · 8 có filter · 4 tên tiếng Việt),
  mỗi câu 4–8 phim đáp án (256 phim, ánh xạ sang TMDB id bằng `eval/resolve.py`).
- **Chỉ dense retrieval** (không RRF/rerank). Câu có filter → áp filter trước. Câu "giống X" đo 2 kiểu:
  *text* (embed nguyên câu hỏi) và *vector phim gốc* (lấy vector của X — cách engine thật làm).
- **Chỉ số**: Recall@100 (phim đúng có lọt top 100 — việc chính của embedding), Recall@10, nDCG@10.

## 2. Kết quả
| Model | Recall@100 | Recall@10 | nDCG@10 | tâm trạng R@100 | giống phim (text) | giống phim (vector phim gốc) | có filter | tên Việt (text) | ms/câu hỏi |
|---|---|---|---|---|---|---|---|---|---|
| **gemini-embedding-001** | **0.904** | **0.491** | **0.479** | **0.944** | **0.899** | **0.988** | **0.927** | **0.667** | 91 |
| text-embedding-3-large | 0.836 | 0.390 | 0.400 | 0.888 | 0.826 | 0.903 | 0.844 | 0.583 | 86 |
| bge-m3 (local CPU) | 0.665 | 0.300 | 0.313 | 0.819 | 0.226 | 0.781 | 0.844 | 0.417 | 122 |

- Gemini thắng **mọi cột**. Cách engine thật tìm "phim giống X" (vector phim gốc) đạt 0.988.
- bge-m3 yếu nhất và **embed 1.537 phim mất 42 phút trên CPU** (API: vài giây) → loại.
- Chi phí embed gemini cho 1.537 phim: không đáng kể (< 1 cent theo `total_usage`).

## 3. Nhìn tận mắt — top 10 của 3 model (✓ = có trong đáp án)

**"phim nhẹ nhàng chữa lành, xem cuối tuần cho thư giãn"**

| # | gemini-embedding-001 | text-embedding-3-large | bge-m3 |
|---|---|---|---|
| 1 | ✓ Perfect Days (2023) | Freaky Friday (2003) | ✓ Perfect Days (2023) |
| 2 | Collateral Beauty (2016) | Silver Linings Playbook (2012) | A Cure for Wellness (2017) |
| 3 | Wonder (2017) | Collateral Beauty (2016) | Ponyo (2008) |
| 4 | ✓ Amélie (2001) | The Unseen River (2020) | Collateral Beauty (2016) |
| 5 | The Perks of Being a Wallflower (2012) | Nostalgia for the Countryside (1997) | The Darjeeling Limited (2007) |
| 6 | Owl and the Sparrow (2008) | 50/50 (2011) | Love & Other Drugs (2010) |
| 7 | Kiki's Delivery Service (1989) | ✓ Amélie (2001) | Bad Moms (2016) |
| 8 | My Neighbor Totoro (1988) | Owl and the Sparrow (2008) | Freaky Friday (2003) |

**"phim giống Ký sinh trùng"** (tên Việt của Parasite, embed nguyên câu — chưa qua bước nhận diện tên)

| # | gemini-embedding-001 | text-embedding-3-large | bge-m3 |
|---|---|---|---|
| 1 | Triangle of Sadness (2022) | Contagion (2011) | Contagion (2011) |
| 2 | The Host (2013) | The Fly (1986) | 28 Days Later (2002) |
| 3 | Shoplifters (2018) | District 9 (2009) | Resident Evil (2002) |
| 4 | The Platform (2019) | Children of Men (2006) | 28 Weeks Later (2007) |
| 5 | Enemy (2014) | Cube (1998) | Cloverfield (2008) |
| 6 | Okja (2017) | The Host (2013) | Life (2017) |
| 8 | ✓ Burning (2018) | The Island (2005) | Monsters, Inc. (2001) |

→ Gemini hiểu "Ký sinh trùng" là **phim Parasite** (ra phim châm biếm giai cấp, phim Hàn), hai model kia hiểu theo nghĩa đen "ký sinh trùng/virus".
Trong engine thật, bước ② còn nhận diện tên trước nên kết quả còn tốt hơn.

Bảng đầy đủ 5 câu: `backend/data/bakeoff.md` · số liệu từng câu: `backend/data/emb/bakeoff.json`.

## 4. Hạn chế
- Đáp án do Claude chọn → chủ quan; nhiều phim "không có trong đáp án" vẫn hợp lý (Shoplifters, Okja cho câu Parasite).
- Kho phim chỉ 1.537 phim và **đã ép chứa mọi phim đáp án** → recall tuyệt đối cao hơn thực tế; dùng để **so sánh giữa các model**, không phải con số cuối.
- Gemini qua endpoint OpenAI-compatible không chọn được `task_type` (query/document); nếu đổi sang API Gemini gốc có thể tốt hơn nữa.

## 5. Đã áp dụng
```
.env: EMBED_MODEL=gemini-embedding-001
$ python -m etl.embed
đổi cột dense: vector(1024) → halfvec(3072)
cần embed: 1537 phim (1537 có sẵn trong cache)
xong: 1537 phim có vector (gemini-embedding-001, 3072 chiều)      (12 giây — dùng lại cache của bài so sánh)
```
Cột `fts` (full-text, dùng cho nguồn keyword ở ④) cũng được tính trong bước này.
