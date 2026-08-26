import collections
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

sys.path.insert(0, "scripts")
import extract_ops_replays as ex
import extract_ops_efficiency as ee


ROOTS = [r"D:\World_of_Warships\replays", r"D:\codexProject\wows-toolkit\replays\replayswows-pve"]


def build_index():
    idx = {}
    for root in ROOTS:
        if not os.path.isdir(root):
            continue
        for dp, _, fn in os.walk(root):
            for f in fn:
                if f.endswith(".wowsreplay"):
                    idx[f] = os.path.join(dp, f)
    return idx


def parse_one(path, build, cache):
    meta, packets = ex.read_replay(path)
    res = ex.find_battle_results(packets)
    if not res:
        return []
    common = ex.resolve_common(res.get("commonList") or [])
    arena = common.get("arena_id") or res.get("arenaUniqueID")
    ppi = res.get("playersPublicInfo") or {}
    table = dict(ee.PUBLIC_FIELDS)
    table.update(ee.resolve_public_table(build, "constants_cache"))
    bc_path = os.path.join("constants_cache", "%s.json" % build)
    bc = None
    if os.path.exists(bc_path):
        bc = json.load(open(bc_path, encoding="utf-8"))
        pub_idx = bc.get("CLIENT_PUBLIC_RESULTS_INDICES") or {}
        if pub_idx.get("buildingInteractions") is not None:
            table["buildingInteractions"] = pub_idx["buildingInteractions"]
    dmg_idx = ee.interaction_damage_indices(build, "constants_cache")
    if not dmg_idx:
        return []

    bdet = (bc.get("CLIENT_BUILDING_INTERACTION_DETAILS") or []) if bc else []
    b_idx = {n: i for i, n in enumerate(bdet)}
    b_dmg = [i for n, i in b_idx.items() if n.startswith("building_damage_")]
    b_killed = b_idx.get("building_killed")

    entities = {}
    for dbid, arr in ppi.items():
        if not isinstance(arr, list):
            continue
        p = {k: arr[idx] for k, idx in table.items() if idx < len(arr)}
        if p.get("account_db_id") is None:
            continue
        p["account_id"] = int(p["account_db_id"])
        p["label"] = str(arr[1]) if len(arr) > 1 else ""
        p["ship_id"] = p.get("vehicle_type_id")
        entities[p["account_id"]] = p

    out = []
    for p in entities.values():
        if p["account_id"] <= 0:
            continue
        inter = p.get("interactions") or {}
        eff_ship = 0.0
        eff_noncombat = 0.0
        for victim_id, ival in inter.items():
            if not isinstance(ival, list):
                continue
            dmg = 0.0
            for i in dmg_idx:
                if i < len(ival) and isinstance(ival[i], (int, float)):
                    dmg += ival[i]
            if dmg <= 0:
                continue
            victim = entities.get(int(victim_id))
            if victim is None or victim.get("team_id") == p.get("team_id"):
                continue
            hp = victim.get("max_health")
            if not hp:
                continue
            label = victim.get("label", "").upper()
            is_noncombat = any(k in label for k in ("TRANSPORT", "BOAT", "TORPEDO", "CARGO", "COMMUNICATION"))
            if is_noncombat:
                eff_noncombat += dmg / float(hp)
            else:
                eff_ship += dmg / float(hp)

        bi = p.get("buildingInteractions") or {}
        b_damage = 0.0
        b_kill_flag = 0
        for bid, bval in bi.items():
            if not isinstance(bval, list):
                continue
            for i in b_dmg:
                if i < len(bval) and isinstance(bval[i], (int, float)):
                    b_damage += bval[i]
            if b_killed is not None and b_killed < len(bval):
                b_kill_flag += 1 if bval[b_killed] else 0
        out.append({
            "arena_id": arena,
            "account_id": p["account_id"],
            "eff_ship": eff_ship,
            "eff_noncombat": eff_noncombat,
            "building_damage": b_damage,
            "building_kills": b_kill_flag,
        })
    return out


