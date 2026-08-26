"""Render survival-vs-XP charts and a Markdown report."""
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


def load_rows():
    lifetime = {}
    for line in open("output/lifetime_cache.jsonl", encoding="utf-8"):
        a, aid, life, dur = json.loads(line)
        lifetime[(a, aid)] = (life, dur)
    name_map = {}
    if os.path.exists("output/ops_name_table.json"):
        for e in json.load(open("output/ops_name_table.json", encoding="utf-8")):
            name_map[e["scenario"]] = (e["name"], e["bracket"], e["variant"])

    MAP_NAME = {
        "Ridge": "神盾", "NavalBase": "杀人鲸", "Labyrinth": "营救猛禽",
        "Naval_Defense": "防守纽波特", "Advance": "那莱", "Atoll": "最终前线",
        "LePVE": "赫尔墨斯", "USS_CL": "樱花绽放",
    }
    NEW_NAME = {
        "WW2_OPERATION_1": "北极护航", "WW2_OPERATION_2": "东京快车",
        "WW2_OPERATION_3": "太平洋攻势",
    }

    def label(scen):
        if scen in name_map:
            n, b, v = name_map[scen]
            return "%s %s" % (n, b) if b else n
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

    by_scen = collections.defaultdict(list)
    for line in open("ops_efficiency_full.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if not r.get("raw_exp") or r.get("raw_exp") <= 0:
            continue
        life, dur = lifetime.get((r["arena_id"], r["account_id"]), (None, r.get("duration_sec")))
        sr = survival_ratio(life, dur)
        by_scen[label(r["scenario"])].append((sr, r["raw_exp"]))
    return by_scen


def main():
    stats = json.load(open("output/survival_analysis.json", encoding="utf-8"))
    per = stats["per_scenario"]
    wm = stats["within_match"]
    os.makedirs("output/survival_charts", exist_ok=True)

    # 1. correlation bar chart
    items = sorted([s for s in per if s["corr"] is not None], key=lambda s: s["corr"])
    labels = [s["label"] for s in items]
    corrs = [s["corr"] for s in items]
    fig, ax = plt.subplots(figsize=(10, 0.32 * len(items) + 2))
    colors = ["#2b83ba" if c >= 0 else "#d7191c" for c in corrs]
    ax.barh(labels, corrs, color=colors)
    ax.set_xlabel("存活时长与基础经验的相关性 (Pearson r)")
    ax.set_title("各剧情地图/分房：存活时长 vs 基础经验 相关性")
    ax.axvline(0, color="#333", linewidth=0.8)
    for i, c in enumerate(corrs):
        ax.text(c + (0.008 if c >= 0 else -0.008), i, "%.2f" % c, va="center",
                ha="left" if c >= 0 else "right", fontsize=8)
    ax.set_xlim(min(corrs) - 0.12, max(corrs) + 0.12)
    plt.tight_layout()
    plt.savefig("output/survival_charts/corr_bar.png", dpi=120)
    plt.close()

    # 2. scatter grid for top 9 by sample size
    by_scen = load_rows()
    top = sorted(by_scen.items(), key=lambda kv: -len(kv[1]))[:9]
    fig, axes = plt.subplots(3, 3, figsize=(14, 12))
    for ax, (label, pairs) in zip(axes.flat, top):
        xs = np.array([p[0] for p in pairs], dtype=float)
        ys = np.array([p[1] for p in pairs], dtype=float)
        ax.scatter(xs, ys, s=6, alpha=0.25, color="#2b83ba")
        if len(xs) > 10:
            k = np.polyfit(xs, ys, 1)
            ax.plot([0, 1], np.polyval(k, [0, 1]), color="#d7191c", linewidth=1.5)
        ax.set_title("%s (n=%d)" % (label, len(xs)), fontsize=10)
        ax.set_xlabel("存活比例")
        ax.set_ylabel("基础经验")
        ax.set_xlim(-0.02, 1.02)
    for ax in axes.flat[len(top):]:
        ax.axis("off")
    plt.suptitle("存活时长 vs 基础经验（样本量前 9 的地图/分房）", fontsize=14)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.savefig("output/survival_charts/scatter_grid.png", dpi=120)
    plt.close()

    # 3. binned survival heatmap for top 12
    top12 = sorted([s for s in per if s["binned"]], key=lambda s: -s["n"])[:12]
    bins = ["0-25%", "25-50%", "50-75%", "75-99%", "100%"]
    mat = np.full((len(bins), len(top12)), np.nan)
    for j, s in enumerate(top12):
        for b in s["binned"]:
            i = bins.index(b["bucket"])
            if 0 <= i < len(bins):
                mat[i, j] = b["mean_xp"]
    fig, ax = plt.subplots(figsize=(12, 4.5))
    im = ax.imshow(mat, aspect="auto", cmap="YlGnBu")
    ax.set_xticks(range(len(top12)))
    ax.set_xticklabels([s["label"] for s in top12], rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(len(bins)))
    ax.set_yticklabels(bins)
    ax.set_xlabel("剧情地图/分房")
    ax.set_ylabel("存活时长区间")
    ax.set_title("各存活区间的平均基础经验（样本量前 12 地图）")
    for i in range(len(bins)):
        for j in range(len(top12)):
            v = mat[i, j]
            if not np.isnan(v):
                ax.text(j, i, "%.0f" % v, ha="center", va="center", fontsize=8)
    plt.colorbar(im, ax=ax, label="平均基础经验")
    plt.tight_layout()
    plt.savefig("output/survival_charts/binned_heatmap.png", dpi=120)
    plt.close()

    # report
    lines = []
    lines.append("# 存活时长与经验收益（按地图/分房）\n")
    lines.append("> 口径：基础经验（raw_exp，不含高账 1.65）。存活时长 = 公开结果第 22 列")
    lines.append("> `life_time_sec`；幸存到结束的玩家该值等于对局时长，缺失/为 0 按存活到结束处理。\n")
    lines.append("## 全局结论（局内去均值，隔离效率/点亮/舰种）\n")
    lines.append("- 控制吃船效率 + 点亮 + 舰种后，存活比例从 0 到 1（早死 → 活到最后）约 +**%.0f** 基础经验。" % wm["survival_coef_xp"])
    lines.append("- 加入存活比例后 R² 从 %.4f 升到 %.4f，说明存活时长对经验有独立于伤害的正向贡献。\n" % (wm["r2_base"], wm["r2_full"]))
    lines.append("## 分地图/分房统计\n")
    lines.append("| 剧情/分房 | 样本 | 相关性 r | 平均基础经验 |")
    lines.append("|---|---|---|---|")
    for s in per:
        corr = "%.3f" % s["corr"] if s["corr"] is not None else "-"
        lines.append("| %s | %d | %s | %.1f |" % (s["label"], s["n"], corr, s["mean_xp"]))
    lines.append("")
    lines.append("## 分档均值（样本量前 12）\n")
    lines.append("| 剧情/分房 | 0-25% | 25-50% | 50-75% | 75-99% | 100% |")
    lines.append("|---|---|---|---|---|---|")
    for s in top12:
        vals = {b["bucket"]: b["mean_xp"] for b in s["binned"]}
        row = [s["label"]]
        for name in bins:
            row.append("%.0f" % vals[name] if name in vals else "-")
        lines.append("| " + " | ".join(map(str, row)) + " |")
    lines.append("")
    lines.append("## 图\n")
    lines.append("![相关性](output/survival_charts/corr_bar.png)\n")
    lines.append("![散点](output/survival_charts/scatter_grid.png)\n")
    lines.append("![分档热图](output/survival_charts/binned_heatmap.png)\n")
    with open("output/survival_report.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("charts -> output/survival_charts/")
    print("report -> output/survival_report.md")


if __name__ == "__main__":
    main()
