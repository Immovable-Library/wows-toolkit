"""Per-bracket survival-rate curves merged into one large figure."""
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


def label_of(scen, name_map):
    if scen in name_map:
        n, b, v = name_map[scen]
        return "%s %s" % (n, b) if b else n
    MAP_NAME = {
        "Ridge": "神盾", "NavalBase": "杀人鲸", "Labyrinth": "营救猛禽",
        "Naval_Defense": "防守纽波特", "Advance": "那莱", "Atoll": "最终前线",
        "LePVE": "赫尔墨斯", "USS_CL": "樱花绽放",
    }
    NEW_NAME = {
        "WW2_OPERATION_1": "北极护航", "WW2_OPERATION_2": "东京快车",
        "WW2_OPERATION_3": "太平洋攻势",
    }
    for code, name in MAP_NAME.items():
        if code in scen:
            if "Flagships" in scen:
                return "%s 9-10" % name
            if "MEDIUM" in scen:
                return "%s 7-9" % name
            if "HIGH" in scen:
                return "%s 8-11" % name
            return "%s 6-8" % name
    for code, name in NEW_NAME.items():
        if code in scen:
            if "67LVL" in scen:
                return "%s 6-7" % name
            if "89LVL" in scen:
                return "%s 7-9" % name
            if "1011LVL" in scen:
                return "%s 9-11" % name
    return scen


def main():
    lifetime = {}
    for line in open("output/lifetime_cache.jsonl", encoding="utf-8"):
        a, aid, life, dur = json.loads(line)
        lifetime[(a, aid)] = (life, dur)

    name_map = {}
    if os.path.exists("output/ops_name_table.json"):
        for e in json.load(open("output/ops_name_table.json", encoding="utf-8")):
            name_map[e["scenario"]] = (e["name"], e["bracket"], e["variant"])

    matches = collections.defaultdict(list)
    for line in open("ops_efficiency_full.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if not r.get("raw_exp") or r.get("raw_exp") <= 0:
            continue
        life, dur = lifetime.get((r["arena_id"], r["account_id"]), (None, r.get("duration_sec")))
        r["surv"] = survival_ratio(life, dur)
        matches[r["scenario"]].append(r)

    cls_codes = {"DD": 0, "CL/CA": 1, "BB": 2, "CV": 3, "SS": 4}

    panels = []
    for scen, rows in matches.items():
        if len(rows) < 80:
            continue
        by_arena = collections.defaultdict(list)
        for r in rows:
            by_arena[r["arena_id"]].append(r)
        recs = []
        for arena, grp in by_arena.items():
            if len(grp) < 2:
                continue
            for r in grp:
                recs.append({
                    "cls": r["ship_class"], "xp": r["raw_exp"], "surv": r["surv"],
                    "eff": r.get("efficiency") or 0.0,
                    "scout": (r.get("scouting_damage") or 0.0) / 100000.0,
                    "arena": arena,
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
        A = np.column_stack([X[:, j] for j in range(len(feats) + 5)])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        resid = y - A @ coef

        bins = np.arange(0.0, 1.05, 0.1)
        mids, means, counts = [], [], []
        for lo, hi in zip(bins[:-1], bins[1:]):
            mask = (surv >= lo) & (surv < hi)
            if hi >= 0.999:
                mask = (surv >= lo) & (surv <= 1.0)
            if mask.sum() < 4:
                continue
            mids.append((lo + hi) / 2)
            means.append(float(resid[mask].mean()))
            counts.append(int(mask.sum()))
        if len(mids) < 3:
            continue
        mids = np.array(mids)
        means = np.array(means)
        w = np.sqrt(np.array(counts, dtype=float))
        quad = np.polyfit(mids, means, 2, w=w)
        panels.append({
            "label": label_of(scen, name_map),
            "n": len(recs),
            "mids": mids, "means": means, "counts": counts,
            "quad_a": float(quad[0]),
        })

    panels.sort(key=lambda p: -p["n"])
    ncol = 5
    nrow = (len(panels) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.0 * ncol, 2.8 * nrow))
    axes = np.array(axes).reshape(-1)

    for ax, p in zip(axes, panels):
        mids = p["mids"]
        means = p["means"]
        w = np.sqrt(np.array(p["counts"], dtype=float))
        quad = np.polyfit(mids, means, 2, w=w)
        lin = np.polyfit(mids, means, 1, w=w)
        xs = np.linspace(0, 1, 50)
        ax.scatter(mids, means, s=np.sqrt(p["counts"]) * 3, alpha=0.6, color="#2b83ba")
        ax.plot(xs, np.polyval(lin, xs), "--", color="#888", linewidth=1)
        ax.plot(xs, np.polyval(quad, xs), "-", color="#d7191c", linewidth=1.5)
        tag = "递减" if quad[0] < 0 else ("递增" if quad[0] > 0 else "线性")
        ax.set_title("%s\nn=%d a=%.0f(%s)" % (p["label"], p["n"], quad[0], tag), fontsize=8)
        ax.set_xlim(0, 1)
        ax.set_xticks([0, 0.5, 1])
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
        ax.axhline(0, color="#ccc", linewidth=0.7)
        ax.set_xlabel("存活比例", fontsize=7)
        ax.set_ylabel("隔离伤害后经验", fontsize=7)

    for ax in axes[len(panels):]:
        ax.axis("off")

    fig.suptitle("各分房：存活带来的经验累积曲线（红=二次拟合，虚=线性；a<0 表示后期速率递减）", fontsize=14)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.savefig("output/survival_charts/rate_by_bracket.png", dpi=110)
    plt.close()

    with open("output/survival_rate_by_bracket.json", "w", encoding="utf-8") as fh:
        json.dump([{
            "label": p["label"], "n": p["n"], "quad_a": p["quad_a"],
            "binned": [{"mid": round(float(m), 2), "mean_xp": round(float(v), 1)}
                       for m, v in zip(p["mids"], p["means"])],
        } for p in panels], fh, indent=2, ensure_ascii=False)

    print("panels:", len(panels))
    for p in panels:
        tag = "递减" if p["quad_a"] < 0 else ("递增" if p["quad_a"] > 0 else "线性")
        print("  %-16s n=%4d a=%7.0f %s" % (p["label"], p["n"], p["quad_a"], tag))
    print("chart -> output/survival_charts/rate_by_bracket.png")
    print("data  -> output/survival_rate_by_bracket.json")


if __name__ == "__main__":
    main()
