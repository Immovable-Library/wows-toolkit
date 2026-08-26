#!/usr/bin/env python3
"""Verify the Operations PR formula by within-match settlement ranking.

For each replay, rate every player with the first-draft formula
(docs/WOWS_OPERATIONS_STATS_PLAN.md section 8.6), then compare the formula's
ranking to the actual settlement ranking (XP, and damage as a secondary label).
"""
from __future__ import annotations

import argparse
import collections
import json
import math

from verify_pr_formula import (
    PREMIUM_XP_MULT,
    account_actual,
    account_expected,
    rating as compute_rating,
)


def load_strength(path):
    return {r["ship_id"]: r for r in json.load(open(path, encoding="utf-8"))}


def subtract_match(op, raw_exp, is_win, stars):
    op = json.loads(json.dumps(op))
    b = op.get("battles", 0)
    if b > 0:
        op["battles"] = b - 1
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


def spearman(xs, ys):
    def ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: (-vals[i], i))
        r = [0] * len(vals)
        for pos, idx in enumerate(order):
            r[idx] = pos
        return r
    if len(xs) < 2:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--strength", default="output/ship_strength_full.json")
    ap.add_argument("--main-cache", default="cache/ship_strength_cache.json")
    ap.add_argument("--verify-cache", default="cache/verify_8rep_cache.json")
    ap.add_argument("--replays", default="tmp_8rep.jsonl")
    ap.add_argument("--min-battles", type=int, default=10)
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args(argv)

    strength = load_strength(args.strength)
    main = json.load(open(args.main_cache, encoding="utf-8"))
    ver = json.load(open(args.verify_cache, encoding="utf-8"))
    cache = {
        "accounts": {**main.get("accounts", {}), **ver.get("accounts", {})},
        "ships": {**main.get("ships", {}), **ver.get("ships", {})},
    }
    fetched_ids = set(ver.get("accounts", {}))

    rows = [json.loads(x) for x in open(args.replays, encoding="utf-8")]
    matches = collections.defaultdict(list)
    for r in rows:
        matches[r["arena_id"]].append(r)

    print("match-level result (sorted by time)")
    print("%-10s %-4s %-10s %-22s %-7s %-7s" % (
        "arena", "n", "label", "predicted_top", "spear", "top1"))
    xp_rhos = []
    dmg_rhos = []
    top1_xp = 0
    top1_dmg = 0
    rated_matches = 0

    for arena, grp in sorted(matches.items(), key=lambda kv: min(r["ts"] for r in kv[1])):
        ts = min(r["ts"] for r in grp)
        rated = []
        for r in grp:
            aid = r["account_id"]
            if str(aid) not in cache["accounts"] or str(aid) not in cache["ships"]:
                continue
            op = cache["accounts"][str(aid)].get("oper_solo")
            if not op:
                continue
            # Leak-free pre-match stats: only the freshly fetched accounts
            # include today's match(es), so only they need the subtraction.
            if str(aid) in fetched_ids:
                for r2 in rows:
                    if r2["account_id"] == aid and r2.get("ts", 0) >= ts:
                        op = subtract_match(op, r2.get("raw_exp"), r2.get("is_win"),
                                            r2.get("stars_server"))
            if op.get("battles", 0) < args.min_battles:
                continue
            actual = account_actual(op)
            expected = account_expected(cache, aid, strength)
            rr = compute_rating(actual, expected)
            rated.append({
                "aid": aid,
                "name": cache["accounts"][str(aid)].get("nickname"),
                "rating": rr["rating"],
                "xp": r.get("raw_exp"),
                "dmg": r.get("damage"),
            })

        if len(rated) < 3:
            continue
        rated_matches += 1
        by_xp = sorted(rated, key=lambda x: -(x["xp"] or 0))
        by_dmg = sorted(rated, key=lambda x: -(x["dmg"] or 0))
        pred = sorted(rated, key=lambda x: -x["rating"])
        rho_xp = spearman([x["rating"] for x in rated], [x["xp"] or 0 for x in rated])
        rho_dmg = spearman([x["rating"] for x in rated], [x["dmg"] or 0 for x in rated])
        if rho_xp is not None:
            xp_rhos.append(rho_xp)
        if rho_dmg is not None:
            dmg_rhos.append(rho_dmg)
        hit_xp = 1 if pred[0]["aid"] == by_xp[0]["aid"] else 0
        hit_dmg = 1 if pred[0]["aid"] == by_dmg[0]["aid"] else 0
        top1_xp += hit_xp
        top1_dmg += hit_dmg
        print("%-10s %-4d %-10s %-22s %-7s %-7s" % (
            str(arena)[-8:], len(rated), "xp", pred[0]["name"], "-" if rho_xp is None else ("%.2f" % rho_xp), hit_xp))
        print("%-10s %-4s %-10s %-22s %-7s %-7s" % (
            "", "", "dmg", "", "-" if rho_dmg is None else ("%.2f" % rho_dmg), hit_dmg))

    if args.detail:
        print("\nPER-MATCH DETAIL (players in predicted order)")
        for arena, grp in sorted(matches.items(), key=lambda kv: min(r["ts"] for r in kv[1])):
            ts = min(r["ts"] for r in grp)
            rated = []
            for r in grp:
                aid = r["account_id"]
                if str(aid) not in cache["accounts"] or str(aid) not in cache["ships"]:
                    continue
                op = cache["accounts"][str(aid)].get("oper_solo")
                if not op:
                    continue
                if str(aid) in fetched_ids:
                    for r2 in rows:
                        if r2["account_id"] == aid and r2.get("ts", 0) >= ts:
                            op = subtract_match(op, r2.get("raw_exp"), r2.get("is_win"),
                                                r2.get("stars_server"))
                if op.get("battles", 0) < args.min_battles:
                    continue
                actual = account_actual(op)
                expected = account_expected(cache, aid, strength)
                rr = compute_rating(actual, expected)
                rated.append({"aid": aid, "name": cache["accounts"][str(aid)].get("nickname"),
                              "rating": rr["rating"], "xp": r.get("raw_exp"),
                              "dmg": r.get("damage")})
            if len(rated) < 3:
                continue
            pred = sorted(rated, key=lambda x: -x["rating"])
            by_xp = sorted(rated, key=lambda x: -(x["xp"] or 0))
            by_dmg = sorted(rated, key=lambda x: -(x["dmg"] or 0))
            xp_rank = {p["aid"]: i + 1 for i, p in enumerate(by_xp)}
            dmg_rank = {p["aid"]: i + 1 for i, p in enumerate(by_dmg)}
            print("\narena %s (n=%d)" % (str(arena)[-8:], len(rated)))
            print("  %-3s %-22s %-7s %-8s %-4s %-8s %-4s" % (
                "#", "name", "rating", "xp", "xpR", "dmg", "dmgR"))
            for i, p in enumerate(pred, 1):
                print("  %-3d %-22s %-7.0f %-8s %-4d %-8s %-4d" % (
                    i, p["name"], p["rating"], p["xp"], xp_rank[p["aid"]],
                    p["dmg"], dmg_rank[p["aid"]]))

    def mean(v):
        return sum(v) / len(v) if v else None

    print("\nSUMMARY")
    print("  rated matches (>=3 rated players): %d / %d" % (rated_matches, len(matches)))
    print("  mean Spearman vs XP   : %s" % (("%.3f" % mean(xp_rhos)) if xp_rhos else "n/a"))
    print("  mean Spearman vs DMG  : %s" % (("%.3f" % mean(dmg_rhos)) if dmg_rhos else "n/a"))
    print("  top-1 hit (XP)        : %d / %d" % (top1_xp, rated_matches))
    print("  top-1 hit (DMG)       : %d / %d" % (top1_dmg, rated_matches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
