# Handoff: WOWS replay 生存端评估开发（续接）

Snapshot date: 2026-09-05. 新对话从这里无缝续接：**生存端评估引擎**（S1 起步）。

## 一句话续接指令（新对话直接粘贴）

> 继续 WOWS 回放生存端/输出端评估开发。先读 `docs/handoff-2026-09-05-wows-replay-survival.md` 与 `C:/Users/asdfg/.codex/skills/wows-replay-parser/specs/2026-09-05-survival-evaluation-engine.md`。仓库 `D:\codexProject\wows-toolkit`，工作树干净，分支 `codex/local-changes`；`games_dir=D:/World_of_Warships`（CLI `--game`），回放 `D:/World_of_Warships/replays/15.7.0.0/`。
>
> **当前状态（已完成并提交）**：
> - **生存端 S1–S4 引擎**：`replayshark survival`（默认 JSONL / `--text` 文本；`--dims s1,s2,s3,s4` 选维度，空=集成 `SurvivalProfile`，给定=模块化访问器）。`wows-replay-insights/src/survival.rs` 产出 `SurvivalReport{ s1:Option<SurvivalProfile>, exposure, hp_timeline, output_coupling }`；维度函数 `assess_exposure`/`assess_hp_timeline`/`assess_output` 独立可组合，`assess_report` 按选中 dims 组合。
> - **输出端 `hit_value.rs`**（命中质量/volley）：`assess` 返回 `AssessOutcome{assessments, excluded}`；`summarize` 按 `victim_entity_id` 分组；`analyze_volleys` 按 `(salvo_id, first_shot)` 拆卷、`SalvoEvent.shots` 按 `(salvo_id, first_shot)` 去重、0 命中卷用 `salvo.clock` 计时；`zone_for_hit` 用 `impact - pose.position`（受害者中心，非枪口）+ 15m/unit 换算；`events` 输出 `material_angle_deg`（服务端，缺则 null）与 `belt_strike_angle_deg`（本地）分开。
> - **S1 诚实化**：`died`/`survival`/`avoidance_ratio`/`self_rescue`/`taken_frac_of_potential`/`survival_score`/`grade` 为 `Option`；规避比按炮弹 lane、缺失置 `null`；复合分封顶(已测量权重占比)；`has_dcp` 三态；去 `u32::MAX`。**已修 bug**：`victim_entity_id → Option<EntityId>` 全链贯通；死船排除；unidentified 三分；S2 approach/kiting 用"同一敌舰窗口两端测距 + 自舰须位移 + 敌位插值"。
> - **输出/生存解耦**：输出维度 `hit_value::self_output_timeline → OutputTimeline{events, dropped}`；生存 S4 只组合它。
> - **固定口径**（AGENTS.md）：先修 bug 再加新功能；新里程碑须在上个 bug/评审阻塞项清空（或用户明确顺延）后才开。提交前按 AGENTS.md 用新鲜 `v4_flash_worker` 子代理做对抗性评审（plaintext-handoff Hook 已配好）。
>
> **装甲网格分区（P1+P2 已完成，本会话）**：原设计"用 `FireSectionGeometry.longitudinal()`(burn 节点) 精化 zone 边界"**不可行**——burn 节点只覆盖船体中段、不含船头/船尾端点。已改用**完整 hull 装甲网格顶点包围盒**（`.geometry` armor_models 三角形）提取每舰长/宽/高(转米) → 每舰缓存 → `zone_for_hit` 逐舰阈值（替换 110m/8m 硬编码；deck/superstructure 6/14m 保持启发式），缺失回退固定值。P0（`hit_value::zone_tests` 15m/unit+yaw，提交 `ab6ffda9`）已并入。
> **装甲网格当前状态**：`crates/wows-replay-insights/src/hull_dim.rs`（HullDim + `hull_dim_from_geometry` + `hull_dims_for_report`）；`hit_value`/`survival` 透传 `Option<&HashMap<EntityId,HullDim>>`；`replayshark` hit-value/survival 命令在 `--game` 可用时经 `open_build_vfs` 建 hull 缓存并透传；`wows-replay-insights` 仅在 `build` 特性下启用 `wowsunpack/models`。真实数据校验：`tests/hull_probe.rs`（ignored）Iowa 270.4m/33.0m、Kleber 141.0m/13.2m；真跑 Georgia Atoll `report --depth` 出现 `Johnston(stern)`（旧固定阈值对驱逐舰不可能产生 stern）。**已知近似（已标注）**：舰按 base model_path 解析（不区分 hull 升级）、bbox 视为以原点居中（前后/左右对称）、assets.bin 未跨回放缓存。
> **装甲网格 P3（部分完成，本会话）**：修装备 hull（`equipped_upgrade("_Hull")` → `model_path_for_hull`，build 无 TTX 时回退 base）+ per-side reach（`HullDim` 改 `fore_m`/`aft_m`/`beam_m`/`height_m` 独立 reach，`zone_for_hit` 首尾边界非对称）。运行时对账已验证：真跑 Georgia Atoll `report --depth` 各 zone（`Johnston(stern)`、`Minnesota(belt/superstructure)`、`Seattle(citadel)`）仍解析到实际 HitLocation 并出伤害估算。
> **P3 剩余**：deck/superstructure 垂直起线仍固定 6/14m（bbox 与总高缩放都不可靠）；精确对账是 `HitLocation.splash_boxes` → `.splash` `SplashBox` 逐舰点-框分类（替换启发式 zone）。P4 可选整局表现整合(生存 + 输出一页)。
> **P3 评审（v4_flash_worker）剩余点**：装甲厚度仍取 base hull（`Vehicle.hit_locations()` 来自首个 hull 组件）而 zone 边界来自装备 hull——本步只证明 zone 字符串能命中 HitLocation，未证明板厚属装备 hull；`--no-default-features` 不可编译为既有包装问题（`hit_value`/`survival` 早于本期就引用 `crate::build`，非回归）；`hull_dim_for_model` 目录级 `.visual` 并集为单目录单模型下的主观风险。
> **其余可选项**：整局表现整合（S1–S4 + hit_value 并成"整局表现"）；H1/M4 解 `visibilityFlags` 逐目标被点亮（标"需数据"，暂缓）。
>
> **常用**：`cargo run -p replayshark -- --game D:/World_of_Warships survival [--dims s1,s2,s3,s4] [--text] <回放>`；`cargo run -p replayshark -- --game D:/World_of_Warships report --depth <回放>`；`cargo test -p wows-replay-insights`（132 lib）；`cargo test -p wows-battle-world`（43）；免 `cargo check --workspace`（rav1e/nasm 环境问题与改动无关）。

