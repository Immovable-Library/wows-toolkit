#!/usr/bin/env python3
"""Confidence intervals and diagnostics for the operations XP-allocation fit.

Reuses fit_class_efficiency for data loading, the within-match K estimator and
the equal-floor model, then adds match-clustered bootstrap confidence intervals
and a non-parametric contribution-match check for the submarine class weight.
"""
import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_class_efficiency as fc  # noqa: E402


def grid_best(matches):
    """Same grid as fit_class_efficiency.fit, but quiet and lean."""
    best = None
    for a in [round(i * 0.02, 2) for i in range(46)]:
        for lam in [round(i * 0.1, 1) for i in range(21)]:
            K = fc.estimate_K(matches, a, lam)
            if K is None:
                continue
            sse = fc.sse_of(matches, a, lam, K)
            if best is None or sse < best[0]:
                best = (sse, a, lam, K)
    return best



def bootstrap_joint(matches, n_iter=500, seed=0):
    """Joint bootstrap: re-estimate (a, lam, K) on each bootstrap sample.

    Unlike bootstrap_K() which fixes (a, lam), this produces proper joint
    uncertainty estimates for all parameters simultaneously.
    """
    rng = np.random.default_rng(seed)
    n = len(matches)
    acc_a = []
    acc_lam = []
    acc_K = collections.defaultdict(list)
    for _ in range(n_iter):
        idx = rng.integers(0, n, n)
        boot_matches = [matches[i] for i in idx]
        sse, a, lam, K = grid_best(boot_matches)
        acc_a.append(a)
        acc_lam.append(lam)
        base = K["CL/CA"]
        if not base or base <= 0:
            continue
        for cl in fc.CLASSES:
            acc_K[cl].append(K[cl] / base)
    ci = {}
    for cl in fc.CLASSES:
        v = np.array(acc_K[cl])
        ci[cl] = {
            "median": float(np.median(v)) if len(v) else None,
            "lo95": float(np.percentile(v, 2.5)) if len(v) else None,
            "hi95": float(np.percentile(v, 97.5)) if len(v) else None,
            "n": int(len(v)),
        }
    a_arr = np.array(acc_a)
    lam_arr = np.array(acc_lam)
    ci["a"] = {"median": float(np.median(a_arr)), "lo95": float(np.percentile(a_arr, 2.5)),
               "hi95": float(np.percentile(a_arr, 97.5))}
    ci["lam"] = {"median": float(np.median(lam_arr)), "lo95": float(np.percentile(lam_arr, 2.5)),
                 "hi95": float(np.percentile(lam_arr, 97.5))}
    return ci


def bootstrap_K(matches, a, lam, n_iter=500, seed=0):
    """Match-clustered bootstrap percentile CI for K rebased to CL/CA=1."""
    rng = np.random.default_rng(seed)
    n = len(matches)
    acc = collections.defaultdict(list)
    for _ in range(n_iter):
        idx = rng.integers(0, n, n)
        K = fc.estimate_K([matches[i] for i in idx], a, lam)
        if K is None:
            continue
        base = K["CL/CA"]
        if not base or base <= 0:
            continue
        for c in fc.CLASSES:
            acc[c].append(K[c] / base)
    ci = {}
    for c in fc.CLASSES:
        v = np.array(acc[c])
        ci[c] = {
            "median": float(np.median(v)) if len(v) else None,
            "lo95": float(np.percentile(v, 2.5)) if len(v) else None,
            "hi95": float(np.percentile(v, 97.5)) if len(v) else None,
            "n": int(len(v)),
        }
    return ci


def matched_contribution_ratio(rows, a, lam):
    """Pair each SS with the closest surface ship (model contribution) per match.

    The floor-adjusted share components should then differ only by the class
    weight, so this ratio lands near K[SS] without any regression machinery.
    """
    matches = fc.build_matches(rows)
    ratios = []
    for md in matches:
        subs = [p for p in md["players"] if p["class"] == "SS"]
        surf = [p for p in md["players"] if p["class"] in ("DD", "CL/CA", "BB")]
        if not subs or not surf:
            continue
        n = md["n"]
        for s in subs:
            cs = fc.contrib(s, lam)
            if cs <= 1e-9 or (s["x"] - a / n) <= 1e-9:
                continue
            best = min(surf, key=lambda q: abs(fc.contrib(q, lam) - cs))
            cb = fc.contrib(best, lam)
            if cb <= 1e-9 or (best["x"] - a / n) <= 1e-9:
                continue
            if not 0.5 <= cs / cb <= 2.0:
                continue
            ratios.append((s["x"] - a / n) / (best["x"] - a / n))
    if not ratios:
        return None
    return {"n": len(ratios), "mean": float(np.mean(ratios)), "median": float(np.median(ratios))}


def main():
    scopes = [
        ("new", ["ops_efficiency.jsonl", "ops_efficiency_pve.jsonl"], {"WW2_OP(new)"}),
        ("legacy", ["ops_efficiency.jsonl", "ops_efficiency_pve.jsonl"], {"PCVO(legacy_op)"}),
        ("pooled", ["ops_efficiency.jsonl", "ops_efficiency_pve.jsonl"], {"WW2_OP(new)", "PCVO(legacy_op)"}),
    ]
    results = {}
    for key, paths, fams in scopes:
        rows = fc.load(paths, fams)
        matches = fc.build_matches(rows)
        sse, a, lam, K = grid_best(matches)
        K_rebased = {c: K[c] / K["CL/CA"] for c in fc.CLASSES}
        r2 = 1.0 - sse / fc.sst_of(matches)
        ci = bootstrap_K(matches, a, lam)
        ci_joint = bootstrap_joint(matches)
        mr = matched_contribution_ratio(rows, a, lam)
        results[key] = {
            "matches": len(matches), "rows": len(rows),
            "a": a, "lam": lam, "r2": round(r2, 4),
            "K": {c: round(K_rebased[c], 3) for c in fc.CLASSES},
            "ci": ci, "ci_joint": ci_joint, "matched_ss_share_ratio": mr,
        }
        print("=" * 70)
        print("SCOPE %s: matches=%d rows=%d a=%.2f lam=%.1f R2=%.4f" % (
            key, len(matches), len(rows), a, lam, r2))
        print("  K (CL/CA = 1.00) with 95% conditional bootstrap CI (a,lam fixed):")
        for c in fc.CLASSES:
            e = ci[c]
            print("    %-6s x%.3f  95%% CI [x%.3f, x%.3f]  (n=%d)" % (
                c, K_rebased[c], e["lo95"], e["hi95"], e["n"]))
        print("  Joint bootstrap CI (a,lam,K re-estimated per sample):")
        for c in fc.CLASSES:
            e = ci_joint[c]
            print("    %-6s x%.3f  95%% CI [x%.3f, x%.3f]  (n=%d)" % (
                c, K_rebased[c], e["lo95"], e["hi95"], e["n"]))
        if "a" in ci_joint:
            print("  a:  median=%.3f  CI [%.3f, %.3f]" % (
                ci_joint["a"]["median"], ci_joint["a"]["lo95"], ci_joint["a"]["hi95"]))
        if "lam" in ci_joint:
            print("  lam: median=%.2f  CI [%.2f, %.2f]" % (
                ci_joint["lam"]["median"], ci_joint["lam"]["lo95"], ci_joint["lam"]["hi95"]))
        if mr:
            print("  SS contribution-matched share ratio: mean %.3f, median %.3f (n=%d)" % (
                mr["mean"], mr["median"], mr["n"]))
    with open("output/allocation_ci.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)
    print("\nresults -> output/allocation_ci.json")


if __name__ == "__main__":
    main()
