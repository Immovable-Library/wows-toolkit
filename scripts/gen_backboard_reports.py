#!/usr/bin/env python3
"""Generate one backboard report per map: every bracket and every wave
composition variant (the fixed pool the match draws from)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


FAMILY_CN = {
    "Ridge": "神盾",
    "NavalBase": "杀人鲸",
    "Labyrinth": "营救猛禽",
    "Naval_Defense": "防守纽波特",
    "Advance": "那莱",
    "Atoll": "最终前线",
    "LePVE": "赫尔墨斯",
    "USS_CL": "樱花绽放",
    "WW2_OPERATION_1": "北极护航",
    "WW2_OPERATION_2": "东京快车",
    "WW2_OPERATION_3": "太平洋攻势",
}

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

WAVE_ORDER = [
    "第一波", "第二波", "第三波", "第四波", "第五波", "第六波", "第七波",
    "第八波", "第九波", "尾BOSS", "BOSS驱逐", "增援", "目标单位", "敌方运输",
    "运输船", "航母", "敌方运输·通讯舰", "特殊设施", "主力波", "终局",
    "增援1", "增援2", "增援3", "增援4", "增援5",
]


def bracket_key(br):
    return BRACKET_ORDER.index(br) if br in BRACKET_ORDER else len(BRACKET_ORDER)


def wave_key(lab):
    return WAVE_ORDER.index(lab) if lab in WAVE_ORDER else len(WAVE_ORDER)


def fmt_variant_ships(v):
    return "、".join(x["ship"] for x in v["ships"])


def main() -> int:
    variants = json.loads(Path("output/wave_variants.json").read_text(encoding="utf-8"))
    side_tasks = json.loads(Path("output/side_tasks.json").read_text(encoding="utf-8"))
    outdir = Path("output/backboard")
    outdir.mkdir(parents=True, exist_ok=True)

    index = []
    for family in sorted(variants.keys(), key=lambda f: list(FAMILY_CN).index(f) if f in FAMILY_CN else 999):
        cn = FAMILY_CN.get(family, family)
        lines = []
        a = lines.append
        a(f"# {cn} 背板报告")
        a("")
        a("> 本报告枚举该地图各分房、各波次的敌人构成分组。数据来自本地回放库，按场次（arena）去重统计。")
        a("> 随机性说明：主波多为固定构成；增援/目标单位/部分波次从固定池子中抽选，出现次数即样本中的抽取频次。")
        a("> 支线/随机任务（水雷舰 Hyaena、伏击者 Ambusher、占领点位 Alpha 等）与主波分开列出，其具体船名随分房变化但任务名固定。")
        a("> 本报告只覆盖敌人构成，不覆盖刷新点位（点位数据不在当前提取链路中）。")
        a("")

        brackets = sorted(variants[family].keys(), key=bracket_key)
        for br in brackets:
            a(f"## {BRACKET_LABEL.get(br, br)}")
            a("")
            waves = variants[family][br]
            for lab in sorted(waves.keys(), key=wave_key):
                vlist = waves[lab]
                a(f"### {lab}")
                a("")
                if len(vlist) == 1:
                    a(f"固定构成：{fmt_variant_ships(vlist[0])}")
                    a("")
                    a(f"（样本 {vlist[0]['matches']} 局，未观察到其它变体）")
                else:
                    total = sum(v["matches"] for v in vlist)
                    a("| 出现次数 | 占比 | 敌人构成 |")
                    a("|---|---|---|")
                    for v in vlist:
                        pct = (100.0 * v["matches"] / total) if total else 0.0
                        a("| %d | %.0f%% | %s |" % (v["matches"], pct, fmt_variant_ships(v)))
                a("")
            tasks = side_tasks.get(family, {}).get(br)
            if tasks:
                a("### 支线/随机任务")
                a("")
                a("| 任务（固定名称） | 敌人构成（随分房变化） |")
                a("|---|---|")
                for task, ships in sorted(tasks.items()):
                    s = "、".join("%s（%d 血）" % (sn, int(cell[1])) if cell[1] else sn
                                  for sn, cell in sorted(ships.items(), key=lambda kv: -kv[1][0]))
                    a("| %s | %s |" % (task, s))
                a("")

        path = outdir / f"{cn}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        index.append(f"- [{cn}](backboard/{cn}.md)")

    summary = ["# 剧情背板报告索引", ""]
    summary += index
    (outdir / "README.md").write_text("\n".join(summary), encoding="utf-8")
    print("wrote", len(index), "backboard reports ->", outdir, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
