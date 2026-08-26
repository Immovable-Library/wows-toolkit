"""Marginal XP rate vs survival time: is late-game XP gain slower?

We cannot see XP per timestamp, so we infer the survival-based XP rate from the
within-match survival effect. Residualize raw_exp on efficiency, scouting and
class inside each match, then bin the residual by survival_ratio. The slope
between adjacent bins is the marginal XP per unit survival.
"""
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, "scripts")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


def survival_ratio(life, dur):
    if life is None or life <= 0 or dur is None or dur <= 0:
        return 1.0
    return min(1.0, max(0.0, float(life) / float(dur)))


def main():
    lifetime = {}
    for line in open("output/lifetime_cache.jsonl", encoding="utf-8"):
        a, aid, life, dur = json.loads(line)
        lifetime[(a, aid)] = (life, dur)

    matches = collections.defaultdict(list)
    for line in open("ops_efficiency_full.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if not r.get("raw_exp") or r.get("raw_exp") <= 0:
            continue
        life, dur = lifetime.get((r["arena_id"], r["account_id"]), (None, r.get("duration_sec")))
        r["surv"] = survival_ratio(life, dur)
        matches[r["arena_id"]].append(r)

    cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}
    recs = []
    for arena, grp in matches.items():
        if len(grp) < 2:
            continue
        for r in grp:
            recs.append({
                "arena": arena, "cls": r["ship_class"], "xp": r["raw_exp"],
                "surv": r["surv"], "eff": r.get("efficiency") or 0.0,
                "scout": (r.get("scouting_damage") or 0.0) / 100000.0,
            })

    by_arena = collections.defaultdict(list)
    for z in recs:
        by_arena[z["arena"]].append(z)

    feats = ["eff", "scout"]
    X = np.zeros((len(recs), len(feats) + 5))
    y = np.zeros(len(recs))
    surv = np.zeros(len(recs))
    for i, z in enumerate(recs):
        grp = by_arena[z["arena"]]
        y[i] = z["xp"] - sum(q["xp"] for q in grp) / len(grp)
        for j, f in enumerate(feats):
            X[i, j] = z[f] - sum(q[f] for q in grp) / len(grp)
        X[i, len(feats) + cls_codes[z["cls"]]] = 1.0
        surv[i] = z["surv"]

    # residualize: remove eff + scout + class
    A = np.column_stack([X[:, j] for j in range(len(feats) + 5)])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ coef

    # bin residual by survival_ratio
    bins = np.arange(0.0, 1.05, 0.1)
    mids, means, counts = [], [], []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (surv >= lo) & (surv < hi)
        if hi >= 0.999:
            mask = (surv >= lo) & (surv <= 1.0)
        if mask.sum() < 5:
            continue
        mids.append((lo + hi) / 2)
        means.append(float(resid[mask].mean()))
        counts.append(int(mask.sum()))

    mids = np.array(mids)
    means = np.array(means)

    # linear and quadratic fit on the binned curve (weighted by count)
    w = np.sqrt(np.array(counts, dtype=float))
    lin = np.polyfit(mids, means, 1, w=w)
    quad = np.polyfit(mids, means, 2, w=w)
    pred_lin = np.polyval(lin, mids)
    pred_quad = np.polyval(quad, mids)

    # marginal rate between bins
    marg_x = (mids[:-1] + mids[1:]) / 2
    marg_y = np.diff(means) / np.diff(mids)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    ax.scatter(mids, means, s=np.sqrt(counts) * 4, alpha=0.6, color="#2b83ba")
    ax.plot(mids, pred_lin, "--", color="#555", label="线性拟合")
    ax.plot(mids, pred_quad, "-", color="#d7191c", label="二次拟合")
    ax.set_xlabel("存活比例（0=开局暴毙，1=活到最后）")
    ax.set_ylabel("局内去均值后的经验（去除伤害/点亮/舰种）")
    ax.set_title("存活带来的经验累积（隔离伤害后）")
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.bar(marg_x, marg_y, width=0.08, color="#2b83ba", alpha=0.7)
    ax.axhline(0, color="#333", linewidth=0.8)
    ax.set_xlabel("存活比例区间中点")
    ax.set_ylabel("边际经验（每单位存活比例）")
    ax.set_title("边际经验获取速率（相邻区间斜率）")
    ax.grid(alpha=0.3)

    # concavity check
    concavity = "递减（后期速率更低）" if quad[0] < 0 else ("递增" if quad[0] > 0 else "近似线性")
    fig.suptitle("经验获取速率 vs 存活时长 —— 二次项符号：%s (a=%.1f)" % (concavity, quad[0]), fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig("output/survival_charts/rate_curve.png", dpi=130)
    plt.close()

    out = {
        "n": len(recs),
        "linear_slope_xp_per_full_survival": round(float(lin[0]), 2),
        "quadratic_a": round(float(quad[0]), 2),
        "concavity": "concave" if quad[0] < 0 else ("convex" if quad[0] > 0 else "linear"),
        "binned": [{"mid": round(float(m), 2), "mean_residual_xp": round(float(v), 1),
                    "n": int(c)} for m, v, c in zip(mids, means, counts)],
        "marginal": [{"mid": round(float(m), 2), "rate_xp_per_survival": round(float(v), 1)}
                     for m, v in zip(marg_x, marg_y)],
    }
    with open("output/survival_rate_analysis.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print("linear slope (XP per full survival): %.1f" % lin[0])
    print("quadratic a: %.1f -> %s" % (quad[0], concavity))
    print("binned means:", {("%.0f%%" % (m * 100)): round(v, 0) for m, v in zip(mids, means)})
    print("marginal rates:", {("%.0f%%" % (m * 100)): round(v, 0) for m, v in zip(marg_x, marg_y)})
    print("chart -> output/survival_charts/rate_curve.png")
    print("data  -> output/survival_rate_analysis.json")


if __name__ == "__main__":
    main()
