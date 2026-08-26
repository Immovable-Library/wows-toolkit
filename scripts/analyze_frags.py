"""Test whether frags (kills) carry an independent reward on top of damage.

Two levels are checked, matching the two existing models:
  1. XP share (allocation): does a player's frag count shift log(raw_exp /
     team_raw) after controlling for the ship-equivalent contribution
     (damage efficiency), spotting, and match fixed effects?
  2. Total pool (team_raw): does team_frags shift log(team_raw) after
     controlling for scenario, stars, win/loss and team damage?
"""
from __future__ import annotations

import collections
import json
import math

import numpy as np


CLASSES = {"DD", "CL/CA", "BB", "CV", "SS"}


def load_rows(path):
    seen = set()
    rows = []
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
        rows.append(r)
    return rows


def player_level(rows):
    """Within-match regression: log(share) ~ contribution + frags + fixed effects."""
    matches = collections.defaultdict(list)
    for r in rows:
        matches[r["arena_id"]].append(r)

    # within-match demean to remove the match fixed effect, then regress the
    # log share on the demeaned predictors.
    recs = []
    for arena, grp in matches.items():
        team_raw = sum(r["raw_exp"] for r in grp)
        if team_raw <= 0 or len(grp) < 2:
            continue
        for r in grp:
            eff = r.get("efficiency") or 0.0
            scout = (r.get("scouting_damage") or 0.0) / 100000.0
            frag = r.get("frags") or 0.0
            cls = r["ship_class"]
            share = r["raw_exp"] / team_raw
            if share <= 0:
                continue
            recs.append({
                "arena": arena, "cls": cls,
                "eff": eff, "scout": scout, "frag": float(frag),
                "y": math.log(share),
            })

    by_arena = collections.defaultdict(list)
    for z in recs:
        by_arena[z["arena"]].append(z)

    def demean(cols):
        X = np.zeros((len(recs), len(cols)))
        y = np.zeros(len(recs))
        for i, z in enumerate(recs):
            grp = by_arena[z["arena"]]
            base = {c: sum(q[c] for q in grp) / len(grp) for c in cols}
            y[i] = z["y"] - sum(q["y"] for q in grp) / len(grp)
            for j, c in enumerate(cols):
                X[i, j] = z[c] - base[c]
        return X, y

    # class dummies are constant within a match only for homogeneous squads;
    # include them as raw columns so multi-class matches are separable.
    cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}
    n_cls = len(cls_codes)

    def demean_with_cls(cols):
        X = np.zeros((len(recs), len(cols) + n_cls))
        y = np.zeros(len(recs))
        for i, z in enumerate(recs):
            grp = by_arena[z["arena"]]
            base = {c: sum(q[c] for q in grp) / len(grp) for c in cols}
            y[i] = z["y"] - sum(q["y"] for q in grp) / len(grp)
            for j, c in enumerate(cols):
                X[i, j] = z[c] - base[c]
            X[i, len(cols) + cls_codes[z["cls"]]] = 1.0
        return X, y

    cols = ["eff", "scout", "frag"]
    X, y = demean_with_cls(cols)
    n = len(X)

    def fit(cols, names):
        A = np.column_stack([X[:, i] for i in cols])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        pred = A @ coef
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot
        return coef, r2

    cls_idx = list(range(len(cols), len(cols) + n_cls))
    c_frag_only, r2_frag_only = fit([2] + cls_idx, ["frags"] + ["cls"] * n_cls)
    c_base, r2_base = fit([0, 1] + cls_idx, ["eff", "scout"] + ["cls"] * n_cls)
    c_frag, r2_frag = fit([0, 1, 2] + cls_idx, ["eff", "scout", "frags"] + ["cls"] * n_cls)

    print("player-level XP share (raw_exp/team_raw), within-match demeaned, n=%d" % n)
    print("  frags only:      frags=%.4f  R2=%.4f" % (c_frag_only[0], r2_frag_only))
    print("  eff+scout only:  eff=%.4f  scout=%.4f  R2=%.4f" % (c_base[0], c_base[1], r2_base))
    print("  eff+scout+frags: eff=%.4f  scout=%.4f  frags=%.4f  R2=%.4f" % (
        c_frag[0], c_frag[1], c_frag[2], r2_frag))

    # frags standardized effect and a simple zero-kill vs kill comparison
    sd_frag = float(np.std(X[:, 2]))
    print("  one extra frag = x%.4f share" % math.exp(c_frag[2]))
    print("  one SD of frags (%.3f) = x%.4f share" % (sd_frag, math.exp(c_frag[2] * sd_frag)))
    return {
        "n": n,
        "coef_frags_only": float(c_frag_only[0]),
        "coef_frags_adj": float(c_frag[2]),
        "r2_frags_only": r2_frag_only,
        "r2_base": r2_base,
        "r2_frag": r2_frag,
    }


def pool_level(rows):
    """Match-level: does team_frags shift team_raw after objective controls?"""
    matches = collections.defaultdict(list)
    for r in rows:
        matches[r["arena_id"]].append(r)

    scen = sorted({grp[0]["scenario"] for grp in matches.values()})
    code = {s: i for i, s in enumerate(scen)}
    X, y = [], []
    for arena, grp in matches.items():
        first = grp[0]
        if first["stars_server"] is None or first["is_win"] is None:
            continue
        team_raw = sum(r["raw_exp"] for r in grp)
        if team_raw <= 0:
            continue
        cols = [1.0, float(first["stars_server"]), 1.0 if first["is_win"] else 0.0]
        v = [0.0] * len(scen)
        v[code[first["scenario"]]] = 1.0
        cols += v
        cols += [float(sum(r.get("damage") or 0 for r in grp)),
                 float(sum(r.get("frags") or 0 for r in grp))]
        X.append(cols)
        y.append(math.log(team_raw))

    X = np.array(X, dtype=float)
    y = np.array(y, dtype=float)
    base_cols = list(range(3 + len(scen)))
    dmg_col = 3 + len(scen)
    frag_col = dmg_col + 1

    def fit(cols):
        A = X[:, cols]
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        pred = A @ coef
        r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
        return coef, r2

    _, r2_obj = fit(base_cols)
    coef_dmg, r2_dmg = fit(base_cols + [dmg_col])
    coef_frag, r2_frag = fit(base_cols + [dmg_col, frag_col])

    print("\npool-level team_raw, n=%d" % len(X))
    print("  objective only: R2=%.4f" % r2_obj)
    print("  + team_dmg:     R2=%.4f  team_dmg coef=%.6f" % (r2_dmg, coef_dmg[-1]))
    print("  + team_frags:   R2=%.4f  team_frags coef=%.6f" % (r2_frag, coef_frag[-1]))
    return {
        "n": len(X),
        "r2_obj": r2_obj,
        "r2_dmg": r2_dmg,
        "r2_frag": r2_frag,
        "coef_team_frags": float(coef_frag[-1]),
    }


def main():
    rows = load_rows("ops_efficiency_full.jsonl")
    p = player_level(rows)
    q = pool_level(rows)
    with open("output/frags_analysis.json", "w", encoding="utf-8") as fh:
        json.dump({"player": p, "pool": q}, fh, indent=2)
    print("\nresults -> output/frags_analysis.json")


if __name__ == "__main__":
    main()
