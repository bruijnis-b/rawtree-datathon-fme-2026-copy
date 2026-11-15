"""Official (expected, no-luck) scores per model over a window, ours and every other team's:
python board.py "2026-11-15 01:33" "2026-11-15 02:13" """
import sys, json, calendar, time
from datetime import datetime
from monitor.rawtree import leaderboard_state, TEAM
from monitor.data import estimated_score
names = {e["public_id"]: (e["internal"].replace("-v1", "") + " " + str({k: v for k, v in e["params"].items() if k in ("embed_model", "embed_model2", "cart", "trend", "alpha", "new") and v not in (0.0, 6.0, 8.0, 1.0, "")})) for e in json.load(open("recsys/model_versions.json", encoding="utf-8"))}
t0, t1 = (calendar.timegm(datetime.strptime(a, "%Y-%m-%d %H:%M").timetuple()) for a in sys.argv[1:3])
st = leaderboard_state(by="model", **{"from": int(t0), "to": int(min(t1, time.time()))})
base, ref = st["baseline"], st["reference"]
print(f"window {sys.argv[1]} - {sys.argv[2]} UTC | baseline conv {base['conversion']:.4f} cold {base['cold_conversion']:.4f} | reference conv {ref['conversion']:.4f} cold {ref['cold_conversion']:.4f} -> reference score {estimated_score(ref['conversion'], ref['cold_conversion'], base, ref):.1f}")
rows = []
for t in st["teams"]:
    sc = estimated_score(t["conversion"], t["cold_conversion"], base, ref)
    best = None
    for v in t.get("versions", []):
        if v["requests"] >= 300:
            s = estimated_score(v["conversion"], v["cold_conversion"], base, ref)
            if best is None or s > best[0]:
                best = (s, v["requests"], v["conversion"], v["cold_conversion"])
    rows.append((sc, t["team_id"], t["requests"], t["conversion"], t["cold_conversion"], t.get("on_time"), len(t.get("versions", [])), best))
rows.sort(reverse=True)
print("rank team      score  conv    cold    on_time requests versions | best single model (>=300 requests): score, requests")
for i, (sc, tid, n, c, cc, ot, nv, best) in enumerate(rows[:12] + [r for r in rows[12:] if r[1] == TEAM], 1):
    b = f"{best[0]:.1f} ({best[1]})" if best else "-"
    print(f"{i:>3}  {tid:9s} {sc:5.1f}  {c:.4f}  {cc:.4f}  {ot!s:7} {n:7d}  {nv:3d}     | {b}{'   <- us' if tid == TEAM else ''}")
ours = next((t for t in st["teams"] if t["team_id"] == TEAM), None)
if ours:
    print("our models in this window:")
    for v in sorted(ours.get("versions", []), key=lambda v: -v["requests"]):
        print(f"   {v['model_version']} {estimated_score(v['conversion'], v['cold_conversion'], base, ref):5.1f}  conv {v['conversion']:.4f}  cold {v['cold_conversion']:.4f}  requests {v['requests']:5d}  {names.get(v['model_version'], '')}")
