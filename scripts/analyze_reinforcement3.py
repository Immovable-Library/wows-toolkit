import json, collections, numpy as np

rows = [json.loads(l) for l in open("ops_efficiency_full.jsonl", encoding="utf-8")]
valid = [r for r in rows if r.get("efficiency") is not None and r.get("raw_exp") is not None and r["raw_exp"] > 0]

by_arena = collections.defaultdict(list)
for r in valid:
    by_arena[r["arena_id"]].append(r)

cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}

# Build player-level data with sec_failed
recs = []
for arena, grp in by_arena.items():
    sec_comp = grp[0].get("secondary_completed")
    sec_total = grp[0].get("secondary_total")
    if sec_total is None or sec_comp is None or sec_total == 0:
        continue
    n_failed = sec_total - sec_comp
    team_raw = sum(p["raw_exp"] for p in grp)
    if team_raw <= 0: continue
    for p in grp:
        recs.append({
            "arena": arena,
            "share": p["raw_exp"] / team_raw,
            "eff_total": p["efficiency"],
            "scouting_damage": p.get("scouting_damage") or 0,
            "ship_class": p.get("ship_class", "CL/CA"),
            "sec_failed": n_failed,
        })

by_a = collections.defaultdict(list)
for z in recs:
    by_a[z["arena"]].append(z)

print("=== Player-level: adding sec_failed as control ===")
for fields, label in [
    (["eff_total", "scouting_damage"], "baseline"),
    (["eff_total", "scouting_damage", "sec_failed"], "+sec_failed"),
]:
    npred = len(fields); n = len(recs)
    X = np.zeros((n, npred + 5)); y = np.zeros(n)
    for i, z in enumerate(recs):
        grp = by_a[z["arena"]]; ng = len(grp)
        y[i] = z["share"] - sum(q["share"] for q in grp) / ng
        for j, f in enumerate(fields):
            val = z[f]
            if f == "scouting_damage": val = val / 100000.0
            X[i, j] = val - sum(q[f] / 100000.0 if f == "scouting_damage" else q[f] for q in grp) / ng
        X[i, npred + cls_codes[z["ship_class"]]] = 1.0
    cols = list(range(npred)) + list(range(npred, npred + 5))
    coef, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
    pred = X[:, cols] @ coef
    r2 = 1 - float(np.sum((y - pred)**2) / np.sum((y - y.mean())**2))
    print("%s: R2=%.4f" % (label, r2))
    for j, f in enumerate(fields):
        print("  %s: %.6f" % (f, coef[j]))
    for j, cls in enumerate(["DD","CL/CA","BB","CV","SS"]):
        if cls == "CL/CA": continue
        print("  K_%s: %.6f" % (cls, coef[npred+j]))
