# Bước 10 — Thử sửa "giống X nhưng …" (27/10) → chỉ giữ 1 thay đổi nhỏ, CHỐT bản AI

## 1. Đã thử
| Bước | Thay đổi thử | Giữ? |
|---|---|---|
| ① parse | thêm trường `ref_diff` = đoạn trích nguyên văn phần user muốn KHÁC phim tham chiếu (kiểm tra là chuỗi con của câu) | **bỏ** |
| ④ RRF | có `ref_diff` → trọng số vector phim tham chiếu ×2 → ×1 | **bỏ** |
| ⑥ Jev `sai_yeu_cau` | thay "chỉ muốn giống phim khác → false" bằng: điểm user muốn KHÁC phim tham chiếu cũng là điều kiện bắt buộc | **giữ** |

Thử đếm từ còn lại sau khi bỏ tên phim để nhận biết "có yêu cầu thêm" → sai nhiều ("thích Parasite thì nên xem gì tiếp" = có; "giống Dune nhưng ngắn hơn" = không) → bỏ ngay, chuyển sang `ref_diff`.
`ref_diff` tách đúng 10/11 câu có "nhưng" (sai: "pha trộn giữa Harry Potter và Lord of the Rings").

## 2. Kết quả (30 câu: 19 "giống X" + 5 "pha trộn" từ eval100 + 6 câu "nhưng" mới, `eval/questions_ref.json`)
| Nhóm | n | Rất hợp trước → sau | Code mới có tác động? |
|---|---|---|---|
| giống phim X | 19 | 51% → 58% | không (`ref_diff` = null) → **mức dao động ±5–10%** |
| pha trộn nhiều phim | 5 | 48% → 57% | 3/5 câu |
| giống X nhưng (mới) | 6 | 47% → 42% | có |
| **Tổng** | 30 | 49% → 55% | |

Jev loại rất mạnh (Dune 27/40, Parasite + Shoplifters 31/40, John Wick 10/40) nhưng điểm không lên → trong 40 ứng viên **không có đủ phim đúng**.
Gốc: vector câu "giống X nhưng …" vẫn mang nghĩa X; hạ trọng số X không đủ. Sửa tận gốc cần thêm lượt tìm vector riêng cho phần "nhưng"
(chậm + tốn, vẫn không bắt hết mọi kiểu) → user chốt **dừng**.

## 3. Chốt bản AI
Flow như `CLAUDE.md` §4 + plan 09. Chất lượng (eval100, steps/09): **98% hợp · 78% rất hợp**. Còn yếu đã biết: "giống X nhưng…", pha trộn nhiều phim.
Chi phí đợt này ~0,95 USD (key Medium 4,35 / 10 · key cũ 60,37 / 70).
