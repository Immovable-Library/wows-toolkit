import json


# Internal scenario key -> (Chinese name, base matchup bracket label, tier range).
# Map codenames come from replay metadata / corpus golden snapshots:
#   Ridge -> Mountain Range (Aegis), NavalBase -> Newport, Labyrinth -> Raptor,
#   Naval_Defense -> Hermes, Advance -> Ultimate Frontier, Atoll -> Narai,
#   USS_CL -> Cherry Blossom, LePVE -> Killer Whale.
# The three new WW2 operations are numbered in release order:
#   OP1 Arctic Convoy, OP2 Tokyo Express, OP3 Pacific Offensive.
NAME = {
    "Ridge": "神盾",
    "NavalBase": "防守纽波特",
    "Labyrinth": "猛禽救援",
    "Naval_Defense": "赫尔墨斯",
    "Advance": "最终前线",
    "Atoll": "纳莱",
    "LePVE": "杀人鲸",
    "USS_CL": "樱花绽放",
}

NEW_NAME = {
    "WW2_OPERATION_1": "北极护航",
    "WW2_OPERATION_2": "东京快车",
    "WW2_OPERATION_3": "太平洋攻势",
}

BRACKET_TIER = {
    "67LVL": "6-7",
    "89LVL": "7-9",
    "1011LVL": "9-11",
    "MEDIUM": "7-9",
    "HIGH": "8-11",
    "-": "6-8",
}


def name_for(scenario):
    if scenario.startswith("WW2_OPERATION"):
        stem = "_".join(scenario.split("_")[:3])
        return NEW_NAME[stem], None
    for key, label in NAME.items():
        if key in scenario:
            return label, key
    return scenario, None


def main():
    rows = json.load(open("output/pool_table.json", encoding="utf-8"))
    out = []
    for r in rows:
        s = r["scenario"]
        label, key = name_for(s)
        if s.startswith("WW2_OPERATION"):
            lvl = r["level"]
            bracket = BRACKET_TIER.get(lvl, lvl)
            variant = lvl
        elif "_MEDIUM_LVL" in s:
            bracket = "7-9"
            variant = "中级"
        elif "_HIGH_LVL" in s and "Flagships" not in s:
            bracket = "8-11"
            variant = "高级"
        elif "Flagships" in s:
            bracket = "9-10"
            variant = "旗舰"
        else:
            bracket = "6-8"
            variant = "普通"
        out.append({
            "scenario": s,
            "name": label,
            "bracket": bracket,
            "variant": variant,
            "base_pool": r["base_pool"],
            "n_full": r["n_full"],
        })

    with open("output/ops_name_table.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    # Primary table: base operation name + bracket + pool.
    print("### 剧情 - 分房 - 基础经验池（胜局 + 5 星）\n")
    for r in out:
        print(f"- {r['name']} {r['bracket']}分房 经验池 {r['base_pool']:.0f}（{r['variant']}，样本 {r['n_full']}）")


if __name__ == "__main__":
    main()
