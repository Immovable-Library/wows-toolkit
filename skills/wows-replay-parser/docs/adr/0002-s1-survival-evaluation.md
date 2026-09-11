# S1 生存端评估：现成数据的生存画像 + 0-100 生存分

背景：输出端（M2）回答「这发命中质量/该不该换弹」，生存端回答「你怎么活下来的」。生存端从 S1 起步，只用已解码数据：被打命中、估伤、着火、DCP/heal、死亡、危险伤害（agro）。设计蓝本见 `specs/2026-09-05-survival-evaluation-engine.md`。

决策：
- 新增 `wows-replay-insights/src/survival.rs`：`assess` 产出 `SurvivalProfile`（JSON），`render` 出文本报告；`replayshark` 新增 `survival` 子命令（默认 JSONL，`--text` 出文本）。
- 被打命中复用已提交输出端引擎 `hit_value::estimate_damage` 与「仅敌方」不变式；对 `victim == self` 的命中，用同一函数估吃伤。
- 受影响/受伤来源（`victim_entity_id == self`）：**必须先修 victim 解析**（见下）。
- 危险伤害 = `DamageStatCategory::Agro`（潜在伤害，按 weapon 拆开）；「规避」= 1 - 实际吃伤 / 危险伤害。
- 着火 = `burn_state_changes`（自舰）的点燃次数；同时用 bitmask 还原「持续火段」，判断 DCP 是否及时覆盖（只对 ≥10s 的持续火段计失，短火/自灭不计）。
- 无 DCP 的舰视「没得用」（资源限制）而非「用错」，自救因子给基线 0.6，不做归因。
- 死亡用 `deaths_by_victim`（自舰）与 `played_duration` 换「死亡时刻占对局比例」；死亡原因未在 BattleReport 暴露，标「需事件级/S3」。

## 修正：`resolve_victim` 改为 owner-aware（wows-battle-world）

原 `resolve_victim` 只在 `.relation().is_enemy()` 的实体里找最近舰。这使「敌方炮弹打中录制者自舰」永远无法把 victim 解析成自舰（自舰 relation 是 Self，不是 Enemy），从而被签到附近敌舰——生存端因此根本拿不到「被打命中」。

决策：victim 候选集依射手（`owner_id`）对录制者的关系取反。
- 射手是敌方 → 候选为录制者方（自舰 + 友军，即 `!is_enemy()`）。
- 射手是自舰/友军/未知 → 候选为敌方（保持输出端「仅敌方」行为）。

这保留 M2 输出端不变式（自舰炮弹仍解析到敌舰；不回归「神风命中 11→14」修复），同时修好 incoming 方向。物理上「你打不到己方」成立，所以候选集按射手关系取反是正确规则，而非单靠「仅敌方」。

## 已知缺口（S1 不做虚假归因）

- 分区饱和：`hit_locations` 依赖 game data（models opt-in）；缺失时 `zone_max_hp=0`，饱和不计，估伤为上限（文本注明「该构建 hit_locations 可能未启用」）。
- 进水状态：burn 日志忽略 flood 位（4-7），BattleReport 无自舰进水/HP 时间线；`flood_status` 标 `unknown`，死亡原因未暴露。
- 走位/暴露/血量管理属 S2/S3，需新增位置/HP 时间线导出。

## S2（2026-09-05 同日追加）：位置时间线 + 近似暴露/走位

背景：原 S1 把暴露/走位归因留到 S2，但 `BattleReport` 无位置时间线。S2 先把位置历史导出落地，再做近似暴露/走位。

决策：
- `wows-battle-world` 新增 `PositionHistoryLog`（`PositionSample{entity,clock,kind}`，`PositionKind::World{position,yaw_deg}` / `Minimap{position,heading_deg,visible}`）。`IngestOptions`/`ProcessOptions` 增 `record_position_history`（默认 false，避免全量成本）；`handle_position`/`handle_player_orientation`/`handle_minimap_updates` 门控记录；`BattleReport::positions_over_time()` 暴露。
- `survival.rs` 新增 `Exposure`（S2）：只用世界坐标（AOI 内），统计自舰/敌舰世界样本数、最近敌舰 min/avg 距离、12km 内暴露占比、12km 内平均敌舰数（按实体去重，避免把同舰密集样本重复计数）、approach/kiting 比例（自舰跨 ~1s 航向 vs 敌舰方向 dot 符号，阈值 0.3）。`cover_status="unknown"`。

