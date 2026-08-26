# 总经验池（AI 工具版）

```yaml
model: team_raw ~ base[scenario] * (1.09 ^ stars) * (win ? 1 : 0.5)
target: log(team_raw)
n_matches: 2058
R2: 0.9576
coefficients:
  stars: 0.0860
  is_win: 0.8209
  team_eff: 0.0031
  team_dmg: 0.0
  n_inactive: -0.0283
```

## 基础经验池（46 场景，胜局 + 5 星口径）

### 剧情名 + 分房映射

```yaml
map_codenames:
  Ridge: {name: 神盾, base_bracket: 6-8}
  NavalBase: {name: 杀人鲸, base_bracket: 6-8}
  Labyrinth: {name: 营救猛禽, base_bracket: 6-8}
  Naval_Defense: {name: 防守纽波特, base_bracket: 6-8}
  Advance: {name: 那莱, base_bracket: 6-8}
  Atoll: {name: 最终前线, base_bracket: 6-8}
  LePVE: {name: 赫尔墨斯, base_bracket: 6-8}
  USS_CL: {name: 樱花绽放, base_bracket: 6-8}
new_operations:
  WW2_OPERATION_1: 北极护航
  WW2_OPERATION_2: 东京快车
  WW2_OPERATION_3: 太平洋攻势
new_op_internal:
  WW2_OPERATION_1: OP_12
  WW2_OPERATION_2: OP_13
  WW2_OPERATION_3: OP_14
new_op_first_wave:
  北极护航:
    "6-7": [卡尔斯鲁厄, T-22, V-170]
    "7-9": [纽伦堡, 莱比锡, T-61, Z-31]
    "9-11": [希佩尔, Z-31, Maerker, Bismarck]
  东京快车:
    "6-7": [若竹, 睦月]
    "7-9": [峰风, 吹雪, 初春]
    "9-11": [晓, 白露, 秋月, 夕立]
  太平洋攻势:
    "6-7": [河内, 石锤]
    "7-9": [金刚, 扶桑, 长门]
    "9-11": [长门, 纪伊, 安达太良]
brackets:
  "67LVL": 6-7
  "89LVL": 7-9
  "1011LVL": 9-11
  MEDIUM: 7-9
  HIGH: 8-11
  Flagships: 9-10
```

### 剧情 - 分房 - 基础经验池（胜局 + 5 星）

```yaml
神盾 6-8 普通: 7477
樱花绽放 6-8 普通: 7698
营救猛禽 6-8 普通: 7915
赫尔墨斯 6-8 普通: 7937
防守纽波特 6-8 普通: 8048
那莱 6-8 普通: 8051
最终前线 6-8 普通: 8109
杀人鲸 6-8 普通: 8352
北极护航 7-9: 8613
北极护航 9-11: 10059
东京快车 7-9: 8761
东京快车 9-11: 9981
太平洋攻势 7-9: 8867
太平洋攻势 9-11: 9970
神盾 7-9 中级: 8638
神盾 8-11 高级: 9884
神盾 9-10 旗舰: 13049
营救猛禽 7-9 中级: 8673
营救猛禽 8-11 高级: 9834
营救猛禽 9-10 旗舰: 13543
防守纽波特 7-9 中级: 8795
防守纽波特 8-11 高级: 9799
防守纽波特 9-10 旗舰: 13509
赫尔墨斯 7-9 中级: 8792
赫尔墨斯 8-11 高级: 9798
赫尔墨斯 9-10 旗舰: 14006
最终前线 7-9 中级: 8552
最终前线 8-11 高级: 9772
最终前线 9-10 旗舰: 13596
樱花绽放 7-9 中级: 8730
樱花绽放 8-11 高级: 9762
樱花绽放 9-10 旗舰: 13500
```

### 内部 ID 原始表（保留）

