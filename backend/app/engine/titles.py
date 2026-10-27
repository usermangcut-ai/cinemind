"""② Nhận diện tên phim user nhắc tới → movie id (pg_trgm trên title / title_vi / original_title / alt_titles)."""
import math
import re

from app.engine.filters import norm

MIN_CONF = 0.6


def _words(s):
    return set(re.findall(r"\w+", norm(s or "")))


def resolve(conn, name):
    """Trả {'id', 'title', 'year', 'conf'} hoặc {'ambiguous': [...]} hoặc None."""
    m = re.search(r"\(?((?:19|20)\d{2})\)?\s*$", name.strip())
    year = int(m.group(1)) if m and norm(name[:m.start()]) else None
    q = norm(name[:m.start()] if year else name)
    qw = _words(q)
    rows = conn.execute(
        """WITH c AS (
             SELECT id, title, title_vi, original_title, year, vote_count, collection_id,
                    GREATEST(similarity(f_unaccent(lower(title)), %(q)s),
                             similarity(f_unaccent(lower(coalesce(title_vi, ''))), %(q)s),
                             similarity(f_unaccent(lower(coalesce(original_title, ''))), %(q)s),
                             coalesce((SELECT max(similarity(f_unaccent(lower(a)), %(q)s)) FROM unnest(alt_titles) a), 0)
                    ) AS sim
             FROM movies
             WHERE f_unaccent(lower(title)) %% %(q)s OR f_unaccent(lower(coalesce(title_vi, ''))) %% %(q)s
                OR f_unaccent(lower(coalesce(original_title, ''))) %% %(q)s
                OR %(q)s <%% f_unaccent(lower(title)) OR %(q)s <%% f_unaccent(lower(coalesce(title_vi, '')))
                OR EXISTS (SELECT 1 FROM unnest(alt_titles) a WHERE f_unaccent(lower(a)) %% %(q)s))
           SELECT id, title, title_vi, original_title, year, vote_count, collection_id, sim FROM c
           WHERE %(y)s::int IS NULL OR year = %(y)s::int
           ORDER BY sim DESC, vote_count DESC LIMIT 30""",
        {"q": q, "y": year}).fetchall()
    cands = []
    for mid, title, title_vi, otitle, yr, votes, coll, sim in rows:
        sim = float(sim)
        # tên gõ nằm trọn trong tên dài ("Bóng ma Anh Quốc" ⊂ "Bóng ma Anh Quốc: Người bất tử") — xét theo TỪ,
        # không theo cụm ký tự (tránh "Lang Gia Bảng" ≈ "Nữ Hoàng Băng Giá"). ×0.9 để tên khớp nguyên vẫn thắng.
        if qw and any(qw <= _words(t) for t in (title, title_vi, otitle)):
            sim = max(sim, 0.9)
        if sim >= MIN_CONF:
            # cộng nhẹ theo độ phổ biến: "Lord of the Rings" → bản 2001, không phải bản hoạt hình 1978 trùng tên
            cands.append((mid, title, yr, votes or 0, sim, coll, sim + 0.1 * math.log10((votes or 0) + 1)))
    if not cands:
        return None
    cands.sort(key=lambda r: -r[6])
    top = cands[0]
    # mơ hồ: phim khác khớp gần bằng VÀ cũng phổ biến
    close = [r for r in cands[1:5] if r[4] >= top[4] - 0.05 and r[3] >= 0.3 * top[3]]
    if close and all(r[5] and r[5] == top[5] for r in close):  # cùng series (Harry Potter 1–8) → phần nổi tiếng nhất
        best = max([top, *close], key=lambda r: r[3])
        return {"id": best[0], "title": best[1], "year": best[2], "conf": round(best[4], 2)}
    if close:
        return {"ambiguous": [{"id": r[0], "title": r[1], "year": r[2]} for r in [top, *close]]}
    return {"id": top[0], "title": top[1], "year": top[2], "conf": round(top[4], 2)}
