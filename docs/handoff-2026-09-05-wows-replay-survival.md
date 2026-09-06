# Handoff: WOWS 回放生存端/输出端评估（续接）

Snapshot date: 2026-09-06. 本文件为最新、干净的续接入口（上一版因分段追加已显冗余，已整体重写）。仓库 `D:\codexProject\wows-toolkit`，分支 `codex/local-changes`，工作树干净。

## 一句话续接指令（新对话直接粘贴）

> 继续 WOWS 回放生存端/输出端评估开发。先读 `docs/handoff-2026-09-05-wows-replay-survival.md` 与 `C:/Users/asdfg/.codex/skills/wows-replay-parser/specs/2026-09-05-survival-evaluation-engine.md`。仓库 `D:\codexProject\wows-toolkit`，工作树干净，分支 `codex/local-changes`；`games_dir=D:/World_of_Warships`（CLI `--game`），回放 `D:/World_of_Warships/replays/15.7.0.0/`。
>
> **当前状态（本会话已完成并提交，依次为）**：
> - **输出端 `hit_value`**（更早，commit `80e7cbd7`）：`report`/`hit-value`/`hit-summary`/`volleys`/`events`，仅主炮/仅敌方、分区饱和、提前量、换弹反事实、逐轮 0-100 评分。
> - **生存端 S1–S4**（`survival.rs`）：`replayshark survival [--dims s1,s2,s3,s4] [--text]`；`SurvivalProfile` 含受击/着火/DCP/heal/死亡/Agro + S2 暴露 + S3 HP 时间线 + S4 输出耦合 + 0-100 生存分。诚实化：`died`/`avoidance_ratio`/`survival_score`/`grade` 等为 `Option`，复合分封顶、fate 门控；`victim_entity_id→Option<EntityId>` 全链；`resolve_victim` 改 owner-aware（敌方射手→候选为录制者方），修复「敌方炮弹打中自舰被签到友舰」。
> - **装甲网格分区 P0–P3b**：P0（`ab6ffda9`）锁定 15m/unit+yaw；P1/P2（`567c9bf3`）`hull_dim.rs` 用 armor 网格 bbox 提取每舰长/宽/高 + `zone_for_hit` 逐舰阈值；P3（`b55c3ce7`）装备 hull（`equipped_upgrade("_Hull")`）+ per-side reach（`HullDim` 改 `fore_m`/`aft_m`/`half_beam_m`/`height_m`）；P3b（`b1d98f1a`）用 `.splash` `SplashBox` 逐舰点-框分类，`exact_zone_for_hit` 取精确 `HitLocation` 键读板厚/饱和，粗粒度 label 保留给 reason/报告 zone。`HullData{dim, zones}`、`hull_data_for_report`、`exact_zone_for_hit`；`assess`/`self_output_timeline`/`survival::assess` 用精确键，饱和记账按精确键（`is_citadel_zone` 识别 Cit/Citadel）。
> - **整局表现 P4**（`3053f03c`）：`replayshark performance [--text]`（`performance.rs` `WholeMatch{survival, output}` + `assess_whole` + `render_whole` 一页文本；默认 JSONL）。输出端主炮估伤与生存 S4 更宽口径已用「主炮」/「输出估伤」区分。
> - **真实板厚 + build 门控**（本会话，待提交）：`hit_value`/`survival` 的 `zone_mm` 改走 `hull_dim::plate_thickness_for_hit`（装备 hull 的 `.geometry` 装甲网格 + `ArmorMap`，按落点射线取最近命中板，`(material_id, layer_index)`→毫米）；`HitLocation.thickness` 恒为 0 的问题随之消除（0mm/`None` 均视为未知→保守 0.33α）；命中板取「离落点最近的交点」而非「射线最先扫过的板」，避免平坦弹道掠过近侧板失真。`hit_value`/`survival` 一并门控于 `build`（`--no-default-features` 干净）。**评审后修正**：命中板改为 `|t - t_impact|` 最近者、plates 路径 0mm 过滤。
> - **审计字段 + 精确区粗 label**（本会话，待提交）：`HitAssessment`/`IncomingHit` 新增 `exact_zone`（splash 框精确键）与 `plate_thickness_mm`（本次 HE/SAP 穿透/估伤读取的板厚；甲板网格优先，粗命中区回退，不可解析为 `null`）。新增 `hit_value::exact_zone_label`（精确键→粗 label，保守映射：Cit/Citadel→citadel、Bow→bow、St/Stern→stern、SS/SSC/Super→superstructure、Cas/Casemate→belt、Deck→deck，未知键保留启发式），在精确区可解析时用映射 label 覆盖报告/文案用的粗 `zone`，修复「DD 甲板/上层建筑命中被标成 citadel」的误导。
>
> **固定口径（AGENTS.md）**：先修 bug，再加新功能；新里程碑须在上个 bug/评审阻塞项清空（或用户明确顺延）后才开；提交前用新鲜 `v4_flash_worker` 子代理做对抗性评审（plaintext-handoff Hook 已配好）；工作区注意 `cargo check --workspace` 因 rav1e/nasm 环境问题失败（与改动无关，免跑）；提交信息不加 AI 署名。