**固定口径**：先修 bug，再加新功能；新里程碑须在上个里程碑的 bug/评审阻塞项清空（或用户明确顺延）后才开。

## S2 已完成（本会话实现）

- **位置时间线导出**：`wows-battle-world` 新增 `PositionHistoryLog` / `PositionSample` / `PositionKind`（World=全精度位置+yaw度；Minimap=归一化位置+heading度+可见性）。`IngestOptions`/`ProcessOptions`/`BattleWorld` 增加 `record_position_history`（默认 false），`handle_position`/`handle_player_orientation`/`handle_minimap_updates` 门控记录；`BattleReport::positions_over_time()` 暴露。
- **近似暴露/走位**（`survival.rs` `Exposure`）：只用世界坐标（AOI 内），`self_samples`/`enemy_samples`、最近敌舰 min/avg 距离、12km 内暴露占比、12km 内平均敌舰数（按实体去重）、approach/kiting 比例（自舰跨 ~1s 航向 vs 敌舰方向的 dot 符号）。`cover_status="unknown"`（地图几何/真实视线未建模，已注明近似）。
- **文档**：ADR 见 skill `docs/adr/0002-s1-survival-evaluation.md`（追加 S2 节）；本 handoff 已更新。

## S1 已完成（本会话实现，含根修）

- **根修**：`wows-battle-world/src/ingest/projectiles.rs` `resolve_victim` 改为 **owner-aware**。原逻辑只搜 `is_enemy()` 实体，导致「敌方炮弹打中自舰」永远把 victim 解析成附近敌舰（自舰不是 enemy），S1 拿不到被打命中。现按 shooter 关系取反候选集：敌方射手 → 候选为录制者方（自舰+友军）；自舰/友军/未知射手 → 候选为敌方（保留输出端「仅敌方」不变式，不回归「神风 11→14」）。
- **新命令**：`replayshark survival [--text] [--ship-names ...] <replay>`。JSON 含 `score_breakdown`（规避/存活/自救 + 权重）、`hits`（逐发：来源/弹种/命中类型/部位/估伤/命中角/舷角/饱和）、`sources`（按攻击者聚合）、`potential_damage`（Agro）、`fires_lit`/`sustained_fires`/`fires_covered`、`dcd`/`repair_party`/`smoke`、`died`/`death_share_of_match`、`conclusions`。
- **S1 评分**（0-100）= 0.40·规避 + 0.35·存活 + 0.25·自救；规避 = 1 - 吃伤/Agro；存活 = 存活为 1，死亡为死亡时刻/对局时长；自救 = DCP 对持续(≥10s)火段的覆盖（无 DCP 的舰给基线 0.6）。
- **测试/验证**：`cargo check -p replayshark` 无警告；`cargo test -p wows-battle-world --lib` 41 passed；`cargo test -p wows-replay-insights --lib` 125 passed。真跑东京快车（佐治亚，存活+heal）、樱花绽放（克尼塞伯克，死亡 76%）均出结果。
- **ADR**：`C:/Users/asdfg/.codex/skills/wows-replay-parser/docs/adr/0002-s1-survival-evaluation.md`。

