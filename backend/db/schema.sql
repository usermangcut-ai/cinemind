-- CineMind schema. Chạy tự động khi container DB khởi tạo lần đầu.
-- Chạy lại thủ công: docker exec -i cinemind-db psql -U cinemind -d cinemind < db/schema.sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS movies (
  id             int PRIMARY KEY,           -- TMDB id (series: -tv_id)
  kind           text NOT NULL DEFAULT 'movie', -- movie | tv (tv chỉ làm phim tham chiếu)
  imdb_id        text,
  title          text NOT NULL,
  original_title text,
  title_vi       text,                      -- TMDB translations (vi)
  overview_vi    text,
  alt_titles     text[] DEFAULT '{}',
  year           int,
  release_date   date,
  runtime        int,
  original_language text,
  genres         text[] DEFAULT '{}',       -- 19 thể loại TMDB
  countries      text[] DEFAULT '{}',       -- ISO 3166-1 (US, KR, VN…)
  keywords       text[] DEFAULT '{}',
  director       text[] DEFAULT '{}',       -- TMDB credits
  writers        text[] DEFAULT '{}',
  cast_top       text[] DEFAULT '{}',       -- 5 diễn viên đầu
  crew_key       text[] DEFAULT '{}',       -- nhạc, quay phim
  collection_id  int,                       -- TMDB collection, gộp phần 1/2/3
  collection     text,
  certification  text,                      -- độ tuổi (US)
  tagline        text,
  overview       text,
  profile        text,                      -- LLM viết (bước 1)
  vote_average   real,
  vote_count     int,
  imdb_rating    real,                      -- IMDb title.ratings (tải hằng ngày)
  imdb_votes     int,
  popularity     real,
  poster_path    text,
  backdrop_path  text,
  dense          vector(1024),              -- bge-m3
  sparse         sparsevec(250002),         -- bge-m3 lexical
  fts            tsvector,                  -- full-text cho nguồn keyword (④)
  updated_at     timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS movies_dense_hnsw ON movies USING hnsw (dense vector_cosine_ops);
CREATE INDEX IF NOT EXISTS movies_genres_gin ON movies USING gin (genres);
CREATE INDEX IF NOT EXISTS movies_countries_gin ON movies USING gin (countries);
CREATE INDEX IF NOT EXISTS movies_year ON movies (year);

CREATE TABLE IF NOT EXISTS trending (
  period   text,                            -- 'week' | 'month'
  rank     int,
  movie_id int REFERENCES movies(id) ON DELETE CASCADE,
  PRIMARY KEY (period, rank)
);

-- Hàm unaccent IMMUTABLE để dùng trong index + cột full-text cho nguồn keyword (④)
CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text
  LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS $$ SELECT public.unaccent('public.unaccent', $1) $$;

CREATE INDEX IF NOT EXISTS movies_fts_gin ON movies USING gin (fts);

CREATE INDEX IF NOT EXISTS movies_title_trgm ON movies USING gin (f_unaccent(lower(title)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS movies_title_vi_trgm ON movies USING gin (f_unaccent(lower(coalesce(title_vi, ''))) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS movies_otitle_trgm ON movies USING gin (f_unaccent(lower(coalesce(original_title, ''))) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS movies_kind ON movies (kind);
