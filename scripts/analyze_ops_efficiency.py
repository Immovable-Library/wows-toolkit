#!/usr/bin/env python3
"""Empirical check of operations XP allocation claims from a community video.

Tests, using every local replay with resolved base XP:
  1. descriptive class XP share / raw XP / XP-per-damage
  2. within-match class coefficient (DD baseline), incl. SS multiplier
  3. whether a submarine shifts XP away from surface ships (tribute effect)
  4. whether a dead-weight / AFK-like player shrinks the team XP pool

All XP uses raw_exp (base XP, no premium or first-win modifiers).
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import sqlite3
import statistics


CLASSES = ["DD", "CL/CA", "BB", "CV", "SS"]
SURFACE = {"DD", "CL/CA", "BB"}


def load_rows(db, families):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    qmarks = ",".join("?" for _ in families)
    rows = []
    cur = con.execute(
        "select * from rows where scenario_family in (%s) and fields_resolved=1 "
        "and raw_exp is not null and raw_exp > 0" % qmarks,
        list(families),
    )
    for r in cur:
        rows.append(dict(r))
    con.close()
    return rows


def group_matches(rows):
    m = collections.defaultdict(list)
    for r in rows:
        m[r["arena_id"]].append(r)
    return m


def fmean(v):
    return statistics.fmean(v) if v else float("nan")


def log1(x):
    return math.log(max(float(x or 0), 0.0) + 1.0)


def describe(rows, label):
    print("\n" + "=" * 78)
    print("SCOPE: %s" % label)
    print("=" * 78)
    matches = group_matches(rows)
    print("matches=%d player-rows=%d" % (len(matches), len(rows)))

    by_class = collections.defaultdict(list)
    share_by_class = collections.defaultdict(list)
    xp_per_dmg = collections.defaultdict(list)
    for arena, grp in matches.items():
        team_raw = sum(r["raw_exp"] for r in grp)
        if not team_raw:
            continue
        for r in grp:
            c = r["ship_class"]
            if c not in CLASSES:
                continue
            by_class[c].append(r["raw_exp"])
            share_by_class[c].append(r["raw_exp"] / team_raw)
            if r["damage"]:
                xp_per_dmg[c].append(r["raw_exp"] * 1000 / r["damage"])

    print("\n  class       n    mean_rawxp  med_rawxp  mean_share  xp_per_1k_dmg")
    for c in CLASSES:
        vals = by_class[c]
        if not vals:
            print("  %-9s %4d   %9s %9s %10s %13s" % (c, 0, "-", "-", "-", "-"))
            continue
        print("  %-9s %4d   %9.1f %9.1f %10.3f %13.2f" % (
            c, len(vals), fmean(vals), statistics.median(vals),
            fmean(share_by_class[c]), fmean(xp_per_dmg[c])))

    if share_by_class["SS"] and share_by_class["DD"]:
        print("\n  raw class mean-share (unadjusted, confounded by performance):")
        print("    SS %.3f | DD %.3f | CL/CA %.3f | BB %.3f | CV %.3f" % (
            fmean(share_by_class["SS"]), fmean(share_by_class["DD"]),
            fmean(share_by_class["CL/CA"]), fmean(share_by_class["BB"]),
            fmean(share_by_class["CV"])))


def within_regression(rows, label):
    matches = group_matches(rows)
    feats = ["log_dmg", "frags", "log_scout", "alive", "tier"]
    dummies = ["BB", "CL/CA", "CV", "SS"]
    names = feats + dummies
    X = []
    y = []
    for arena, grp in matches.items():
        valid = [r for r in grp if r["ship_class"] in CLASSES and r["tier"] is not None]
        if len(valid) < 2 or len({r["ship_class"] for r in valid}) < 2:
            continue
        ys = [log1(r["raw_exp"]) for r in valid]
        xs = []
        for r in valid:
            row = [
                log1(r["damage"]),
                float(r["frags"] or 0),
                log1(r["scouting_damage"]),
                1.0 if r["is_alive"] else 0.0,
                float(r["tier"]),
            ]
            row += [1.0 if r["ship_class"] == d else 0.0 for d in dummies]
            xs.append(row)
        ym = fmean(ys)
        xm = [fmean([x[i] for x in xs]) for i in range(len(names))]
        y.extend(v - ym for v in ys)
        for x in xs:
            X.append([x[i] - xm[i] for i in range(len(names))])

    n = len(y)
    if n < 20:
        print("\n  (within regression skipped: too few within-match class-varied rows)")
        return None
    k = len(names)
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for i in range(n):
        for a in range(k):
            xty[a] += X[i][a] * y[i]
            for b in range(k):
                xtx[a][b] += X[i][a] * X[i][b]
    b = solve(xtx, xty)
    if b is None:
        print("\n  (within regression failed: singular design)")
        return None
    resid = [y[i] - sum(X[i][a] * b[a] for a in range(k)) for i in range(n)]
    cov = hc0_cov(X, resid, xtx)
    coeffs = dict(zip(names, b))
    ses = {}

    print("\n  WITHIN-MATCH OLS: log(raw_exp) ~ performance + class (DD = baseline)")
    print("  n=%d within-match rows, k=%d" % (n, k))
    print("  %-9s %9s %9s %9s %9s" % ("term", "coef", "se", "t", "p"))
    for i, name in enumerate(names):
        se = math.sqrt(max(cov[i][i], 0.0))
        ses[name] = se
        t = b[i] / se if se > 1e-12 else None
        p = 2 * norm_tail(abs(t)) if t is not None else None
        print("  %-9s %9.4f %9.4f %9s %9s" % (
            name, b[i], se,
            ("%.2f" % t) if t is not None else "-",
            ("%.4f" % p) if p is not None else "-"))

    print("\n  class multipliers vs DD (exp(coef)):")
    for d in dummies:
        c = coeffs[d]
        se = ses[d]
        lo = math.exp(c - 1.96 * se)
        hi = math.exp(c + 1.96 * se)
        print("    %-6s vs DD: x%.2f  (95%% CI x%.2f..x%.2f)" % (d, math.exp(c), lo, hi))

    surf = (coeffs["BB"] + coeffs["CL/CA"]) / 2.0
    print("    SS vs surface(avg BB+CL/CA): x%.2f" % math.exp(coeffs["SS"] - surf))
    print("    CV vs surface(avg BB+CL/CA): x%.2f" % math.exp(coeffs["CV"] - surf))
    return {"coeffs": coeffs, "ses": ses, "n": n}


def solve(xtx, xty):
    k = len(xtx)
    a = [row[:] for row in xtx]
    rhs = xty[:]
    for i in range(k):
        pivot = i
        for j in range(i, k):
            if abs(a[j][i]) > abs(a[pivot][i]):
                pivot = j
        if abs(a[pivot][i]) < 1e-12:
            return None
        a[i], a[pivot] = a[pivot], a[i]
        rhs[i], rhs[pivot] = rhs[pivot], rhs[i]
        d = a[i][i]
        for j in range(i, k):
            a[i][j] /= d
        rhs[i] /= d
        for j in range(k):
            if j == i:
                continue
            f = a[j][i]
            if f == 0:
                continue
            for c in range(i, k):
                a[j][c] -= f * a[i][c]
            rhs[j] -= f * rhs[i]
    return rhs


def invert(a):
    k = len(a)
    aug = [a[i][:] + [1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]
    for i in range(k):
        pivot = i
        for j in range(i, k):
            if abs(aug[j][i]) > abs(aug[pivot][i]):
                pivot = j
        if abs(aug[pivot][i]) < 1e-12:
            return None
        aug[i], aug[pivot] = aug[pivot], aug[i]
        d = aug[i][i]
        for j in range(2 * k):
            aug[i][j] /= d
        for j in range(k):
            if j == i:
                continue
            f = aug[j][i]
            for c in range(2 * k):
                aug[j][c] -= f * aug[i][c]
    return [aug[i][k:] for i in range(k)]


def matmul(a, b):
    ra = len(a)
    ca = len(a[0])
    cb = len(b[0])
    out = [[0.0] * cb for _ in range(ra)]
    for i in range(ra):
        for j in range(cb):
            out[i][j] = sum(a[i][t] * b[t][j] for t in range(ca))
    return out


def hc0_cov(X, resid, xtx):
    k = len(xtx)
    inv = invert(xtx)
    if inv is None:
        return [[0.0] * k for _ in range(k)]
    n = len(X)
    meat = [[0.0] * k for _ in range(k)]
    for i in range(n):
        e2 = resid[i] * resid[i]
        for a in range(k):
            for b in range(k):
                meat[a][b] += X[i][a] * e2 * X[i][b]
    return matmul(matmul(inv, meat), inv)


def norm_tail(x):
    if x < 0:
        return 1.0 - norm_tail(-x)
    t = 1.0 / (1.0 + 0.2316419 * x)
    d = 0.3989422804014327 * math.exp(-x * x / 2.0)
    p = d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    return p


def sub_tribute(rows):
    matches = group_matches(rows)
    ss_matches = []
    no_ss_matches = []
    for arena, grp in matches.items():
        classes = [r["ship_class"] for r in grp if r["ship_class"] in CLASSES]
        if "SS" in classes:
            ss_matches.append(grp)
        else:
            no_ss_matches.append(grp)

    def shares(matches_list, cls):
        out = []
        for grp in matches_list:
            team_raw = sum(r["raw_exp"] for r in grp)
            if not team_raw:
                continue
            for r in grp:
                if r["ship_class"] in cls:
                    out.append(r["raw_exp"] / team_raw)
        return out

    ss_share = shares(ss_matches, {"SS"})
    surf_in_ss = shares(ss_matches, SURFACE)
    surf_in_noss = shares(no_ss_matches, SURFACE)
    print("\n  SUB-PRESENCE ('tribute') EFFECT")
    print("    matches with SS=%d, without SS=%d" % (len(ss_matches), len(no_ss_matches)))
    if ss_share:
        print("    mean SS share of team base XP: %.3f  (equal split 1/7=%.3f)" % (
            fmean(ss_share), 1 / 7))
    if surf_in_ss and surf_in_noss:
        print("    surface mean share, SS-matches : %.3f" % fmean(surf_in_ss))
        print("    surface mean share, no-SS      : %.3f" % fmean(surf_in_noss))
        print("    difference                     : %+.3f" % (fmean(surf_in_ss) - fmean(surf_in_noss)))


def matched_damage_ratio(rows, cls, label):
    matches = group_matches(rows)
    ratios = []
    n = 0
    for arena, grp in matches.items():
        target = [r for r in grp if r["ship_class"] == cls]
        surf = [r for r in grp if r["ship_class"] in SURFACE]
        if not target or not surf:
            continue
        for t in target:
            best = min(surf, key=lambda s: abs((s["damage"] or 0) - (t["damage"] or 0)))
            if best["raw_exp"] and t["raw_exp"]:
                ratios.append(t["raw_exp"] / best["raw_exp"])
                n += 1
    if ratios:
        print("    %-3s matched-damage raw_exp ratio vs nearest surface ship: mean %.2f, median %.2f (n=%d)" % (
            cls, fmean(ratios), statistics.median(ratios), n))
    return ratios


def per_ship_breakdown(rows, cls, label):
    matches = group_matches(rows)
    agg = collections.defaultdict(list)
    for arena, grp in matches.items():
        team_raw = sum(r["raw_exp"] for r in grp)
        if not team_raw:
            continue
        for r in grp:
            if r["ship_class"] == cls:
                agg[r["ship_name"] or "unknown"].append(r["raw_exp"] / team_raw)
    if not agg:
        return
    print("    %s ship-level mean share (n>=1):" % cls)
    for name, shares in sorted(agg.items(), key=lambda kv: -len(kv[1])):
        print("      %-22s n=%2d  mean_share=%.3f" % (name, len(shares), fmean(shares)))


def pool_by_stars(rows):
    matches = group_matches(rows)
    recs = collections.defaultdict(list)
    for arena, grp in matches.items():
        inactive = [r for r in grp if r["ship_class"] in CLASSES
                    and not r["is_alive"]
                    and (r["frags"] or 0) == 0
                    and (r["damage"] or 0) < 10000]
        team_raw = sum(r["raw_exp"] for r in grp)
        stars = max((r["stars_server"] for r in grp if r["stars_server"] is not None), default=None)
        recs[(grp[0]["scenario_family"], stars)].append({
            "inactive": 1 if inactive else 0,
            "team_raw": team_raw,
        })
    print("\n  TEAM POOL vs COMPLETION, split by inactive-player presence")
    print("  family                stars  inactive  matches  mean_team_rawxp")
    for (fam, stars), items in sorted(recs.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        for flag in (0, 1):
            sub = [x for x in items if x["inactive"] == flag]
            if not sub:
                continue
            print("  %-20s %5s %9s %7d %16.1f" % (
                fam, str(stars), "yes" if flag else "no",
                len(sub), fmean([x["team_raw"] for x in sub])))


def deadweight_pool(rows):
    matches = group_matches(rows)
    families = collections.defaultdict(list)
    for arena, grp in matches.items():
        fam = grp[0]["scenario_family"]
        inactive = [r for r in grp if r["ship_class"] in CLASSES
                    and not r["is_alive"]
                    and (r["frags"] or 0) == 0
                    and (r["damage"] or 0) < 10000]
        team_raw = sum(r["raw_exp"] for r in grp)
        team_dmg = sum(r["damage"] or 0 for r in grp)
        stars = max((r["stars_server"] for r in grp if r["stars_server"] is not None), default=None)
        families[fam].append({
            "n_inactive": len(inactive),
            "team_raw": team_raw,
            "team_dmg": team_dmg,
            "stars": stars,
        })

    print("\n  DEAD-WEIGHT / AFK PROXY -> TEAM XP POOL")
    print("  proxy: died with 0 frags and <10k damage (likely AFK or instant death)")
    for fam, recs in sorted(families.items()):
        by_n = collections.defaultdict(list)
        for rec in recs:
            by_n[min(rec["n_inactive"], 2)].append(rec)
        print("\n  family=%s" % fam)
        print("    n_inactive  matches  mean_team_rawxp  mean_stars  mean_team_dmg")
        for n in sorted(by_n):
            grp = by_n[n]
            label_n = "%d+" % n if n == 2 else str(n)
            stars_vals = [r["stars"] for r in grp if r["stars"] is not None]
            print("    %-11s %7d %16.1f %11s %14.0f" % (
                label_n, len(grp), fmean([r["team_raw"] for r in grp]),
                ("%.2f" % fmean(stars_vals)) if stars_vals else "-",
                fmean([r["team_dmg"] for r in grp])))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="replays.db")
    ap.add_argument("--scope", choices=["new", "all"], default="all")
    args = ap.parse_args(argv)

    fams_new = ["WW2_OP(new)"]
    fams_all = ["WW2_OP(new)", "PCVO(legacy_op)"]
    scopes = []
    if args.scope == "new":
        scopes.append(("WW2_OP(new) only", load_rows(args.db, fams_new)))
    else:
        scopes.append(("WW2_OP(new) only", load_rows(args.db, fams_new)))
        scopes.append(("WW2_OP(new) + PCVO(legacy_op)", load_rows(args.db, fams_all)))

    results = {}
    for label, rows in scopes:
        describe(rows, label)
        reg = within_regression(rows, label)
        if label.startswith("WW2_OP(new) +"):
            sub_tribute(rows)
            print("\n  MATCHED-DAMAGE RATIO (non-parametric class premium)")
            matched_damage_ratio(rows, "SS", label)
            matched_damage_ratio(rows, "CV", label)
            print("\n  PER-SHIP BREAKDOWN")
            per_ship_breakdown(rows, "SS", label)
            per_ship_breakdown(rows, "CV", label)
            deadweight_pool(rows)
            pool_by_stars(rows)
        results[label] = {"n_rows": len(rows), "n_matches": len(group_matches(rows)), "reg": reg}

    out = "output/ops_efficiency_analysis.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2, default=str)
    print("\nresults written to %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
