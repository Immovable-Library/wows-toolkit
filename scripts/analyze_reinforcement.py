import json, collections, numpy as np

rows = [json.loads(l) for l in open("ops_efficiency_full.jsonl", encoding="utf-8")]
valid = [r for r in rows if r.get("efficiency") is not None and r.get("raw_exp") is not None and r["raw_exp"] > 0]

by_arena = collections.defaultdict(list)
for r in valid:
    by_arena[r["arena_id"]].append(r)

recs = []
for arena, grp in by_arena.items():
    sec_comp = grp[0].get("secondary_completed")
    sec_total = grp[0].get("secondary_total")
    if sec_total is None or sec_comp is None or sec_total == 0:
        continue
    sc = grp[0].get("scenario_family", "")
    n_failed = sec_total - sec_comp
    
    team_eff = sum(p["efficiency"] for p in grp)
    team_raw = sum(p["raw_exp"] for p in grp)
    n_players = len(grp)
    
    if team_eff <= 0: continue
    
    if sc == "WW2_OP(new)":
        reinf_eff_total = max(0, n_failed * 1.04 * n_players)
    else:
        reinf_eff_total = 0
    
    reinf_eff_total = min(reinf_eff_total, team_eff * 0.5)
    
    for p in grp:
        share = p["raw_exp"] / team_raw if team_raw > 0 else 0
        eff = p["efficiency"]
        eff_share = eff / team_eff if team_eff > 0 else 0
        reinf_eff = eff_share * reinf_eff_total
        regular_eff = eff - reinf_eff
        
        recs.append({
            "arena": arena, "share": share,
            "eff_total": eff, "eff_regular": regular_eff, "eff_reinforcement": reinf_eff,
            "scouting_damage": p.get("scouting_damage") or 0,
            "ship_class": p.get("ship_class", "CL/CA"),
            "scenario": sc, "n_failed": n_failed,
        })

print("Total recs:", len(recs))

ww2 = [r for r in recs if r["scenario"] == "WW2_OP(new)"]
print("WW2_OP recs:", len(ww2))

cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}

def run_reg(recs_list, fields, label):
    by_arena2 = collections.defaultdict(list)
    for z in recs_list:
        by_arena2[z["arena"]].append(z)
    n = len(recs_list); npred = len(fields); ncls = 5
    X = np.zeros((n, npred + ncls)); y = np.zeros(n)
    for i, z in enumerate(recs_list):
        grp = by_arena2[z["arena"]]; ng = len(grp)
        y[i] = z["share"] - sum(q["share"] for q in grp) / ng
        for j, f in enumerate(fields):
            val = z[f]
            if f == "scouting_damage": val = val / 100000.0
            X[i, j] = val - sum(q[f] / 100000.0 if f == "scouting_damage" else q[f] for q in grp) / ng
        X[i, npred + cls_codes[z["ship_class"]]] = 1.0
    cols = list(range(npred)) + list(range(npred, npred + ncls))
    coef, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
    pred = X[:, cols] @ coef
    r2 = 1 - float(np.sum((y - pred)**2) / np.sum((y - y.mean())**2))
    print("%s: R2=%.4f" % (label, r2))
    for j, f in enumerate(fields):
        print("  %s: %.6f" % (f, coef[j]))
    for j, cls in enumerate(["DD","CL/CA","BB","CV","SS"]):
        if cls == "CL/CA": continue
        print("  K_%s: %.6f" % (cls, coef[npred+j]))

print()
print("=== WW2_OP ===")
run_reg(ww2, ["eff_total", "scouting_damage"], "baseline")
run_reg(ww2, ["eff_regular", "eff_reinforcement", "scouting_damage"], "split reg/reinf")

print()
print("=== ALL GAMES ===")
run_reg(recs, ["eff_total", "scouting_damage"], "baseline")
run_reg(recs, ["eff_regular", "eff_reinforcement", "scouting_damage"], "split reg/reinf")

# Summary stats
print()
rein_mean = np.mean([z["eff_reinforcement"] for z in ww2])
tot_mean = np.mean([z["eff_total"] for z in ww2])
print("WW2_OP reinf_eff mean:", round(rein_mean, 3))
print("WW2_OP total_eff mean:", round(tot_mean, 3))
print("WW2_OP reinf fraction:", round(rein_mean / tot_mean, 3) if tot_mean > 0 else 0)
