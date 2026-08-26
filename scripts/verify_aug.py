#!/usr/bin/env python3
"""Verify the Operations PR formula across a full month of replays.

Two outputs per rated match:
  1. ranking: sort players by Rating, compare to the actual XP settlement rank.
  2. XP: predicted_xp = rXP * ship_expected_xp, compared to the replay base XP.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os

from verify_pr_formula import (
    PREMIUM_XP_MULT,
    account_actual,
    rating as compute_rating,
    ship_expected,
)


def load_strength(path):
    return {r["ship_id"]: r for r in json.load(open(path, encoding="utf-8"))}


def subtract_match(op, raw_exp, is_win, stars):
    op = json.loads(json.dumps(op))
    if op.get("battles", 0) > 0:
        op["battles"] -= 1
    if is_win:
        op["wins"] = max(0, op.get("wins", 0) - 1)
        wbt = op.get("wins_by_tasks")
        if wbt and stars is not None:
            k = str(int(stars))
            wbt[k] = max(0, wbt.get(k, 0) - 1)
    else:
        op["losses"] = max(0, op.get("losses", 0) - 1)
    if raw_exp is not None:
        op["xp"] = max(0, op.get("xp", 0) - int(raw_exp * PREMIUM_XP_MULT))
    return op


def ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: (-vals[i], i))
    r = [0] * len(vals)
    for pos, idx in enumerate(order):
        r[idx] = pos
    return r


def spearman(xs, ys):
    if len(xs) < 2:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
    return num / den if den else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--strength", default="output/ship_strength_full.json")
    ap.add_argument("--main-cache", default="cache/ship_strength_cache.json")
    ap.add_argument("--extra-cache", action="append", default=[],
                    help="additional cache fetched after August (repeatable)")
    ap.add_argument("--replays", default="tmp_aug.jsonl")
    ap.add_argument("--min-ship-battles", type=int, default=5)
    args = ap.parse_args(argv)

    strength = load_strength(args.strength)
    main = json.load(open(args.main_cache, encoding="utf-8"))
    accounts = dict(main.get("accounts", {}))
    ships = dict(main.get("ships", {}))
    fetched_ids = set()
    for p in args.extra_cache:
        c = json.load(open(p, encoding="utf-8"))
        accounts.update(c.get("accounts", {}))
        ships.update(c.get("ships", {}))
        fetched_ids.update(c.get("accounts", {}))
    cache = {"accounts": accounts, "ships": ships}
    f_main = os.path.getmtime(args.main_cache)

    rows = [json.loads(x) for x in open(args.replays, encoding="utf-8")]
    acct_matches = collections.defaultdict(list)
    for r in rows:
        acct_matches[r["account_id"]].append(
            (r["ts"], r.get("raw_exp"), r.get("is_win"), r.get("stars_server"), r["ship_id"]))

    matches = collections.defaultdict(list)
    for r in rows:
        matches[r["arena_id"]].append(r)

    xp_rhos = []
    xp_only_rhos = []
    norm_rhos = []
    ship_norm_rhos = []
    base_rhos = []
    top1 = 0
    top3 = 0
    raw_top1 = 0
    norm_top1 = 0
    ship_norm_top1 = 0
    rated_matches = 0
    pred_xps = []
    actual_xps = []
    ratings_all = []

    for arena, grp in sorted(matches.items(), key=lambda kv: min(r["ts"] for r in kv[1])):
        ts = min(r["ts"] for r in grp)
        rated = []
        for r in grp:
            aid = r["account_id"]
            if str(aid) not in cache["accounts"] or str(aid) not in cache["ships"]:
                continue
            ship_op = None
            for e in cache["ships"][str(aid)].get("ships", []):
                if e["ship_id"] == r["ship_id"]:
                    ship_op = json.loads(json.dumps(e.get("oper_solo") or {}))
                    break
            if ship_op is None:
                continue
            for (mts, m_xp, m_win, m_stars, m_ship) in acct_matches[aid]:
                if mts >= ts and m_ship == r["ship_id"]:
                    if str(aid) in fetched_ids or mts <= f_main:
                        ship_op = subtract_match(ship_op, m_xp, m_win, m_stars)
            if ship_op.get("battles", 0) < args.min_ship_battles:
                continue
            ship_actual = account_actual(ship_op)
            if ship_actual["xp"] is None or ship_actual["win"] is None or ship_actual["five_star"] is None:
                continue
            se = ship_expected(cache, aid, r["ship_id"], strength)
            ship_expected_d = {"xp": se["xp"], "win": se["win"], "five_star": se["five_star"]}
            rr = compute_rating(ship_actual, ship_expected_d)
            predicted_xp = rr["r_xp"] * se["xp"]
            rated.append({"aid": aid, "rating": rr["rating"], "r_xp": rr["r_xp"],
                          "xp": r.get("raw_exp"), "pred_xp": predicted_xp,
                          "ship_xp": ship_actual["xp"], "ship_exp": se["xp"],
                          "ship_rxp": rr["r_xp"]})
            pred_xps.append(predicted_xp)
            actual_xps.append(r.get("raw_exp"))
            ratings_all.append(rr["rating"])

        if len(rated) < 3:
            continue
        rated_matches += 1
        rho = spearman([x["rating"] for x in rated], [x["xp"] or 0 for x in rated])
        if rho is not None:
            xp_rhos.append(rho)
        xo = spearman([x["pred_xp"] for x in rated], [x["xp"] or 0 for x in rated])
        if xo is not None:
            xp_only_rhos.append(xo)
        no = spearman([x["r_xp"] for x in rated],
                      [(x["xp"] or 0) / x["ship_exp"] for x in rated])
        if no is not None:
            norm_rhos.append(no)
        ship_norm_rated = [x for x in rated if x["ship_rxp"] is not None]
        if len(ship_norm_rated) >= 3:
            sn = spearman([x["ship_rxp"] for x in ship_norm_rated],
                          [(x["xp"] or 0) / x["ship_exp"] for x in ship_norm_rated])
            if sn is not None:
                ship_norm_rhos.append(sn)
        base_rated = [x for x in rated if x["ship_xp"] is not None]
        if len(base_rated) >= 3:
            br = spearman([x["ship_xp"] for x in base_rated], [x["xp"] or 0 for x in base_rated])
            if br is not None:
                base_rhos.append(br)
        by_xp = sorted(rated, key=lambda x: -(x["xp"] or 0))
        pred = sorted(rated, key=lambda x: -x["rating"])
        if pred[0]["aid"] == by_xp[0]["aid"]:
            top1 += 1
        if by_xp[0]["aid"] in {x["aid"] for x in pred[:3]}:
            top3 += 1
        pred_raw = sorted(rated, key=lambda x: -x["pred_xp"])
        if pred_raw[0]["aid"] == by_xp[0]["aid"]:
            raw_top1 += 1
        by_norm = sorted(rated, key=lambda x: -(x["xp"] or 0) / x["ship_exp"])
        pred_norm = sorted(rated, key=lambda x: -x["r_xp"])
        if pred_norm[0]["aid"] == by_norm[0]["aid"]:
            norm_top1 += 1
        if len(ship_norm_rated) >= 3:
            by_ship_norm = sorted(ship_norm_rated, key=lambda x: -(x["xp"] or 0) / x["ship_exp"])
            pred_ship_norm = sorted(ship_norm_rated, key=lambda x: -x["ship_rxp"])
            if pred_ship_norm[0]["aid"] == by_ship_norm[0]["aid"]:
                ship_norm_top1 += 1

    pe = pearson(pred_xps, actual_xps)
    sp = spearman(pred_xps, actual_xps)
    mae = mean([abs(p - a) for p, a in zip(pred_xps, actual_xps)]) if pred_xps else None
    rmse = math.sqrt(mean([(p - a) ** 2 for p, a in zip(pred_xps, actual_xps)])) if pred_xps else None
    mean_a = mean(actual_xps)
    ss_res = sum((a - p) ** 2 for a, p in zip(actual_xps, pred_xps))
    ss_tot = sum((a - mean_a) ** 2 for a in actual_xps)
    r2 = 1 - ss_res / ss_tot if ss_tot else None

    print("AUGUST OPERATIONS VERIFICATION")
    print("  rated matches (>=3 rated players): %d / %d" % (rated_matches, len(matches)))
    print("  player-match observations         : %d" % len(pred_xps))
    print()
    print("RANKING (ship-level: rXP = ship_avg_xp / ship_expected_xp; weights XP=700, five_star=0, win=0)")
    print("  RAW target (panel XP)      : ship_avg_xp -> mean Spearman %s, top-1 %d/%d = %.1f%%" % (
        ("%.3f" % mean(xp_only_rhos)) if xp_only_rhos else "n/a",
        raw_top1, rated_matches, 100 * raw_top1 / rated_matches if rated_matches else 0))
    print("  NORMALIZED (XP / ship_exp)  : ship_rxp    -> mean Spearman %s, top-1 %d/%d = %.1f%%" % (
        ("%.3f" % mean(norm_rhos)) if norm_rhos else "n/a",
        norm_top1, rated_matches, 100 * norm_top1 / rated_matches if rated_matches else 0))
    print()
    print("XP (predicted_xp = rXP * ship_expected_xp, base XP)")
    print("  Pearson       : %s" % ("%.3f" % pe if pe is not None else "n/a"))
    print("  Spearman      : %s" % ("%.3f" % sp if sp is not None else "n/a"))
    print("  MAE           : %.1f" % mae if mae is not None else "  MAE           : n/a")
    print("  RMSE          : %.1f" % rmse if rmse is not None else "  RMSE          : n/a")
    print("  R^2           : %s" % ("%.3f" % r2 if r2 is not None else "n/a"))
    print("  mean actual   : %.1f" % mean_a if mean_a is not None else "  mean actual   : n/a")
    print("  mean predicted: %.1f" % mean(pred_xps) if pred_xps else "  mean predicted: n/a")
    return 0


def mean(v):
    return sum(v) / len(v) if v else None


def median(v):
    if not v:
        return None
    s = sorted(v)
    n = len(s)
    return (s[n // 2] + s[(n - 1) // 2]) / 2


if __name__ == "__main__":
    raise SystemExit(main())
