import json, collections, numpy as np

rows = [json.loads(l) for l in open("ops_efficiency_full.jsonl", encoding="utf-8")]
valid = [r for r in rows if r.get("efficiency") is not None and r.get("raw_exp") is not None and r["raw_exp"] > 0]

by_arena = collections.defaultdict(list)
for r in valid:
    by_arena[r["arena_id"]].append(r)

# Build all PCVO sec_failed=0 games with scenario info
games = []
for arena, grp in by_arena.items():
    sec_comp = grp[0].get("secondary_completed")
    sec_total = grp[0].get("secondary_total")
    if sec_total is None or sec_comp is None or sec_total == 0:
        continue
    if sec_total - sec_comp != 0:
        continue
    sc = grp[0].get("scenario_family", "")
    if sc != "PCVO(legacy_op)":
        continue
    team_eff = sum(p["efficiency"] for p in grp)
    team_raw = sum(p["raw_exp"] for p in grp)
    n = len(grp)
    games.append({
        "arena": arena,
        "scenario_name": grp[0].get("scenario", ""),
        "eff_per": team_eff / n,
        "raw_per": team_raw / n,
        "team_eff": team_eff,
        "team_raw": team_raw,
        "n": n,
    })

# Check: which scenarios have the most games?
from collections import Counter
sc_dist = Counter(g["scenario_name"] for g in games)
print("Scenarios in sec_failed=0:")
for sc, cnt in sc_dist.most_common(20):
    grp = [g for g in games if g["scenario_name"] == sc]
    print("  %s: n=%d, eff_per=%.2f, raw/eff=%.1f" % (
        sc[:50], cnt,
        np.mean([g["eff_per"] for g in grp]),
        np.mean([g["raw_per"] / g["eff_per"] for g in grp])))

# Now: within each scenario, split by eff_per and compare raw/eff
print()
print("=== Within-scenario comparison: low-eff vs high-eff (sec_failed=0) ===")
for sc, cnt in sc_dist.most_common(15):
    if cnt < 10:
        continue
    grp = [g for g in games if g["scenario_name"] == sc]
    median_eff = np.median([g["eff_per"] for g in grp])
    low = [g for g in grp if g["eff_per"] <= median_eff]
    high = [g for g in grp if g["eff_per"] > median_eff]
    low_ratio = np.mean([g["raw_per"] / g["eff_per"] for g in low])
    high_ratio = np.mean([g["raw_per"] / g["eff_per"] for g in high])
    diff_pct = (high_ratio / low_ratio - 1) * 100
    print("  %s:" % sc[:40])
    print("    low: eff=%.2f raw/eff=%.0f (n=%d) | high: eff=%.2f raw/eff=%.0f (n=%d) | diff=%.1f%%" % (
        np.mean([g["eff_per"] for g in low]), low_ratio, len(low),
        np.mean([g["eff_per"] for g in high]), high_ratio, len(high),
        diff_pct))

# Also: regression at player level within each scenario, with game_eff_per interaction
print()
print("=== Player-level: eff * game_eff_category interaction ===")
# Build player data
pcvo_data = []
for arena, grp in by_arena.items():
    sec_comp = grp[0].get("secondary_completed")
    sec_total = grp[0].get("secondary_total")
    if sec_total is None or sec_comp is None or sec_total == 0:
        continue
    if sec_total - sec_comp != 0:
        continue
    if grp[0].get("scenario_family", "") != "PCVO(legacy_op)":
        continue
    team_eff = sum(p["efficiency"] for p in grp)
    team_raw = sum(p["raw_exp"] for p in grp)
    n = len(grp)
    game_eff_per = team_eff / n
    for p in grp:
        pcvo_data.append({
            "arena": arena,
            "scenario": grp[0].get("scenario", ""),
            "share": p["raw_exp"] / team_raw,
            "eff": p["efficiency"],
            "scout": p.get("scouting_damage") or 0,
            "ship_class": p.get("ship_class", "CL/CA"),
            "game_eff_per": game_eff_per,
        })

cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}
by_a = collections.defaultdict(list)
for z in pcvo_data:
    by_a[z["arena"]].append(z)

# Add interaction: eff * game_eff_per
n = len(pcvo_data); npred = 3
X = np.zeros((n, npred + 5)); y = np.zeros(n)
for i, z in enumerate(pcvo_data):
    grp = by_a[z["arena"]]; ng = len(grp)
    y[i] = z["share"] - sum(q["share"] for q in grp) / ng
    X[i, 0] = z["eff"] - sum(q["eff"] for q in grp) / ng
    X[i, 1] = z["scout"] / 100000.0 - sum(q["scout"] / 100000.0 for q in grp) / ng
    X[i, 2] = z["eff"] * z["game_eff_per"] - sum(q["eff"] * q["game_eff_per"] for q in grp) / ng
    X[i, npred + cls_codes[z["ship_class"]]] = 1.0
cols = list(range(npred)) + list(range(npred, npred + 5))
coef, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
pred = X[:, cols] @ coef
r2 = 1 - float(np.sum((y - pred)**2) / np.sum((y - y.mean())**2))
print("R2=%.4f" % r2)
print("eff: %.6f" % coef[0])
print("scout: %.6f" % coef[1])
print("eff * game_eff_per: %.6f" % coef[2])
print("-> negative = higher game_eff_per (more extra ships) = less XP per eff")
print("-> positive = higher game_eff_per = more XP per eff")
