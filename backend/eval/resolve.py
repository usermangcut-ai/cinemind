"""Đổi "Tên (Năm)" trong questions.json → TMDB id trong DB → questions_resolved.json."""
import json, re, sys
from pathlib import Path

import psycopg

from app import config

HERE = Path(__file__).parent
REFS = {
    "sim-01": "Interstellar (2014)", "sim-02": "Interstellar (2014)", "sim-03": "Parasite (2019)",
    "sim-04": "La La Land (2016)", "sim-05": "John Wick (2014)", "sim-06": "Spirited Away (2001)",
    "sim-07": "Get Out (2017)", "sim-08": "Before Sunrise (1995)", "vi-01": "Inception (2010)",
    "vi-02": "Parasite (2019)", "vi-03": "Train to Busan (2016)", "vi-04": "A Quiet Place (2018)",
}


def find(conn, label):
    title, year = re.match(r"(.+) \((\d{4})\)$", label).groups()
    year = int(year)
    row = conn.execute(
        """SELECT id FROM movies
           WHERE (lower(title) = lower(%(t)s) OR lower(original_title) = lower(%(t)s)
                  OR lower(%(t)s) = ANY(SELECT lower(x) FROM unnest(alt_titles) x))
             AND year BETWEEN %(y)s - 1 AND %(y)s + 1
           ORDER BY vote_count DESC LIMIT 1""", {"t": title, "y": year}).fetchone()
    return row[0] if row else None


def main():
    qs = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    missing = []
    with psycopg.connect(config.DATABASE_URL) as conn:
        for q in qs:
            q["expect_ids"] = []
            for label in q["expect"]:
                mid = find(conn, label)
                (q["expect_ids"].append(mid) if mid else missing.append(f"{q['id']}: {label}"))
            if q["id"] in REFS:
                q["ref"] = find(conn, REFS[q["id"]])
                if not q["ref"]:
                    missing.append(f"{q['id']}: REF {REFS[q['id']]}")
    (HERE / "questions_resolved.json").write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(q["expect"]) for q in qs)
    print(f"{len(qs)} câu, {total - len(missing)}/{total} phim đáp án tìm được trong DB")
    for m in missing:
        print("  thiếu:", m)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
