#!/usr/bin/env python3
"""Fit operations XP share regressions on fine-grained damage types.

Model (within-match demeaned share OLS, mirroring analyze_damage_concentration):
    share_i = raw_exp_i / team_raw
    share ~ eff_by_type + scouting_damage/100000 + class dummies

Class dummies cover all five classes (DD, CL/CA, BB, CV, SS) and enter raw;
continuous regressors and the XP share are centered on the match mean. Rows
with zero raw XP or zero total efficiency are excluded. Standard errors are
HC0. The damage-type set is discovered from the extracted data: categories
with zero total (event-mode weapons such as lasers/missiles) are excluded.
"""
from __future__ import annotations

import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_ops_replays import normalize_class


ROOT = Path(__file__).resolve().parent.parent
CLASSES = ["DD", "CL/CA", "BB", "CV", "SS"]
DUMMIES = ["DD", "CL/CA", "BB", "CV", "SS"]


def load_rows():
    dt_path = ROOT / "output" / "damage_type_analysis.jsonl"
    rows = [json.loads(l) for l in dt_path.open(encoding="utf-8")]

    ship_class = {}
    eff_path = ROOT / "ops_efficiency_full.jsonl"
    if eff_path.exists():
        for l in eff_path.open(encoding="utf-8"):
            r = json.loads(l)
            ship_class[(r["arena_id"], r["account_id"])] = r["ship_class"]

    ships = {}
    cache_path = ROOT / "ships_cache.json"
    if cache_path.exists():
        ships = json.loads(cache_path.read_text(encoding="utf-8"))

    out = []
    for r in rows:
        key = (r["arena_id"], r["account_id"])
        cls = ship_class.get(key)
        if cls is None:
            entry = ships.get(str(r["ship_id"])) if r.get("ship_id") is not None else None
            cls = normalize_class(entry.get("type")) if entry else None
        if cls not in CLASSES:
            continue
        if not r.get("team_raw") or r["team_raw"] <= 0:
            continue
        out.append({**r, "ship_class": cls})
    return out


def categories(rows):
    """eff_* columns present in the data with nonzero totals, in fixed order."""
    totals = collections.Counter()
    for r in rows:
        for k, v in r.items():
            if k.startswith("eff_") and k != "eff_total":
                totals[k] += float(v or 0.0)
    return [k for k in sorted(totals) if totals[k] > 0]


def design(rows, types, with_class=True):
    """Within-match demeaned design (match fixed effects)."""
    groups = collections.defaultdict(list)
    for r in rows:
        if not (r.get("raw_exp") or 0) > 0 or not (r.get("eff_total") or 0) > 0:
            continue
        groups[r["arena_id"]].append(r)
    Xs, ys = [], []
    for grp in groups.values():
        if len(grp) < 2:
            continue
        Xg, yg = [], []
        for r in grp:
            x = [float(r.get(t) or 0.0) for t in types]
            x.append((float(r.get("scouting_damage") or 0.0)) / 100000.0)
            if with_class:
                x.extend(1.0 if r["ship_class"] == d else 0.0 for d in DUMMIES)
            Xg.append(x)
            yg.append(float(r["raw_exp"]) / r["team_raw"])
        Xg = np.array(Xg, dtype=float)
        yg = np.array(yg, dtype=float)
        Xs.append(Xg - Xg.mean(axis=0))
        ys.append(yg - yg.mean())
    k = len(types) + 1 + (len(DUMMIES) if with_class else 0)
    X = np.vstack(Xs) if Xs else np.zeros((0, k), dtype=float)
    y = np.concatenate(ys) if ys else np.zeros(0, dtype=float)
    return X, y


def fit(X, y, names):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    n, k = X.shape
    sse = float(resid @ resid)
    sst = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - sse / sst if sst > 0 else float("nan")
    xtx_inv = np.linalg.pinv(X.T @ X)
    meat = (X * resid[:, None] ** 2).T @ X
    cov = xtx_inv @ meat @ xtx_inv
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    return {
        "coef": [float(c) for c in coef],
        "se": [float(s) for s in se],
        "n": int(n),
        "r2": r2,
        "sse": sse,
        "fields": names,
    }


