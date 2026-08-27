import json, collections, numpy as np

rows = [json.loads(l) for l in open("ops_efficiency_full.jsonl", encoding="utf-8")]
valid = [r for r in rows if r.get("efficiency") is not None and r.get("raw_exp") is not None and r["raw_exp"] > 0]

by_arena = collections.defaultdict(list)
for r in valid:
    by_arena[r["arena_id"]].append(r)

# Build game-level stats
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

# Focus on WW2_OP (new ops) where sec_failed varies more
ww2 = [g for g in games if g["scenario"] == "WW2_OP(new)"]
print("WW2_OP games:", len(ww2))

# Distribution of eff_per by sec_failed
print()
print("WW2_OP team_eff_per_player by sec_failed:")
for nf in sorted(set(g["sec_failed"] for g in ww2)):
    vals = [g["eff_per"] for g in ww2 if g["sec_failed"] == nf]
    if vals:
        print("  sec_failed=%d: mean=%.2f, median=%.2f, std=%.2f, min=%.2f, max=%.2f (n=%d)" % (
            nf, np.mean(vals), np.median(vals), np.std(vals), np.min(vals), np.max(vals), len(vals)))

# Key comparison: within sec_failed=0, is there a bimodal distribution?
# Low eff = cut off, high eff = killed reinforcements?
print()
print("=== sec_failed=0: team_eff_per distribution ===")
vals0 = sorted([g["eff_per"] for g in ww2 if g["sec_failed"] == 0])
print("n=%d, min=%.2f, max=%.2f" % (len(vals0), vals0[0], vals0[-1]))
# deciles
for pct in [10, 25, 50, 75, 90]:
    idx = int(len(vals0) * pct / 100)
    print("  %d%%: %.2f" % (pct, vals0[idx]))

# If there IS a bimodal split, let's try splitting at the median
# and compare raw_per for high-eff vs low-eff sec_failed=0 games
print()
print("=== sec_failed=0: split by median eff_per ===")
if len(vals0) > 0:
    median_eff = np.median(vals0)
    low = [g for g in ww2 if g["sec_failed"] == 0 and g["eff_per"] <= median_eff]
    high = [g for g in ww2 if g["sec_failed"] == 0 and g["eff_per"] > median_eff]
    for label, grp in [("low-eff", low), ("high-eff", high)]:
        if grp:
            print("%s: eff_per=%.2f, raw_per=%.0f, raw/eff=%.0f (n=%d)" % (
                label,
                np.mean([g["eff_per"] for g in grp]),
                np.mean([g["raw_per"] for g in grp]),
                np.mean([g["raw_per"] for g in grp]) / np.mean([g["eff_per"] for g in grp]),
                len(grp)))

# Also check: compare sec_failed=0 (possibly cut off OR killed reinforcements)
# with sec_failed=1 games where the extra eff is from 1 wave of reinforcements
print()
print("=== Comparison: sec_failed=0 vs sec_failed=1 ===")
for nf in [0, 1]:
    grp = [g for g in ww2 if g["sec_failed"] == nf]
    if grp:
        print("sec_failed=%d: eff_per=%.2f, raw_per=%.0f, raw/eff=%.0f (n=%d)" % (
            nf,
            np.mean([g["eff_per"] for g in grp]),
            np.mean([g["raw_per"] for g in grp]),
            np.mean([g["raw_per"] for g in grp]) / np.mean([g["eff_per"] for g in grp]),
            len(grp)))

# The user's exact question: among sec_failed=0, 
# compare those likely "cut off" (low eff) vs "killed reinforcements" (high eff)
# If killing reinforcements gives same XP, raw/eff should be similar
# If killing reinforcements gives NO XP, raw/eff should be lower for high-eff group
print()
print("=== Key test: raw/eff ratio for low-eff vs high-eff in sec_failed=0 ===")
for label, grp in [("low-eff (cut off?)", low), ("high-eff (killed reinf?)", high)]:
    if grp:
        ratios = [g["raw_per"] / g["eff_per"] for g in grp]
        print("%s: raw/eff=%.1f +- %.1f" % (label, np.mean(ratios), np.std(ratios)))