不自欺：
- 「暴露」只用「位置 + 12km 内有已知敌舰」这一可测证据；真实视线（island LOS）与掩体距离未建模，一律标近似；`visibilityFlags`（H1/M4）未解锁，不能区分「被集火」vs「被点亮」。
- 位置样本只覆盖 AOI 内（世界坐标）；AOI 外/远处敌舰无世界样本，可能低估暴露密度——文本已注明。
- 运动方向用跨 ~1s 的起点，避免相邻毫秒级采样位移过小导致 approach/kiting 恒为 0。

已知留待 S3：HP 时间线（血量管理/濒死时刻）。地图几何（masks）与 LOS 归因仍为后续事件级。

## P1/P2（2026-09-05 同日追加）：装甲网格逐舰分区（修正 burn 节点不可行）

背景：输出端 `hit_value::zone_for_hit` 原用固定、按大和级战舰标定的阈值（bow/stern 110m、belt 8m、deck 6m、superstructure 14m）。对驱逐舰，110m 大于船体半长、8m 大于半宽，导致整舰命中被误判为 citadel。

修正（原设计用 `FireSectionGeometry.longitudinal()`，burn 节点精化 zone 边界）：**不可行**。burn 节点（skeleton extender `EP_Fire_N`）只覆盖船体中段，不含船头/船尾端点。改用**完整 hull 装甲网格顶点包围盒**（`.geometry` 的 `armor_models` 三角形）提取每舰长/宽/高。

决策：
- 模型空间右手系，+Z 朝船头（长）、+X 舷向（宽）、+Y 上（高），1 ship-model 单位 = 15m（`ShipModelDistance` 与 `WORLD_TO_METERS` 同为 15）。装甲网格是整船（bow 到 stern），其三角形包围盒给出正确长宽（真实的 Iowa 270.4m/33.0m，Kleber 141.0m/13.2m；Z 长、X 宽、Y 高）。测试 `tests/hull_probe.rs`（ignored，需 install）锁定该事实。
- `hull_dim.rs`：`HullDim{length_m,beam_m,height_m}`；`hull_dim_from_geometry`（纯，由 `armor_models` 三角形求 bbox，×15 转米）；`hull_dims_for_report`（读 `assets.bin` + VFS，逐舰解析 `.model` 目录下的 `.visual` → `.geometry`，并集 bbox；按 `path_entry.self_id` 直接定位 visual，避免跨舰同名叶子串扰；逐部件失败 `continue`，整机失败回退启发式）。
- `zone_for_hit(hit, Option<&HullDim>)`：有 hull 时 bow = half_length × 0.814、belt = half_beam × 0.485（这 0.814/0.485 是按 Iowa bbox 220.4m/33.0m 对旧 110m/8m 的标定，使大舰行为不变、小舰成比例缩小）；deck/superstructure 保持固定 6/14m（bbox 无法定位甲板/上层建筑起线，按总高缩放会把驱逐舰甲板放到任何真实命中之下——诚实留作启发式）。无 hull 回退旧固定值。
- CALLERS：`assess`/`summarize`/`analyze_volleys`/`render_report`/`render_normal_report`/`render_deep_report`/`self_output_timeline` 增 `Option<&HashMap<EntityId,HullDim>>`；`survival` 的 `assess`/`assess_report`/`assess_output`/`render` 透传（S1 被打命中以自舰 hull 分区）。
- CLI：`replayshark` 的 hit-value/survival 命令在 `--game` 可用时经 `open_build_vfs` 构建 hull 缓存并透传；无 VFS（extracted 无 assets.bin）则 `None` 回退。
- 特性：`wows-replay-insights` 仅在 `build` 特性下启用 `wowsunpack/models`（geometry/assets_bin），避免无 `build` 消费方拉入 gltf/image。`ShipAssets::from_game_dir` 用 `vfs-mmap` 门控（它引用 `game_data`，本已 vfs-mmap 门控）。

