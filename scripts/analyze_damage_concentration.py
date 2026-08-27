#!/usr/bin/env python3
"""Per-victim damage concentration analysis for DD vs other classes."""
import collections, json, os, sys, numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_ops_replays as ex

PUBLIC_FIELDS = {
    "account_db_id": 0, "name": 1, "team_id": 6, "vehicle_type_id": 7,
    "max_health": 15, "is_alive": 21, "ships_killed": 32,
}
SHIFTING = ["raw_exp", "exp", "scouting_damage", "damage", "resources", "interactions"]

def is_operation(sc):
    return (sc.startswith("WW2_OPERATION") or sc.startswith("PCVO") or sc.startswith("OP_")
            or sc.startswith("Attack_On_Base") or sc == "Defense" or sc.startswith("Dunkirk") or sc.startswith("USS_CL"))

def resolve_public_table(build, cache_dir):
    table = dict(PUBLIC_FIELDS)
    if build is None: return table
    f = Path(cache_dir) / ("%s.json" % build)
    if not f.exists(): return table
    c = json.loads(f.read_text(encoding="utf-8"))
    pub = c.get("CLIENT_PUBLIC_RESULTS_INDICES") or {}
    for k in SHIFTING:
        if k in pub and pub[k] is not None: table[k] = pub[k]
    return table

def interaction_damage_indices(build, cache_dir):
    if build is None: return []
    f = Path(cache_dir) / ("%s.json" % build)
    if not f.exists(): return []
    c = json.loads(f.read_text(encoding="utf-8"))
    veh = c.get("CLIENT_VEH_INTERACTION_DETAILS") or []
    return [i for i, name in enumerate(veh) if name.startswith("damage_")]

def parse_one(path, build, ver, table, dmg_idx):
    meta, packets = ex.read_replay(path)
    results = ex.find_battle_results(packets)
    if results is None: return None
    common = ex.resolve_common(results.get("commonList") or [])
    ppi = results.get("playersPublicInfo") or {}
    entities = {}
    for dbid, arr in ppi.items():
        if not isinstance(arr, list): continue
        p = {k: arr[idx] for k, idx in table.items() if idx < len(arr)}
        if p.get("account_db_id") is None: continue
        p["account_id"] = int(p["account_db_id"])
        p["ship_id"] = p.get("vehicle_type_id")
        entities[p["account_id"]] = p
    humans = [p for p in entities.values() if p["account_id"] > 0]
    if not humans: return None

    # per-victim efficiency for each human
    rows = []
    for p in humans:
        inter = p.get("interactions") or {}
        victim_effs = []
        for victim_id, ival in inter.items():
            if not isinstance(ival, list): continue
            dmg = sum(ival[i] for i in dmg_idx if i < len(ival) and isinstance(ival[i], (int, float)))
            if dmg <= 0: continue
            victim = entities.get(int(victim_id))
            if victim is None: continue
            if victim.get("team_id") == p.get("team_id"): continue
            hp = victim.get("max_health")
            if not hp: continue
            victim_effs.append(dmg / float(hp))
        # compute concentration
        if victim_effs:
            arr = np.array(victim_effs)
            total = arr.sum()
            shares = arr / total if total > 0 else arr
            hhi = float(np.sum(shares ** 2))  # Herfindahl
            top1 = float(np.max(shares)) if total > 0 else 0.0
            top3 = float(np.sum(np.sort(shares)[-3:])) if total > 0 and len(shares) >= 3 else (1.0 if total > 0 else 0.0)
        else:
            total = 0.0; hhi = 0.0; top1 = 0.0; top3 = 0.0
        rows.append({
            "arena_id": common.get("arena_id") or results.get("arenaUniqueID"),
            "account_id": p["account_id"],
            "ship_id": p["ship_id"],
            "raw_exp": p.get("raw_exp"),
            "scouting_damage": p.get("scouting_damage") or 0,
            "n_victims": len(victim_effs),
            "eff_total": total,
            "hhi": hhi,
            "top1_share": top1,
            "top3_share": top3,
        })
    return rows

# load ship cache
ships = json.load(open("ships_cache.json", encoding="utf-8"))
CLASS_MAP = {"Destroyer": "DD", "Cruiser": "CL/CA", "Battleship": "BB", "AirCarrier": "CV", "Submarine": "SS"}
def get_class(sid):
    e = ships.get(str(sid))
    if e and isinstance(e, dict): return CLASS_MAP.get(e.get("type", ""), "CL/CA")
    return "CL/CA"

# discover replays
root = Path("replays")
paths = []
for dp, _, fns in os.walk(root):
    for f in fns:
        if f.endswith(".wowsreplay"): paths.append(Path(dp) / f)

targets = []
metas = {}
for p in paths:
    try:
        m = ex.read_meta_only(str(p))
        sc = str(m.get("scenario") or "")
        b, v = ex.build_and_version(m)
        if is_operation(sc) and b is not None and b >= 9129736:
            targets.append(str(p))
            metas[str(p)] = (b, v)
    except Exception: continue
print("ops replays: %d" % len(targets), file=sys.stderr)

regs = {}
for p in targets:
    b, v = metas[p]
    if b not in regs:
        regs[b] = (b, v, resolve_public_table(b, "constants_cache"), interaction_damage_indices(b, "constants_cache"))