## 当前验证基线（截至 2026-09-06）

- `cargo test -p wows-replay-insights --lib`：**143 passed**（含 `plate_thickness_casts_to_the_nearest_plate`、`plate_thickness_prefers_the_impact_plate_over_a_grazed_one`、`exact_zone_label_maps_known_keys_only`）。
- `cargo test -p wows-battle-world --lib`：**43 passed**。
- `cargo check -p replayshark` / `-p wows-replay-insights`（含 `--no-default-features`）：干净。
- `cargo clippy -p wows-replay-insights -p replayshark`：新增告警无（既有风格项未动）。
- 真实数据探测（ignored，需 `WOWS_DIR=D:/World_of_Warships`）：`tests/hull_probe.rs`（Iowa 全长 270.4m/宽 33.0m、Kleber 141.0m/13.2m、Balao 94.9m/8.7m）；`tests/zones_probe.rs`（Kleber/Iowa 的 splash 框→`HitLocation` 键映射）。
- 真跑 Georgia Atoll（`20260813_210427_PASB729-Georgia_s06_Atoll.wowsreplay`）：`report --depth`、`survival --text`、`performance --text`/JSON 均出结果；精确区使饱和命中 7→13。

## 遗留/未完成项（新对话可从这里继续）

**优先级建议**（均注明严重性/来源）：
1. **~~`--no-default-features` 编译破~~（已修，`6ee88d5c` 之后本会话）**：`hit_value`/`survival` 已一并门控于 `build`（与 `hull_dim` 一致），`cargo check -p wows-replay-insights --no-default-features` 现为干净。原为既有包装问题，非本会话回归；工作区成员一律启用 `build`/`battle-report`/`wowssb`，不受影响。
2. **per-hull `hit_locations` 取板厚**（评审 MEDIUM，部分推进）：板厚已改为从装备 hull 的 `.geometry` 装甲网格 + `ArmorMap` 在落点取（`hull_dim::plate_thickness_for_hit`），按 `(material_id, layer_index)` 读毫米——不再依赖恒为 0 的 `HitLocation.thickness`。但 `ArmorMap` 仍取自 `build.ship.vehicle().armor()`（base hull），饱和预算 `max_hp` 仍取自 base `hit_locations`；若装备 hull 与 base hull 的装甲/分区不同，仍可能错配。修法：从装备 hull 组件取 `hit_locations()` 与 `armor`，或加「命中查无键比例过高则丢 plates」的覆盖率门槛。
3. **~~`HitLocation.thickness` 当前解析为 0~~（已修，本会话）**：`estimate_damage`/`pen_verdict` 的 `zone_mm` 现优先走 `zone_mm_for`（`plate_thickness_for_hit`），取装甲网格落点真实板厚；0mm 视为 unknown（`Some(0)`/`None` 均→保守 0.33α），不再判 HE 全穿。15.7 数据同样解析为 0（zones_probe 实测 Kleber 全 `thickness=0`），故该修复为必要。
4. **~~`exact_zone` 审计字段~~（已修，本会话）**：`HitAssessment`/`IncomingHit` 新增 `exact_zone`（splash 框精确键）与 `plate_thickness_mm`（本次读取的板厚），饱和/厚度变化现在可审计；真跑 Georgia 已见 `exact_zone:"Cit"/"SS"/"Cas"/"SSC"` 与真实板厚。
5. **per-ship 缓存**（评审 MEDIUM）：`hull_data_for_report` 每回放重读 assets.bin + VFS + 全量 `paths_storage` 扫描，跨回放无记忆化。批处理优化：按 (version, source) hoist 一次 VFS + parsed `PrototypeDatabase`，缓存 `HullData` 按模型目录。
6. **~~deck/superstructure 垂直起线仍固定 6/14m~~（已修，本会话）**：报告/文案的粗 `zone` 现由 `exact_zone_label` 从 splash 框精确键推导（未知键才回退 `zone_for_hit` 固定阈值），DD 甲板/上层建筑 hit 不再被标成「citadel」；真跑 Georgia 的 Monaghan HE 命中现为 superstructure/belt/deck/stern（此前大量误标 citadel）。但 `zone_for_hit` 函数本身仍保留固定 6/14m（作为无 splash 框时的回退），回退情形下误差仍在，已标注。
7. **半开/闭区间**（评审 LOW）：`exact_zone_for_hit` 用 `<= b.max`（闭），游戏 `getSplashBoxNameAtPoint` 为半开（`< box_max`）；当前同名框共享键所以无害，但建议镜像半开语义。
8. **`build_zones` last-wins 非确定**（评审 LOW）：若某 splash 框名被多个 `HitLocation` 认领，`HashMap` 迭代顺序导致非确定；观测数据一名一键，建议加断言或注明假设。
9. **`resolve_victim` 的 `MinimapPlacement` 边界换算**（早期记录）：恢复 AOI 外/边界目标，需地图边界数据。
10. **H1/M4 `visibilityFlags` 逐目标点亮**：标「需数据」，暂缓——不能区分「被集火」vs「被点亮」。
11. **S2 暴露近似**：仅 AOI 内世界样本，远处敌舰无世界样本可能低估暴露密度；真实视线/掩体未建模，`cover_status="unknown"`（已注明近似）。地图几何（masks）与 LOS 归因留待事件级。

