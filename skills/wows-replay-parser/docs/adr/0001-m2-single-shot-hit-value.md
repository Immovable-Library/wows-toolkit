# M2 改为单轮命中价值评估，以 Rust + wowsunpack 物理为准

背景：原 M2 设计为「期望命中率 vs 实际命中率」以区分散布 RNG（H2）与瞄准（H3）。实测发现 wowsunpack 未抽取 sigma、官方 WG API（需 application_id）不提供跳弹角/引信阈值/分段装甲常量，且目标是可操作建议（提前量、穿深判定、换弹种收益）而非纯数值。故把 M2 重构为单轮命中价值评估。

决策：
- 计算放 Rust（wows-replay-insights / replayshark `analyze`），复用 wowsunpack 的 `ShellInfo` + 装甲模型（`ArmorModel`/`ArmorMap`/`armor_materials`）+ 弹道；命中点装甲用 `ArmorModel` 三角宫求交。
- 官方 WG API 仅作弹种伤害/起火率/最大散布的交叉核对，不作核心数据源。
- 弹药三态 AP/HE/SAP，仅主炮，鱼雷搁置；每艘主炮仅两种弹种（HE+AP / HE+SAP / SAP+AP），故反事实只对比另一弹种。
- 换弹种反事实 = 同射程同目标角度下，瞄准点换到该弹种最优落点区（AP=主装/核心是否可穿，HE=上层溅射+起火，SAP=中层）；不是瞄准点不变、单纯把 HE 换成 AP 的同弹道换弹。
- sigma 仅作为「散布是否反常」的置信度说明，不当作硬依赖。

后果：命中角不能依赖 `terminal_ballistics`（15.7.0.0 很多命中该字段为 null），需由 `salvo.shots[].origin → hit.position` 弹道向量 vs 命中点板法线推导。穿透模型是 wows_shell 社区公式，统一标「近似」，不冒充客户端精确值。

后续决策（2026-09-05 同日）：
- **仅主炮弹种**才做换弹反事实；副炮/AA 自动炮命中排除（不可手动换弹，给出主炮换 HE 建议属无效）。
- **仅敌方可作受害舰**：玩家的炮弹只能伤害敌方；`victim_entity_id` 是「最近舰」启发式，AOI 外目标会签到自军/盟友（东京快车迪米特里即友军误归属），故分析只保留 `Relation::is_enemy` 的受害舰。
- **分区饱和**：用 `HitLocation.max_hp` 作分区电量，按时序累计，电量耗尽后非核心命中降到 ~1/6；`HitLocation.thickness` 作该区穿深基准；citadel 永远 100%。
- **报告分档**：`report`（按目标，普通）、`report --depth`（逐轮全量，含弹种/目标/命中数/勋带/部位/原因/评分）。
- **本地舰名对照表**：`data/ships_zh.json`（skill 目录）；Rust 内嵌默认同名，未知回退英文名（第一个 `_` 后）。
- 根因 TODO：`resolve_victim` 仅用 `Transform3d`（AOI），应改用/叠加 `MinimapPlacement`（全舰）并限定敌方，以根治 AOI 外目标的误归属与丢失。
