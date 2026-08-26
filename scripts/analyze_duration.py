"""Does battle duration move the operations XP pool or per-player share?

Duration is a match-level variable, so it cannot be identified inside the
within-match allocation regression. We test it at the pool level against the
objective model, and at the player level by adding log(duration) to a pooled
allocation regression.
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


def match_rows(matches):
    out = []
    for arena, grp in matches.items():
        first = grp[0]
        if first["stars_server"] is None or first["is_win"] is None:
            continue
        if first["duration_sec"] is None or first["duration_sec"] <= 0:
            continue
        out.append({
            "arena_id": arena,
            "scenario": first["scenario"],
            "stars": first["stars_server"],
            "is_win": first["is_win"],
            "duration": float(first["duration_sec"]),
            "team_raw": sum(r["raw_exp"] for r in grp),
            "team_eff": sum(r.get("efficiency") or 0 for r in grp),
        })
    return out


def pool_regression(rows):
    scen = sorted({r["scenario"] for r in rows})
    code = {s: i for i, s in enumerate(scen)}
    y = np.log(np.array([r["team_raw"] for r in rows]))

    def design(r, dur_mode):
        cols = [1.0, float(r["stars"]), 1.0 if r["is_win"] else 0.0]
        v = [0.0] * len(scen)
        v[code[r["scenario"]]] = 1.0
        cols += v
        if dur_mode == "log":
            cols.append(math.log(r["duration"]))
        elif dur_mode == "lin":
            cols.append(r["duration"] / 60.0)
        return cols

    def fit(mode):
        X = np.array([design(r, mode) for r in rows])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ coef
        r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
        return coef, r2

    _, r2_obj = fit("none")
    coef_lin, r2_lin = fit("lin")
    coef_log, r2_log = fit("log")

    print("pool-level log(team_raw), n=%d" % len(rows))
    print("  objective only          : R2=%.4f" % r2_obj)
    print("  + duration (min)        : R2=%.4f  coef=%.5f per min" % (r2_lin, coef_lin[-1]))
    print("  + log(duration)         : R2=%.4f  coef=%.5f (elasticity)" % (r2_log, coef_log[-1]))
    # duration range in minutes
    dur_min = np.array([r["duration"] / 60 for r in rows])
    print("  duration range: %.1f - %.1f min" % (dur_min.min(), dur_min.max()))
    if dur_mode_has_effect(coef_log[-1], dur_min):
        print("  implied pool multiplier across duration range: x%.3f" % math.exp(coef_log[-1] * (math.log(dur_min.max()) - math.log(dur_min.min()))))
    return {
        "n": len(rows),
        "r2_obj": round(r2_obj, 4),
        "r2_lin": round(r2_lin, 4),
        "r2_log": round(r2_log, 4),
        "coef_per_min": round(float(coef_lin[-1]), 5),
        "coef_log_elasticity": round(float(coef_log[-1]), 5),
    }


def dur_mode_has_effect(coef, _):
    return abs(coef) > 1e-9


def player_level(matches):
    """Pooled allocation regression with scenario fixed effects and log(duration)."""
    rows = []
    scen_all = sorted({grp[0]["scenario"] for grp in matches.values()})
    scen_code = {s: i for i, s in enumerate(scen_all)}
    for arena, grp in matches.items():
        first = grp[0]
        if first["stars_server"] is None or first["is_win"] is None:
            continue
        if not first.get("duration_sec"):
            continue
        team_raw = sum(r["raw_exp"] for r in grp)
        if team_raw <= 0 or len(grp) < 2:
            continue
        n = len(grp)
        for r in grp:
            share = r["raw_exp"] / team_raw
            if share <= 0:
                continue
            rows.append({
                "share": share,
                "eff": r.get("efficiency") or 0.0,
                "scout": (r.get("scouting_damage") or 0.0) / 100000.0,
                "cls": r["ship_class"],
                "scenario": first["scenario"],
                "n": n,
                "logdur": math.log(float(first["duration_sec"])),
            })

    cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}
    X = []
    y = []
    for r in rows:
        row = [1.0, r["eff"], r["scout"], r["logdur"], 1.0 / r["n"]]
        d = [0.0] * 5
        d[cls_codes[r["cls"]]] = 1.0
        row += d
        sv = [0.0] * len(scen_all)
        sv[scen_code[r["scenario"]]] = 1.0
        row += sv
        X.append(row)
        y.append(math.log(r["share"]))

    X = np.array(X)
    y = np.array(y)
    class_idx = list(range(5, 10))
    scen_idx = list(range(10, 10 + len(scen_all)))
    def fit(cols):
        A = X[:, cols]
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        pred = A @ coef
        r2 = 1 - float(np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
        return coef, r2

    base = [0, 1, 2, 4] + class_idx + scen_idx
    withdur = [0, 1, 2, 3, 4] + class_idx + scen_idx
    coef_base, r2_base = fit(base)
    coef_dur, r2_dur = fit(withdur)

    print("\nplayer-level log(share), n=%d" % len(rows))
    print("  eff+scout+floor+class         : R2=%.4f" % r2_base)
    print("  + log(duration)               : R2=%.4f  coef=%.5f" % (r2_dur, coef_dur[3]))
    return {
        "n": len(rows),
        "r2_base": round(r2_base, 4),
        "r2_dur": round(r2_dur, 4),
        "coef_logdur": round(float(coef_dur[3]), 5),
    }


def main():
    matches = load("ops_efficiency_full.jsonl")
    rows = match_rows(matches)
    p = pool_regression(rows)
    pl = player_level(matches)
    with open("output/duration_analysis.json", "w", encoding="utf-8") as fh:
        json.dump({"pool": p, "player": pl}, fh, indent=2)
    print("\nresults -> output/duration_analysis.json")


if __name__ == "__main__":
    main()
