#!/usr/bin/env python3
"""Reverse-engineer the operations total-XP pool.

Questions:
  1. What determines team_raw (sum of base XP across players)?
  2. Is the pool objective-based (map + difficulty + stars + secondary tasks)
     or does it also scale directly with team efficiency/damage?
  3. How much do failed secondary tasks and dead-weight players reduce it?
"""
from __future__ import annotations

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
    out = []
    for arena, grp in matches.items():
        first = grp[0]
        team_raw = sum(r["raw_exp"] for r in grp)
        team_eff = sum(r["efficiency"] for r in grp)
        team_dmg = sum(r["damage"] or 0 for r in grp)
        team_frags = sum(r["frags"] or 0 for r in grp)
        n = len(grp)
        n_inactive = sum(
            1 for r in grp
            if not r.get("is_alive") and (r.get("frags") or 0) == 0 and (r.get("damage") or 0) < 10000
        )
        out.append({
            "arena_id": arena,
            "scenario": first["scenario"],
            "family": first["scenario_family"],
            "bracket": first["bracket"],
            "difficulty": first["difficulty"],
            "stars": first["stars_server"],
            "secondary_completed": first["secondary_completed"],
            "secondary_total": first["secondary_total"],
            "is_win": first["is_win"],
            "finish_type": first["finish_type"],
            "n": n,
            "n_inactive": n_inactive,
            "duration": first["duration_sec"],
            "team_raw": team_raw,
            "team_eff": team_eff,
            "team_dmg": team_dmg,
            "team_frags": team_frags,
        })
    return out


def fmean(v):
    return sum(v) / len(v) if v else float("nan")


def describe(rows):
    print("matches:", len(rows))
    print("\nteam_raw by stars:")
    by_stars = collections.defaultdict(list)
    for r in rows:
        if r["stars"] is not None:
            by_stars[r["stars"]].append(r["team_raw"])
    for s in sorted(by_stars):
        print("  stars=%s  n=%4d  mean_team_raw=%8.1f  median=%8.1f" % (
            s, len(by_stars[s]), fmean(by_stars[s]), np.median(by_stars[s])))

    print("\nteam_raw by secondary_completed:")
    by_sec = collections.defaultdict(list)
    for r in rows:
        if r["secondary_completed"] is not None and r["stars"] == 5:
            by_sec[r["secondary_completed"]].append(r["team_raw"])
    for s in sorted(by_sec):
        print("  sec=%s  n=%4d  mean_team_raw=%8.1f" % (s, len(by_sec[s]), fmean(by_sec[s])))

    print("\nteam_raw by win/loss:")
    by_win = collections.defaultdict(list)
    for r in rows:
        by_win[r["is_win"]].append(r["team_raw"])
    for w in (True, False, None):
        print("  win=%s  n=%4d  mean_team_raw=%8.1f" % (w, len(by_win[w]), fmean(by_win[w])))

    print("\ncorrelations with team_raw:")
    for name, key in (("team_eff", "team_eff"), ("team_dmg", "team_dmg"),
                      ("team_frags", "team_frags"), ("duration", "duration"),
                      ("stars", "stars")):
        xs = [r[key] for r in rows if r[key] is not None]
        ys = [r["team_raw"] for r in rows if r[key] is not None]
        print("  %-10s r=%.4f" % (name, np.corrcoef(xs, ys)[0, 1]))

    # within-scenario correlation of team_raw and team_eff (is the pool fixed per map?)
    by_scen = collections.defaultdict(list)
    for r in rows:
        by_scen[r["scenario"]].append(r)
    scen_stats = []
    for scen, grp in by_scen.items():
        if len(grp) < 5:
            continue
        xs = [r["team_eff"] for r in grp]
        ys = [r["team_raw"] for r in grp]
        scen_stats.append((scen, len(grp), fmean(ys), np.std(ys), np.corrcoef(xs, ys)[0, 1]))
    print("\ntop scenarios by mean team_raw (n>=5):")
    for scen, n, mu, sd, corr in sorted(scen_stats, key=lambda x: -x[2])[:25]:
        print("  %-42s n=%3d mean=%8.1f sd=%6.1f corr(raw,eff)=%+.3f" % (scen, n, mu, sd, corr))


def regression(rows):
    rows = [r for r in rows if r["stars"] is not None and r["secondary_completed"] is not None and r["is_win"] is not None]
    scen_codes = {s: i for i, s in enumerate(sorted({r["scenario"] for r in rows}))}

    def design(r, with_perf):
        cols = [1.0, float(r["stars"]), float(r["secondary_completed"]), 1.0 if r["is_win"] else 0.0]
        scen = [0.0] * len(scen_codes)
        scen[scen_codes[r["scenario"]]] = 1.0
        cols += scen
        if with_perf:
            cols += [float(r["team_eff"]), float(r["team_dmg"]), float(r["n_inactive"])]
        return cols

    for label, with_perf in (("objective-only (scenario+stars+secondary+win)", False),
                             ("objective + performance", True)):
        X = np.array([design(r, with_perf) for r in rows])
        y = np.log(np.array([r["team_raw"] for r in rows]))
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ coef
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot
        print("\n[%s] R2 = %.4f  (n=%d)" % (label, r2, len(rows)))
        print("  intercept      : %.3f" % coef[0])
        print("  stars          : %.4f" % coef[1])
        print("  secondary      : %.4f" % coef[2])
        print("  is_win         : %.4f" % coef[3])
        if with_perf:
            print("  team_eff       : %.6f" % coef[-3])
            print("  team_dmg       : %.6f" % coef[-2])
            print("  n_inactive     : %.4f" % coef[-1])


def main():
    path = "ops_efficiency_full.jsonl"
    matches = load(path)
    rows = match_rows(matches)
    describe(rows)
    regression(rows)


if __name__ == "__main__":
    main()
