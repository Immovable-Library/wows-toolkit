import json, collections, numpy as np

rows = [json.loads(l) for l in open("ops_efficiency_full.jsonl", encoding="utf-8")]
valid = [r for r in rows if r.get("efficiency") is not None and r.get("raw_exp") is not None and r["raw_exp"] > 0]

by_arena = collections.defaultdict(list)
for r in valid:
    by_arena[r["arena_id"]].append(r)

games = []
for arena, grp in by_arena.items():
    sec_comp = grp[0].get("secondary_completed")
    sec_total = grp[0].get("secondary_total")
    if sec_total is None or sec_comp is None or sec_total == 0:
        continue
    team_eff = sum(p["efficiency"] for p in grp)
    team_raw = sum(p["raw_exp"] for p in grp)
    n = len(grp)
    games.append({
        "arena": arena,
        "scenario": grp[0].get("scenario_family", ""),
        "sec_comp": sec_comp,
        "sec_total": sec_total,
        "sec_failed": sec_total - sec_comp,
        "eff_per": team_eff / n,
        "raw_per": team_raw / n,
        "team_eff": team_eff,
        "team_raw": team_raw,
        "n": n,
    })

# PCVO: has sec_failed=0 games
pcvo = [g for g in games if g["scenario"] == "PCVO(legacy_op)"]
print("PCVO games:", len(pcvo))

# Distribution for sec_failed=0
vals0 = sorted([g["eff_per"] for g in pcvo if g["sec_failed"] == 0])
print()
print("=== PCVO sec_failed=0: team_eff_per distribution (n=%d) ===" % len(vals0))
print("min=%.2f, max=%.2f, mean=%.2f, median=%.2f, std=%.2f" % (
    vals0[0], vals0[-1], np.mean(vals0), np.median(vals0), np.std(vals0)))
for pct in [10, 25, 50, 75, 90]:
    idx = int(len(vals0) * pct / 100)
    print("  %d%%: %.2f" % (pct, vals0[idx]))

# Check for bimodality - look at histogram
print()
print("=== Histogram of team_eff_per (sec_failed=0) ===")
bins = [0, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8, 10, 20]
for i in range(len(bins)-1):
    count = sum(1 for v in vals0 if bins[i] <= v < bins[i+1])
    bar = "#" * (count // 2)
    print("  [%.1f-%.1f): %d %s" % (bins[i], bins[i+1], count, bar))

# Split by median and compare
print()
print("=== Split sec_failed=0 by median eff_per ===")
median_eff = np.median(vals0)
low = [g for g in pcvo if g["sec_failed"] == 0 and g["eff_per"] <= median_eff]
high = [g for g in pcvo if g["sec_failed"] == 0 and g["eff_per"] > median_eff]
for label, grp in [("low-eff (cut off?)", low), ("high-eff (killed reinf?)", high)]:
    grp_ratios = [g["raw_per"] / g["eff_per"] for g in grp]
    print("%s: eff_per=%.2f, raw_per=%.0f, raw/eff=%.1f +- %.1f (n=%d)" % (
        label,
        np.mean([g["eff_per"] for g in grp]),
        np.mean([g["raw_per"] for g in grp]),
        np.mean(grp_ratios), np.std(grp_ratios),
        len(grp)))

# Compare with sec_failed=1 (known to have 1 wave of reinforcements)
print()
print("=== PCVO: sec_failed=0 vs sec_failed=1 ===")
for nf in [0, 1]:
    grp = [g for g in pcvo if g["sec_failed"] == nf]
    grp_ratios = [g["raw_per"] / g["eff_per"] for g in grp]
    print("sec_failed=%d: eff_per=%.2f, raw_per=%.0f, raw/eff=%.1f +- %.1f (n=%d)" % (
        nf, np.mean([g["eff_per"] for g in grp]),
        np.mean([g["raw_per"] for g in grp]),
        np.mean(grp_ratios), np.std(grp_ratios),
        len(grp)))

# Also: player-level within sec_failed=0, compare high-eff vs low-eff
print()
print("=== Player-level: sec_failed=0, split by game-level eff_per ===")
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
    n = len(grp)
    eff_per = team_eff / n
    # tag each game
    for p in grp:
        p["_game_eff_per"] = eff_per

# all PCVO sec_failed=0 players
pcvo_sf0 = []
for arena, grp in by_arena.items():
    sec_comp = grp[0].get("secondary_completed")
    sec_total = grp[0].get("secondary_total")
    if sec_total is None or sec_comp is None or sec_total == 0:
        continue
    if sec_total - sec_comp != 0:
        continue
    if grp[0].get("scenario_family", "") != "PCVO(legacy_op)":
        continue
    team_raw = sum(p["raw_exp"] for p in grp)
    for p in grp:
        pcvo_sf0.append({
            "arena": arena,
            "share": p["raw_exp"] / team_raw,
            "eff": p["efficiency"],
            "scout": p.get("scouting_damage") or 0,
            "ship_class": p.get("ship_class", "CL/CA"),
            "game_eff_per": p.get("_game_eff_per", 0),
        })

cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}

median_g_eff = np.median([r["game_eff_per"] for r in pcvo_sf0])
low_p = [r for r in pcvo_sf0 if r["game_eff_per"] <= median_g_eff]
high_p = [r for r in pcvo_sf0 if r["game_eff_per"] > median_g_eff]

for label, recs_list in [("low-eff game", low_p), ("high-eff game", high_p)]:
    by_a = collections.defaultdict(list)
    for z in recs_list:
        by_a[z["arena"]].append(z)
    fields = ["eff", "scout"]
    n = len(recs_list); npred = len(fields)
    X = np.zeros((n, npred + 5)); y = np.zeros(n)
    for i, z in enumerate(recs_list):
        grp = by_a[z["arena"]]; ng = len(grp)
        y[i] = z["share"] - sum(q["share"] for q in grp) / ng
        X[i, 0] = z["eff"] - sum(q["eff"] for q in grp) / ng
        X[i, 1] = z["scout"] / 100000.0 - sum(q["scout"] / 100000.0 for q in grp) / ng
        X[i, npred + cls_codes[z["ship_class"]]] = 1.0
    cols = list(range(npred)) + list(range(npred, npred + 5))
    coef, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
    pred = X[:, cols] @ coef
    r2 = 1 - float(np.sum((y - pred)**2) / np.sum((y - y.mean())**2))
    print("%s (n=%d): R2=%.4f, eff=%.6f" % (label, n, r2, coef[0]))