def normal_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def contrast_test(X, y, names, i, j):
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ coef
    xtx_inv = np.linalg.pinv(X.T @ X)
    meat = (X * resid[:, None] ** 2).T @ X
    cov = xtx_inv @ meat @ xtx_inv
    diff = float(coef[i] - coef[j])
    var = cov[i, i] + cov[j, j] - 2.0 * cov[i, j]
    se = math.sqrt(max(var, 0.0))
    t = diff / se if se > 1e-12 else None
    p = 2.0 * (1.0 - normal_cdf(abs(t))) if t is not None else None
    return {"a": names[i], "b": names[j], "diff": diff, "se": se,
            "t": t, "p": p}


def presence(rows, types):
    out = {}
    totals = {t: 0.0 for t in types}
    counts = collections.Counter()
    games = collections.defaultdict(set)
    for r in rows:
        for t in types:
            v = float(r.get(t) or 0.0)
            if v > 0:
                totals[t] += v
                counts[t] += 1
                games[t].add(r["arena_id"])
    total_eff = sum(r.get("eff_total") or 0.0 for r in rows)
    for t in types:
        out[t] = {
            "total_eff": round(totals[t], 3),
            "share_of_eff": round(totals[t] / total_eff, 5) if total_eff else 0.0,
            "n_rows_nonzero": counts[t],
            "n_games_nonzero": len(games[t]),
        }
    return out, total_eff


def class_composition(rows, types):
    out = {}
    for cls in CLASSES:
        sub = [r for r in rows if r["ship_class"] == cls]
        if not sub:
            continue
        rec = {"n": len(sub)}
        for t in types + ["eff_total"]:
            rec[t] = round(sum(r.get(t) or 0.0 for r in sub) / len(sub), 3)
        tot = sum(r.get("eff_total") or 0.0 for r in sub)
        for t in types:
            rec["share_%s" % t] = round(
                sum(r.get(t) or 0.0 for r in sub) / tot, 4) if tot else 0.0
        out[cls] = rec
    return out


def main(argv=None):
    rows = load_rows()
    types = categories(rows)
    games = len({r["arena_id"] for r in rows})
    print("rows=%d games=%d" % (len(rows), games), file=sys.stderr)
    print("nonzero damage types: %d" % len(types), file=sys.stderr)
    for t in types:
        print("  %s" % t, file=sys.stderr)

    pres, total_eff = presence(rows, types)

    names_full = types + ["scouting_damage"] + DUMMIES
    base = ["eff_total", "scouting_damage"] + DUMMIES
    no_class = types + ["scouting_damage"]

    results = {
        "n_replays": games,
        "n_rows": len(rows),
        "total_eff": round(total_eff, 3),
        "damage_types": types,
        "presence": pres,
    }

    X, y = design(rows, ["eff_total"])
    results["baseline"] = fit(X, y, base)

    X_cls, y_cls = design(rows, types)
    results["damage_split"] = fit(X_cls, y_cls, names_full)

    X_nc, y_nc = design(rows, types, with_class=False)
    results["no_class"] = fit(X_nc, y_nc, no_class)

    contrasts = [
        ("eff_secondary", "eff_main"),
        ("eff_tbomb", "eff_torpedo"),
        ("eff_tbomb", "eff_bomb"),
        ("eff_bomb", "eff_main"),
        ("eff_torpedo", "eff_main"),
        ("eff_fire", "eff_main"),
        ("eff_flood", "eff_main"),
        ("eff_rocket", "eff_bomb"),
        ("eff_skip", "eff_bomb"),
        ("eff_depth_charge", "eff_main"),
    ]
    results["contrasts"] = {}
    for a, b in contrasts:
        if a not in types or b not in types:
            continue
        i = names_full.index(a)
        j = names_full.index(b)
        results["contrasts"]["%s_vs_%s" % (a, b)] = contrast_test(X_cls, y_cls, names_full, i, j)

    results["class_composition"] = class_composition(rows, types)

    out = ROOT / "output" / "damage_type_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\npresence (total eff / share / rows / games):")
    for t in types:
        p = pres[t]
        print("  %-14s %10.1f %7.4f %8d %7d" % (
            t, p["total_eff"], p["share_of_eff"], p["n_rows_nonzero"], p["n_games_nonzero"]))
    print("\nbaseline R2=%.4f  damage_split R2=%.4f" % (
        results["baseline"]["r2"], results["damage_split"]["r2"]))
    m = results["damage_split"]
    for f, c, s in zip(m["fields"], m["coef"], m["se"]):
        print("  %-14s %10.5f (se %.5f)" % (f, c, s))
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
