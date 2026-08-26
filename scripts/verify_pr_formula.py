#!/usr/bin/env python3
"""Verify the first-draft Operations PR formula against a set of replays.

Formula (docs/WOWS_OPERATIONS_STATS_PLAN.md section 8.6):

    rXP    = actual_avg_xp / expected_avg_xp
    rS     = actual_five_star / expected_five_star
    rW     = actual_win_rate / expected_win_rate
    Rating = 700 * rXP + 200 * rS + 100 * rW

Expected values come from output/ship_strength_full.json
(abs_xp_avg / five_star / win_rate), weighted by the player's per-ship
battle count (ships with >= 5 battles only). Ships missing from the strength
table fall back to the player's account mean.
"""
from __future__ import annotations

import argparse
import json

PREMIUM_XP_MULT = 1.65  # WG oper_solo.xp is premium-inclusive; base = api / 1.65

W_XP = 700
W_FIVE_STAR = 0  # kept in the formula, weight disabled
W_WIN = 0        # kept in the formula, weight disabled


def load_strength(path):
    tbl = json.load(open(path, encoding="utf-8"))
    return {r["ship_id"]: r for r in tbl}


def five_star_rate(op):
    b = op.get("battles", 0)
    if not b:
        return None
    return (op.get("wins_by_tasks") or {}).get("5", 0) / b


def account_actual(op):
    b = op["battles"]
    return {
        "battles": b,
        "xp": op["xp"] / b / PREMIUM_XP_MULT,
        "win": op["wins"] / b,
        "five_star": five_star_rate(op),
    }


def account_expected(cache, account_id, strength):
    acct_op = cache["accounts"][str(account_id)]["oper_solo"]
    actual = account_actual(acct_op)
    ships = cache["ships"][str(account_id)]["ships"]

    tot = 0
    num_xp = num_five = num_win = 0.0
    covered = 0
    fallback = 0
    for s in ships:
        op = s.get("oper_solo") or {}
        b = op.get("battles", 0)
        if b < 5:
            continue
        sid = s["ship_id"]
        row = strength.get(sid)
        if row is not None:
            ex = row["abs_xp_avg"]
            ef = row["five_star"]
            ew = row["win_rate"]
            covered += b
        else:
            ex = actual["xp"]
            ef = actual["five_star"]
            ew = actual["win"]
            fallback += b
        num_xp += ex * b
        num_five += ef * b
        num_win += ew * b
        tot += b

    return {
        "battles_weighted": tot,
        "covered_battles": covered,
        "fallback_battles": fallback,
        "xp": num_xp / tot if tot else None,
        "win": num_win / tot if tot else None,
        "five_star": num_five / tot if tot else None,
    }


def rating(actual, expected):
    r_xp = actual["xp"] / expected["xp"]
    r_s = actual["five_star"] / expected["five_star"]
    r_w = actual["win"] / expected["win"]
    return {
        "r_xp": r_xp,
        "r_s": r_s,
        "r_w": r_w,
        "rating": W_XP * r_xp + W_FIVE_STAR * r_s + W_WIN * r_w,
    }


def ship_expected(cache, account_id, ship_id, strength):
    actual = account_actual(cache["accounts"][str(account_id)]["oper_solo"])
    row = strength.get(ship_id)
    if row is not None:
        return {
            "xp": row["abs_xp_avg"],
            "win": row["win_rate"],
            "five_star": row["five_star"],
            "from": "table",
        }
    return {
        "xp": actual["xp"],
        "win": actual["win"],
        "five_star": actual["five_star"],
        "from": "account_mean",
    }


