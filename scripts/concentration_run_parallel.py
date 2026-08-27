#!/usr/bin/env python3
"""Parallel variant of concentration_run.py (HHI per-victim concentration)."""
import json, collections, os, sys, numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_ops_replays as ex


ships = json.load(open("ships_cache.json", encoding="utf-8"))
CLASS_MAP = {"Destroyer": "DD", "Cruiser": "CL/CA", "Battleship": "BB",
             "AirCarrier": "CV", "Submarine": "SS"}


def get_class(sid):
    e = ships.get(str(sid))
    return CLASS_MAP.get(e.get("type", ""), "CL/CA") if e and isinstance(e, dict) else "CL/CA"


PUBLIC_FIELDS = {"account_db_id": 0, "name": 1, "team_id": 6, "vehicle_type_id": 7,
                 "max_health": 15, "is_alive": 21, "ships_killed": 32}
SHIFTING = ["raw_exp", "exp", "scouting_damage", "damage", "resources", "interactions"]


def resolve_public_table(build, cache_dir):
    table = dict(PUBLIC_FIELDS)
    if build is None:
        return table
    f = Path(cache_dir) / ("%s.json" % build)
    if not f.exists():
        return table
    c = json.loads(f.read_text(encoding="utf-8"))
    pub = c.get("CLIENT_PUBLIC_RESULTS_INDICES") or {}
    for k in SHIFTING:
        if k in pub and pub[k] is not None:
            table[k] = pub[k]
    return table


def interaction_damage_indices(build, cache_dir):
    if build is None:
        return []
    f = Path(cache_dir) / ("%s.json" % build)
    if not f.exists():
        return []
    c = json.loads(f.read_text(encoding="utf-8"))
    veh = c.get("CLIENT_VEH_INTERACTION_DETAILS") or []
    return [i for i, name in enumerate(veh) if name.startswith("damage_")]


def is_operation(sc):
    return (sc.startswith("WW2_OPERATION") or sc.startswith("PCVO") or sc.startswith("OP_")
            or sc.startswith("Attack_On_Base") or sc == "Defense" or sc.startswith("Dunkirk")
            or sc.startswith("USS_CL"))


def parse_game(path, reg):
    b, v, table, dmg_idx = reg
    meta, packets = ex.read_replay(path)
    results = ex.find_battle_results(packets)
    if results is None:
        return None
    common = ex.resolve_common(results.get("commonList") or [])
    ppi = results.get("playersPublicInfo") or {}
    entities = {}
    for dbid, arr in ppi.items():
        if not isinstance(arr, list):
            continue
        pe = {k: arr[idx] for k, idx in table.items() if idx < len(arr)}
        if pe.get("account_db_id") is None:
            continue
        pe["account_id"] = int(pe["account_db_id"])
        pe["ship_id"] = pe.get("vehicle_type_id")
        entities[pe["account_id"]] = pe
    humans = [pe for pe in entities.values() if pe["account_id"] > 0]
    if not humans:
        return None
    out = []
    for pe in humans:
        inter = pe.get("interactions") or {}
        victim_effs = []
        for victim_id, ival in inter.items():
            if not isinstance(ival, list):
                continue
            dmg = sum(ival[i] for i in dmg_idx if i < len(ival) and isinstance(ival[i], (int, float)))
            if dmg <= 0:
                continue
            victim = entities.get(int(victim_id))
            if victim is None:
                continue
            if victim.get("team_id") == pe.get("team_id"):
                continue
            hp = victim.get("max_health")
            if not hp:
                continue
            victim_effs.append(dmg / float(hp))
        if victim_effs:
            arr_v = np.array(victim_effs)
            total = arr_v.sum()
            shares = arr_v / total if total > 0 else arr_v
            hhi = float(np.sum(shares ** 2))
            top1 = float(np.max(shares)) if total > 0 else 0.0
            top3 = float(np.sum(np.sort(shares)[-3:])) if total > 0 else 0.0
        else:
            total = 0.0
            hhi = 0.0
            top1 = 0.0
            top3 = 0.0
        out.append({
            "arena_id": common.get("arena_id") or results.get("arenaUniqueID"),
            "account_id": pe["account_id"], "ship_id": pe["ship_id"],
            "raw_exp": pe.get("raw_exp"), "scouting_damage": pe.get("scouting_damage") or 0,
            "n_victims": len(victim_effs), "eff_total": total,
            "hhi": hhi, "top1_share": top1, "top3_share": top3,
        })
    return out


