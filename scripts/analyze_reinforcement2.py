import json, collections, numpy as np

rows = [json.loads(l) for l in open("ops_efficiency_full.jsonl", encoding="utf-8")]
valid = [r for r in rows if r.get("efficiency") is not None and r.get("raw_exp") is not None and r["raw_exp"] > 0]

by_arena = collections.defaultdict(list)
for r in valid:
    by_arena[r["arena_id"]].append(r)

cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}

def run_player_reg(recs_list, label):
    by_a = collections.defaultdict(list)
    for z in recs_list:
        by_a[z["arena"]].append(z)
    fields = ["eff_total", "scouting_damage"]
    npred = len(fields); n = len(recs_list)
    X = np.zeros((n, npred + 5)); y = np.zeros(n)
    for i, z in enumerate(recs_list):
        grp = by_a[z["arena"]]; ng = len(grp)
        y[i] = z["share"] - sum(q["share"] for q in grp) / ng
        X[i, 0] = z["eff_total"] - sum(q["eff_total"] for q in grp) / ng
        X[i, 1] = z["scouting_damage"] / 100000.0 - sum(q["scouting_damage"] / 100000.0 for q in grp) / ng
        X[i, npred + cls_codes[z["ship_class"]]] = 1.0
    cols = list(range(npred)) + list(range(npred, npred + 5))
    coef, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
    pred = X[:, cols] @ coef
    r2 = 1 - float(np.sum((y - pred)**2) / np.sum((y - y.mean())**2))
    print("%s (n=%d): R2=%.4f, eff=%.6f, scout=%.6f" % (label, n, r2, coef[0], coef[1]))
    for j, cls in enumerate(["DD","CL/CA","BB","CV","SS"]):
        if cls == "CL/CA": continue
        print("  K_%s=%.6f" % (cls, coef[npred+j]))

# Build player-level recs grouped by sec_failed
recs_by_fail = collections.defaultdict(list)
for arena, grp in by_arena.items():
    sec_comp = grp[0].get("secondary_completed")
    sec_total = grp[0].get("secondary_total")
    if sec_total is None or sec_comp is None or sec_total == 0:
        continue
    n_failed = sec_total - sec_comp
    team_raw = sum(p["raw_exp"] for p in grp)
    if team_raw <= 0: continue
    for p in grp:
        recs_by_fail[n_failed].append({
            "arena": arena,
            "share": p["raw_exp"] / team_raw,
            "eff_total": p["efficiency"],
            "scouting_damage": p.get("scouting_damage") or 0,
            "ship_class": p.get("ship_class", "CL/CA"),
        })

print("=== Separate regressions by sec_failed ===")
print("If reinforcement damage = 0 XP, eff coefficient should be LOWER in high sec_failed games")
for nf in sorted(recs_by_fail.keys()):
    run_player_reg(recs_by_fail[nf], "sec_failed=%d" % nf)

# Also: game-level regression with more control
print()
print("=== Game-level: team_raw_per ~ team_eff_per + sec_failed + interaction ===")
arena_stats = []
for arena, grp in by_arena.items():
    sec_comp = grp[0].get("secondary_completed")
    sec_total = grp[0].get("secondary_total")
    if sec_total is None or sec_comp is None or sec_total == 0:
        continue
    team_eff = sum(p["efficiency"] for p in grp)
    team_raw = sum(p["raw_exp"] for p in grp)
    n = len(grp)
    arena_stats.append({
        "eff_per": team_eff / n,
        "raw_per": team_raw / n,
        "sec_failed": sec_total - sec_comp,
        "scenario": grp[0].get("scenario_family", ""),
    })

# Add scenario dummies
scenarios = sorted(set(a["scenario"] for a in arena_stats))
sc_map = {s: i for i, s in enumerate(scenarios)}

X = np.zeros((len(arena_stats), 2 + len(sc_map)))
y = np.zeros(len(arena_stats))
for i, a in enumerate(arena_stats):
    y[i] = a["raw_per"]
    X[i, 0] = a["eff_per"]
    X[i, 1] = a["eff_per"] * a["sec_failed"]
    X[i, 2 + sc_map[a["scenario"]]] = 1.0
cols = list(range(2 + len(sc_map)))
coef, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
pred = X[:, cols] @ coef
r2 = 1 - float(np.sum((y - pred)**2) / np.sum((y - y.mean())**2))
print("R2=%.4f" % r2)
print("eff_per: %.1f" % coef[0])
print("eff_per * sec_failed: %.1f" % coef[1])
print("-> negative = reinforcement eff worth less; positive = worth more")