## 常用命令与关键类型

- 校验：`cargo test -p wows-replay-insights --lib`；`cargo test -p wows-battle-world --lib`；`cargo check -p replayshark`；免 `cargo check --workspace`（rav1e/nasm）。
- 运行（`--game` 或 `-g`）：
  - `cargo run -p replayshark -- --game D:/World_of_Warships survival [--dims s1,s2,s3,s4] [--text] <回放>`
  - `cargo run -p replayshark -- --game D:/World_of_Warships report [--depth] <回放>`
  - `cargo run -p replayshark -- --game D:/World_of_Warships performance [--text] <回放>`
  - `cargo run -p replayshark -- --game D:/World_of_Warships hit-value|hit-summary|volleys|events <回放>`
- 真实数据探测（ignored）：`$env:WOWS_DIR='D:/World_of_Warships'; cargo test -p wows-replay-insights --test hull_probe -- --ignored --nocapture`（另有 `zones_probe`）。
- 关键类型：`BattleReport`（`self_damage_stats`/`burn_state_changes`/`active_consumables`/`deaths_by_victim`/`hit_history`/`salvos`/`positions_over_time()`/`hp_timeline()`）。`ResolvedShotHit`（`hit`/`victim_entity_id`/`victim_pose`/`salvo`）。`hit_value::zone_for_hit`/`exact_zone_for_hit`/`victim_hit_location`/`hit_location_for`/`zone_mm_for`。`hull_dim::{HullDim,HullData,HullZones,hull_data_for_report,plate_thickness_for_hit}`。`survival::{assess,assess_report,assess_exposure,assess_hp_timeline,assess_output,render}`。`performance::{assess_whole,render_whole}`。
- 技能：`C:/Users/asdfg/.codex/skills/wows-replay-parser`；设计文档 `specs/2026-09-05-survival-evaluation-engine.md`；ADR `docs/adr/0002-s1-survival-evaluation.md`（含 S1–S4 + P1/P2/P3/P3b/P4 各节）；`scripts/review.py`（跑 report）；中文舰名表 `ship_names.json`（`--ship-names`）。

## 关键不变式（输出/生存端延续）

- 换弹反事实仅主炮；副炮/AA 命中排除。受害舰必须 `Relation::is_enemy`；`victim_entity_id` 是「最近舰」启发式。
- 命中角由 `salvo.shots[].origin -> hit.position` 弹道向量 vs 装甲法线推（不依赖 null 的 `terminal_ballistics`）。
- 分区饱和：`HitLocation.max_hp` 作电量，耗尽后非核心命中 ~1/6；citadel（`Cit`/`Citadel`）永不饱和。
- 穿透用 wows_shell 社区公式，统一标「近似」。估伤为上限，非客户端精确值。
- 生存先于输出；「暴露/自救」只报可测证据，不臆断；`cover_status="unknown"`、`visibilityFlags` 未解。
- 舰名：运行时 `--ship-names <ship_names.json>`（含 CJK 才用，英文回退内嵌表）。
