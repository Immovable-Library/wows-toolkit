---
name: wows-replay-parser
description: 解析本机 World of Warships .wowsreplay 文件（剧情/随机/联合/非对称/乱斗/活动等），
  输出人均一行 JSONL 并幂等追加进 SQLite；可按玩家生成解析报告。
  当用户要求“解析 replay、落库、追加朋友给的 rep、生成某玩家的解析报告”时使用本 skill。
metadata:
  version: 1.0.0
---

# wows-replay-parser

把本地 `.wowsreplay` 文件解析成结构化数据并落库（SQLite），可再按玩家出报告。零编译，纯 Python。

## 特色表前置校验（必读）

分析任何 rep / 玩家战斗表现前，必须先查 `reports/舰船特色表.xlsx`：

1. 确定待分析玩家本批 rep 中驾驶的舰船（用 ship_id 或 中文/英文名定位）。
2. 在特色表中找到该船所在行（996 艘全量、未和谐中文名、可按 中文名/英文名 检索），读取 28 个特色列。
3. 特色列以值 `1` 为准，空单元格视为未标注。
4. 若该船所有特色列均为空（未标注）：
   - **拒绝执行分析**，不输出战斗/风格/效率等任何结论；
   - 明确告知用户：该船尚未标注特色，请先在 `reports/舰船特色表.xlsx` 对应行手动填 `1`，完成后重新发起分析。
5. 标注齐全后，基于该船特色（副炮流、水听、高机动、强鱼雷等）展开深入分析，并结合吃船效率/点亮/生存等数据解释打法。
6. 分析前先运行 `python scripts/learn_features.py`：把用户写在备注列的自由描述自动抽取为特色（匹配已有列填 `1`、无法匹配的短语新增为特色列），并刷新表头冻结与列宽；之后再用 `feature_gate.py` 校验。

- 同一批 rep 开多条船时逐船校验，任一主开船只未标注即整体拒绝。
- 拒绝时调用 `scripts/feature_gate.py`（带 `--apply-filter`）生成「待标注清单」：直接给出每艘未标注船的 **Excel 行号**、中文/英文名与空特色列，并把特色表筛选为仅显示待标注行——用户打开表格即可直接看到并填写 `1`，无需自行查找。用户可在 Excel 中清除筛选查看全表；补标后重跑校验即可。
- 特色列定义与来源映射见特色表「特色模型说明」页签。

```bash
# 检查本次涉及的船（可混用中文/英文名），输出行号与标注状态，存在未标注时退出码为 1
python scripts/feature_gate.py 大和 Knesebeck "North Carolina 2"
# 同上，并把特色表筛选为只显示待标注行（推荐：拒绝分析时使用）
python scripts/feature_gate.py 大和 Knesebeck --apply-filter
# 列出全表所有未标注行
python scripts/feature_gate.py --all-unannotated
```

## 依赖

```bash
pip install cryptography
```

其余全是标准库。舰船名/等级/舰种解析走 WG 百科 API（需联网，一次性批量请求 + 本地缓存），可关闭。

## 工作流程

本目录结构：

- `scripts/extract_ops_replays.py` —— 解析 + 落库主脚本
- `scripts/player_report.py` —— 玩家解析报告生成器
- `scripts/extract_ops_efficiency.py` —— 剧情「吃船效率」提取（PR/经验分配分析输入）
- `scenario_names.json` —— 剧情内部码 → 标准中文名映射表（报告展示用）
- `ship_names.json` —— 舰船 ID → 标准中文舰名映射表（报告展示用）
- `reports/舰船特色表.xlsx` —— 舰船特色标注表（996 艘全量，未和谐中文名；分析前必须校验，见下文）
- `scripts/feature_gate.py` —— 特色表校验：按船名定位 Excel 行号并输出待标注清单
- `scripts/learn_features.py` —— 备注自学习：从备注列抽取关键信息，匹配/合并/新增特色列，并自动冻结表头船名列、自适应列宽
- `constants_cache/` —— 各 build 的字段索引表（13.10+ 已内置；脚本可自动从 `padtrack/wows-constants` 抓取缺失 build）

### 1. 解析并落库（幂等追加）

```bash
python scripts/extract_ops_replays.py "D:\replays" \
  --db replays.db --out replays_parsed.jsonl \
  --constants-dir constants_cache \
  --ship-cache ships_cache.json --workers 8
```

- 目录会**递归逐层**扫描所有 `.wowsreplay`。
- 默认**追加 + 去重**：按 `arena_id`（场次唯一 ID）+ `account_id` 去重，同一份 rep 重跑是空操作；`--overwrite` 才清空重建。
- 输出：`--out` 的 JSONL（人均一行）+ `--db` 的 SQLite（表 `rows`，唯一索引 `(arena_id, account_id)`）。

### 2. 生成玩家报告

```bash
python scripts/player_report.py --db replays.db --player SKmon --out reports\SKmon_report.md
# 可选过滤：
#   --family pvp / ops / coop / ...（scenario_family 子串匹配）
#   --match-group pvp / brawl / cooperative / ...
```

## 剧情标准名称

描述剧情对局（报告、汇总、聊天输出）时，用标准中文剧情名称，不要直接展示内部场景码
（如 `PCVO004_OP_01_04_s02_Naval_Defense_MEDIUM_LVL`）。映射表见根目录
`scenario_names.json`；程序化映射用 `scripts/scenario_names.py` 的 `standard_name(scenario)`。

