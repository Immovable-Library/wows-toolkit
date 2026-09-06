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
>
> **固定口径（AGENTS.md）**：先修 bug，再加新功能；新里程碑须在上个 bug/评审阻塞项清空（或用户明确顺延）后才开；提交前用新鲜 `v4_flash_worker` 子代理做对抗性评审（plaintext-handoff Hook 已配好）；工作区注意 `cargo check --workspace` 因 rav1e/nasm 环境问题失败（与改动无关，免跑）；提交信息不加 AI 署名。

## 当前验证基线（截至 2026-09-06）

- `cargo test -p wows-replay-insights --lib`：**140 passed**。
- `cargo test -p wows-battle-world --lib`：**43 passed**。
- `cargo check -p replayshark` / `-p wows-replay-insights`：干净。
- `cargo clippy -p wows-replay-insights -p replayshark`：新增告警无（既有风格项未动）。
- 真实数据探测（ignored，需 `WOWS_DIR=D:/World_of_Warships`）：`tests/hull_probe.rs`（Iowa 全长 270.4m/宽 33.0m、Kleber 141.0m/13.2m、Balao 94.9m/8.7m）；`tests/zones_probe.rs`（Kleber/Iowa 的 splash 框→`HitLocation` 键映射）。
- 真跑 Georgia Atoll（`20260813_210427_PASB729-Georgia_s06_Atoll.wowsreplay`）：`report --depth`、`survival --text`、`performance --text`/JSON 均出结果；精确区使饱和命中 7→13。

## 遗留/未完成项（新对话可从这里继续）

**优先级建议**（均注明严重性/来源）：
1. **`--no-default-features` 编译破**（既有包装问题，非本会话回归；评审 HIGH，但仅影响特殊特性组合）：`hit_value`/`survival` 无条件引用 `crate::build::ResolvedBuild`（build 特性门控），`hull_dim` 也门控于 build，故 `cargo check -p wows-replay-insights --no-default-features` 失败。工作区成员一律启用 `build`/`battle-report`/`wowssb`，正常运行不受影响。修法：把 `hit_value`/`survival` 一并门控于 `build`（或把 `HullDim`/`SHIP_MODEL_TO_METERS` 移入非门控模块）。
2. **per-hull `hit_locations` 取板厚**（评审 MEDIUM）：`victim_hit_location`/`hit_location_for` 用的 `Vehicle.hit_locations()` 来自首个（stock）hull 组件，而 zone 边界来自装备 hull——装备 hull 的边界可能配 stock hull 的板厚/饱和预算。目前只证明「精确区键能找到 HitLocation」，未证明板厚属装备 hull。修法：从装备 hull 组件取 `hit_locations()`，或待 splash-box 分类器一并收口。
3. **`HitLocation.thickness` 当前解析为 0**（本机 bin `13015811`；评审 MEDIUM）：`estimate_damage` 对 `Some(0)` 判 HE 全穿（alpha），`None` 则 0.33α——精确分类改变了部分区（曾落到 `Hull`/`None` 的）HE 估伤。建议核对：板厚应从 `ArmorMap` 取而非 `HitLocation.thickness`，并确认 15.7 数据是否同样 0 厚度。
4. **`exact_zone` 审计字段**（评审 LOW）：`HitAssessment`/`IncomingHit` 只暴露粗粒度 `zone`，不暴露是否用了精确键——审计饱和/厚度变化需要加 `exact_zone`（或精确键）字段。
5. **per-ship 缓存**（评审 MEDIUM）：`hull_data_for_report` 每回放重读 assets.bin + VFS + 全量 `paths_storage` 扫描，跨回放无记忆化。批处理优化：按 (version, source) hoist 一次 VFS + parsed `PrototypeDatabase`，缓存 `HullData` 按模型目录。
6. **deck/superstructure 垂直起线仍固定 6/14m**（已知近似）：`exact_zone_for_hit` 定了精确板厚，但报告里的粗粒度 `zone` 字段仍用 `zone_for_hit` 的固定垂直阈值——DD 甲板 hit（y≈3-6m）可能标成「citadel」而板厚取对了。需在报告或文档标注，或把粗 label 也由 splash 框推导。
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
- 关键类型：`BattleReport`（`self_damage_stats`/`burn_state_changes`/`active_consumables`/`deaths_by_victim`/`hit_history`/`salvos`/`positions_over_time()`/`hp_timeline()`）。`ResolvedShotHit`（`hit`/`victim_entity_id`/`victim_pose`/`salvo`）。`hit_value::zone_for_hit`/`exact_zone_for_hit`/`victim_hit_location`/`hit_location_for`。`hull_dim::{HullDim,HullData,HullZones,hull_data_for_report}`。`survival::{assess,assess_report,assess_exposure,assess_hp_timeline,assess_output,render}`。`performance::{assess_whole,render_whole}`。
- 技能：`C:/Users/asdfg/.codex/skills/wows-replay-parser`；设计文档 `specs/2026-09-05-survival-evaluation-engine.md`；ADR `docs/adr/0002-s1-survival-evaluation.md`（含 S1–S4 + P1/P2/P3/P3b/P4 各节）；`scripts/review.py`（跑 report）；中文舰名表 `ship_names.json`（`--ship-names`）。

## 关键不变式（输出/生存端延续）

- 换弹反事实仅主炮；副炮/AA 命中排除。受害舰必须 `Relation::is_enemy`；`victim_entity_id` 是「最近舰」启发式。
- 命中角由 `salvo.shots[].origin -> hit.position` 弹道向量 vs 装甲法线推（不依赖 null 的 `terminal_ballistics`）。
- 分区饱和：`HitLocation.max_hp` 作电量，耗尽后非核心命中 ~1/6；citadel（`Cit`/`Citadel`）永不饱和。
- 穿透用 wows_shell 社区公式，统一标「近似」。估伤为上限，非客户端精确值。
- 生存先于输出；「暴露/自救」只报可测证据，不臆断；`cover_status="unknown"`、`visibilityFlags` 未解。
- 舰名：运行时 `--ship-names <ship_names.json>`（含 CJK 才用，英文回退内嵌表）。