all_rows = []
with ProcessPoolExecutor(max_workers=8) as pool:
    futs = {}
    for p in targets:
        b, v = metas[p]
        futs[pool.submit(parse_one, p, *regs[b])] = p
    done = 0
    for fut in as_completed(futs):
        done += 1
        try:
            g = fut.result()
            if g: all_rows.extend(g)
        except Exception as exc:
            print("SKIP", futs[fut], exc, file=sys.stderr)
        if done % 50 == 0: print("  parsed %d/%d" % (done, len(futs)), file=sys.stderr)
print("parsed %d games, %d rows" % (len(set(r["arena_id"] for r in all_rows)), len(all_rows)), file=sys.stderr)

# add ship_class
for r in all_rows:
    r["ship_class"] = get_class(r["ship_id"])

# filter valid
valid = [r for r in all_rows if r.get("raw_exp") and r["raw_exp"] > 0 and r["eff_total"] > 0]
print("valid rows: %d" % len(valid), file=sys.stderr)

# group by arena
by_arena = collections.defaultdict(list)
for r in valid:
    by_arena[r["arena_id"]].append(r)

recs = []
for arena, grp in by_arena.items():
    team = sum(p["raw_exp"] for p in grp)
    if team <= 0 or len(grp) < 2: continue
    for p in grp:
        recs.append({"arena": arena, "share": p["raw_exp"] / team, **p})

# class concentration stats
print("\n=== DAMAGE CONCENTRATION BY CLASS ===")
for cls in ["DD", "CL/CA", "BB", "CV", "SS"]:
    cls_rows = [z for z in recs if z["ship_class"] == cls]
    if not cls_rows: continue
    print("%s (n=%d):" % (cls, len(cls_rows)))
    print("  n_victims: mean=%.1f, median=%.0f" % (np.mean([z["n_victims"] for z in cls_rows]), np.median([z["n_victims"] for z in cls_rows])))
    print("  eff_total: mean=%.2f" % np.mean([z["eff_total"] for z in cls_rows]))
    print("  HHI: mean=%.3f, median=%.3f" % (np.mean([z["hhi"] for z in cls_rows]), np.median([z["hhi"] for z in cls_rows])))
    print("  top1_share: mean=%.3f" % np.mean([z["top1_share"] for z in cls_rows]))
    print("  top3_share: mean=%.3f" % np.mean([z["top3_share"] for z in cls_rows]))

# regression: add HHI as predictor
cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}
by_arena2 = collections.defaultdict(list)
for z in recs:
    by_arena2[z["arena"]].append(z)

print("\n=== REGRESSION WITH HHI ===")
fields_list = [
    (["eff_total", "scouting_damage"], "baseline"),
    (["eff_total", "scouting_damage", "hhi"], "+HHI"),
    (["eff_total", "scouting_damage", "n_victims"], "+n_victims"),
    (["eff_total", "scouting_damage", "top1_share"], "+top1_share"),
    (["eff_total", "scouting_damage", "hhi", "n_victims"], "+HHI+n_victims"),
]

for fields, label in fields_list:
    n = len(recs)
    n_pred = len(fields)
    n_cls = 5
    X = np.zeros((n, n_pred + n_cls))
    y = np.zeros(n)
    for i, z in enumerate(recs):
        grp = by_arena2[z["arena"]]
        ng = len(grp)
        y[i] = z["share"] - sum(q["share"] for q in grp) / ng
        for j, f in enumerate(fields):
            val = z[f]
            if f == "scouting_damage": val = val / 100000.0
            X[i, j] = val - sum(q[f] / 100000.0 if f == "scouting_damage" else q[f] for q in grp) / ng
        X[i, n_pred + cls_codes[z["ship_class"]]] = 1.0
    cols = list(range(n_pred)) + list(range(n_pred, n_pred + n_cls))
    coef, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
    pred = X[:, cols] @ coef
    r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
    print("%-20s R2=%.4f" % (label, r2), end="")
    for j, f in enumerate(fields):
        if f not in ("eff_total", "scouting_damage"):
            print("  %s=%.5f" % (f, coef[j]), end="")
    print()

# check: do DD have lower HHI?
print("\n=== DD vs CA at same eff_total ===")
# bin by eff_total and compare HHI
bins = [(0, 2), (2, 4), (4, 6), (6, 10), (10, 99)]
for lo, hi in bins:
    dd_rows = [z for z in recs if z["ship_class"] == "DD" and lo <= z["eff_total"] < hi]
    ca_rows = [z for z in recs if z["ship_class"] == "CL/CA" and lo <= z["eff_total"] < hi]
    if dd_rows and ca_rows:
        dd_hhi = np.mean([z["hhi"] for z in dd_rows])
        ca_hhi = np.mean([z["hhi"] for z in ca_rows])
        dd_n = np.mean([z["n_victims"] for z in dd_rows])
        ca_n = np.mean([z["n_victims"] for z in ca_rows])
        print("eff [%d,%d): DD n=%d HHI=%.3f nv=%.1f | CA n=%d HHI=%.3f nv=%.1f" % (lo, hi, len(dd_rows), dd_hhi, dd_n, len(ca_rows), ca_hhi, ca_n))
