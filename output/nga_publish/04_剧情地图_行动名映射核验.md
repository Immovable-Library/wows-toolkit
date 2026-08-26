# 剧情场景映射核验：地图名 + 行动名（修正后）

> 目的：用回放解析器取到的内部场景码 + 官方 wiki 的「地图名 / 行动名」，验证修正后中文名映射是否一致。

## 结论

**一致。** 8 个老剧情场景（PCVO）的内部地图码 → 官方地图名 → 官方行动名 → 中文行动名，四层一一对应，无冲突。

## 证据链（可复现）

1. 回放头部 `mapName` / `mapDisplayName` 给出内部地图码（例：`s02_Naval_Defense`、`s06_Atoll`）。
2. 回放 `playersPublicInfo` 中 bot 的 `name` 字段给出 `IDS_OP_XX_YY_*`，`XX_YY` 与 `scenario` 里的 `OP_XX_YY` 一致，用于锁定行动编号。
3. WG 官方 wiki `Ship:Scenarios` 给出「Map: X」→「Operation: Y」的权威对应。
4. 逐图敌军/友军船型签名独立印证（如 列克星敦 + 密苏里 + 5 艘运输船 = 那莱）。

## 修正前后对照表

| 场景代码 | 官方地图名 | 官方行动名（英文） | 中文行动名（修正后） | 修正前（错误） |
|---|---|---|---|---|
| `Ridge` | Mountain Range | Aegis | 神盾 | 神盾（无误） |
| `NavalBase` | Naval Base | Killer Whale | 杀人鲸 | 防守纽波特 |
| `Labyrinth` | Labyrinth | Raptor Rescue | 营救猛禽 | 猛禽救援 |
| `Naval_Defense` | Newport | Defense of Naval Station Newport | 防守纽波特 | 赫尔墨斯 |
| `Advance` | Sunda Islands | Narai | 那莱 | 纳莱 |
| `Atoll` | Ultimate Frontier | The Ultimate Frontier | 最终前线 | 终极前线 |
| `LePVE` | Hermes（同行动名题） | Hermes | 赫尔墨斯 | 杀人鲸 |
| `USS_CL` | Cherry Blossom（同行动名题） | Cherry Blossom | 樱花绽放 | 樱花绽放（无误） |

>说明：Hermes 与 Cherry Blossom 在 wiki「Scenarios」总表里未单独列出「Map:」字段，其地图与行动名同题，故根据内部码 `LePVE` / `USS_CL` 码定，地图显示名与行动名一致。

## 那莱（Narai / Advance）专判

- bot 键 `IDS_OP_02_03_*`：运输船 `IDS_OP_02_03_AT_TRANSPORT_A_1..5`，合 5 艘；另有 `IDS_OP_02_03_AT_COMMUNICATION`、`IDS_OP_02_03_AT_SHIP_DEFENDER_*`。
- 敌军签名（回放 `playersPublicInfo`）：Lexington×1、Missouri×1、Bretagne×1（玩家称“白劳易”）、New York×1、Queen Elizabeth×2、Leander×2，与玩家提供的“列克星敦 + 密苏里 + 白劳易 + 纽约 + 伊丽莎白女王 + 利安得”完全吻合。
- 官方地图名 = Sunda Islands（巽他群岛），行动名 = Narai（那莱）。
- 常态队列仅 6-8 档，无中/高级变体（与玩家“那莱没有高级模式”一致）。

## 附：WW2 新行动映射

| 内部场景 | 中文行动名 | 英文行动名 |
|---|---|---|
| `WW2_OPERATION_1` | 北极护航 | Arctic Convoy |
| `WW2_OPERATION_2` | 东京快车 | Tokyo Express |
| `WW2_OPERATION_3` | 太平洋攻势 | Pacific Offensive |
