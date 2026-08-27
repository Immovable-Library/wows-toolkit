import json, collections, os, sys, numpy as np
from pathlib import Path
sys.path.insert(0, "scripts")
import extract_ops_replays as ex

ships = json.load(open("ships_cache.json", encoding="utf-8"))
CLASS_MAP = {"Destroyer":"DD","Cruiser":"CL/CA","Battleship":"BB","AirCarrier":"CV","Submarine":"SS"}
def get_class(sid):
    e = ships.get(str(sid))
    return CLASS_MAP.get(e.get("type",""),"CL/CA") if e and isinstance(e,dict) else "CL/CA"

PUBLIC_FIELDS = {"account_db_id":0,"name":1,"team_id":6,"vehicle_type_id":7,"max_health":15,"is_alive":21,"ships_killed":32}
SHIFTING = ["raw_exp","exp","scouting_damage","damage","resources","interactions"]

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

def is_operation(sc):
    return (sc.startswith("WW2_OPERATION") or sc.startswith("PCVO") or sc.startswith("OP_")
            or sc.startswith("Attack_On_Base") or sc == "Defense" or sc.startswith("Dunkirk") or sc.startswith("USS_CL"))

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
print("ops replays:", len(targets))

regs = {}
for p in targets:
    b, v = metas[p]
    if b not in regs:
        regs[b] = (b, v, resolve_public_table(b, "constants_cache"), interaction_damage_indices(b, "constants_cache"))

all_rows = []
done = 0
for p in targets:
    b, v = metas[p]
    reg = regs[b]
    try:
        meta, packets = ex.read_replay(p)
        results = ex.find_battle_results(packets)
        if results is None: continue
        common = ex.resolve_common(results.get("commonList") or [])
        ppi = results.get("playersPublicInfo") or {}
        table = reg[2]
        dmg_idx = reg[3]
        entities = {}
        for dbid, arr in ppi.items():
            if not isinstance(arr, list): continue
            pe = {k: arr[idx] for k, idx in table.items() if idx < len(arr)}
            if pe.get("account_db_id") is None: continue
            pe["account_id"] = int(pe["account_db_id"])
            pe["ship_id"] = pe.get("vehicle_type_id")
            entities[pe["account_id"]] = pe
        humans = [pe for pe in entities.values() if pe["account_id"] > 0]
        if not humans: continue
        for pe in humans:
            inter = pe.get("interactions") or {}
            victim_effs = []
            for victim_id, ival in inter.items():
                if not isinstance(ival, list): continue
                dmg = sum(ival[i] for i in dmg_idx if i < len(ival) and isinstance(ival[i], (int, float)))
                if dmg <= 0: continue
                victim = entities.get(int(victim_id))
                if victim is None: continue
                if victim.get("team_id") == pe.get("team_id"): continue
                hp = victim.get("max_health")
                if not hp: continue
                victim_effs.append(dmg / float(hp))
            if victim_effs:
                arr_v = np.array(victim_effs)
                total = arr_v.sum()
                shares = arr_v / total if total > 0 else arr_v
                hhi = float(np.sum(shares ** 2))
                top1 = float(np.max(shares)) if total > 0 else 0.0
                top3 = float(np.sum(np.sort(shares)[-3:])) if total > 0 else 0.0
            else:
                total = 0.0; hhi = 0.0; top1 = 0.0; top3 = 0.0
            all_rows.append({
                "arena_id": common.get("arena_id") or results.get("arenaUniqueID"),
                "account_id": pe["account_id"], "ship_id": pe["ship_id"],
                "raw_exp": pe.get("raw_exp"), "scouting_damage": pe.get("scouting_damage") or 0,
                "n_victims": len(victim_effs), "eff_total": total,
                "hhi": hhi, "top1_share": top1, "top3_share": top3,
            })
    except Exception as exc:
        pass
    done += 1
    if done % 50 == 0: print("  parsed", done, "/", len(targets))

unique_arenas = len(set(r["arena_id"] for r in all_rows))
print("parsed games:", unique_arenas, "rows:", len(all_rows))

for r in all_rows: r["ship_class"] = get_class(r["ship_id"])
valid = [r for r in all_rows if r.get("raw_exp") and r["raw_exp"] > 0 and r["eff_total"] > 0]
print("valid rows:", len(valid))

by_arena = collections.defaultdict(list)
for r in valid: by_arena[r["arena_id"]].append(r)
recs = []
for arena, grp in by_arena.items():
    team = sum(p["raw_exp"] for p in grp)
    if team <= 0 or len(grp) < 2: continue
    for p in grp: recs.append({"arena": arena, "share": p["raw_exp"] / team, **p})

print()
print("=== DAMAGE CONCENTRATION BY CLASS ===")
for cls in ["DD","CL/CA","BB","CV","SS"]:
    cr = [z for z in recs if z["ship_class"] == cls]
    if not cr: continue
    print(cls, "(n=%d):" % len(cr))
    print("  n_victims: mean=%.1f, median=%.0f" % (np.mean([z["n_victims"] for z in cr]), np.median([z["n_victims"] for z in cr])))
    print("  eff_total: mean=%.2f" % np.mean([z["eff_total"] for z in cr]))
    print("  HHI: mean=%.3f, median=%.3f" % (np.mean([z["hhi"] for z in cr]), np.median([z["hhi"] for z in cr])))
    print("  top1_share: mean=%.3f" % np.mean([z["top1_share"] for z in cr]))
    print("  top3_share: mean=%.3f" % np.mean([z["top3_share"] for z in cr]))

cls_codes = {"DD":0,"CL/CA":1,"BB":2,"CV":3,"SS":4}
by_arena2 = collections.defaultdict(list)
for z in recs: by_arena2[z["arena"]].append(z)

print()
print("=== REGRESSION ===")
for fields, label in [
    (["eff_total","scouting_damage"], "baseline"),
    (["eff_total","scouting_damage","hhi"], "+HHI"),
    (["eff_total","scouting_damage","n_victims"], "+n_victims"),
    (["eff_total","scouting_damage","top1_share"], "+top1_share"),
    (["eff_total","scouting_damage","hhi","n_victims"], "+HHI+n_victims"),
]:
    n = len(recs); npred = len(fields); ncls = 5
    X = np.zeros((n, npred + ncls)); y = np.zeros(n)
    for i, z in enumerate(recs):
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
    parts = ["%-20s R2=%.4f" % (label, r2)]
    for j, f in enumerate(fields):
        if f not in ("eff_total","scouting_damage"):
            parts.append("%s=%.5f" % (f, coef[j]))
    print("  ".join(parts))

print()
print("=== DD vs CA at same eff_total ===")
for lo, hi in [(0,2),(2,4),(4,6),(6,10),(10,99)]:
    dd = [z for z in recs if z["ship_class"]=="DD" and lo <= z["eff_total"] < hi]
    ca = [z for z in recs if z["ship_class"]=="CL/CA" and lo <= z["eff_total"] < hi]
    if dd and ca:
        print("eff [%d,%d): DD n=%d HHI=%.3f nv=%.1f | CA n=%d HHI=%.3f nv=%.1f" % (
            lo, hi, len(dd), np.mean([z["hhi"] for z in dd]), np.mean([z["n_victims"] for z in dd]),
            len(ca), np.mean([z["hhi"] for z in ca]), np.mean([z["n_victims"] for z in ca])))
