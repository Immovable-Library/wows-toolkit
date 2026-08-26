#!/usr/bin/env python3
"""Fit operations XP allocation: equal floor + class-weighted contribution.

Model for a match with n players:
    contribution_i = ship_eff_i + lam * (scouting_damage_i / 100000)
    XP_share_i = a / n + (1 - a) * K[class_i] * contribution_i
                         / sum_j(K[class_j] * contribution_j)

where a is the equally-distributed pool fraction, lam weights spotting in
ship-equivalent units, and K[class] is the class multiplier (K[DD] = 1).
We grid-search (a, lam) and estimate K at each point via within-match
log-ratio regression.
"""
from __future__ import annotations

import argparse
import collections
import json
import math

import numpy as np


CLASSES = ["DD", "CL/CA", "BB", "CV", "SS"]
DUMMIES = ["BB", "CL/CA", "CV", "SS"]


def load(paths, families):
    rows = []
    seen = set()
    for path in paths:
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r.get("scenario_family") not in families:
                continue
            if not r.get("raw_exp") or r.get("raw_exp") <= 0:
                continue
            if not r.get("team_eff") or r.get("team_eff") <= 0:
                continue
            if r.get("ship_class") not in CLASSES:
                continue
            key = (r.get("arena_id"), r.get("account_id"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
    return rows


def group(rows):
    m = collections.defaultdict(list)
    for r in rows:
        m[r["arena_id"]].append(r)
    return m


def build_matches(rows):
    matches = []
    for arena, grp in group(rows).items():
        team_raw = sum(r["raw_exp"] for r in grp)
        if team_raw <= 0 or len(grp) < 2:
            continue
        players = [{
            "class": r["ship_class"],
            "E": r["efficiency"],
            "S": (r["scouting_damage"] or 0) / 100000.0,
            "x": r["raw_exp"] / team_raw,
        } for r in grp]
        matches.append({"n": len(players), "players": players})
    return matches


def contrib(p, lam):
    return p["E"] + lam * p["S"]


def estimate_K(matches, a, lam):
    X, Y = [], []
    for md in matches:
        n = md["n"]
        valid = [p for p in md["players"] if contrib(p, lam) > 1e-9 and (p["x"] - a / n) > 1e-9]
        if len(valid) < 2 or len({p["class"] for p in valid}) < 2:
            continue
        ys = [math.log(p["x"] - a / n) - math.log(contrib(p, lam)) for p in valid]
        xs = [[1.0 if p["class"] == d else 0.0 for d in DUMMIES] for p in valid]
        ym = np.mean(ys)
        xm = np.mean(xs, axis=0)
        Y.extend(ys - ym)
        X.extend([np.array(x) - xm for x in xs])
    if len(Y) < 30:
        return None
    X = np.array(X)
    Y = np.array(Y)
    coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
    K = {"DD": 1.0}
    for d, c in zip(DUMMIES, coef):
        K[d] = math.exp(float(c))
    return K


def sse_of(matches, a, lam, K):
    sse = 0.0
    for md in matches:
        n = md["n"]
        denom = sum(K[p["class"]] * contrib(p, lam) for p in md["players"])
        if denom <= 0:
            continue
        for p in md["players"]:
            pred = a / n + (1 - a) * K[p["class"]] * contrib(p, lam) / denom
            sse += (p["x"] - pred) ** 2
    return sse


def sst_of(matches):
    return sum((p["x"] - 1.0 / md["n"]) ** 2 for md in matches for p in md["players"])


def fit(rows, label):
    matches = build_matches(rows)
    print("\n  [%s] %d matches" % (label, len(matches)))
    sst = sst_of(matches)

    best = None
    for a in [round(i * 0.02, 2) for i in range(46)]:
        for lam in [round(i * 0.1, 1) for i in range(21)]:
            K = estimate_K(matches, a, lam)
            if K is None:
                continue
            sse = sse_of(matches, a, lam, K)
            if best is None or sse < best["sse"]:
                best = {"a": a, "lam": lam, "K": K, "sse": sse}

    r2 = 1 - best["sse"] / sst
    K = best["K"]
    # rebase to CL/CA = 1.00
    base = K["CL/CA"]
    K_rebased = {c: K[c] / base for c in CLASSES}
    print("    fitted: a (equal floor) = %.2f, lam (scout/100k) = %.1f" % (best["a"], best["lam"]))
    print("    fitted R2 = %.4f" % r2)
    print("    class multipliers K (CL/CA = 1.00):")
    for c in CLASSES:
        print("      %-6s x%.3f" % (c, K_rebased[c]))
    print("    SS vs CL/CA: x%.3f" % (K_rebased["SS"] / K_rebased["CL/CA"]))
    print("    CV vs CL/CA: x%.3f" % (K_rebased["CV"] / K_rebased["CL/CA"]))
    best["K_rebased"] = K_rebased
    return best


def sub_formula_check(rows, label):
    matches = build_matches(rows)
    obs = []
    for md in matches:
        team_eff = sum(q["E"] for q in md["players"])
        if team_eff <= 0:
            continue
        for p in md["players"]:
            if p["class"] != "SS":
                continue
            y = p["E"] / team_eff
            x_actual = p["x"]
            x_pred_175 = 1.75 * y / (1 + 0.75 * y)
            obs.append((y, x_actual, x_pred_175))
    if not obs:
        print("  [%s] no subs" % label)
        return
    print("\n  [%s] SUB formula check, n=%d" % (label, len(obs)))
    print("    mean x_actual          : %.4f" % np.mean([o[1] for o in obs]))
    print("    mean x_pred(1.75)      : %.4f" % np.mean([o[2] for o in obs]))
    print("    MAE |actual - 1.75pred|: %.4f" % np.mean([abs(o[1] - o[2]) for o in obs]))
    print("    MAE |actual - y|       : %.4f" % np.mean([abs(o[1] - o[0]) for o in obs]))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replays", nargs="+", default=["ops_efficiency.jsonl", "ops_efficiency_pve.jsonl"])
    ap.add_argument("--scope", choices=["new", "legacy", "all"], default="all")
    args = ap.parse_args(argv)

    fams_new = {"WW2_OP(new)"}
    fams_legacy = {"PCVO(legacy_op)"}
    fams_all = {"WW2_OP(new)", "PCVO(legacy_op)"}
    scope_map = {
        "new": [("new ops only", load(args.replays, fams_new))],
        "legacy": [("legacy ops only", load(args.replays, fams_legacy))],
        "all": [
            ("new ops only", load(args.replays, fams_new)),
            ("legacy ops only", load(args.replays, fams_legacy)),
            ("new + legacy", load(args.replays, fams_all)),
        ],
    }
    scopes = scope_map[args.scope]

    results = {}
    for label, rows in scopes:
        print("=" * 78)
        print("SCOPE: %s  (rows=%d)" % (label, len(rows)))
        print("=" * 78)
        res = fit(rows, label)
        sub_formula_check(rows, label)
        results[label] = res
        print()

    with open("output/class_efficiency_fit.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2, default=str)
    print("results -> output/class_efficiency_fit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
