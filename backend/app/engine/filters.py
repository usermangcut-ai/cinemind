"""③ Filter cứng: validate (chống bịa) → SQL WHERE → nới dần khi quá ít phim."""
import datetime
import unicodedata

GENRES = ["Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary", "Drama", "Family", "Fantasy",
          "History", "Horror", "Music", "Mystery", "Romance", "Science Fiction", "TV Movie", "Thriller", "War",
          "Western"]
GENRE_VI = {"Action": "Hành động", "Adventure": "Phiêu lưu", "Animation": "Hoạt hình", "Comedy": "Hài",
            "Crime": "Tội phạm", "Documentary": "Tài liệu", "Drama": "Chính kịch", "Family": "Gia đình",
            "Fantasy": "Kỳ ảo", "History": "Lịch sử", "Horror": "Kinh dị", "Music": "Âm nhạc", "Mystery": "Bí ẩn",
            "Romance": "Tình cảm", "Science Fiction": "Khoa học viễn tưởng", "TV Movie": "Phim truyền hình",
            "Thriller": "Giật gân", "War": "Chiến tranh", "Western": "Viễn Tây"}
COUNTRY_VI = {"US": "Mỹ", "GB": "Anh", "KR": "Hàn Quốc", "JP": "Nhật Bản", "CN": "Trung Quốc", "HK": "Hồng Kông",
              "TW": "Đài Loan", "FR": "Pháp", "DE": "Đức", "IT": "Ý", "ES": "Tây Ban Nha", "IN": "Ấn Độ",
              "TH": "Thái Lan", "VN": "Việt Nam", "CA": "Canada", "AU": "Úc", "MX": "Mexico", "BR": "Brazil",
              "RU": "Nga", "SE": "Thuỵ Điển", "DK": "Đan Mạch", "NO": "Na Uy", "IE": "Ireland", "NZ": "New Zealand"}
# Thể loại chỉ được thành filter khi trích dẫn chứa đúng từ khoá của thể loại đó (chặn "tâm lý" → Chính kịch)
GENRE_WORDS = {
    "Action": ["hanh dong", "action"], "Adventure": ["phieu luu", "adventure"],
    "Animation": ["hoat hinh", "anime", "animation", "phim hoat"], "Comedy": ["hai", "comedy", "vui nhon"],
    "Crime": ["toi pham", "crime", "hinh su"], "Documentary": ["tai lieu", "documentary"],
    "Drama": ["chinh kich", "drama"], "Family": ["gia dinh", "family", "ca nha"],
    "Fantasy": ["ky ao", "fantasy", "than thoai", "phep thuat"], "History": ["lich su", "history", "co trang"],
    "Horror": ["kinh di", "horror", "ma", "rung ron"], "Music": ["am nhac", "nhac kich", "music", "ca nhac"],
    "Mystery": ["bi an", "trinh tham", "mystery"], "Romance": ["tinh cam", "lang man", "romance", "tinh yeu"],
    "Science Fiction": ["khoa hoc vien tuong", "vien tuong", "sci-fi", "scifi", "sci fi"],
    "TV Movie": ["tv movie"], "Thriller": ["giat gan", "thriller"], "War": ["chien tranh", "war"],
    "Western": ["vien tay", "cao boi", "western"],
}
KIND_WORDS = {"tv": ["phim bo", "series", "seri", "tv show", "truyen hinh", "nhieu tap"],
              "movie": ["phim le", "chieu rap", "dien anh", "movie"]}
CERTS = ["G", "PG", "PG-13", "R", "NC-17"]
FIELDS = {"year_min", "year_max", "runtime_min", "runtime_max", "genres", "exclude_genres", "countries",
          "exclude_countries", "certification_max", "person", "kind"}
# Thứ tự nới: bỏ cái ít quan trọng trước. Điều kiện loại trừ ("không …") không bao giờ tự nới.
RELAX_ORDER = ["genres", "runtime_min", "runtime_max", "year_min", "year_max", "certification_max", "countries", "kind"]
MIN_RESULTS = 5


def norm(s):
    s = unicodedata.normalize("NFD", str(s).lower()).replace("đ", "d")
    return " ".join("".join(c for c in s if unicodedata.category(c) != "Mn").split())


def _clean_value(field, v):
    year_now = datetime.date.today().year
    if field in ("year_min", "year_max"):
        v = int(v)
        return v if 1900 <= v <= year_now + 1 else None
    if field in ("runtime_min", "runtime_max"):
        v = int(v)
        return v if 30 <= v <= 300 else None
    if field in ("genres", "exclude_genres"):
        v = [g for g in (v if isinstance(v, list) else [v]) if g in GENRES]
        return v or None
    if field in ("countries", "exclude_countries"):
        v = [c.upper() for c in (v if isinstance(v, list) else [v]) if isinstance(c, str) and len(c) == 2]
        return v or None
    if field == "certification_max":
        return v if v in CERTS else None
    if field == "person":
        return v.strip() if isinstance(v, str) and v.strip() else None
    if field == "kind":
        return v if v in ("movie", "tv") else None
    return None