def main():
    root = Path("replays")
    paths = []
    for dp, _, fns in os.walk(root):
        for f in fns:
            if f.endswith(".wowsreplay"):
                paths.append(Path(dp) / f)

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
        except Exception:
            continue
    print("ops replays:", len(targets), file=sys.stderr)

    regs = {}
    for p in targets:
        b, v = metas[p]
        if b not in regs:
            regs[b] = (b, v, resolve_public_table(b, "constants_cache"),
                       interaction_damage_indices(b, "constants_cache"))

    all_rows = []
    done = 0
    with ProcessPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(parse_game, p, regs[metas[p][0]]): p for p in targets}
        for fut in as_completed(futs):
            done += 1
            try:
                rows = fut.result()
                if rows:
                    all_rows.extend(rows)
            except Exception:
                pass
            if done % 50 == 0:
                print("  parsed", done, "/", len(targets), file=sys.stderr)

    for r in all_rows:
        r["ship_class"] = get_class(r["ship_id"])
    seen = set()
    dedup_rows = []
    dup = 0
    for r in all_rows:
        key = (r.get("arena_id"), r.get("account_id"))
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        dedup_rows.append(r)
    valid = [r for r in dedup_rows if r.get("raw_exp") and r["raw_exp"] > 0 and r["eff_total"] > 0]
    print("parsed rows:", len(all_rows), "dup rows:", dup, "valid rows:", len(valid), file=sys.stderr)

    by_arena = collections.defaultdict(list)
    for r in valid:
        by_arena[r["arena_id"]].append(r)
    recs = []
    for arena, grp in by_arena.items():
        team = sum(p["raw_exp"] for p in grp)
        if team <= 0 or len(grp) < 2:
            continue
        for p in grp:
            recs.append({"arena": arena, "share": p["raw_exp"] / team, **p})

    print("\n=== DAMAGE CONCENTRATION BY CLASS ===")
    class_stats = {}
    for cls in ["DD", "CL/CA", "BB", "CV", "SS"]:
        cr = [z for z in recs if z["ship_class"] == cls]
        if not cr:
            continue
        s = {
            "n": len(cr),
            "n_victims_mean": float(np.mean([z["n_victims"] for z in cr])),
            "eff_total_mean": float(np.mean([z["eff_total"] for z in cr])),
            "hhi_mean": float(np.mean([z["hhi"] for z in cr])),
            "hhi_median": float(np.median([z["hhi"] for z in cr])),
            "top1_share_mean": float(np.mean([z["top1_share"] for z in cr])),
            "top3_share_mean": float(np.mean([z["top3_share"] for z in cr])),
        }
        class_stats[cls] = s
        print("%s (n=%d):" % (cls, s["n"]))
        print("  n_victims: mean=%.1f" % s["n_victims_mean"])
        print("  eff_total: mean=%.2f" % s["eff_total_mean"])
        print("  HHI: mean=%.3f, median=%.3f" % (s["hhi_mean"], s["hhi_median"]))
        print("  top1_share: mean=%.3f" % s["top1_share_mean"])
        print("  top3_share: mean=%.3f" % s["top3_share_mean"])

    cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}
    by_arena2 = collections.defaultdict(list)
    for z in recs:
        by_arena2[z["arena"]].append(z)

    print("\n=== REGRESSION ===")
    reg_results = {}
    for fields, label in [
        (["eff_total", "scouting_damage"], "baseline"),
        (["eff_total", "scouting_damage", "hhi"], "+HHI"),
        (["eff_total", "scouting_damage", "n_victims"], "+n_victims"),
        (["eff_total", "scouting_damage", "top1_share"], "+top1_share"),
        (["eff_total", "scouting_damage", "hhi", "n_victims"], "+HHI+n_victims"),
    ]:
        n = len(recs)
        npred = len(fields)
        ncls = 5
        X = np.zeros((n, npred + ncls))
        y = np.zeros(n)
        for i, z in enumerate(recs):
            grp = by_arena2[z["arena"]]
            ng = len(grp)
            y[i] = z["share"] - sum(q["share"] for q in grp) / ng
            for j, f in enumerate(fields):
                val = z[f]
                if f == "scouting_damage":
                    val = val / 100000.0
                X[i, j] = val - sum(q[f] / 100000.0 if f == "scouting_damage" else q[f] for q in grp) / ng
            X[i, npred + cls_codes[z["ship_class"]]] = 1.0
        cols = list(range(npred)) + list(range(npred, npred + ncls))
        coef, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
        pred = X[:, cols] @ coef
        r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
        parts = ["%-20s R2=%.4f" % (label, r2)]
        for j, f in enumerate(fields):
            if f not in ("eff_total", "scouting_damage"):
                parts.append("%s=%.5f" % (f, coef[j]))
        print("  ".join(parts))
        reg_results[label] = {"r2": r2, "coef": [float(c) for c in coef], "fields": fields}

    with open("output/concentration_full.json", "w", encoding="utf-8") as fh:
        json.dump({"n_recs": len(recs), "class_stats": class_stats, "regressions": reg_results},
                  fh, ensure_ascii=False, indent=2)
    print("results -> output/concentration_full.json", file=sys.stderr)


if __name__ == "__main__":
    main()
