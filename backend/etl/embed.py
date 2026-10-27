"""Embed phim đã có profile bằng EMBED_MODEL → cột movies.dense (halfvec), cập nhật cột fts cho nguồn keyword.

Dùng lại vector đã cache ở data/emb/<model>.npz (từ bài so sánh model) nếu có; chỉ embed phần còn thiếu.
Đổi model khác số chiều → cột dense được đổi kiểu và xoá vector cũ.
Chạy:  .venv/Scripts/python -m etl.embed        (phim)   ·   python -m etl.embed --tv   (series)
"""
import sys

import numpy as np
import psycopg
from pgvector import HalfVector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app import config
from app.embedder import embed, movie_text

COLS = "id, title, title_vi, year, genres, profile, overview, keywords, director"


def main(model=config.EMBED_MODEL, batch=256, tv=False):
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        register_vector(conn)
        dim = len(embed(["thử"], model)[0])
        cur_type = conn.execute("SELECT format_type(atttypid, atttypmod) t FROM pg_attribute "
                                "WHERE attrelid = 'movies'::regclass AND attname = 'dense'").fetchone()["t"]
        if cur_type != f"halfvec({dim})":
            print(f"đổi cột dense: {cur_type} → halfvec({dim})")
            conn.execute("DROP INDEX IF EXISTS movies_dense_hnsw")
            conn.execute(f"ALTER TABLE movies ALTER COLUMN dense TYPE halfvec({dim}) USING NULL")
            conn.execute(f"CREATE INDEX movies_dense_hnsw ON movies USING hnsw (dense halfvec_cosine_ops)")
            conn.commit()

        # phim: chỉ embed khi đã có hồ sơ · series (--tv): embed từ tóm tắt/từ khoá, không cần hồ sơ (chỉ làm phim tham chiếu)
        cond = "kind = 'tv'" if tv else "kind = 'movie' AND profile IS NOT NULL"
        todo = conn.execute(f"SELECT {COLS} FROM movies WHERE {cond} AND dense IS NULL ORDER BY id").fetchall()
        cache = config.ROOT / f"data/emb/{model}.npz"
        cached = {}
        if cache.exists():
            z = np.load(cache)
            cached = dict(zip(z["ids"].tolist(), z["vecs"]))
        print(f"cần embed: {len(todo)} phim ({sum(m['id'] in cached for m in todo)} có sẵn trong cache)")

        for i in range(0, len(todo), batch):
            chunk = todo[i:i + batch]
            need = [m for m in chunk if m["id"] not in cached]
            if need:
                for m, v in zip(need, embed([movie_text(m) for m in need], model)):
                    cached[m["id"]] = v
            with conn.cursor() as c:
                c.executemany("UPDATE movies SET dense = %s WHERE id = %s",
                              [(HalfVector(cached[m["id"]]), m["id"]) for m in chunk])
            conn.commit()
            print(f"  {min(i + batch, len(todo))}/{len(todo)}", flush=True)

        conn.execute("""UPDATE movies SET fts =
              setweight(to_tsvector('simple', f_unaccent(lower(title || ' ' || coalesce(title_vi, '')))), 'A') ||
              setweight(to_tsvector('simple', f_unaccent(lower(coalesce(profile, '') || ' ' ||
                        array_to_string(keywords, ' ') || ' ' || array_to_string(genres, ' ')))), 'B') ||
              setweight(to_tsvector('simple', f_unaccent(lower(coalesce(overview, '')))), 'C')
            WHERE profile IS NOT NULL""")
        n = conn.execute("SELECT count(dense) n FROM movies").fetchone()["n"]
    print(f"xong: {n} phim có vector ({model}, {dim} chiều)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(*(args[:1]), tv="--tv" in sys.argv)
