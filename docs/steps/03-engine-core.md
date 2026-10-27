# Bước 3 — Engine lõi ③ filter · ④ retrieval + RRF · ⑤ đa dạng hoá

> Trạng thái: ✅ chạy được, đã chỉnh tham số bằng bộ đánh giá.
> Code: `backend/app/engine/filters.py`, `retrieve.py`, `titles.py` · Đánh giá: `eval/engine_eval.py --core`, `eval/sweep.py`.

## 1. Đã làm
| Bước | Cách làm |
|---|---|
| ③ Filter | `filters.to_sql()` sinh WHERE. `genres` = **có ít nhất 1** thể loại (`&&`), `exclude_*` = không được có. Còn < 5 phim → nới theo thứ tự `genres → runtime → year → certification → countries` (điều kiện "không …" không bao giờ tự nới). Không còn phim nào → trả `clarify` |
| ② Tên phim | `titles.resolve()`: pg_trgm trên `title`, `title_vi`, `original_title`, `alt_titles` (bỏ dấu bằng `f_unaccent`), hiểu cả năm đi kèm ("Dune 2021", "Dune (1984)") |
| ④ Nguồn | `dense_query` (vector câu hỏi) · `keyword` (Postgres full-text trên tên + hồ sơ + từ khoá) · `dense_ref` (vector phim tham chiếu) · `crew` (trùng đạo diễn/biên kịch/diễn viên/nhạc/quay phim). Mỗi nguồn top 200 |
| ④ Gộp | RRF có trọng số `Σ w / (60 + hạng)` + cộng nhẹ theo điểm IMDb và ưu tiên thời lượng mơ hồ → top 100 |
| ⑤ | Mỗi collection giữ 1 phim → MMR (λ = 0.7) → **40 phim** đưa vào rerank |

### Nhận diện tên phim — kết quả thật
```
Hố đen tử thần     → Interstellar (2014) conf 1.0
Ký sinh trùng      → Parasite (2019)
intersteller       → Interstellar (2014) conf 0.62      (gõ sai vẫn ra)
Kẻ trộm giấc mơ    → Inception (2010)
Chuyến tàu sinh tử → Train to Busan (2016)
Vùng đất câm lặng  → A Quiet Place (2018)
Hai Phượng         → Furie (2019)
Dune               → Dune (2021)          (bản 1984 ít vote hơn nhiều → không hỏi lại)
Dune (1984)        → Dune (1984)
Lật mặt            → ambiguous: Face/Off (1997) | Paycheck (2003)   → trả clarify
```

## 2. Chỉnh trọng số RRF (`eval/sweep.py`, không gọi LLM)
| trọng số (query, keyword, ref, crew) | R@100 | nDCG@10 |
|---|---|---|
| (1, 0, 0, 0) — chỉ dense câu hỏi | 0.904 | 0.479 |
| (1, 0.7, 1, 0.5) — thiết kế ban đầu | 0.946 | 0.490 |
| (1, 0.3, 1, 0.3) | 0.957 | 0.525 |
| (1, 0.2, 2, 0.2) | 0.957 | 0.540 |
| **(1, 0.3, 2, 0.5)** ← chọn | **0.961** | **0.542** |

→ Vector của **phim tham chiếu** quan trọng nhất (×2); keyword giúp ít (×0.3) vì dense của gemini đã bắt được từ khoá.

| ⑤ giữ n phim | λ MMR | phim đáp án còn lại sau ⑤ |
|---|---|---|
| 30 | 0.7 | 0.777 |
| **40** | **0.7** | **0.834** |
| 50 | 0.85 | 0.843 |

→ λ gần như không ảnh hưởng; số phim giữ lại mới quan trọng. Chọn 40 (50 chỉ hơn 1% mà prompt rerank dài thêm 25%).

## 3. Kết quả sau khi chỉnh (`eval/engine_eval.py --core`)
| Nhóm | n | dense-only R@100 | RRF R@100 | sau ⑤ (40 phim vào rerank) | dense nDCG@10 | RRF nDCG@10 |
|---|---|---|---|---|---|---|
| tâm trạng | 20 | 0.944 | 0.952 | 0.803 | 0.516 | 0.540 |
| giống phim | 8 | 0.982 | 1.000 | 0.926 | 0.624 | 0.643 |
| có filter | 8 | 0.927 | 0.927 | 0.844 | 0.516 | 0.531 |
| tên Việt | 4 | 1.000 | 1.000 | 0.958 | 0.694 | 0.640 |
| **tất cả** | 40 | 0.954 | **0.961** | **0.851** | 0.556 | **0.569** |

*"dense-only" ở đây đã dùng vector phim tham chiếu cho câu "giống X" (khác bảng ở bước 2).*

## 4. Kho lớn hơn (3.789 phim) — đo lại & chỉnh lại
Kho lớn gấp 2,5 → nhiều phim "gây nhiễu" hơn, điểm giảm (con số này **sát thực tế hơn** kho 1.537):

| trọng số (query, keyword, ref, crew) | R@100 | nDCG@10 |
|---|---|---|
| (1, 0, 0, 0) — chỉ dense câu hỏi | 0.816 | 0.346 |
| (1, 0.3, 2, 0.5) — đang dùng | 0.870 | 0.386 |
| (1, 0.3, 2, 1) | 0.866 | 0.400 |
| **(1, 0, 2, 0.5)** ← chọn lại: **tắt keyword** | **0.885** | **0.409** |

→ Trên kho lớn, nguồn keyword (full-text) **kéo điểm xuống**; tắt đi (code bỏ qua luôn truy vấn khi trọng số = 0).

| ⑤ giữ n phim | λ | phim đáp án còn lại |
|---|---|---|
| **40** | 0.7 | 0.704 |
| 50 | 0.7 | 0.734 |
| 60 | 0.9 | 0.763 |
Giữ 40 vì 60 phim làm prompt rerank dài thêm 50% (độ trễ đã là vấn đề). Khi có Jev (chấm song song) nên nâng lên 60.

Kết quả sau khi chỉnh (`engine_eval --core`, kho 3.789):
| Nhóm | n | dense-only R@100 | RRF R@100 | sau ⑤ | dense nDCG@10 | RRF nDCG@10 |
|---|---|---|---|---|---|---|
| tâm trạng | 20 | 0.830 | 0.855 | 0.668 | 0.335 | 0.408 |
| giống phim | 8 | 0.964 | 0.946 | 0.818 | 0.528 | 0.541 |
| có filter | 8 | 0.906 | 0.927 | 0.693 | 0.423 | 0.476 |
| tên Việt | 4 | 1.000 | 1.000 | 0.917 | 0.605 | 0.494 |
| **tất cả** | 40 | 0.889 | **0.902** | 0.728 | 0.418 | **0.457** |

## 5. Hạn chế
- Engine chỉ gợi ý trong 3.789 phim đã có hồ sơ + vector (11.4k phim còn lại có dữ liệu nhưng chưa có).
- Bước ⑤ là nơi mất phim đúng nhiều nhất (0.902 → 0.728 trên kho 3.789). Nếu rerank nhanh hơn (Jev) nên nâng lên 60 phim.