def ship_historical(cache, account_id, ship_id):
    ships = cache["ships"][str(account_id)]["ships"]
    for s in ships:
        if s["ship_id"] == ship_id:
            op = s.get("oper_solo") or {}
            b = op.get("battles", 0)
            return {
                "battles": b,
                "xp": (op["xp"] / b / PREMIUM_XP_MULT) if b else None,
                "win": (op["wins"] / b) if b else None,
                "five_star": five_star_rate(op),
            }
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--strength", default="output/ship_strength_full.json")
    ap.add_argument("--cache", default="cache/ship_strength_cache.json")
    ap.add_argument("--replays", default="tmp_8rep.jsonl")
    ap.add_argument("--account-id", type=int, default=566060956)
    args = ap.parse_args(argv)

    strength = load_strength(args.strength)
    cache = json.load(open(args.cache, encoding="utf-8"))
    aid = args.account_id

    actual = account_actual(cache["accounts"][str(aid)]["oper_solo"])
    expected = account_expected(cache, aid, strength)
    r = rating(actual, expected)
    print("ACCOUNT", aid)
    print("  actual  : xp=%.1f five_star=%.4f win=%.4f battles=%d" % (
        actual["xp"], actual["five_star"], actual["win"], actual["battles"]))
    print("  expected: xp=%.1f five_star=%.4f win=%.4f (weighted_battles=%d covered=%d fallback=%d)" % (
        expected["xp"], expected["five_star"], expected["win"],
        expected["battles_weighted"], expected["covered_battles"], expected["fallback_battles"]))
    print("  rXP=%.3f rS=%.3f rW=%.3f Rating=%.1f" % (r["r_xp"], r["r_s"], r["r_w"], r["rating"]))

    rows = [json.loads(x) for x in open(args.replays, encoding="utf-8")]
    me = [x for x in rows if x.get("account_id") == aid]
    me.sort(key=lambda x: x.get("ts") or 0)
    print("\nPER-MATCH")
    print("%-8s %-14s %-10s %-5s %-5s %-8s %-8s %-5s" % (
        "ship", "family", "win", "stars", "five", "raw_exp", "exp", "dmg"))
    for x in me:
        stars = x.get("stars_server")
        five = 1 if stars == 5 else 0
        print("%-8s %-14s %-5s %-5s %-5s %-8s %-8s %-5s" % (
            x.get("ship_name"), x.get("scenario_family"),
            "win" if x.get("is_win") else ("loss" if x.get("is_loss") else "draw"),
            stars, five, x.get("raw_exp"), x.get("exp"), x.get("damage")))

    print("\nSHIP EXPECTED + HISTORICAL")
    for sid, name in ((4276008752, "Knesebeck"), (4276041040, "Ipiranga")):
        se = ship_expected(cache, aid, sid, strength)
        sh = ship_historical(cache, aid, sid)
        print("  %s (%d): expected xp=%.1f five=%.4f win=%.4f [%s]" % (
            name, sid, se["xp"], se["five_star"], se["win"], se["from"]))
        if sh:
            print("            hist battles=%d xp=%s five=%.4f win=%.4f" % (
                sh["battles"],
                ("%.1f" % sh["xp"]) if sh["xp"] else None,
                sh["five_star"], sh["win"]))

    print("\nPER-MATCH RATING (rXP uses replay base XP; expected XP is WG-API basis)")
    print("%-8s %-5s %-5s %-5s %-8s %-8s %-7s %-7s %-8s %-8s" % (
        "ship", "win", "five", "stars", "raw_exp", "exp_xp", "rW", "rS",
        "rating", "rating1.5x"))
    ratings = []
    ratings_scaled = []
    wins = five_stars = 0
    for x in me:
        sid = x.get("ship_id")
        se = ship_expected(cache, aid, sid, strength)
        stars = x.get("stars_server")
        five = 1 if stars == 5 else 0
        win = 1 if x.get("is_win") else 0
        wins += win
        five_stars += five
        rw = win / se["win"]
        rs = five / se["five_star"]
        rx = x.get("raw_exp") / se["xp"]
        rx15 = x.get("raw_exp") * 1.5 / se["xp"]
        m = 700 * rx + 200 * rs + 100 * rw
        m15 = 700 * rx15 + 200 * rs + 100 * rw
        ratings.append(m)
        ratings_scaled.append(m15)
        print("%-8s %-5s %-5s %-5s %-8s %-8s %-7.2f %-7.2f %-8.1f %-8.1f" % (
            x.get("ship_name"), win, five, stars, x.get("raw_exp"), se["xp"],
            rw, rs, m, m15))

    import statistics
    print("\nSUMMARY")
    print("  win      : %d/%d = %.1f%%" % (wins, len(me), 100 * wins / len(me)))
    print("  five-star: %d/%d = %.1f%%" % (five_stars, len(me), 100 * five_stars / len(me)))
    print("  mean raw_exp: %.1f" % statistics.mean(x["raw_exp"] for x in me))
    print("  per-match rating mean/median (base xp)  : %.1f / %.1f" % (
        statistics.mean(ratings), statistics.median(ratings)))
    print("  per-match rating mean/median (1.5x xp)  : %.1f / %.1f" % (
        statistics.mean(ratings_scaled), statistics.median(ratings_scaled)))
    print("  account rating (predicted)              : %.1f" % r["rating"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
