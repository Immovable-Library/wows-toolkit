#!/usr/bin/env python3
"""Generate the compact per-map per-wave big table (Markdown + CSV)."""

from __future__ import annotations

import collections
import json
import struct
from pathlib import Path


FAMILY_ORDER = [
    ("WW2_OPERATION_1", "89LVL", "北极护航 OP_12"),
    ("WW2_OPERATION_2", "89LVL", "东京快车 OP_13"),
    ("WW2_OPERATION_3", "89LVL", "太平洋攻势 OP_14"),
    ("Ridge", "BASE", "神盾 Ridge"),
    ("NavalBase", "BASE", "杀人鲸 NavalBase"),
    ("Labyrinth", "BASE", "营救猛禽 Labyrinth"),
    ("Naval_Defense", "BASE", "防守纽波特 Naval_Defense"),
    ("Advance", "BASE", "那莱 Narai"),
    ("Atoll", "BASE", "最终前线 Atoll"),
    ("LePVE", "BASE", "赫尔墨斯 Hermes"),
    ("USS_CL", "BASE", "樱花绽放 Cherry"),
]

WAVE_COLS = ["第一波", "第二波", "第三波", "第四波", "第五波", "第六波", "第七波", "第八波", "第九波"]
SPECIAL_COLS = ["尾BOSS", "BOSS驱逐", "增援", "目标单位", "敌方运输", "敌方运输·通讯舰", "运输船", "航母", "特殊设施", "主力波", "终局", "增援1", "增援2", "增援3", "增援4", "增援5"]

COASTAL = {
    "WW2_OPERATION_1": "无岸炮",
    "WW2_OPERATION_2": "无岸炮",
    "WW2_OPERATION_3": "无岸炮",
    "Ridge": "ART_*（岸炮）",
    "NavalBase": "无岸炮",
    "Labyrinth": "ART_*（岸炮）",
    "Naval_Defense": "ART_*（岸炮）",
    "Advance": "无岸炮",
    "Atoll": "ART_*（岸炮）",
    "LePVE": "ART_*（岸炮）",
    "USS_CL": "ART_*（岸炮）",
}


def load_mo(path):
    data = Path(path).read_bytes()
    magic = struct.unpack_from("<I", data, 0)[0]
    e = "<" if magic == 0x950412DE else ">"
    _rev, n, o_orig, o_trans, _hs, _oh = struct.unpack_from(e + "IIIIII", data, 4)

    def table(off):
        out = []
        for i in range(n):
            ln, so = struct.unpack_from(e + "II", data, off + i * 8)
            out.append(data[so:so + ln].decode("utf-8", "replace"))
        return out

    return dict(zip(table(o_orig), table(o_trans)))


def friendly_ai(mo):
    out = collections.defaultdict(list)
    with open("output/wave_raw.jsonl", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            family = r.get("family")
            if not family:
                continue
            names = []
            for e in r["entities"]:
                n = e.get("name") or ""
                if e.get("team_id") == 0 and (e.get("account_id") or 0) < 0 and n.startswith("IDS_"):
                    names.append(mo.get(n, n))
            if names:
                out[family].extend(names)
    return {f: sorted(set(v)) for f, v in out.items()}


def cell_ships(items):
    return "、".join(it["ship"] for it in items)


def main() -> int:
    ships = json.loads(Path("output/wave_ships_full.json").read_text(encoding="utf-8"))
    mo = load_mo("D:/World_of_Warships/bin/13015811/res/texts/zh/LC_MESSAGES/global.mo")
    fr = friendly_ai(mo)

    rows = []
    for family, bracket, label in FAMILY_ORDER:
        waves = ships.get(family, {}).get(bracket, {})
        row = {"地图": label}
        for col in WAVE_COLS:
            items = waves.get(col)
            row[col] = cell_ships(items) if items else "—"
        special = []
        for col in SPECIAL_COLS:
            items = waves.get(col)
            if items:
                special.append("%s：%s" % (col, cell_ships(items)))
        if COASTAL.get(family):
            special.append(COASTAL[family])
        row["敌方特殊/设施"] = "；".join(special) if special else "—"
        row["友方辅助/目标"] = "、".join(fr.get(family, [])) if family in fr else "—"
        rows.append(row)

    cols = ["地图"] + WAVE_COLS + ["敌方特殊/设施", "友方辅助/目标"]

    md = []
    md.append("# 剧情敌人波次对照总表（中文船名，最常见分房）")
    md.append("")
    md.append("数据来源：本地回放库（`D:\\codexProject\\wows-toolkit\\replays` 与 `D:\\World_of_Warships\\replays`）。")
    md.append("本表展示每张地图最常见的分房：新剧情 89LVL（8~9），老剧情 BASE（普通 6–8）；全部分房见 `ops_wave_report.md` 与 `backboard/`。")
    md.append("波次按敌人显示名（字头/编组名）还原先后顺序；`敌方特殊/设施` 与 `友方辅助/目标` 已按阵营拆分。")
    md.append("")
    md.append("| " + " | ".join(cols) + " |")
    md.append("|" + "---|" * len(cols))
    for row in rows:
        md.append("| " + " | ".join(row[c] for c in cols) + " |")
    md.append("")
    Path("output/ops_enemy_wave_table.md").write_text("\n".join(md), encoding="utf-8")

    csv = [",".join(cols)]
    for row in rows:
        csv.append(",".join('"%s"' % row[c].replace('"', '""') for c in cols))
    Path("output/ops_enemy_wave_table.csv").write_text("\n".join(csv) + "\n", encoding="utf-8")

    print("wrote output/ops_enemy_wave_table.md and .csv", file=__import__("sys").stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