```yaml
PCVO010_OP_09_s09_LePVE_HIGH_LVL_Flagships_Random: {level: HIGH, n: 4, base: 14006}
PCVO009_OP_02_02_s06_Atoll_HIGH_LVL_Flagships_Random: {level: HIGH, n: 12, base: 13596}
PCVO003_OP_01_03_s03_Labyrinth_HIGH_LVL_Flagships_Random: {level: HIGH, n: 7, base: 13543}
PCVO004_OP_01_04_s02_Naval_Defense_HIGH_LVL_Flagships_Random: {level: HIGH, n: 12, base: 13509}
PCVO011_OP_10_s10_USS_CL_HIGH_LVL_Flagships_Random: {level: HIGH, n: 10, base: 13500}
PCVO001_OP_01_01_37_Ridge_HIGH_LVL_Flagships_Random: {level: HIGH, n: 7, base: 13049}
PCVO004_OP_01_04_s02_Naval_Defense_HIGH_LVL_Flagships_Fire: {level: HIGH, n: 1, base: 13031}
PCVO001_OP_01_01_37_Ridge_HIGH_LVL_Flagships_Drop: {level: HIGH, n: 2, base: 12984}
PCVO009_OP_02_02_s06_Atoll_HIGH_LVL_Flagships_Drop: {level: HIGH, n: 1, base: 12919}
PCVO003_OP_01_03_s03_Labyrinth_HIGH_LVL_Flagships_Focus: {level: HIGH, n: 1, base: 12784}
PCVO009_OP_02_02_s06_Atoll_HIGH_LVL_Flagships_Fire: {level: HIGH, n: 1, base: 12700}
PCVO010_OP_09_s09_LePVE_HIGH_LVL_Flagships_Fire: {level: HIGH, n: 1, base: 12557}
PCVO003_OP_01_03_s03_Labyrinth_HIGH_LVL_Flagships_Fire: {level: HIGH, n: 3, base: 12549}
PCVO010_OP_09_s09_LePVE_HIGH_LVL_Flagships_Drop: {level: HIGH, n: 1, base: 12409}
PCVO004_OP_01_04_s02_Naval_Defense_HIGH_LVL_Flagships_Drop: {level: HIGH, n: 2, base: 12382}
PCVO009_OP_02_02_s06_Atoll_HIGH_LVL_Flagships_Focus: {level: HIGH, n: 1, base: 12232}
PCVO003_OP_01_03_s03_Labyrinth_HIGH_LVL_Flagships_Drop: {level: HIGH, n: 2, base: 12155}
PCVO011_OP_10_s10_USS_CL_HIGH_LVL_Flagships_Fire: {level: HIGH, n: 1, base: 12115}
PCVO004_OP_01_04_s02_Naval_Defense_HIGH_LVL_Flagships_Focus: {level: HIGH, n: 1, base: 12032}
PCVO001_OP_01_01_37_Ridge_HIGH_LVL_Flagships_Focus: {level: HIGH, n: 1, base: 11774}
WW2_OPERATION_1_1011LVL: {level: 1011LVL, n: 12, base: 10059}
WW2_OPERATION_2_1011LVL: {level: 1011LVL, n: 7, base: 9981}
WW2_OPERATION_3_1011LVL: {level: 1011LVL, n: 27, base: 9970}
PCVO001_OP_01_01_37_Ridge_HIGH_LVL: {level: HIGH, n: 40, base: 9884}
PCVO003_OP_01_03_s03_Labyrinth_HIGH_LVL: {level: HIGH, n: 108, base: 9834}
PCVO004_OP_01_04_s02_Naval_Defense_HIGH_LVL: {level: HIGH, n: 98, base: 9799}
PCVO010_OP_09_s09_LePVE_HIGH_LVL: {level: HIGH, n: 33, base: 9798}
PCVO009_OP_02_02_s06_Atoll_HIGH_LVL: {level: HIGH, n: 117, base: 9772}
PCVO011_OP_10_s10_USS_CL_HIGH_LVL: {level: HIGH, n: 116, base: 9762}
WW2_OPERATION_3_89LVL: {level: 89LVL, n: 28, base: 8867}
PCVO004_OP_01_04_s02_Naval_Defense_MEDIUM_LVL: {level: MEDIUM, n: 35, base: 8795}
PCVO010_OP_09_s09_LePVE_MEDIUM_LVL: {level: MEDIUM, n: 13, base: 8792}
WW2_OPERATION_2_89LVL: {level: 89LVL, n: 16, base: 8761}
PCVO011_OP_10_s10_USS_CL_MEDIUM_LVL: {level: MEDIUM, n: 31, base: 8730}
PCVO003_OP_01_03_s03_Labyrinth_MEDIUM_LVL: {level: MEDIUM, n: 21, base: 8673}
PCVO001_OP_01_01_37_Ridge_MEDIUM_LVL: {level: MEDIUM, n: 15, base: 8638}
WW2_OPERATION_1_89LVL: {level: 89LVL, n: 3, base: 8613}
PCVO009_OP_02_02_s06_Atoll_MEDIUM_LVL: {level: MEDIUM, n: 17, base: 8552}
PCVO002_OP_01_02_s01_NavalBase: {level: "-", n: 19, base: 8352}
PCVO009_OP_02_02_s06_Atoll: {level: "-", n: 29, base: 8109}
PCVO008_OP_02_03_s07_Advance: {level: "-", n: 14, base: 8051}
PCVO004_OP_01_04_s02_Naval_Defense: {level: "-", n: 16, base: 8048}
PCVO010_OP_09_s09_LePVE: {level: "-", n: 11, base: 7937}
PCVO003_OP_01_03_s03_Labyrinth: {level: "-", n: 19, base: 7915}
PCVO011_OP_10_s10_USS_CL: {level: "-", n: 33, base: 7698}
PCVO001_OP_01_01_37_Ridge: {level: "-", n: 9, base: 7477}
```

## 影响池子的因素

1. scenario（地图基线）
2. level（难度 / 旗舰变体 / 等级段）
3. stars（0-5，每星 x1.09）
4. win/loss（胜 x2.27）
5. team efficiency（可忽略）
6. team damage（无）
7. inactive players（每名 x0.972）
8. battle duration（log elasticity -0.032, negligible; R2 0.9576 -> 0.9577）

## 挂机 vs 暴毙

```yaml
server_flag_visibility: false   # teammate is_afk / is_ineffective not in replay public data
proxy:
  afk_like: {damage: 0, frags: 0, scouting: 0, early_dead: true}
  died_early: {some_damage_or_frags: true, dead: true}
pool_multiplier:
  afk_like: 0.927    # -7.5% per player, n=5 matches
  died_early: 0.970  # -3% per player
one_seventh: 0.857   # player-reported -14.3%, not observed in this sample
```

## 脚本 / 数据

- fit: `scripts/fit_xp_pool.py`
- table: `scripts/gen_pool_table.py` -> `output/pool_table.json`
- name/bracket: `scripts/gen_ops_name_table.py` -> `output/ops_name_table.json`
- data: `ops_efficiency_full.jsonl`
- afk/death split: `scripts/analyze_afk_death.py` -> `output/afk_death_analysis.json`

注：新剧情 6-7（67LVL）档无「打赢 + 5 星」样本，故池子缺失；7-9 / 9-11 档已给出。

映射校验：`scripts/check_ww2_bots.py` 从 replay 提取敌方 `ENEMY_WAVE_*` bot
阵容，确认 WW2_OPERATION_1/2/3 = 北极护航 / 东京快车 / 太平洋攻势。