已知近似（已标注）：
- 舰按 base `model_path` 解析，不区分装备的 hull 升级（hull 间长宽差异小，留待 P3 用 `vehicle.model_path_for_hull`）。
- bbox 视为以模型原点居中，前后/左右对称（per-side reach 留待后续）。
- `assets.bin` 未跨回放缓存（handoff P1 的「每舰缓存」留待批处理优化）。

验证：`cargo check -p wows-replay-insights`/`-p replayshark` 干净；`cargo test -p wows-replay-insights --lib` 138 通过（新增 `per_ship_bow_boundary_rescues_a_destroyer_hit`、`merge_takes_the_max_extent`、`junk_geometry_yields_none`）；`cargo test -p wows-battle-world --lib` 43 通过；`tests/hull_probe.rs`（ignored）实测 Iowa/Kleber 长宽高正确。真跑 Georgia Atoll `report --depth`：`Johnston(stern)`、`Minnesota(superstructure/belt/deck)` 等出现——旧固定阈值对驱逐舰不可能产生 stern，证实逐舰分区生效。

## P3（同日追加）：装备 hull + per-side reach（对账 hit_locations 的第一步）

对账目标：zone 分类要与 GameParams `hit_locations`（装甲厚度）一致。上一步两个近似在本步收口：
- **装备 hull**：`hull_dims_for_report` 改为按 `fire_chance::resolve::equipped_upgrade(build, "_Hull", ttx.hulls.keys())` 解析装备 hull 升级，并经 `vehicle.model_path_for_hull` 取模型路径；build 无 TTX hull 组件时回退 base `model_path`（`equipped_upgrade`/`SlotGap` 提升为 pub(crate)）。
- **per-side reach**：`HullDim` 从「对称总长/半宽」改为「`fore_m`/`aft_m`/`beam_m`/`height_m`」独立 reach（取自 bbox 的 min/max），`zone_for_hit` 的首尾边界用非对称 `fore*0.814`/`aft*0.814`，舷侧用 `beam_m*0.485`。

仍在（诚实开放项）：deck/superstructure 垂直起线仍用固定 6/14m，因 bbox 与总高缩放都不可靠；真正精确的对账是 `HitLocation.splash_boxes` 名称 → `.splash` 的 `SplashBox` 3D 框（`geometry::parse_splash_file`），逐舰做点-框包含分类，替换启发式 zone——此为后续里程碑（或 P4 前置）。`assets.bin` 未跨回放缓存（批处理优化）。垂直起线在驱逐舰上仍会把 y≈3-6m 的甲板命中读成 citadel（已注明）。

对抗性评审（v4_flash_worker）标记的剩余点：
- **装甲厚度仍取 base hull**：`victim_hit_location`/`hit_location_for` 用的 `Vehicle.hit_locations()` 来自首个 hull 组件（provider 解析），而 zone 边界来自装备 hull——即装备 hull 的边界配 base hull 的板厚。本步只验证「每个 zone 字符串能找到 HitLocation」，未验证板厚属于装备 hull。待 splash-box 分类器替换后一并收口。
- **`--no-default-features` 不可编译**（既有，非本步回归）：`hit_value`/`survival` 早于本次改动就无条件引用 `crate::build::ResolvedBuild`（build 特性门控），而 `hull_dim` 也门控于 build。工作区成员一律启用 build/battle-report/wowssb，故正常运行不受影响；属 crate 最小特性形态的既有包装问题。
- **目录级 `.visual` 扫描并集**：`hull_dim_for_model` 扫描 `/{model_dir}/` 下所有 `.visual` 并并集 bbox；若某目录被多个 hull 模型共享或含非 hull 几何，会并集出错误外扩。多为单目录单模型，故为主观风险而非已证实 bug。

## P3b（同日追加）：`.splash` splash-box 精确对账（替换启发式 zone）

用游戏自己的 `.splash` `SplashBox` 逐舰做点-框分类，得到精确 `HitLocation` 键，取该键的板厚/饱和预算，并保留粗粒度 label 供 reason/saturation 文本。

