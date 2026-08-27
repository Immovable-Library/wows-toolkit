import json, collections, numpy as np

rows = [json.loads(l) for l in open("ops_efficiency_full.jsonl", encoding="utf-8")]
valid = [r for r in rows if r.get("efficiency") is not None and r.get("raw_exp") is not None and r["raw_exp"] > 0]

by_arena = collections.defaultdict(list)
for r in valid:
    by_arena[r["arena_id"]].append(r)

# Build player-level data with game-level stats
recs = []
for arena, grp in by_arena.items():
    sec_comp = grp[0].get("secondary_completed")
    sec_total = grp[0].get("secondary_total")
    if sec_total is None or sec_comp is None or sec_total == 0:
        continue
    n_failed = sec_total - sec_comp
    sc = grp[0].get("scenario_family", "")
    team_eff = sum(p["efficiency"] for p in grp)
    team_raw = sum(p["raw_exp"] for p in grp)
    n = len(grp)
    game_eff_per = team_eff / n
    for p in grp:
        recs.append({
            "arena": arena,
            "share": p["raw_exp"] / team_raw,
            "eff": p["efficiency"],
            "scout": p.get("scouting_damage") or 0,
            "ship_class": p.get("ship_class", "CL/CA"),
            "sec_failed": n_failed,
            "scenario": sc,
            "game_eff_per": game_eff_per,
            "game_eff_total": team_eff,
            "game_raw_total": team_raw,
        })

cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}

# Test 1: The key question - does sec_failed matter AFTER controlling for game_eff?
# Run within each scenario, regress share ~ eff + scout + class + game_eff_per + sec_failed
print("=== Test 1: share ~ eff + scout + class + game_eff_per + sec_failed ===")
print("If sec_failed matters after controlling for game_eff, the dilution is specific to reinforcements")
print("If sec_failed disappears after controlling for game_eff, the dilution is just game duration")

for sc in ["PCVO(legacy_op)", "WW2_OP(new)"]:
    sc_recs = [r for r in recs if r["scenario"] == sc]
    if len(sc_recs) < 100:
        continue
    
    by_a = collections.defaultdict(list)
    for r in sc_recs:
        by_a[r["arena"]].append(r)
    
    # Model 1: eff + scout + class + game_eff_per
    # Model 2: eff + scout + class + game_eff_per + sec_failed
    for fields, label in [
        (["eff", "scout", "game_eff_per"], "base"),
        (["eff", "scout", "game_eff_per", "sec_failed"], "+sec_failed"),
    ]:
        n = len(sc_recs); npred = len(fields)
        X = np.zeros((n, npred + 5)); y = np.zeros(n)
        for i, z in enumerate(sc_recs):
            grp = by_a[z["arena"]]; ng = len(grp)
            y[i] = z["share"] - sum(q["share"] for q in grp) / ng
            for j, f in enumerate(fields):
                val = z[f]
                if f == "scout": val = val / 100000.0
                X[i, j] = val - sum(q[f] / 100000.0 if f == "scout" else q[f] for q in grp) / ng
            X[i, npred + cls_codes[z["ship_class"]]] = 1.0
        cols = list(range(npred)) + list(range(npred, npred + 5))
        coef, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
        pred = X[:, cols] @ coef
        r2 = 1 - float(np.sum((y - pred)**2) / np.sum((y - y.mean())**2))
        print("  %s [%s]: R2=%.4f" % (label, sc, r2), end="")
        for j, f in enumerate(fields):
            if f in ("game_eff_per", "sec_failed"):
                print("  %s=%.6f" % (f, coef[j]), end="")
        print()

# Test 2: game-level regression
# team_raw_per ~ team_eff_per + sec_failed + scenario_dummies
print()
print("=== Test 2: Game-level: raw_per ~ eff_per + sec_failed (with scenario FE) ===")
games = {}
for arena, grp in by_arena.items():
    sec_comp = grp[0].get("secondary_completed")
    sec_total = grp[0].get("secondary_total")
    if sec_total is None or sec_comp is None or sec_total == 0:
        continue
    team_eff = sum(p["efficiency"] for p in grp)
    team_raw = sum(p["raw_exp"] for p in grp)
    n = len(grp)
    games[arena] = {
        "eff_per": team_eff / n,
        "raw_per": team_raw / n,
        "sec_failed": sec_total - sec_comp,
        "scenario": grp[0].get("scenario_family", ""),
        "scenario_name": grp[0].get("scenario", ""),
    }

game_list = list(games.values())
# Get unique scenario names
sc_names = sorted(set(g["scenario_name"] for g in game_list))
sc_map = {s: i for i, s in enumerate(sc_names)}

X = np.zeros((len(game_list), 3 + len(sc_map)))
y = np.zeros(len(game_list))
for i, g in enumerate(game_list):
    y[i] = g["raw_per"]
    X[i, 0] = g["eff_per"]
    X[i, 1] = g["sec_failed"]
    X[i, 2] = g["eff_per"] * g["sec_failed"]
    X[i, 3 + sc_map[g["scenario_name"]]] = 1.0

cols = list(range(3 + len(sc_map)))
coef, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
pred = X[:, cols] @ coef
r2 = 1 - float(np.sum((y - pred)**2) / np.sum((y - y.mean())**2))
print("R2=%.4f" % r2)
print("eff_per: %.1f" % coef[0])
print("sec_failed: %.1f" % coef[1])
print("eff_per * sec_failed: %.1f" % coef[2])
print("-> If sec_failed is negative after controlling for eff_per, reinforcements reduce XP")
print("-> If interaction is negative, reinforcement eff is worth less per unit")

# Test 3: The simplest test - within same scenario, does sec_failed predict raw/eff?
print()
print("=== Test 3: Game-level raw/eff ~ sec_failed (within scenario) ===")
for sc_name in sorted(set(g["scenario_name"] for g in game_list)):
    grp = [g for g in game_list if g["scenario_name"] == sc_name]
    if len(grp) < 20:
        continue
    # regress raw_per ~ eff_per + sec_failed
    X = np.zeros((len(grp), 2))
    y = np.zeros(len(grp))
    for i, g in enumerate(grp):
        y[i] = g["raw_per"]
        X[i, 0] = g["eff_per"]
        X[i, 1] = g["sec_failed"]
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    print("  %s (n=%d): eff=%.0f, sec_failed=%.0f" % (sc_name[:50], len(grp), coef[0], coef[1]))
