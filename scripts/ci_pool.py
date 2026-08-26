#!/usr/bin/env python3
"""Finish-type decomposition and bootstrap CI for the operations pool model.

Reuses fit_xp_pool for row loading and the pooled per-match rows, then adds:
  1. a finish_type x win/loss cross-tab (to test whether non-win finishes can
     be separated from the win flag in this sample), and
  2. match-clustered bootstrap confidence intervals for the log-linear pool
     coefficients (stars, secondary-completed, win/loss).
"""
import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_xp_pool as fp  # noqa: E402


def design(rows):
    scen = sorted({r["scenario"] for r in rows})
    code = {s: i for i, s in enumerate(scen)}
    X = []
    names = ["intercept", "stars", "secondary", "is_win"] + scen
    for r in rows:
        cols = [1.0, float(r["stars"]), float(r["secondary_completed"]),
                1.0 if r["is_win"] else 0.0]
        v = [0.0] * len(scen)
        v[code[r["scenario"]]] = 1.0
        cols += v
        X.append(cols)
    return np.array(X), names


def lstsq(X, y):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return coef


def bootstrap_coef(rows, n_iter=500, seed=0):
    X, names = design(rows)
    y = np.log(np.array([r["team_raw"] for r in rows]))
    rng = np.random.default_rng(seed)
    n = len(rows)
    acc = collections.defaultdict(list)
    for _ in range(n_iter):
        idx = rng.integers(0, n, n)
        c = lstsq(X[idx], y[idx])
        for i, nm in enumerate(names):
            acc[nm].append(c[i])
    return names, acc


def ci_interval(vals):
    v = np.array(vals)
    return {
        "coef": float(np.median(v)),
        "lo95": float(np.percentile(v, 2.5)),
        "hi95": float(np.percentile(v, 97.5)),
    }


def main():
    rows = fp.match_rows(fp.load("ops_efficiency_full.jsonl"))
    rows = [r for r in rows if r["stars"] is not None
            and r["secondary_completed"] is not None
            and r["is_win"] is not None]
    print("usable matches:", len(rows))

    xtab = collections.Counter((r["finish_type"], r["is_win"]) for r in rows)
    print("\nfinish_type x is_win cross-tab:")
    for (ft, w), c in sorted(xtab.items(), key=lambda kv: str(kv[0])):
        print("  %-28s win=%s  %4d" % (ft, str(w), c))

    X, names = design(rows)
    y = np.log(np.array([r["team_raw"] for r in rows]))
    coef = lstsq(X, y)
    pred = X @ coef
    r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
    print("\nobjective-only fit (scenario + stars + secondary + is_win): R2=%.4f" % r2)
    for i, nm in enumerate(names):
        if nm in ("intercept", "stars", "secondary", "is_win"):
            print("  %-10s coef=%.4f" % (nm, coef[i]))

    names_b, acc = bootstrap_coef(rows)
    ci = {nm: ci_interval(acc[nm]) for nm in ("stars", "secondary", "is_win")}
    print("\nbootstrap 95%% CI (match-clustered, n_boot=%d):" % len(acc["stars"]))
    for nm in ("stars", "secondary", "is_win"):
        e = ci[nm]
        print("  %-10s coef=%.4f  CI [%.4f, %.4f]" % (nm, e["coef"], e["lo95"], e["hi95"]))
    print("  per-star multiplier      : x%.3f  CI [x%.3f, x%.3f]" % (
        np.exp(ci["stars"]["coef"]), np.exp(ci["stars"]["lo95"]), np.exp(ci["stars"]["hi95"])))
    print("  win vs loss multiplier   : x%.3f  CI [x%.3f, x%.3f]" % (
        np.exp(ci["is_win"]["coef"]), np.exp(ci["is_win"]["lo95"]), np.exp(ci["is_win"]["hi95"])))
    print("  loss vs win multiplier   : x%.3f  CI [x%.3f, x%.3f]" % (
        np.exp(-ci["is_win"]["coef"]), np.exp(-ci["is_win"]["hi95"]), np.exp(-ci["is_win"]["lo95"])))

    out = {
        "n_matches": len(rows),
        "finish_type_x_win": {str(k): v for k, v in xtab.items()},
        "r2": round(r2, 4),
        "coef": {nm: round(float(coef[i]), 4) for i, nm in enumerate(names) if nm in ("intercept", "stars", "secondary", "is_win")},
        "ci_95": ci,
        "per_star_multiplier": {k: round(float(v), 3) for k, v in {"coef": np.exp(ci["stars"]["coef"]), "lo95": np.exp(ci["stars"]["lo95"]), "hi95": np.exp(ci["stars"]["hi95"])}.items()},
        "win_vs_loss_multiplier": {k: round(float(v), 3) for k, v in {"coef": np.exp(ci["is_win"]["coef"]), "lo95": np.exp(ci["is_win"]["lo95"]), "hi95": np.exp(ci["is_win"]["hi95"])}.items()},
        "loss_vs_win_multiplier": {k: round(float(v), 3) for k, v in {"coef": np.exp(-ci["is_win"]["coef"]), "lo95": np.exp(-ci["is_win"]["hi95"]), "hi95": np.exp(-ci["is_win"]["lo95"])}.items()},
    }
    with open("output/pool_fit.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("\nresults -> output/pool_fit.json")


if __name__ == "__main__":
    main()

