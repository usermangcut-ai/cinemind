# Bước 09 — Jev loại phim sai yêu cầu cứng (27/10)

## 1. Vấn đề (ca thật từ UI)
"T muốn tìm phim với nam nhân vật ở thời kỳ dân quốc trung quốc từ 2023 trở đi" → chỉ ~5/10 đúng; 5 phim cổ trang phong kiến
/ thập niên 1990 vẫn lọt top 10 (74–81%), bước ⑦ còn bịa lý do "thời dân quốc" cho chúng.
"tìm phim trung quốc kiểu kể về 1 thiếu gia đi" → The Myth, The Heir, I Will Never Let You Go (nữ chính / không phải thiếu gia) vẫn có mặt.

Nguyên nhân: Jev chỉ chấm **mức khớp** (trung bình cốt truyện + chủ đề) → phim cùng không khí nhưng sai điều kiện vẫn điểm cao;
Jev không được xem `overview` (nơi có thời đại / kiểu nhân vật); ⑦ bị ép viết lý do cho đủ 10 phim.

## 2. Sửa (`app/engine/rank.py`, `app/config.py`)
| Chỗ | Thay đổi |
|---|---|
| `_card(..., overview=400)` cho Jev | thêm 400 ký tự đầu `overview` |
| Jev thêm câu `sai_yeu_cau` (noul) | "User có nêu rõ điều kiện BẮT BUỘC (thời đại, bối cảnh, nơi chốn, kiểu nhân vật chính, nghề nghiệp, đối tượng câu chuyện…) mà phim KHÔNG đáp ứng? … chỉ nêu cảm giác / chủ đề chung / giống phim khác → false". Quy tắc chung, không viết riêng case nào |
| Lọc sau Jev | `sai_yeu_cau ≥ 0.6` → loại hẳn; còn < `MIN_KEEP`=3 → giữ 3 phim gần nhất + note "kho ít phim đúng, nói thật"; còn < 10 → note "chỉ có N phim" |
| `MIN_SCORE` (điểm sàn) | thêm biến, **mặc định 0 (tắt)** — chưa có số liệu cần bật |
| Prompt ⑦ `EXPLAIN_SYSTEM` | lý do chỉ nêu điều có thật trong thông tin phim; không gán điều kiện user cho phim; có thể < 10 phim |
| `_debug.rank.dropped` | id các phim bị Jev loại |
| Bước ① | **không sửa**: ca Dân Quốc thiếu `countries=CN` là hợp lý ("trung quốc" ở đây là bối cảnh, không phải nước sản xuất) |
| `eval/eval100.py` | nhận `[thư_mục] [file_câu_hỏi]`; tỉ lệ tính trên số phim thực trả; thêm cột "Số phim TB", "Câu < 5 phim" |

## 3. Kết quả
### Bộ 16 câu bối cảnh / kiểu nhân vật (`eval/questions_ctx.json`, giám khảo claude-haiku-4-5)
| Nhóm | n | Hợp trước → sau | Rất hợp trước → sau |
|---|---|---|---|
| bối cảnh / thời đại | 7 | 91% → **100%** | 91% → **97%** |
| kiểu nhân vật | 6 | 98% → **100%** | 80% → 82% |
| đối chứng (câu rộng) | 3 | 100% → 100% | 90% → **97%** |
| **Tổng** | 16 | 96% → **100%** | 87% → **91%** |

Ca c01 (Dân Quốc): hợp 5/10 → **10/10** (8 rất hợp). Jev loại 21/40 ứng viên, gồm đúng Blossoms Shanghai, White Cat Legend,
Flourished Peony (trước đó nằm top 10). c06 "nữ chính là bác sĩ": loại Dr. Romantic, The Good Doctor, Scrubs (nam chính).
Câu rộng không bị loại oan (vẫn 10 phim).

### Eval 100 câu (so với steps/08; lưu ý kho đã thêm 1.300 hồ sơ series châu Á nên không thuần do bước này)
| Nhóm | n | Hợp 08 → 09 | Rất hợp 08 → 09 |
|---|---|---|---|
| giống phim X | 19 | 93% → 98% | 48% → 51% |
| tâm trạng / cảm xúc | 14 | 99% → 100% | 77% → **95%** |
| mô tả cốt truyện / chủ đề | 10 | 99% → 100% | 77% → **89%** |
| ràng buộc rõ | 12 | 92% → 98% | 70% → **94%** |
| hoàn cảnh xem | 7 | 97% → 100% | 73% → **96%** |
| pha trộn nhiều phim | 5 | 84% → 96% | 36% → 48% |
| loại trừ | 6 | 97% → 97% | 78% → **90%** |
| mơ hồ | 3 | 100% → 100% | 95% → 70% (3 câu, dao động) |
| series | 8 | 92% → 98% | 52% → 69% |
| theo người | 4 | 98% → 100% | 92% → 92% |
| cách gõ Việt | 8 | 95% → 96% | 52% → 70% |
| hỏi tiếp | 4 | 95% → 100% | 70% → 80% |
| **Tổng** | 100 | **95% → 98%** | **65% → 78%** |
Độ trễ p50 10,7 → 11,2 s · p90 18,1 → 23,2 s · max 67 s. Số phim trả TB 9,9; không câu nào < 5 phim.
Còn yếu: "giống X nhưng …" (John Wick ít máu me, Dune ngắn hơn) và pha trộn nhiều phim — việc 3.1 ROADMAP.

### Bước ① — thử gpt-4.1 thay gpt-4.1-mini (`eval.parse_eval`)
| Model | Câu có filter khớp | Filter bịa | Intent |
|---|---|---|---|
| gpt-4.1-mini | **17/17** | 0/32 | 15/15 |
| gpt-4.1 | 16/17 | 0/32 | 15/15 |
→ **giữ gpt-4.1-mini**.

## 4. Chi phí đợt này
Key Medium (gpt): 1,51 USD · key cũ (Jev + embedding + giám khảo): 1,81 USD → ~3,3 USD (2 lần eval ctx, 1 lần eval 100, parse_eval).
