"""Does killing a higher-tier AI ship pay more per ship-equivalent?

The existing allocation model credits a full kill of any ship as 1.0 ship-
equivalent (damage / max_hp), so a tier 11 and a tier 9 kill are equal there.
Here we split each player's efficiency by victim tier and test, within match,
whether the XP share per ship-equivalent differs by the victim's tier.
"""
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


def resolve_ship_tier(ship_id, cache):
    info = cache.get(str(ship_id))
    return info.get("tier") if info else None


def parse_one(path, build, cache):
    meta, packets = ex.read_replay(path)
    res = ex.find_battle_results(packets)
    if not res:
        return []
    common = ex.resolve_common(res.get("commonList") or [])
    arena = common.get("arena_id") or res.get("arenaUniqueID")
    ppi = res.get("playersPublicInfo") or {}
    table = dict(ee.PUBLIC_FIELDS)
    shifted = ee.resolve_public_table(build, "constants_cache")
    table.update(shifted)
    dmg_idx = ee.interaction_damage_indices(build, "constants_cache")
    if not dmg_idx:
        return []

    entities = {}
    for dbid, arr in ppi.items():
        if not isinstance(arr, list):
            continue
        p = {k: arr[idx] for k, idx in table.items() if idx < len(arr)}
        if p.get("account_db_id") is None:
            continue
        p["account_id"] = int(p["account_db_id"])
        p["tier"] = resolve_ship_tier(p.get("vehicle_type_id"), cache)
        entities[p["account_id"]] = p

    out = []
    for p in entities.values():
        if p["account_id"] <= 0:
            continue
        inter = p.get("interactions") or {}
        buckets = collections.defaultdict(float)
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
            t = victim.get("tier") or 0
            if t <= 5:
                bucket = "t4_5"
            elif t <= 7:
                bucket = "t6_7"
            elif t <= 9:
                bucket = "t8_9"
            else:
                bucket = "t10_11"
            buckets[bucket] += dmg / float(hp)
        if buckets:
            out.append({
                "arena_id": arena,
                "account_id": p["account_id"],
                "bucket_eff": dict(buckets),
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

    cache_path = "output/victim_tier_contrib.jsonl"
    contribs = []
    if os.path.exists(cache_path):
        for line in open(cache_path, encoding="utf-8"):
            contribs.append(json.loads(line))
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

    by = collections.defaultdict(list)
    for c in contribs:
        by[(c["arena_id"], c["account_id"])].append(c)

    # join into matches
    matches = collections.defaultdict(list)
    for r in rows:
        if not r.get("raw_exp") or r.get("raw_exp") <= 0:
            continue
        key = (r["arena_id"], r["account_id"])
        be = {}
        if key in by:
            be = by[key][0]["bucket_eff"]
        matches[r["arena_id"]].append({
            "account_id": r["account_id"],
            "ship_class": r["ship_class"],
            "raw_exp": r["raw_exp"],
            "team_raw": r["team_raw"],
            "efficiency": r["efficiency"],
            "scouting_damage": r["scouting_damage"] or 0,
            "bucket_eff": be,
        })

    # within-match demeaned regression of log share on bucket efficiencies
    BUCKETS = ["t4_5", "t6_7", "t8_9", "t10_11"]
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
                "buckets": {b: p["bucket_eff"].get(b, 0.0) for b in BUCKETS},
                "scout": p["scouting_damage"] / 100000.0,
            })

    by_arena = collections.defaultdict(list)
    for z in recs:
        by_arena[z["arena"]].append(z)

    cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}
    n_pred = len(BUCKETS) + 1  # buckets + scout
    X = np.zeros((len(recs), n_pred + 5))
    y = np.zeros(len(recs))
    for i, z in enumerate(recs):
        grp = by_arena[z["arena"]]
        y[i] = z["y"] - sum(q["y"] for q in grp) / len(grp)
        for j, b in enumerate(BUCKETS):
            X[i, j] = z["buckets"][b] - sum(q["buckets"][b] for q in grp) / len(grp)
        X[i, len(BUCKETS)] = z["scout"] - sum(q["scout"] for q in grp) / len(grp)
        X[i, n_pred + cls_codes[z["cls"]]] = 1.0

    # fit with all buckets
    A = np.column_stack([X[:, j] for j in range(n_pred)] + [X[:, j] for j in range(n_pred, n_pred + 5)])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    pred = A @ coef
    r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
    print("n=%d  bucket+scout+class model R2=%.4f" % (len(recs), r2))
    print("bucket coefficients (log share per ship-equivalent):")
    for j, b in enumerate(BUCKETS):
        print("  %-6s %.4f" % (b, coef[j]))
    print("  scout %.4f" % coef[len(BUCKETS)])

    # compare against total efficiency + scout model
    X2 = np.zeros((len(recs), 2 + 5))
    for i, z in enumerate(recs):
        grp = by_arena[z["arena"]]
        eff = z["buckets"][BUCKETS[0]] + z["buckets"][BUCKETS[1]] + z["buckets"][BUCKETS[2]] + z["buckets"][BUCKETS[3]]
        X2[i, 0] = eff - sum((q["buckets"][BUCKETS[0]] + q["buckets"][BUCKETS[1]] + q["buckets"][BUCKETS[2]] + q["buckets"][BUCKETS[3]]) for q in grp) / len(grp)
        X2[i, 1] = z["scout"] - sum(q["scout"] for q in grp) / len(grp)
        X2[i, 2 + cls_codes[z["cls"]]] = 1.0
    A2 = np.column_stack([X2[:, j] for j in range(7)])
    coef2, *_ = np.linalg.lstsq(A2, y, rcond=None)
    pred2 = A2 @ coef2
    r2_total = 1 - float(np.sum((y - pred2) ** 2) / np.sum((y - y.mean()) ** 2))
    print("total-eff + scout + class model R2=%.4f" % r2_total)

    out = {
        "n": len(recs),
        "bucket_coef": {b: round(float(coef[j]), 4) for j, b in enumerate(BUCKETS)},
        "scout_coef": round(float(coef[len(BUCKETS)]), 4),
        "bucket_r2": round(r2, 4),
        "total_eff_r2": round(r2_total, 4),
    }
    with open("output/victim_tier_analysis.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("results -> output/victim_tier_analysis.json")


if __name__ == "__main__":
    main()
