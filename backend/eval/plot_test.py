"""So embed tóm tắt TMDB (cũ) vs cốt truyện Wikipedia (mới) trên cùng 1 nhóm phim; hồ sơ giữ nguyên."""
import json, sys
import numpy as np, psycopg
from psycopg.rows import dict_row
from app import config
from app.embedder import embed, movie_text

sys.stdout.reconfigure(encoding="utf-8")
ids = [int(x) for x in open("data/plot_test_ids.txt").read().strip().split(",")]
with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as c:
    ms = c.execute("SELECT id, title, title_vi, year, genres, profile, overview, plot, keywords, director FROM movies WHERE id = ANY(%s)", (ids,)).fetchall()
ms = [m for m in ms if m["plot"]]
pos = {m["id"]: i for i, m in enumerate(ms)}
old = embed([movie_text(m) for m in ms])
new = embed([movie_text({**m, "overview": m["plot"]}) for m in ms])
qs = [q for q in json.load(open("eval/questions_resolved.json", encoding="utf-8")) if any(i in pos for i in q["expect_ids"])]
qv = embed([q["q"] for q in qs])
print(f"{len(ms)} phim · {len(qs)} câu hỏi có đáp án nằm trong nhóm này · tóm tắt TB {np.mean([len((m['overview'] or '').split()) for m in ms]):.0f} từ → cốt truyện TB {np.mean([len(m['plot'].split()) for m in ms]):.0f} từ\n")
rows = []
for q, v in zip(qs, qv):
    rel = [pos[i] for i in q["expect_ids"] if i in pos]
    res = {}
    for name, M in (("cũ", old), ("mới", new)):
        qq = M[pos[q["ref"]]] if q.get("ref") in pos else v
        s = M @ qq
        if q.get("ref") in pos: s[pos[q["ref"]]] = -9
        order = list(np.argsort(-s))
        ranks = [order.index(r) + 1 for r in rel]
        res[name] = (np.mean([1 / r for r in ranks]), sum(r <= 5 for r in ranks) / len(ranks))
    rows.append((q, res))
for name in ("cũ", "mới"):
    print(f"{name:4}: MRR {np.mean([r[1][name][0] for r in rows]):.3f} · phim đúng trong top 5 (trên {len(ms)} phim) {np.mean([r[1][name][1] for r in rows]):.3f}")
for t in ("mood", "similar", "filter", "vi_title"):
    sel = [r for r in rows if r[0]["type"] == t]
    if sel: print(f"   {t:9} n={len(sel):2}  MRR cũ {np.mean([r[1]['cũ'][0] for r in sel]):.3f} → mới {np.mean([r[1]['mới'][0] for r in sel]):.3f}")
print("\nCâu thay đổi nhiều nhất:")
for q, res in sorted(rows, key=lambda r: -abs(r[1]["mới"][0] - r[1]["cũ"][0]))[:6]:
    print(f"   {q['q'][:60]:60} MRR {res['cũ'][0]:.2f} → {res['mới'][0]:.2f}")
m = next(m for m in ms if m["id"] == 157336)
print("\nMẫu cốt truyện (Interstellar):", m["plot"][:350].replace("\n", " "), "…")
