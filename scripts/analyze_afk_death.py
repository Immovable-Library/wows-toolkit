"""Split the old 'n_inactive' pool penalty into AFK / leaver / early-death.

The previous pool model counted a player as inactive only when they died with
zero frags and less than 10k damage. That mixes two behaviors:
  - zero contribution: no damage, no frags, no spotting (a likely AFK/leaver);
  - died-early: some damage or frags but dead before the end.

Here we test whether these two classes carry different pool penalties, and
whether a zero-contribution player costs the team about 1/7 of the pool.
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


def classify(matches):
    rows = []
    for arena, grp in matches.items():
        first = grp[0]
        if first["stars_server"] is None or first["is_win"] is None:
            continue
        n = len(grp)
        team_raw = sum(r["raw_exp"] for r in grp)
        if team_raw <= 0:
            continue

        zero = []
        early = []
        for r in grp:
            dmg = r.get("damage") or 0
            frag = r.get("frags") or 0
            scout = r.get("scouting_damage") or 0
            alive = r.get("is_alive")
            if dmg == 0 and frag == 0 and scout == 0:
                zero.append(r)
            elif alive is False and dmg < 20000 and frag <= 1:
                early.append(r)

        rows.append({
            "arena_id": arena,
            "scenario": first["scenario"],
            "stars": first["stars_server"],
            "secondary": first["secondary_completed"],
            "is_win": first["is_win"],
            "n": n,
            "team_raw": team_raw,
            "team_dmg": sum(r.get("damage") or 0 for r in grp),
            "team_frags": sum(r.get("frags") or 0 for r in grp),
            "n_zero": len(zero),
            "n_early": len(early),
            "zero_raw": sum(r["raw_exp"] for r in zero),
        })
    return rows


def pool_regression(rows):
    scen = sorted({r["scenario"] for r in rows})
    code = {s: i for i, s in enumerate(scen)}

    def design(r, mode):
        cols = [1.0, float(r["stars"]), 1.0 if r["is_win"] else 0.0]
        v = [0.0] * len(scen)
        v[code[r["scenario"]]] = 1.0
        cols += v
        if mode in ("zero", "both"):
            cols.append(float(r["n_zero"]))
        if mode in ("early", "both"):
            cols.append(float(r["n_early"]))
        return cols

    y = np.log(np.array([r["team_raw"] for r in rows]))
    for mode in ("zero", "early", "both"):
        X = np.array([design(r, mode) for r in rows])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ coef
        r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
        tail = coef[3 + len(scen):]
        print("mode %-6s R2=%.4f" % (mode, r2), "coefs:", [round(float(c), 4) for c in tail])
        if mode == "zero" and len(tail):
            print("  zero-contribution player multiplier: x%.3f (1/7 would be x0.857)" % math.exp(float(tail[0])))
        if mode == "early" and len(tail):
            print("  died-early player multiplier: x%.3f" % math.exp(float(tail[0])))
        if mode == "both" and len(tail) == 2:
            print("  zero x%.3f  early x%.3f" % (math.exp(float(tail[0])), math.exp(float(tail[1]))))


def per_player(rows):
    # raw XP a zero-contribution player still receives (their share of the floor)
    zero_rows = [r for r in rows if r["n_zero"] > 0]
    if not zero_rows:
        print("no zero-contribution rows")
        return
    fracs = []
    for r in zero_rows:
        # zero_raw / team_raw is the fraction that went to zero players
        fracs.append(r["zero_raw"] / r["team_raw"])
    fracs = np.array(fracs)
    print("\nzero-contribution players:")
    print("  matches with a zero player: %d" % len(zero_rows))
    print("  mean zero_share of pool: %.4f  median %.4f" % (fracs.mean(), np.median(fracs)))
    print("  (uniform 1/n would be about 1/7 = %.4f)" % (1 / 7))


def main():
    matches = load("ops_efficiency_full.jsonl")
    rows = classify(matches)
    print("matches:", len(rows))
    print("with zero-contribution:", sum(1 for r in rows if r["n_zero"] > 0))
    print("with died-early:", sum(1 for r in rows if r["n_early"] > 0))
    print("with either:", sum(1 for r in rows if r["n_zero"] + r["n_early"] > 0))
    pool_regression(rows)
    per_player(rows)
    with open("output/afk_death_analysis.json", "w", encoding="utf-8") as fh:
        json.dump({
            "matches": len(rows),
            "n_zero": sum(1 for r in rows if r["n_zero"] > 0),
            "n_early": sum(1 for r in rows if r["n_early"] > 0),
        }, fh, indent=2)
    print("\nresults -> output/afk_death_analysis.json")


if __name__ == "__main__":
    main()