def validate(filters, user_text):
    """4 lớp chống bịa: field cho phép · enum/giới hạn · evidence có thật trong câu user · không mâu thuẫn.
    Trả (giữ lại, bị bỏ kèm lý do)."""
    kept, dropped, text = [], [], norm(user_text)
    for f in filters or []:
        field, ev = f.get("field"), f.get("evidence") or ""
        if field not in FIELDS:
            dropped.append((f, "field không cho phép"))
            continue
        try:
            value = _clean_value(field, f.get("value"))
        except (TypeError, ValueError):
            value = None
        if value is None:
            dropped.append((f, "giá trị không hợp lệ"))
            continue
        if not ev or norm(ev) not in text:
            dropped.append((f, "evidence không có trong câu user"))
            continue
        if field in ("genres", "exclude_genres"):
            words = f" {norm(ev)} "
            ok = [g for g in value if any(f" {w} " in words for w in GENRE_WORDS.get(g, []))]
            if not ok:
                dropped.append((f, "trích dẫn không gọi đúng tên thể loại"))
                continue
            value = ok
        if field == "kind" and not any(f" {w} " in f" {norm(ev)} " for w in KIND_WORDS[value]):
            dropped.append((f, "user không nói rõ phim lẻ/series"))
            continue
        kept.append({"field": field, "value": value, "evidence": ev})
    return kept, dropped


def merge(current, added, removed_fields):
    """Filter giữ theo hội thoại: filter cũ (trừ field bị gỡ / bị thay) + filter mới."""
    new_fields = {f["field"] for f in added}
    out = [f for f in current or [] if f["field"] not in new_fields and f["field"] not in set(removed_fields or [])]
    return out + added


def conflicts(filters):
    by = {f["field"]: f["value"] for f in filters}
    msgs = []
    if by.get("year_min") and by.get("year_max") and by["year_min"] > by["year_max"]:
        msgs.append(("year_min", "year_max"))
    if by.get("runtime_min") and by.get("runtime_max") and by["runtime_min"] > by["runtime_max"]:
        msgs.append(("runtime_min", "runtime_max"))
    if set(by.get("genres") or []) & set(by.get("exclude_genres") or []):
        msgs.append(("genres", "exclude_genres"))
    if set(by.get("countries") or []) & set(by.get("exclude_countries") or []):
        msgs.append(("countries", "exclude_countries"))
    return msgs


def label(f):
    field, v = f["field"], f["value"]
    if field == "year_min": return f"Từ {v}"
    if field == "year_max": return f"Đến {v}"
    if field == "runtime_max": return f"Dưới {v} phút"
    if field == "runtime_min": return f"Trên {v} phút"
    if field == "genres": return ", ".join(GENRE_VI.get(g, g) for g in v)
    if field == "exclude_genres": return "Không " + ", ".join(GENRE_VI.get(g, g).lower() for g in v)
    if field == "countries": return "Phim " + ", ".join(COUNTRY_VI.get(c, c) for c in v)
    if field == "exclude_countries": return "Không phim " + ", ".join(COUNTRY_VI.get(c, c) for c in v)
    if field == "certification_max": return f"Độ tuổi ≤ {v}"
    if field == "person": return v
    if field == "kind": return "Chỉ series" if v == "tv" else "Chỉ phim lẻ"
    return str(v)


def to_sql(filters, base_min_votes=0):
    # chỉ phim/series ĐÃ có hồ sơ mới được gợi ý (series chưa có hồ sơ chỉ dùng làm phim tham chiếu)
    where, params = ["profile IS NOT NULL", "vote_count >= %(min_votes)s"], {"min_votes": base_min_votes}
    for i, f in enumerate(filters):
        field, v, p = f["field"], f["value"], f"f{i}"
        params[p] = v
        if field == "year_min": where.append(f"year >= %({p})s")
        elif field == "year_max": where.append(f"year <= %({p})s")
        elif field == "runtime_min": where.append(f"runtime >= %({p})s")
        elif field == "runtime_max": where.append(f"runtime <= %({p})s")
        elif field == "genres": where.append(f"genres && %({p})s::text[]")  # có ít nhất 1 thể loại
        elif field == "exclude_genres": where.append(f"NOT (genres && %({p})s::text[])")
        elif field == "countries": where.append(f"countries && %({p})s::text[]")
        elif field == "exclude_countries": where.append(f"NOT (countries && %({p})s::text[])")
        elif field == "certification_max":
            params[p] = CERTS[: CERTS.index(v) + 1]
            where.append(f"certification = ANY(%({p})s::text[])")
        elif field == "kind":
            where.append(f"kind = %({p})s")
        elif field == "person":
            params[p] = norm(v).replace("-", " ")  # "Bong Joon-ho" = "Bong Joon Ho"
            where.append(f"EXISTS (SELECT 1 FROM unnest(director || cast_top || writers) x "
                         f"WHERE replace(f_unaccent(lower(x)), '-', ' ') = %({p})s)")
    return " AND ".join(where), params


def apply(conn, filters, exclude_ids=()):
    """Áp filter, nới dần nếu còn < MIN_RESULTS phim. Trả (where, params, filters_cuối, đã_nới, số_phim)."""
    active, relaxed = [dict(f) for f in filters], []
    while True:
        where, params = to_sql(active)
        if exclude_ids:
            where += " AND NOT (id = ANY(%(excl)s))"
            params["excl"] = list(exclude_ids)
        n = conn.execute(f"SELECT count(*) FROM movies WHERE profile IS NOT NULL AND {where}", params).fetchone()[0]
        if n >= MIN_RESULTS:
            return where, params, active, relaxed, n
        nxt = next((fld for fld in RELAX_ORDER if any(f["field"] == fld for f in active)), None)
        if nxt is None:
            return where, params, active, relaxed, n
        relaxed += [f for f in active if f["field"] == nxt]
        active = [f for f in active if f["field"] != nxt]