### S1 已知缺口（不加虚假归因）

- 分区饱和依赖 `hit_locations`（models opt-in），缺失时估伤为上限（文本已注明）。
- 进水状态：burn 日志忽略 flood 位；BattleReport 无自舰进水/HP 时间线，`flood_status=unknown`，死亡原因未暴露。
- 走位/暴露/血量管理 = S2/S3。

## S1 打分诚实化（本会话对抗性复审修复）

针对"数据缺失时虚高/满分"的评审 BLOCKER 与复审安全隐患，`crates/wows-replay-insights/src/survival.rs` 已改：

- **fate 门控**：`died` 改 `Option<bool>`，`survival_factor` 仅在「确认死亡」或「`battle_result()` 为 `Some`（对局跑完）」时为 `Some`，否则 `None`；`survival_score`/`grade` 改 `Option`——截断/退出回放不再输出"整局存活/100 分"，而是 `null` + 结论"对局未到终局, 是否存活未知"。
- **自救**：`burn_state_observed()==false`（burningFlags 未复制）时 `self_rescue=None`，不再凭"没着火"给满分。
- **规避 lane 对齐**：`weapon_is_shell` 区分炮弹/非炮弹；`avoidance_ratio` 用 `1 - shell_taken / shell_potential`；存在未识别命中或着火（非炮弹伤害证据）时置 `null`，并抑制"规避/隐蔽良好"结论、注明受限。
- **复合分封顶**（复审核心）：`normalized_composite` 把分数封顶在"已测量权重占比"（已知因子权重和），缺失数据无法得到与完整测量相同的满分。单测 `composite_never_reaches_perfect_from_missing_data` 锁定该语义。
- **配套**：`has_dcp` 同时看 DCP 激活日志；`dcp_charges` 用 `Option`（去掉 `u32::MAX` 哨兵）；S2 `exposed_time_frac`/`approach_frac`/`kiting_frac`/`enemies_within_12km_avg` 空 lane 改为 `None` 不造 0；`score_breakdown.score` 从 0-100 改为 0-1 归一化。
- **新字段**：`match_complete`（bool）、`shell_potential_damage`、`non_shell_potential_damage`（f32）——下游 JSON 消费方需按 `null` 处理 Option 字段。

### 验证

- `cargo test -p wows-replay-insights`：131 lib tests 全绿（新增 6 个诚实性单测）。
- `cargo clippy -p wows-replay-insights`：无新增警告（剩余为既有风格项）。
- 真跑真实回放：Atoll 完整对局评分 74→58，规避 `?`（3 发未识别）；批量 6 个中原来两个 100 分回放封顶 60。

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

- Repo：`D:\codexProject\wows-toolkit`（git；生存端 S1/S2 + S1 诚实化已提交，前面是输出端 commit `80e7cbd7`）。
- 游戏目录（CLI `-g`）：`D:/World_of_Warships`；回放 `D:/World_of_Warships/replays/15.7.0.0/`。
- 输出端跑法：`cargo run -p replayshark -- -g D:/World_of_Warships report --depth --ship-names C:/Users/asdfg/.codex/skills/wows-replay-parser/ship_names.json <replay>`
- Skill：`C:/Users/asdfg/.codex/skills/wows-replay-parser`；术语表 `CONTEXT.md`；ADR `docs/adr/0001-m2-single-shot-hit-value.md`；`scripts/review.py`（跑 report）。
- 关键类型：`BattleReport`（`self_damage_stats`/`burn_state_changes`/`active_consumables`/`deaths_by_victim`/`hit_history`/`salvos`/`presence`）。`ResolvedShotHit`（`hit`/`victim_entity_id`/`victim_pose`/`salvo`）；`Player::relation()`（`is_enemy`）。新类型访问：`EntityId::raw()`、`GameParamId::raw()`、`GameClock.0`、`ShipConfigData::max_hp`、`Vehicle::hit_locations()`。

## 后续迭代（已记录，非本次重点）

1. **装甲网格分区**：P1（`hull_dim` 提取 + 线程化 + CLI 接线）与 P2（`zone_for_hit` 逐舰阈值）已完成并提交。P3 与 `hit_location` 对账（base-model vs 装备 hull、per-side reach、6/14m 垂直起线）与 P4 整局整合为后续。
2. `resolve_victim` 的 `MinimapPlacement` 边界换算（恢复 AOI 外目标，需地图边界）。
3. 生存端（本次续接目标）：S1 → S2 → S3 → S4。