| 内部码 | 标准名称 | 英文名 |
|---|---|---|
| `Ridge` | 神盾 | Aegis |
| `NavalBase` | 杀人鲸 | Killer Whale |
| `Labyrinth` | 营救猛禽 | Raptor Rescue |
| `Naval_Defense` | 防守纽波特 | Defense of Naval Station Newport |
| `Advance` | 那莱 | Narai |
| `Atoll` | 最终前线 | The Ultimate Frontier |
| `LePVE` | 赫尔墨斯 | Hermes |
| `USS_CL` | 樱花绽放 | Cherry Blossom |
| `WW2_OPERATION_1` | 北极护航 | Arctic Convoy |
| `WW2_OPERATION_2` | 东京快车 | Tokyo Express |
| `WW2_OPERATION_3` | 太平洋攻势 | Pacific Offensive |

- 入库 / JSONL 保留原始内部码（数据保真），仅在展示层替换。
- 未收录的内部码原样保留并提示补表，不要臆造名称。
- 来源：本机 wows-toolkit `scripts/gen_ops_name_table.py` + `output/ops_scenario_mapping_verified.md`
  （已按官方 wiki 核验）。

## 舰船标准名称

描述舰船时用标准中文舰名（如 克尼塞伯克、伊皮兰加），不要用英文名。映射表见根目录
`ship_names.json`（ship_id → 中文名，来源：本机 wows-toolkit `output/ship_strength_full.json`）；
程序化映射用 `scripts/ship_names.py` 的 `cn_name(ship_id, fallback_en)`。

- 入库 / JSONL 保留英文名（数据保真），仅在展示层替换。
- 未收录的舰船保留英文名并提示补表，不要臆造译名。

## 关键参数

| 参数 | 说明 |
|---|---|
| `--db` | SQLite 输出，默认 `replays.db`，`INSERT OR IGNORE` 幂等 |
| `--out` | JSONL 输出，默认 `replays_parsed.jsonl`，追加写 |
| `--constants-dir` | per-build 索引表缓存目录，默认 `constants_cache` |
| `--no-fetch` | 不从 GitHub 抓索引（离线跑已有缓存） |
| `--no-resolve-ships` | 跳过 WG 舰船名解析 |
| `--ship-cache` | ship_id→船名缓存文件，默认 `ships_cache.json` |
| `--workers` | 多进程数，默认 CPU 核数 |
| `--overwrite` | 清空 JSONL 和 DB 重建（默认追加） |

## 输出字段（人均一行）

局级：`source build client_version fields_resolved match_group scenario_family ts arena_id
scenario map_kind bracket difficulty is_win is_loss is_draw stars_server team_damage team_exp ...`
个人：`account_id name ship_id ship_name tier ship_class damage frags exp raw_exp
scouting_damage is_alive ...`

## 重要边界（务必先读）

1. **字段索引随版本变**：`damage/exp` 索引在 13.10→15.7 间漂移（412→426）。脚本按 build 选索引。
2. **版本覆盖三档**：
   - `>= 13.10`：damage/exp/raw_exp/星级 全量正确；
   - `12.6 ~ 13.8`：只有稳定字段（船/队/击杀/存活/胜负/星级），`damage/exp` 置空且 `fields_resolved=false`；
   - `< 12.6`（12.4/12.5）：无独立战报包（0x22 是 `NestedPropertyUpdate`），JSON 路线解析不了。
3. 新 build（朋友其它区服/新版本）：会自动抓索引；抓不到会降级并打印 unresolved 提示，把该 build 的常量补进 `constants_cache/<build>.json` 即可。
4. 败局会令 `stars_server=0`；机械完成数在 `secondary_completed`，二者含义不同。

## 示例：追加朋友 rep + 出报告

```bash
# 追加
python scripts/extract_ops_replays.py "D:\replays\skmon" --db ..\replays.db --workers 4
# 报告
python scripts/player_report.py --db ..\replays.db --player SKmon
```


## 提取「吃船效率」供剧情分析

从剧情 replay 额外重建社区口径的「吃船效率」：对每艘敌舰累加 (你对其伤害 / 其最大血量)，
击沉船合计约为 1、未沉船按比例计。这是 PR 与经验分配分析的核心输入，和 `player_report.py` 的
人均聚合报告互补。

```bash
python scripts/extract_ops_efficiency.py "D:\replays" \
  --out ops_efficiency.jsonl --constants-dir constants_cache \
  --ship-cache ships_cache.json --workers 8
```

- 只处理剧情场景（`WW2_OPERATION` / `PCVO` / `OP_` / 等）且 `build >= 9129736`。
- 输出人均一行 JSONL，在 `extract_ops_replays.py` 字段之上额外追加：
  `efficiency`（吃船效率）、`sum_dmg_check`、`n_victims`，以及本局全队聚合
  `team_raw` / `team_eff` / `team_damage` / `team_frags`。
- 字段索引按 build 读取 `constants_cache/<build>.json` 的
  `CLIENT_PUBLIC_RESULTS_INDICES` 与 `CLIENT_VEH_INTERACTION_DETAILS`；缺失 build 会自动抓取，
  抓不到时该 build 的 `efficiency` 退化为 0，人工补 cache 后重跑即可。

