"""Survival time vs base XP, grouped by operation map and bracket.

life_time_sec sits at the stable public index 22. A player who survives the
whole match has life_time_sec equal to the match duration; a player who dies
early has a shorter value. We treat a missing or zero value as "survived to
the end" (ratio 1.0).
"""
import collections
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

sys.path.insert(0, "scripts")
import extract_ops_replays as ex


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


def parse_lifetime(path):
    meta, packets = ex.read_replay(path)
    res = ex.find_battle_results(packets)
    if not res:
        return []
    common = ex.resolve_common(res.get("commonList") or [])
    arena = common.get("arena_id") or res.get("arenaUniqueID")
    dur = common.get("duration_sec")
    ppi = res.get("playersPublicInfo") or {}
    out = []
    for dbid, arr in ppi.items():
        if int(arr[0]) <= 0:
            continue
        life = arr[22] if len(arr) > 22 else None
        out.append((arena, int(arr[0]), life, dur))
    return out


def load_ops(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if not r.get("raw_exp") or r.get("raw_exp") <= 0:
            continue
        rows.append(r)
    return rows


def survival_ratio(life, dur):
    if life is None or life <= 0 or dur is None or dur <= 0:
        return 1.0
    return min(1.0, max(0.0, float(life) / float(dur)))


def main():
    rows = load_ops("ops_efficiency_full.jsonl")
    idx = build_index()
    sources = {r["source"] for r in rows}

    cache_path = "output/lifetime_cache.jsonl"
    lifetime = {}
    if os.path.exists(cache_path):
        for line in open(cache_path, encoding="utf-8"):
            a, aid, life, dur = json.loads(line)
            lifetime[(a, aid)] = (life, dur)
    else:
        jobs = [idx[s] for s in sources if s in idx]
        with ProcessPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(parse_lifetime, p): p for p in jobs}
            for fut in as_completed(futs):
                got = fut.result()
                for a, aid, life, dur in got:
                    lifetime[(a, aid)] = (life, dur)
        with open(cache_path, "w", encoding="utf-8") as fh:
            for (a, aid), (life, dur) in lifetime.items():
                fh.write(json.dumps([a, aid, life, dur]) + "\n")

    # attach
    for r in rows:
        key = (r["arena_id"], r["account_id"])
        life, dur = lifetime.get(key, (None, r.get("duration_sec")))
        r["life_time_sec"] = life
        r["duration_sec"] = dur if dur is not None else r.get("duration_sec")
        r["survival_ratio"] = survival_ratio(life, r["duration_sec"])

    # display mapping
    name_map = {}
    if os.path.exists("output/ops_name_table.json"):
        for e in json.load(open("output/ops_name_table.json", encoding="utf-8")):
            name_map[e["scenario"]] = (e["name"], e["bracket"], e["variant"])

    MAP_NAME = {
        "Ridge": "神盾", "NavalBase": "杀人鲸", "Labyrinth": "营救猛禽",
        "Naval_Defense": "防守纽波特", "Advance": "那莱", "Atoll": "最终前线",
        "LePVE": "赫尔墨斯", "USS_CL": "樱花绽放",
    }
    NEW_NAME = {
        "WW2_OPERATION_1": "北极护航", "WW2_OPERATION_2": "东京快车",
        "WW2_OPERATION_3": "太平洋攻势",
    }

    def label(scen):
        if scen in name_map:
            n, b, v = name_map[scen]
            return "%s %s" % (n, b) if b else n
        for code, name in MAP_NAME.items():
            if code in scen:
                if "Flagships" in scen:
                    return "%s 9-10" % name
                if "MEDIUM" in scen:
                    return "%s 7-9" % name
                if "HIGH" in scen:
                    return "%s 8-11" % name
                return "%s 6-8" % name
        for code, name in NEW_NAME.items():
            if code in scen:
                if "67LVL" in scen:
                    return "%s 6-7" % name
                if "89LVL" in scen:
                    return "%s 7-9" % name
                if "1011LVL" in scen:
                    return "%s 9-11" % name
        return scen

    # per-scenario stats
    by_scen = collections.defaultdict(list)
    for r in rows:
        by_scen[r["scenario"]].append(r)

    stats = []
    for scen, grp in by_scen.items():
        if len(grp) < 40:
            continue
        xs = np.array([r["survival_ratio"] for r in grp], dtype=float)
        ys = np.array([r["raw_exp"] for r in grp], dtype=float)
        corr = float(np.corrcoef(xs, ys)[0, 1]) if len(grp) > 2 else None
        buckets = [
            ("0-25%", (xs < 0.25)),
            ("25-50%", (xs >= 0.25) & (xs < 0.5)),
            ("50-75%", (xs >= 0.5) & (xs < 0.75)),
            ("75-99%", (xs >= 0.75) & (xs < 0.999)),
            ("100%", (xs >= 0.999)),
        ]
        binned = []
        for name, mask in buckets:
            vals = ys[mask]
            if len(vals) >= 3:
                binned.append({"bucket": name, "n": int(len(vals)),
                               "mean_xp": round(float(vals.mean()), 1)})
        stats.append({
            "scenario": scen,
            "label": label(scen),
            "n": len(grp),
            "corr": round(corr, 3) if corr is not None else None,
            "mean_xp": round(float(ys.mean()), 1),
            "binned": binned,
        })

    stats.sort(key=lambda s: -s["n"])
    with open("output/survival_analysis.json", "w", encoding="utf-8") as fh:
        json.dump({"per_scenario": stats}, fh, indent=2, ensure_ascii=False)

    # global within-match survival effect (isolate from efficiency)
    matches = collections.defaultdict(list)
    for r in rows:
        matches[r["arena_id"]].append(r)
    cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}
    recs = []
    for arena, grp in matches.items():
        if len(grp) < 2:
            continue
        for r in grp:
            recs.append({
                "arena": arena, "cls": r["ship_class"], "xp": r["raw_exp"],
                "surv": r["survival_ratio"], "eff": r.get("efficiency") or 0.0,
                "scout": (r.get("scouting_damage") or 0.0) / 100000.0,
            })
    by_arena = collections.defaultdict(list)
    for z in recs:
        by_arena[z["arena"]].append(z)
    feats = ["surv", "eff", "scout"]
    X = np.zeros((len(recs), len(feats) + 5))
    y = np.zeros(len(recs))
    for i, z in enumerate(recs):
        grp = by_arena[z["arena"]]
        y[i] = z["xp"] - sum(q["xp"] for q in grp) / len(grp)
        for j, f in enumerate(feats):
            X[i, j] = z[f] - sum(q[f] for q in grp) / len(grp)
        X[i, len(feats) + cls_codes[z["cls"]]] = 1.0
    def fit(cols):
        A = X[:, cols]
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        pred = A @ coef
        r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
        return coef, r2
    cls_cols = list(range(len(feats), len(feats) + 5))
    coef_base, r2_base = fit([1, 2] + cls_cols)
    coef_full, r2_full = fit([0, 1, 2] + cls_cols)
    surv_coef = float(coef_full[0])
    print("within-match survival effect:")
    print("  eff+scout+class       R2=%.4f" % r2_base)
    print("  + survival_ratio      R2=%.4f  coef=%.2f xp per full survival" % (r2_full, surv_coef))
    print("  (surviving the whole match vs dying at start = %.0f base XP)" % surv_coef)

    with open("output/survival_analysis.json", "w", encoding="utf-8") as fh:
        json.dump({
            "within_match": {
                "n": len(recs), "r2_base": round(r2_base, 4),
                "r2_full": round(r2_full, 4),
                "survival_coef_xp": round(surv_coef, 2),
            },
            "per_scenario": stats,
        }, fh, indent=2, ensure_ascii=False)
    print("results -> output/survival_analysis.json")


if __name__ == "__main__":
    main()
