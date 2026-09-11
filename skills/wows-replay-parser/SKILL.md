---
name: wows-replay-parser
description: 解析本机 World of Warships .wowsreplay 文件（剧情/随机/联合/非对称/乱斗/活动等），
  输出人均一行 JSONL 并幂等追加进 SQLite；可按玩家生成解析报告。
  当用户要求“解析 replay、落库、追加朋友给的 rep、生成某玩家的解析报告”时使用本 skill。
metadata:
  version: 1.0.0
---

> 快照说明：本目录是 `C:/Users/asdfg/.codex/skills/wows-replay-parser` 的同步快照（脚本、SKILL.md、
> 名称表、specs）。权威副本在 skills 目录，改脚本先改源头再整体同步，不要在快照里单独改代码。
> 库（replays.db / replays_all.db）不在快照里，脚本要从 skill 目录或显式 --db 运行。

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
- **入库门槛**：默认只收 `wows-replay-cache/approval_pool.json` 认可的地图/版本（见下节）。

### 1b. 两库分工（必读）

两个库长期并存，别混用：

| 库 | 内容 | 用途 |
|---|---|---|
| `replays.db` | 只含认可池内的 rep（默认闸门） | 出生点标定、按图统计等**版本强相关**工作 |
| `replays_all.db` | 所有能解析的 rep（无闸门） | 逆向 WG 收益/经验算法等**要全量样本**的分析 |

```bash
# 全量库：采集一切可解析的 rep（--db/--out 缺省时按闸门状态自动落到对应库）
python scripts/extract_ops_replays.py "D:\World_of_Warships\replays" \
  --no-approval-filter \
  --constants-dir constants_cache --ship-cache ships_cache.json --workers 8

# 门槛库：从全量库派生 / 改池子规则后重新套闸门（不重新解析 rep，幂等）
python scripts/gate_db.py --src replays_all.db --dst replays.db --dry-run
python scripts/gate_db.py --src replays_all.db --dst replays.db
```

- 门槛口径只写在 `C:/Users/asdfg/.codex/skills/wows-replay-cache/approval_pool.json`
  （`families` / `scenarios` / `min_build`），实现唯一：`approval_lib.classify`。
  改口径只改 JSON，不改脚本；改完重跑 `gate_db.py` 即可。
- `--db` / `--out` 缺省值跟着闸门走：开闸写 `replays.db` + `replays_parsed.jsonl`，
  `--no-approval-filter` 写 `replays_all.db` + `replays_parsed_all.jsonl`。
  显式把 `--db replays.db` 和 `--no-approval-filter` 一起用时脚本直接报错退出。
- `gate_db.py` 用目标库自己的 scenario+build 判定该删谁，所以源库不全也不会误删认可局；
  它拒绝在源库 0 行、或没有任何 arena 过闸时动手。
- 闸门只能复算 DB 里已有的字段（scenario / build）。若将来规则需要别的字段
  （例如 operation id），得先把它落库再重解析，`gate_db.py` 无法凭空补。

### 2. 生成玩家报告

```bash
python scripts/player_report.py --player SKmon --out reports\SKmon_report.md
# 默认读全量库 replays_all.db（表现/收益类分析）；版本强相关时显式 --db replays.db
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
| `LOW_LVL_OPERATION_1` | 烈火试炼 | Trial by Fire |
| `LOW_LVL_OPERATION_2` | 钢铁蜂群 | Swarm of Steel |
| `LOW_LVL_OPERATION_3` | 蜂巢 | Beehive |

- 入库 / JSONL 保留原始内部码（数据保真），仅在展示层替换。
- 未收录的内部码原样保留并提示补表，不要臆造名称。
- 来源：本机 wows-toolkit `scripts/gen_ops_name_table.py` + `output/ops_scenario_mapping_verified.md`
  （已按官方 wiki 核验）。
- 15.8 起的低级剧情（2-6 级房，`LOW_LVL_OPERATION_*`）名称取自客户端 `global.mo`
  （zh/en，build 13187581）：`LOW_LVL_OPERATION_1/2/3` 分别复用
  `10_NE_big_race` / `33_new_tierra` / `13_OC_new_dawn` 三张既有 space。

## 舰船标准名称

描述舰船时用标准中文舰名（如 克尼塞伯克、伊皮兰加），不要用英文名。映射表见根目录
`ship_names.json`（ship_id → 中文名，来源：本机 wows-toolkit `output/ship_strength_full.json`）；
程序化映射用 `scripts/ship_names.py` 的 `cn_name(ship_id, fallback_en)`。

- 入库 / JSONL 保留英文名（数据保真），仅在展示层替换。
- 未收录的舰船保留英文名并提示补表，不要臆造译名。

## 关键参数

| 参数 | 说明 |
|---|---|
| `--db` | SQLite 输出；缺省 `replays.db`（开闸时）或 `replays_all.db`（`--no-approval-filter` 时），`INSERT OR IGNORE` 幂等 |
| `--out` | JSONL 输出，追加写；缺省 `replays_parsed.jsonl` / `replays_parsed_all.jsonl`（同上跟随闸门） |
| `--approval-pool` | 认可池 JSON，默认 `wows-replay-cache/approval_pool.json`（可用环境变量 `WOWS_REPLAY_CACHE_SKILL` 改 skill 目录） |
| `--no-approval-filter` | 关闭闸门，采集全部可解析 rep；与显式 `--db replays.db` 互斥 |
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
# 追加到全量库（朋友 rep 常不在认可池内，也要留档）
python scripts/extract_ops_replays.py "D:\replays\skmon" --db replays_all.db --no-approval-filter --workers 4
# 门槛库随全量库刷新
python scripts/gate_db.py --src replays_all.db --dst replays.db
# 报告（默认读全量库）
python scripts/player_report.py --player SKmon
```

