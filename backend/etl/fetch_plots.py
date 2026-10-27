"""Kéo cốt truyện dài (mục Plot / Synopsis, 400–700 từ) từ Wikipedia tiếng Anh cho phim/series đã có hồ sơ → cột movies.plot.

Ánh xạ TMDB id → bài Wikipedia qua Wikidata (P4947 = TMDB movie, P4983 = TMDB TV). Không cần WARP.
Cốt truyện có spoil → CHỈ dùng để embed, không hiển thị. Nội dung Wikipedia: CC BY-SA.
Chạy:  .venv/Scripts/python -m etl.fetch_plots
"""
import re, sys, time
from concurrent.futures import ThreadPoolExecutor

import httpx
import psycopg

from app import config

UA = {"User-Agent": "CineMindStudentProject/0.1 (https://github.com/; cinemind@example.org) httpx"}
SPARQL = "https://query.wikidata.org/sparql"
WIKI = "https://en.wikipedia.org/w/api.php"


def wikidata_titles(client, tmdb_ids, prop):
    vals = " ".join(f'"{i}"' for i in tmdb_ids)
    q = (f"SELECT ?tmdb ?article WHERE {{ VALUES ?tmdb {{{vals}}} ?item wdt:{prop} ?tmdb . "
         f"?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }}")
    for attempt in range(4):
        try:
            r = client.get(SPARQL, params={"query": q, "format": "json"}, timeout=60)
            r.raise_for_status()
            return {b["tmdb"]["value"]: httpx.URL(b["article"]["value"]).path.rsplit("/", 1)[1]
                    for b in r.json()["results"]["bindings"]}
        except (httpx.HTTPError, ValueError):
            time.sleep(3 * (attempt + 1))
    return {}


def clean(wt):
    wt = re.sub(r"<!--.*?-->|<ref[^>]*/>|<ref.*?</ref>", "", wt, flags=re.S)
    for _ in range(3):
        wt = re.sub(r"\{\{[^{}]*\}\}", "", wt)
    wt = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", wt)
    wt = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", wt)
    wt = re.sub(r"'''?|<[^>]+>", "", wt)
    return re.sub(r"\s+\n|\n{2,}", "\n", wt).strip()


def plots(client, titles):
    """Tối đa 50 bài / request. Trả {title: plot}."""
    r = client.get(WIKI, params={"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                                 "titles": "|".join(titles), "format": "json", "formatversion": 2, "redirects": 1},
                   timeout=60)
    r.raise_for_status()
    d = r.json()["query"]
    back = {x["to"]: x["from"] for x in d.get("redirects", []) + d.get("normalized", [])}
    out = {}
    for p in d.get("pages", []):
        if "revisions" not in p:
            continue
        wt = p["revisions"][0]["slots"]["main"]["content"]
        m = re.search(r"^==\s*(Plot|Synopsis|Plot summary|Premise)\s*==\s*$(.*?)(?=^==[^=])", wt, re.S | re.M)
        if m:
            txt = clean(m.group(2))
            if len(txt.split()) >= 60:
                t = p["title"]
                out[back.get(t, t)] = txt
    return out


def main(only_ids=None):
    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute("ALTER TABLE movies ADD COLUMN IF NOT EXISTS plot text")
        conn.commit()
        rows = conn.execute("SELECT id, kind FROM movies WHERE profile IS NOT NULL AND plot IS NULL").fetchall()
        if only_ids:
            rows = [r for r in rows if r[0] in set(only_ids)]
        print(f"cần tìm cốt truyện: {len(rows)}", flush=True)
        with httpx.Client(headers=UA) as client:
            title_of = {}
            for kind, prop in (("movie", "P4947"), ("tv", "P4983")):
                ids = [str(abs(r[0])) for r in rows if r[1] == kind]
                for i in range(0, len(ids), 200):
                    for tmdb, title in wikidata_titles(client, ids[i:i + 200], prop).items():
                        title_of[int(tmdb) * (-1 if kind == "tv" else 1)] = title.replace("_", " ")
                    time.sleep(0.5)
                print(f"  {kind}: {sum(1 for k in title_of if (k < 0) == (kind == 'tv'))} có bài Wikipedia", flush=True)
            by_title = {}
            titles = list(dict.fromkeys(title_of.values()))
            chunks = [titles[i:i + 50] for i in range(0, len(titles), 50)]
            with ThreadPoolExecutor(3) as pool:
                for res in pool.map(lambda c: plots(client, c), chunks):
                    by_title.update(res)
            n = 0
            with conn.cursor() as cur:
                for mid, title in title_of.items():
                    if title in by_title:
                        cur.execute("UPDATE movies SET plot = %s WHERE id = %s", (by_title[title], mid))
                        n += 1
        words = conn.execute("SELECT avg(array_length(regexp_split_to_array(plot, '\\s+'), 1))::int FROM movies WHERE plot IS NOT NULL").fetchone()[0]
    print(f"xong: {n} phim có cốt truyện (trung bình {words} từ)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ids = None
    if "--ids" in sys.argv:
        ids = [int(x) for x in sys.argv[sys.argv.index("--ids") + 1].split(",")]
    main(ids)
