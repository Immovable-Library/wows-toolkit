# Handoff: WOWS replay 生存端评估开发（续接）

Snapshot date: 2026-09-05. 新对话从这里无缝续接：**生存端评估引擎**（S1 起步）。

## 一句话续接指令（新对话直接粘贴）

> 继续 WOWS 回放生存端评估开发。先读 `docs/handoff-2026-09-05-wows-replay-survival.md` 与 `C:/Users/asdfg/.codex/skills/wows-replay-parser/specs/2026-09-05-survival-evaluation-engine.md`，按方案从 **S1（生存画像：被打命中+估伤/着火进水/DCP-heal/死亡/Agro，0-100 生存分）** 开始；复用已提交的输出端引擎（`replayshark`，commit `80e7cbd7`）的 `hit_value::estimate_damage` 与敌人限定逻辑；`games_dir=D:/World_of_Warships`。

## 已完成并发布（输出端，commit 80e7cbd7）

- **`replayshark` 命令**：`report`（普通=按目标 / `--depth`=逐轮全量）、`hit-value`（逐发）、`hit-summary`（按目标教训）、`volleys`（逐轮 0-100 评分）。`--ship-names` 运行时加载本地中文舰名表。
- **`events`**：逐发带弹种全参数（AP/HE/SAP+穿深/跳弹/引信/口径）+ 几何命中角/`angle_on_bow_deg`。
- **`hit_value` 模块**（`crates/wows-replay-insights/src/hit_value.rs`）：仅主炮 / 仅敌方可作受害舰 / 分区饱和（`HitLocation.max_hp`）/ 提前量 / 换弹反事实（含"别换"正向提示）/ DD 切弹窗口 / 逐轮评分。
- **核心根修**（`wows-battle-world/src/ingest/projectiles.rs`）：`resolve_victim` 仅搜敌方，根治"AOI 外目标被签到盟友/自军"（东京快车迪米特里）。已实测：神风命中 11→14（回收被误归属弹着）。
- **`fire_chance::geometry`**：`belt_strike_angle` / `angle_on_bow` 辅助。

### 验证

- `cargo check -p replayshark` 全绿（拉全 + wows-battle-world + wows-replay-insights + 其它）。
- 东京快车 + 竞技神（佐治亚）真跑通；中文舰名、敌方限定、饱和、提前量、评分均出结果。
- 注：`cargo check --workspace` 会因 `rav1e`（需 nasm，本机未装）失败——**既有环境问题，与改动无关**。

## 输出端关键不变式（生存端复用/延续）

- 换弹反事实仅主炮；副炮/AA 命中排除。
- 受害舰必须 `Relation::is_enemy`；`victim_entity_id` 是"最近舰"启发式。
- 命中角由 `salvo.shots[].origin -> hit.position` 弹道向量 vs 装甲法线推（不依赖 null 的 `terminal_ballistics`）。
- 分区饱和：`HitLocation.max_hp` 作电量，耗尽后非核心命中 ~1/6；citadel 永远 100%。
- 穿透用 wows_shell 社区公式，统一标"近似"。
- 舰名：运行时 `--ship-names <ship_names.json>`（含 CJK 才用，英文回退落内嵌表）。

## 生存端设计蓝本（下一步）

读 `C:/Users/asdfg/.codex/skills/wows-replay-parser/specs/2026-09-05-survival-evaluation-engine.md`。要点：

- **目标**：评价"怎么活下来的"——生存质量 + "活着才有输出"的生存→输出耦合。
- **维度**：受击/暴露、伤害承受、规避/走位、自救（DCP/heal）、死亡/濒死、生存→输出耦合。
- **里程碑**：S1 生存画像（现有数据）→ S2 位置时间线（暴露/kiting/掩体）→ S3 HP 时间线（血量/濒死）→ S4 整合评分。
- **不自欺**：被集火≠你的错（可能团队卖点）；"暴露"需位置+敌舰视线支撑；"自救差"要分"用错"vs"没得用"。

## 生存端数据事实（已摸底）

| 数据 | 状态 | 用途 |
|---|---|---|
| `self_damage_stats`（`DamageStatCategory::Agro`） | 现成 | 潜在伤害/被瞄准火力 |
| `burn_state_changes`/`burn_state_observed` | 现成 | 着火次数/持续 |
| `active_consumables` | 现成 | DCP/维修/烟 使用时机 |
| `deaths_by_victim`/`battle_result`/`finish_type` | 现成 | 死亡/终局 |
| `hit_history`（`victim_entity_id == self`） | 现成 | 被打命中（来源/武器/命中类型/落点），复用 `estimate_damage` 估吃伤 |
| **位置时间线**（`Position` 0x0a / `Transform3d`/`MinimapPlacement`） | **缺**（`BattleReport` 只有 `presence()` 观测窗口） | S2 走位/暴露/kiting/掩体——**需新增导出** |
| **HP 时间线** | **缺** | S3 血量管理/濒死/耦合——**需新增导出** |
| `visibilityFlags`/`DetectedByHydrophone` | 未解（H1/M4） | 被几舰点亮/为何——限制"被集火 vs 被点亮" |

### 生存端需新增的 M1 式导出（类比已实现的 hit/salvo history）

- 位置历史：在 `wows-battle-world` 记录每实体 `Transform3d`/`MinimapPlacement` 到 `PositionHistoryLog`，`BattleReport` 暴露 `positions_over_time()`。
- HP 历史：记录自机 HP 变化到 log，`BattleReport` 暴露 `hp_timeline()`。

## 环境与命令速查

- Repo：`D:\codexProject\wows-toolkit`（git，工作树干净，HEAD=80e7cbd7）。
- 游戏目录（CLI `-g`）：`D:/World_of_Warships`；回放 `D:/World_of_Warships/replays/15.7.0.0/`。
- 输出端跑法：`cargo run -p replayshark -- -g D:/World_of_Warships report --depth --ship-names C:/Users/asdfg/.codex/skills/wows-replay-parser/ship_names.json <replay>`
- Skill：`C:/Users/asdfg/.codex/skills/wows-replay-parser`；术语表 `CONTEXT.md`；ADR `docs/adr/0001-m2-single-shot-hit-value.md`；`scripts/review.py`（跑 report）。
- 关键类型：`BattleReport`（`self_damage_stats`/`burn_state_changes`/`active_consumables`/`deaths_by_victim`/`hit_history`/`salvos`/`presence`）。`ResolvedShotHit`（`hit`/`victim_entity_id`/`victim_pose`/`salvo`）；`Player::relation()`（`is_enemy`）。新类型访问：`EntityId::raw()`、`GameParamId::raw()`、`GameClock.0`、`ShipConfigData::max_hp`、`Vehicle::hit_locations()`。

## 后续迭代（已记录，非本次重点）

1. **装甲网格分区**（推后）：需启用 `models`（opt-in）+ 游戏几何加载器 + Möller–Trumbore 求交 + 每舰缓存；**第 0 步先验证坐标空间**（防 #42/#43 单位错配）。
2. `resolve_victim` 的 `MinimapPlacement` 边界换算（恢复 AOI 外目标，需地图边界）。
3. 生存端（本次续接目标）：S1 → S2 → S3 → S4。