## 点亮-变现归因（Tier 1，表层净额）

分析"玩家是不是被队友收割了点亮"时**只能做净额归因**，不能做逐目标因果断言。

### 机制不变式（必须遵守）

- 点亮伤害只归属**唯一点亮该目标**的那个己方玩家。
- 同一目标的隐蔽圈内**同时有 ≥2 个己方**（同时侦测）时，该目标的点亮伤害归零，谁都拿不到。
- `scouting_damage`（0x22 战报结算）是**已按上述规则结算后的净额**：它是"我拿到多少点亮结算"的**下限证据**，
  不是"我点亮了多少目标"，也不能证明"那一个击杀是谁抢走的"。

由此：**高净点亮证明游戏确实把一部分独亮点亮收益记给了你；低净点亮不能反推"你没点亮"，
因为你可能正是被同圈队友互相清零的那一个。** 这两种情况表层数据无法区分，属事件级归因的范围。

### 用法

```bash
python scripts/spot_credit.py --player uomouse --date 20260904 --out reports\uomouse_spot.md
# 默认读全量库 replays_all.db；要看门槛库的版本强相关子集时显式 --db replays.db
```

- 只读 `scouting_damage` / `damage` / `frags` + 团队构成，输出逐场「点亮-变现画像」。
- 只对 **PvE 对局**（`match_group` = pve / cooperative，且入库样本是单队 ≥2 人）出判定；
  其余模式、单人样本、老版本无结算的局一律标 `unresolved` / `样本不适用` / `非 PvE 对局`，不给结论。
- 判定是**保守且分级**的：只有表层净额支持时才到"独亮被收割/自亮自吃"；
  疑似人群并存则明确标"需事件级验证"，不做因果断言。
- 判定分级逻辑、阈值与"不自欺"规则见
  `specs/2026-09-05-event-credit-attribution-engine.md`。看走位/瞄准/散布等根因请走事件级，不要用本脚本断根因。

## 事件级单轮命中价值评估（M2 输出端）

分析"我这轮炮弹落点/命中质量、该不该换弹"用 Rust 事件级引擎（`replayshark`），而非 Tier1 净额。
它从回放逐发重建：弹种（AP/HE/SAP，每舰仅两种）、命中类型（过穿/未击穿/核心/跳弹/命）、部位、
穿深/跳弹、提前量、分区饱和减伤、DD 切弹窗口，并给每轮 0-100 评分。只报证据支持的结论。

```bash
# 普通报告（按目标教训，中文舰名）
python scripts/review.py --game D:/World_of_Warships <replay>        # 普通
python scripts/review.py --game D:/World_of_Warships --deep <replay> # 深度（逐轮全量）
# 二进制直达：
replayshark -g D:/World_of_Warships report --ship-names <skill>/ship_names.json <replay>
replayshark -g D:/World_of_Warships report --depth --ship-names <skill>/ship_names.json <replay>
# 其它：hit-value / hit-summary / volleys
```

### 机制不变式（必须遵守）

- **仅主炮弹种**做换弹反事实；副炮/AA 自动炮命中排除（不可手动换弹）。
- **仅敌方可作受害舰**：玩家的炮弹只能伤害敌方；`victim_entity_id` 是"最近舰"启发式，AOI 外目标
  会签到自军/盟友（东京快车迪米特里即友军误归属），故只保留 `Relation::is_enemy` 的受害舰。
- **命中角几何推导**：不依赖 `terminal_ballistics`（15.7 很多命中为 null），用
  `salvo.shots[].origin -> hit.position` 弹道向量 vs 装甲法线。
- **分区饱和**：用 `HitLocation.max_hp` 作分区电量，耗尽后非核心命中降到 ~1/6；citadel 永远 100%。
- **舰名**：优先运行时 `--ship-names <ship_names.json>`（ship_id→中文，含 CJK 才用）；内嵌表兜底。

### 鉴定分级

沿用 `已证实 / 净额支持 / 疑似（需事件级）/ 无证据`；穿透模型是 wows_shell 社区公式，统一标"近似"。
设计蓝本与里程碑见 `specs/2026-09-05-event-credit-attribution-engine.md`（M2 单轮命中价值）、
生存端见 `specs/2026-09-05-survival-evaluation-engine.md`；术语表 `CONTEXT.md`，决策记录 `docs/adr/`。


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
