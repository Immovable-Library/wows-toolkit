"""Spawn/reinforcement waves vs the XP pool for a chosen operation.

Cherry Blossom (USS_CL) keeps spawning enemies until near the end, and Killer
Whale (NavalBase) has five reinforcement waves. In both, the total "meat"
(team damage / frags / ship-equivalents) varies with how much the team eats.
We test whether that meat moves the team pool after controlling stars and win.
"""
import argparse
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


def op_rows(matches, tag):
    rows = []
    for arena, grp in matches.items():
        first = grp[0]
        if tag not in first["scenario"]:
            continue
        if first["stars_server"] is None or first["is_win"] is None:
            continue
        team_raw = sum(r["raw_exp"] for r in grp)
        team_dmg = sum(r.get("damage") or 0 for r in grp)
        team_eff = sum(r.get("efficiency") or 0 for r in grp)
        team_frags = sum(r.get("frags") or 0 for r in grp)
        rows.append({
            "scenario": first["scenario"],
            "stars": float(first["stars_server"]),
            "win": 1.0 if first["is_win"] else 0.0,
            "duration": float(first.get("duration_sec") or 0),
            "team_raw": team_raw,
            "team_dmg": team_dmg,
            "team_eff": team_eff,
            "team_frags": team_frags,
        })
    return rows


def describe(rows, label):
    print("%s matches: %d" % (label, len(rows)))
    for label, key in (("team_damage", "team_dmg"), ("team_eff", "team_eff"),
                       ("team_frags", "team_frags"), ("duration", "duration")):
        xs = np.array([r[key] for r in rows], dtype=float)
        ys = np.array([r["team_raw"] for r in rows], dtype=float)
        print("  %-12s range %.0f-%.0f  corr(team_raw)=%+.3f" % (
            label, xs.min(), xs.max(), np.corrcoef(xs, ys)[0, 1]))

    # full-star wins only: does meat still vary and correlate with pool?
    sub = [r for r in rows if r["win"] == 1 and r["stars"] == 5]
    if sub:
        xs = np.array([r["team_dmg"] for r in sub], dtype=float)
        ys = np.array([r["team_raw"] for r in sub], dtype=float)
        print("\n  full-star wins (n=%d): team_damage range %.0f-%.0f, corr=%.3f" % (
            len(sub), xs.min(), xs.max(), np.corrcoef(xs, ys)[0, 1]))
        xe = np.array([r["team_eff"] for r in sub], dtype=float)
        print("  full-star wins: team_eff range %.1f-%.1f, corr=%.3f" % (
            xe.min(), xe.max(), np.corrcoef(xe, ys)[0, 1]))


def regression(rows, label):
    scen = sorted({r["scenario"] for r in rows})
    code = {s: i for i, s in enumerate(scen)}
    y = np.log(np.array([r["team_raw"] for r in rows]))

    def design(r, mode):
        cols = [1.0, r["stars"], r["win"]]
        v = [0.0] * len(scen)
        v[code[r["scenario"]]] = 1.0
        cols += v
        if mode in ("dmg", "both"):
            cols.append(r["team_dmg"])
        if mode in ("eff", "both"):
            cols.append(r["team_eff"])
        return cols

    def fit(mode):
        X = np.array([design(r, mode) for r in rows])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ coef
        r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
        return coef, r2

    _, r2_obj = fit("none")
    coef_dmg, r2_dmg = fit("dmg")
    coef_eff, r2_eff = fit("eff")
    coef_both, r2_both = fit("both")

    print("\n%s pool regression log(team_raw):" % label)
    print("  stars + win + scenario            : R2=%.4f" % r2_obj)
    print("  + team_damage                     : R2=%.4f  coef=%.6f" % (r2_dmg, coef_dmg[-1]))
    print("  + team_eff                        : R2=%.4f  coef=%.6f" % (r2_eff, coef_eff[-1]))
    print("  + team_damage + team_eff          : R2=%.4f" % r2_both)
    return {
        "n": len(rows),
        "r2_obj": round(r2_obj, 4),
        "r2_dmg": round(r2_dmg, 4),
        "r2_eff": round(r2_eff, 4),
        "r2_both": round(r2_both, 4),
        "coef_team_dmg": round(float(coef_dmg[-1]), 6),
        "coef_team_eff": round(float(coef_eff[-1]), 6),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="USS_CL", help="scenario substring filter")
    ap.add_argument("--label", default="Cherry Blossom")
    args = ap.parse_args(argv)
    matches = load("ops_efficiency_full.jsonl")
    rows = op_rows(matches, args.tag)
    print("operation: %s (%s)" % (args.label, args.tag))
    describe(rows, args.label)
    r = regression(rows, args.label)
    out = "output/cherry_spawn_analysis.json" if args.tag == "USS_CL" else "output/killerwhale_spawn_analysis.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(r, fh, indent=2)
    print("\nresults ->", out)


if __name__ == "__main__":
    main()