def main():
    rows = [json.loads(l) for l in open("ops_efficiency_full.jsonl", encoding="utf-8")]
    idx = build_index()
    sources = {r["source"] for r in rows}
    cache = json.load(open("ships_cache.json", encoding="utf-8"))

    jobs = []
    for s in sources:
        p = idx.get(s)
        if not p:
            continue
        r = next((x for x in rows if x["source"] == s), None)
        if r is None:
            continue
        jobs.append((p, r["build"]))

    cache_path = "output/noncombat_contrib.jsonl"
    contribs = []
    if os.path.exists(cache_path):
        contribs = [json.loads(l) for l in open(cache_path, encoding="utf-8")]
    else:
        with ProcessPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(parse_one, p, b, cache): p for p, b in jobs}
            for fut in as_completed(futs):
                got = fut.result()
                if got:
                    contribs.extend(got)
        with open(cache_path, "w", encoding="utf-8") as fh:
            for c in contribs:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    by = {}
    for c in contribs:
        by[(c["arena_id"], c["account_id"])] = c

    matches = collections.defaultdict(list)
    for r in rows:
        if not r.get("raw_exp") or r.get("raw_exp") <= 0:
            continue
        c = by.get((r["arena_id"], r["account_id"]), {})
        matches[r["arena_id"]].append({
            "account_id": r["account_id"],
            "ship_class": r["ship_class"],
            "raw_exp": r["raw_exp"],
            "scouting_damage": r["scouting_damage"] or 0,
            "eff_ship": c.get("eff_ship", 0.0),
            "eff_noncombat": c.get("eff_noncombat", 0.0),
            "building_damage": c.get("building_damage", 0.0),
            "building_kills": c.get("building_kills", 0),
        })

    recs = []
    for arena, grp in matches.items():
        team = sum((p["raw_exp"] or 0) for p in grp)
        if team <= 0 or len(grp) < 2:
            continue
        for p in grp:
            share = (p["raw_exp"] or 0) / team
            if share <= 0:
                continue
            recs.append({
                "arena": arena,
                "cls": p["ship_class"],
                "y": share,
                "x": {
                    "eff_ship": p["eff_ship"],
                    "eff_noncombat": p["eff_noncombat"],
                    "scout": p["scouting_damage"] / 100000.0,
                    "bdmg": p["building_damage"] / 100000.0,
                    "bkill": float(p["building_kills"]),
                },
            })

    by_arena = collections.defaultdict(list)
    for z in recs:
        by_arena[z["arena"]].append(z)

    cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}
    features = ["eff_ship", "eff_noncombat", "scout", "bdmg", "bkill"]
    n_pred = len(features)
    X = np.zeros((len(recs), n_pred + 5))
    y = np.zeros(len(recs))
    for i, z in enumerate(recs):
        grp = by_arena[z["arena"]]
        y[i] = z["y"] - sum(q["y"] for q in grp) / len(grp)
        for j, f in enumerate(features):
            X[i, j] = z["x"][f] - sum(q["x"][f] for q in grp) / len(grp)
        X[i, n_pred + cls_codes[z["cls"]]] = 1.0

    def fit(cols):
        A = X[:, cols]
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        pred = A @ coef
        r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
        return coef, r2

    cls_cols = list(range(n_pred, n_pred + 5))
    coef_base, r2_base = fit([0, 2] + cls_cols)
    coef_nc, r2_nc = fit([0, 1, 2] + cls_cols)
    coef_full, r2_full = fit(list(range(n_pred)) + cls_cols)

    print("n=%d" % len(recs))
    print("ship_eff + scout + class        : R2=%.4f" % r2_base)
    print("  + noncombat ship_eff          : R2=%.4f" % r2_nc)
    print("  + building dmg/kill           : R2=%.4f" % r2_full)
    print("\nfull model coefficients (share per unit):")
    for j, f in enumerate(features):
        print("  %-14s %.5f" % (f, coef_full[j]))

    out = {
        "n": len(recs),
        "r2_base": round(r2_base, 4),
        "r2_noncombat": round(r2_nc, 4),
        "r2_full": round(r2_full, 4),
        "coef": {f: round(float(coef_full[j]), 5) for j, f in enumerate(features)},
    }
    with open("output/noncombat_analysis.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("\nresults -> output/noncombat_analysis.json")


if __name__ == "__main__":
    main()