决策：
- `hull_dim.rs` 增 `HullZones{boxes, zone_for_box}`（box 名 → 精确区键，来自 `Vehicle.hit_locations()` 各区的 `splash_boxes()` 名）与 `HullData{dim, zones}`；`hull_dims_for_report` → `hull_data_for_report`（逐舰读 `.geometry` dims + `.splash` 兄弟框）；`exact_zone_for_hit` 把 body 偏移映射为模型坐标 `[body.z, body.y, body.x]` 后做包含判定，返回映射键，否则 `None`。
- `hit_value`/`survival`：`zone_for_hit` 仍出粗粒度 label；`assess`/`self_output_timeline`/`survival::assess` 用 `exact_zone_for_hit(...).unwrap_or(zone)` 作为 `victim_hit_location` 的查询键，使厚度/饱和读精确区。粗粒度 zone 仅保留给 `reason_for`/swap 文本与报告 zone 字段。
- 真数据验证：Kleber 8 个 `HitLocation`（Bow/Cas/SS/St/Hull/SG/Ammo_1/Ammo_2），splash 框名 `CM_SB_<zone>` 清晰映射；`exact_zone_for_hit` 单测 + `tests/zones_probe.rs`（ignored）断言框→区映射。真跑 Georgia Atoll 饱和命中由 7 增至 13，因精确区 `max_hp` 池生效。

评审（v4_flash_worker）修复/记录：
- **修复（HIGH）**：`exact_zone_for_hit` 首框未映射时继续扫描（真实引擎框 `CM_SB_engine_*` 未映射且嵌在 `CM_SB_cit_1` 内），否则机械区命中错误回落粗粒度；单测 `exact_zone_skips_an_unmapped_overlapping_box` 锁定。
- **修复（HIGH）**：饱和记账与 citadel never-saturate 门改按 `hitloc_zone`（精确键）而非粗粒度 `zone`，避免一个粗粒度桶混算多个不同 `max_hp` 的精确区；`is_citadel_zone` 识别 `Cit`/`Citadel`。
- **记录（MEDIUM）**：当前安装所有 `HitLocation.thickness` 解析为 0（`estimate_damage` 对 `Some(0)` 判 HE 全穿 0.33α→α），使精确分类对薄甲区 HE 估伤上调——此为 HE 全穿语义，非 bug；若 15.7 数据同样 0 厚度则一致。板厚/区键仍可能来自 stock hull（provider）而非装备 hull（待 splash 分类器 + per-hull hit_locations 一并收口）。精确键缺失时 `hit_location_for` 仍静默回退 `Hull`，属版本偏差边缘情况。
- **记录（LOW）**：包含用闭区间而游戏为半开（`< box_max`）；`build_zones` 同名框多键时 last-wins 非确定（数据中一名多键未出现）；报告未暴露 `exact_zone` 字段（审计 13-vs-7 需加，留作后续）。

## P4（同日追加）：整局表现整合（生存 + 输出一页）

把生存端（S1-S4 的 `SurvivalProfile`）与输出端（`hit_value::assess`/`analyze_volleys`/`summarize`）合并成一张「整局表现」。

决策：
- `performance.rs`：`WholeMatch{survival: SurvivalProfile, output: OutputSummary}`；`OutputSummary` 含主炮估伤/命中数/未评估数、轮均分/打中轮数/最高轮分、饱和命中数、逐目标 lessons。`assess_whole(report, params, hull)` 聚合；`render_whole` 输出一页文本（地图/模式/结果/时长 → 输出端 → 生存端 S1-S4 → 结论/综合）。
- `replayshark` 新增 `performance` 命令：默认 JSON（serialize `WholeMatch`），`--text` 一页。命令行 `--game` 时经 `hull_data_for_report` 建 per-ship 精确区/维度缓存并透传。
- 口径：输出端 `estimated_damage` 为主炮命中（`hit_value::assess` 仅主炮换弹语义）；生存 S4 `output_coupling.output_damage_estimated` 更宽（含非主炮）。一页文本用「主炮」与「输出估伤」区分，避免同页两个不同数字被误读。

验证：真跑 Georgia Atoll `performance --text` / 默认 JSON 均出结果；`cargo test -p wows-replay-insights --lib` 140 通过；`cargo check -p replayshark` 干净；clippy 无新增告警。
