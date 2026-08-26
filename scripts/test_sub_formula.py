#!/usr/bin/env python3
"""Quick check of the sub-efficiency formula using kills as an efficiency proxy.

The community formula: a submarine's pre-bonus efficiency share is y, its
bonus efficiency is 1.75*y, so its final XP share is x = 1.75*y/(1+0.75*y).

We cannot observe efficiency directly (no per-target damage in the replay
summary), so here we proxy y with the sub's share of team kills. This is an
approximation: kills miss partial-damage contributions.
"""
from __future__ import annotations

import sqlite3
import statistics


CLASSES = {"DD", "CL/CA", "BB", "CV", "SS"}


def fmean(v):
    return statistics.fmean(v) if v else float("nan")


def main():
    con = sqlite3.connect("replays.db")
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "select * from rows where scenario_family in ('WW2_OP(new)','PCVO(legacy_op)') "
        "and fields_resolved=1 and raw_exp is not null and raw_exp > 0")]
    con.close()

    matches = {}
    for r in rows:
        matches.setdefault(r["arena_id"], []).append(r)

    obs = []
    for arena, grp in matches.items():
        team_raw = sum(r["raw_exp"] for r in grp)
        team_frags = sum(r["frags"] or 0 for r in grp)
        team_dmg = sum(r["damage"] or 0 for r in grp)
        if not team_raw or not team_frags or not team_dmg:
            continue
        subs = [r for r in grp if r["ship_class"] == "SS"]
        if not subs:
            continue
        for s in subs:
            y_frag = (s["frags"] or 0) / team_frags
            y_dmg = (s["damage"] or 0) / team_dmg
            x_actual = s["raw_exp"] / team_raw
            x_pred = 1.75 * y_frag / (1 + 0.75 * y_frag)
            obs.append({
                "ship": s["ship_name"],
                "y_frag": y_frag,
                "y_dmg": y_dmg,
                "x_actual": x_actual,
                "x_pred": x_pred,
            })

    print("SUB EFFICIENCY FORMULA CHECK (y proxied by kill share), n=%d subs" % len(obs))
    print()
    print("  mean sub share of team kills  (y_frag)  : %.3f" % fmean([o["y_frag"] for o in obs]))
    print("  mean sub share of team damage (y_dmg)   : %.3f" % fmean([o["y_dmg"] for o in obs]))
    print("  mean sub share of team base XP (x_actual): %.3f" % fmean([o["x_actual"] for o in obs]))
    print("  formula-predicted XP share     (x_pred)  : %.3f" % fmean([o["x_pred"] for o in obs]))
    print()
    print("  mean (x_actual - y_frag) : %+.3f  (bonus over kill share)" % fmean([o["x_actual"] - o["y_frag"] for o in obs]))
    print("  mean (x_pred   - y_frag) : %+.3f  (formula's predicted bonus)" % fmean([o["x_pred"] - o["y_frag"] for o in obs]))
    print("  mean (x_actual - y_dmg)  : %+.3f  (bonus over damage share)" % fmean([o["x_actual"] - o["y_dmg"] for o in obs]))
    print()
    print("  mean |x_actual - x_pred| : %.3f" % fmean([abs(o["x_actual"] - o["x_pred"]) for o in obs]))
    print("  mean |x_actual - y_frag| : %.3f" % fmean([abs(o["x_actual"] - o["y_frag"]) for o in obs]))
    print("  mean |x_actual - y_dmg|  : %.3f" % fmean([abs(o["x_actual"] - o["y_dmg"]) for o in obs]))

    # top subs by observed share
    by_ship = {}
    for o in obs:
        by_ship.setdefault(o["ship"], []).append(o["x_actual"])
    print()
    print("  top subs by mean actual XP share (n>=2):")
    for name, shares in sorted(by_ship.items(), key=lambda kv: -fmean(kv[1])):
        if len(shares) >= 2:
            print("    %-20s n=%2d mean_share=%.3f" % (name, len(shares), fmean(shares)))


if __name__ == "__main__":
    main()
