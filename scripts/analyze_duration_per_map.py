"""Within-map duration effect on the team XP pool.

For each scenario with enough matches, regress log(team_raw) on stars, win and
log(duration). This removes the between-map confound and answers whether, on
the same map, a longer battle moves the pool.
"""
import collections
import json
import math

import numpy as np


CLASSES = {"DD", "CL/CA", "BB", "CV", "SS"}


def load(path):
    seen = set()
    matches = collections.defaultdict(list)
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if not r.get("raw_exp") or r.get("raw_exp") <= 0:
            continue
        if r.get("ship_class") not in CLASSES:
            continue
        key = (r["arena_id"], r["account_id"])
        if key in seen:
            continue
        seen.add(key)
        matches[r["arena_id"]].append(r)
    return matches


def match_rows(matches):
    rows = collections.defaultdict(list)
    for arena, grp in matches.items():
        first = grp[0]
        if first["stars_server"] is None or first["is_win"] is None:
            continue
        if not first.get("duration_sec") or first["duration_sec"] <= 0:
            continue
        rows[first["scenario"]].append({
            "stars": float(first["stars_server"]),
            "win": 1.0 if first["is_win"] else 0.0,
            "logdur": math.log(float(first["duration_sec"])),
            "dur_min": float(first["duration_sec"]) / 60.0,
            "team_raw": sum(r["raw_exp"] for r in grp),
        })
    return rows


def main():
    matches = load("ops_efficiency_full.jsonl")
    by_scen = match_rows(matches)

    results = []
    print("%-46s %4s %8s %8s" % ("scenario", "n", "coef", "R2"))
    for scen, rows in sorted(by_scen.items(), key=lambda kv: -len(kv[1])):
        if len(rows) < 20:
            continue
        y = np.log(np.array([r["team_raw"] for r in rows]))
        X = np.array([[1.0, r["stars"], r["win"], r["logdur"]] for r in rows])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ coef
        r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
        print("%-46s %4d %+8.4f %8.4f" % (scen, len(rows), coef[3], r2))
        results.append({
            "scenario": scen,
            "n": len(rows),
            "coef_logdur": round(float(coef[3]), 4),
            "r2": round(r2, 4),
        })

    coefs = np.array([r["coef_logdur"] for r in results])
    ns = np.array([r["n"] for r in results], dtype=float)
    print("\nper-map log(duration) coefficients:")
    print("  n_scenarios=%d  mean=%.4f  median=%.4f  min=%.4f  max=%.4f" % (
        len(coefs), coefs.mean(), np.median(coefs), coefs.min(), coefs.max()))
    print("  weighted mean (by n) = %.4f" % float(np.sum(coefs * ns) / np.sum(ns)))
    print("  count negative = %d / %d" % (int((coefs < 0).sum()), len(coefs)))

    # inverse-variance style: within-map duration effect is small and mixed
    with open("output/duration_per_map_analysis.json", "w", encoding="utf-8") as fh:
        json.dump({
            "n_scenarios": len(results),
            "mean_coef": round(float(coefs.mean()), 4),
            "median_coef": round(float(np.median(coefs)), 4),
            "weighted_mean_coef": round(float(np.sum(coefs * ns) / np.sum(ns)), 4),
            "n_negative": int((coefs < 0).sum()),
            "per_scenario": results,
        }, fh, indent=2, ensure_ascii=False)
    print("\nresults -> output/duration_per_map_analysis.json")


if __name__ == "__main__":
    main()
