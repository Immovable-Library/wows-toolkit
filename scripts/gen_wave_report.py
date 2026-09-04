#!/usr/bin/env python3
"""Generate the full per-map per-bracket operations report (Markdown)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


FAMILY_CN = {
    "Ridge": "神盾（Aegis / Mountain Range）",
    "NavalBase": "杀人鲸（Killer Whale / Naval Base）",
    "Labyrinth": "营救猛禽（Raptor Rescue / Labyrinth）",
    "Naval_Defense": "防守纽波特（Defense of Naval Station Newport）",
    "Advance": "那莱（Narai / Sunda Islands）",
    "Atoll": "最终前线（The Ultimate Frontier）",
    "LePVE": "赫尔墨斯（Hermes）",
    "USS_CL": "樱花绽放（Cherry Blossom）",
    "WW2_OPERATION_1": "北极护航（Arctic Convoy）",
    "WW2_OPERATION_2": "东京快车（Tokyo Express）",
    "WW2_OPERATION_3": "太平洋攻势（Pacific Offensive）",
}

FAMILY_ORDER = [
    "WW2_OPERATION_1", "WW2_OPERATION_2", "WW2_OPERATION_3",
    "Ridge", "NavalBase", "Labyrinth", "Naval_Defense",
    "Advance", "Atoll", "LePVE", "USS_CL",
]

BRACKET_LABEL = {
    "BASE": "普通（6–8）",
    "MEDIUM": "中等",
    "HIGH": "高等",
    "67LVL": "6~7 级",
    "89LVL": "8~9 级",
    "9LVL": "9 级",
    "1011LVL": "10~11 级",
}

BRACKET_ORDER = ["67LVL", "89LVL", "9LVL", "1011LVL", "BASE", "MEDIUM", "HIGH"]


def bracket_key(br):
    return BRACKET_ORDER.index(br) if br in BRACKET_ORDER else len(BRACKET_ORDER)


def fmt_ships(items):
    seen = {}
    for it in items:
        name = it["ship"]
        hp = it.get("hp")
        if name not in seen:
            seen[name] = hp
    parts = []
    for name, hp in seen.items():
        if hp:
            parts.append(f"{name}（{int(hp):,} 血）")
        else:
            parts.append(name)
    return "、".join(parts)


def fmt_coef(w):
    if not w or w.get("relative") is None:
        return w.get("note") if w else "—"
    rel = w["relative"]
    t = w.get("t")
    se = w.get("se")
    if t is None or abs(t) < 1.96:
        star = ""
    elif abs(t) >= 2.58:
        star = " ***"
    else:
        star = " **"
    s = "%.2f" % rel
    if se is not None:
        s += " ± %.2f" % se
    if t is not None:
        s += "（t=%+.1f）" % t
    return s + star


def main() -> int:
    ships = json.loads(Path("output/wave_ships_full.json").read_text(encoding="utf-8"))
    coefs = json.loads(Path("output/wave_coefs_full.json").read_text(encoding="utf-8"))

    out = []
    a = out.append

    a("# 剧情逐波敌人构成与收益系数（全分房）")
    a("")
    a("> 本报告可直接上传 GitHub。数据来自本地回放解包，覆盖新剧情 67/89/9/1011 分房与老剧情普通/中等/高等（排除旗舰模式）。")
    a("")

    a("## TL;DR")
    a("")
    a("1. **逐波代表船名已补齐为中文**，并覆盖全部分房；血量均为剧情内实际初始血量（`max_health`）。")
    a("2. **绝大多数波次的收益系数 ≈ 1.0**，即“满血击杀任意船 = 1 个船等价，收益与船的血量 / 等级无关”，未发现系统性高收益波次。")
    a("3. **名字带 `BOSS` 的单位不等于高收益，也不等于低收益**：北极护航 `BOSS_DD_*` 实际是 Z-38（游戏内显示名 `Fritz 1~3`），系数约 1.0；各图尾 boss（武藏 / 约克）相对全图平均约 1.0–1.7x，统计上不显著。")
    a("4. **明确的低收益单位是运输船 / 通讯 / 环境设施**，其每船等价收益显著低于常规战舰（约 0.25–0.7x）。")
    a("5. 早前“东京快车尾 boss 武藏 2.296x、北极护航 BOSS_DD 0.756x”**均未复现**。")
    a("")

    a("## 口径与方法")
    a("")
    a("- **分房覆盖**：新剧情取 `67LVL`（6~7）、`89LVL`（8~9）、`9LVL`（9）、`1011LVL`（10~11）；老剧情取 `BASE`（普通 6–8）、`MEDIUM`（中等）、`HIGH`（高等）。`Flagships`（旗舰模式）已排除。")
    a("- **支线/随机任务已剔除**：水雷舰 `Hyaena`、伏击者 `Ambusher`（及其支援 `Beta`）、占领点位 `Alpha`、点位 `Gamma`/`Delta`、侦察站、港口等单位不计入主波次，单独见 `output/backboard/*.md`。")
    a("- **收益系数定义**：个人经验按“吃船效率”分配，吃船效率 = 你对某船的伤害 ÷ 该船剧情内血量。满血击杀任意船 = 1 个船等价。收益系数 = 每 1 个船等价的经验收益（相对值）。")
    a("- **估计方法**：局内去均值回归。因变量为玩家基础经验份额，自变量为该玩家对各波敌人造成的船等价效率、点亮伤害、舰种哑变量。")
    a("- **相对系数** = 该波系数 ÷ 其余所有敌人平均系数；`**`=5% 显著，`***`=1% 显著。")
    a("- **注意**：相对系数是“相对本图平均”，用于识别明显偏离，而非绝对倍率。")
    a("")

    a("## 逐图逐波表")
    a("")

    for family in FAMILY_ORDER:
        if family not in ships:
            continue
        a(f"### {FAMILY_CN.get(family, family)}")
        a("")
        brackets = sorted(ships[family].keys(), key=bracket_key)
        for br in brackets:
            waves = ships[family][br]
            meta = coefs.get(family, {}).get(br, {})
            coef_waves = {w["wave"]: w for w in meta.get("waves", [])}
            a(f"#### {BRACKET_LABEL.get(br, br)}")
            a("")
            if meta:
                a(f"> 样本：{meta.get('n_matches')} 局 / {meta.get('n_players')} 人次；基线模型 R²≈{meta.get('r2_base', 0):.3f}。")
                a("")
            a("| 波次 | 代表船名（剧情内血量） | 相对收益系数（vs 全图平均） |")
            a("|---|---|---|")
            for lab in waves:
                items = waves[lab]
                c = coef_waves.get(lab)
                a("| %s | %s | %s |" % (lab, fmt_ships(items), fmt_coef(c)))
            a("")

    a("## 尾 boss 与特殊单位专项")
    a("")
    a("| 地图 | 分房 | 单位 | 船名（血量） | 相对收益系数 | 结论 |")
    a("|---|---|---|---|---|---|")
    a("| 东京快车 | 89LVL | `WAVE_36`（尾 boss） | 武藏（97,300） | ≈1.09（不显著） | 无高收益加成 |")
    a("| 太平洋攻势 | 89LVL | `WAVE_310`（尾 boss） | 武藏（97,300） | ≈1.67（不显著） | 疑似略高，未达显著 |")
    a("| 北极护航 | 89LVL | `WAVE_310`（尾 boss） | 约克（32,600） | ≈1.22（不显著） | 无高收益加成 |")
    a("| 北极护航 | 89LVL | `BOSS_DD_01~03` | Z-38（19,400，显示名 Fritz 1~3） | ≈0.96–1.00 | 无特殊加成 |")
    a("")

    a("## 主要结论")
    a("")
    a("1. 剧情个人经验按“吃船效率（伤害 ÷ 目标血量）”分配；满血击杀任意船 = 1 个船等价，与目标血量 / 等级无关。")
    a("2. 未发现明确的“高收益 boss”目标；`BOSS` 标签只是剧本内的特殊目标命名。")
    a("3. 运输船、通讯设施、环境设施等非战舰单位的每船等价收益显著偏低，是唯一稳定可见的“特殊系数”来源。")
    a("4. 尾 boss 武藏在东京快车约 1.09x、在太平洋攻势约 1.67x，均未达 5% 显著。")
    a("")

    a("## 复现")
    a("")
    a("```text")
    a("python scripts/extract_wave_data.py \"D:\\codexProject\\wows-toolkit\\replays\" \"D:\\World_of_Warships\\replays\" --out output\\wave_raw.jsonl --constants-dir constants_cache --ship-cache ships_cache.json --workers 8")
    a("python scripts/analyze_waves_full.py")
    a("python scripts/gen_wave_report.py")
    a("python scripts/gen_backboard_reports.py")
    a("```")
    a("")
    a("- 中间数据：`output/wave_raw.jsonl`、`output/wave_ships_full.json`、`output/wave_coefs_full.json`、`output/wave_variants.json`")
    a("- 最终报告：`output/ops_wave_report.md`、`output/backboard/*.md`")
    a("")

    a("## 局限")
    a("")
    a("- 部分冷门分房（如 9LVL、部分老剧情中等/高等）样本偏少，单波系数噪声较大，只作参考。")
    a("- 逐波效率在局内高度相关，单波系数不宜过度解读；结论以“整体≈1.0 + 明确低收益单位”为准。")
    a("- 本表为经验拟合结果，非 WG 服务端官方定式。")
    a("")

    Path("output/ops_wave_report.md").write_text("\n".join(out), encoding="utf-8")
    print("wrote output/ops_wave_report.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
