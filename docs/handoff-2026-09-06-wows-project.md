# WoWs 工具集 项目交接文档（2026-09-06）

这是 `codex/local-changes` 分支（基于 upstream `landaire/wows-toolkit`）的**项目总交接**。
本分支在此之上叠加了「操作剧本经验分析」（方向④）等自定义模块。**新会话先读本文件**，再按需往下钻：

- 方向③详细续接：`docs/handoff-2026-09-05-wows-replay-survival.md`
- 方向④核心文档：`docs/Q6_CLASS_K_ANALYSIS.md`、`docs/PROJECT_CONTEXT.md`、`docs/WOWS_OPERATIONS_DEV_PLAN.md`
- 方向① skill 文档：`.codex/skills/wows-map-spawn-atlas/SKILL.md`、`wows-ship-spawn-probe/SKILL.md`、`wows-replay-cache/SKILL.md`
- 方向② skill 文档：`.codex/skills/wows-replay-parser/SKILL.md`

## 1. 开发方向总览

| # | 方向 | 状态 | 入口 | 数据源 | 交付物 |
|---|------|------|------|--------|--------|
| ① | 出生点 / 出生时间标定 | **活跃** | `wows-map-spawn-atlas`、`wows-ship-spawn-probe`、`wows-replay-cache` | `wows-replay-cache/cache/cache.sqlite`(33.7GB)、`replays/` | `output/{atlas,那莱}` 背板图、`wows-ship-spawn-probe/{已标定,未标定}` |
| ② | 玩家剧情 PR 量化 | **封存**（数据不足） | `wows-replay-parser` | `replays/replayswows-pve`、`replays.db`、`reports/舰船特色表.xlsx`(996艘) | `output/backboard`、玩家报告 |
| ③ | 当前 rep 深度分析报告 | **活跃** | 本仓库 `replayshark` / `wows-replay-insights` | `D:/World_of_Warships/replays`(15.7.0.0) | `survival`/`performance`/`report` 输出、`docs/handoff-...survival.md` |
| ④ | 逆向 WG 经验/收益算法 | **封存**（数据不足） | 本分支 ops 模块（Python） | `ops_efficiency_full.jsonl`(2060局)、`replays/` | `docs/Q6_CLASS_K_ANALYSIS.md`、`output/WOWS_OPERATIONS_INTERIM.md`、NGA 发布帖 |

> 状态来源（用户确认，2026-09-06）：①②逻辑相反——①③积极推进中；②④因数据量不够先封存。**清理后**：①③的资源（`target/`、`wows-replay-cache/cache/`、`replays/`、`output/{atlas,那莱}`、scripts/crates/docs）全部保留；②④的可再生加工缓存已清（见 §4）。

## 2. 各方向进度与未来计划

### ① 出生点 / 出生时间标定（活跃）

**已完成**
- 单船探针：`wows-ship-spawn-probe/scripts/probe_ship.py`（从所有 `.wowsreplay` 抽「首次被点亮」坐标散点，人工判断出生点，不自动下结论）。
- 地图出生点背板：`wows-map-spawn-atlas/scripts/render_map_spawns.py`（按分房/刷新机制拆图，`--mechanism normal|forced`，每船带呼号/中文名/出生时间）。
- 回放缓存：`wows-replay-cache`（解密成 Tier1 zst + Tier2 索引 + Tier3 spawns 表，`cache.sqlite`，**33.7GB**；缓存命中秒出，避免每次重解全部 rep）。
- 机制文档：`player_spawn_mechanics.md`（玩家出生/组队落位：舰种锚点、双人队块位、`prebattle_id` 识别）、`newport_reinforcement.md`（纽波特马汉+本森增援）。
- 工作区配套脚本：`scripts/calibrate_narai_spawn_probes.py`、`wave*_spawn_analysis.py`、`defender_sapper_spawn_analysis.py`、`defender_sapper_trigger_proximity.py`、`transport_motion_analysis.py`、`gen_wave_report.py`、`plot_survival*.py` 等。

**进行中 / 待办**
- `wows-ship-spawn-probe/未标定/` 里位置或时间仍浮动的船需人工标定 → 移入 `已标定/`，并经 `wows-map-spawn-atlas/confirmed_spawns.json`（`--confirm-file`）反哺背板渲染。
- 有的地图/分房可能还有未确认的浮动出生点；`render_map_spawns.py` 会在校验发现未确认时直接退出并打印缺失清单，需逐图补标定。

**未来**：补齐各剧情图全分房的出生点确认；把确认结果固化到 `confirmed_spawns.json`；扩展新地图族（`spawn_lib.py::MAP_IDX`）；按刷新机制（强制/正常）标注每船刷新时间。

### ② 玩家剧情 PR 量化（封存，数据不足）

**已完成**
- 解析落库：`skill/scripts/extract_ops_replays.py` → 人均一行 JSONL + SQLite `replays.db`，幂等追加、多 worker、常量表自动抓取。
- 玩家报告：`player_report.py`；剧情「吃船效率」提取：`extract_ops_efficiency.py`。
- 舰船特色表：`reports/舰船特色表.xlsx`（996 艘、未和谐中文名、28 个特色列）；`feature_gate.py`（按船名定位行号、校验、未标注即拒绝分析、生成待标注清单）；`learn_features.py`（备注列自学习，匹配/合并/新增特色列）。
- 工作区：`scripts/gen_backboard_reports.py`、`enhanced_analysis.py`、`ship_zh.py`、`reports/SKmon_解析报告.md` 等。

**封存原因 / 未来**
- 数据量不足 + 未标注特色 → `feature_gate.py` 会拒绝输出任何战斗/风格/效率结论（按用户设定的「特色表未标注即拒绝」口径）。
- 未来：先采集更多剧情 rep；再全量标注 996 艘特色列；然后跑 `player_report.py` 做玩家 PR/风格量化，并与方向③的 `survival`/`performance` 指标打通。

### ③ 当前 rep 深度分析报告（活跃）

**已完成（非常深入）**
- `replayshark` CLI：`report [--depth]`、`hit-value`/`hit-summary`/`volleys`/`events`、`survival [--dims s1,s2,s3,s4] [--text]`、`performance [--text]`。
- 输出端：仅主炮/仅敌方、分区饱和、提前量、换弹反事实、逐轮 0-100 评分；精确区板厚由 `.geometry` 装甲网格 + `ArmorMap` 在落点取（`hull_dim::plate_thickness_for_hit`），命中板取「离落点最近交点」。
- 生存端 S1–S4：受击/着火/DCP/heal/死亡/Agro + S2 暴露 + S3 HP 时间线 + S4 输出耦合 + 0-100 生存分；诚实化（`Option`/fate 门控/覆盖率为 unknown 不臆断）。
- 审计与修正：`HitAssessment`/`IncomingHit` 新增 `exact_zone`/`plate_thickness_mm`；`exact_zone_label` 修复 DD 甲板被标成 citadel；半开区间镜像游戏；`build_zones` 确定性；`--no-default-features` 编译修。

**详细现状与遗留项**：`docs/handoff-2026-09-05-wows-replay-survival.md`（唯一续接入口，含每个 commit 相位与剩余项）。

**未来（按优先级）**
- `#2`：装备 hull 的 `ArmorMap`/`hit_locations` 取数（目前 `ArmorMap`/`max_hp` 读 base `Vehicle`；底层是 TTX 层取数）。
- `#5`：per-ship `HullData` 缓存（需自引用借用——`PrototypeDatabase` 借用 `assets_bin` 字节——或 `Box::leak`/`self_cell`，并穿线 replayshark 4 个近似循环；本会话评估后回退）。
- `#9/#10/#11`（数据项）：地图几何 masks / LOS 归因、`visibilityFlags` 逐目标点亮、S2 真实视线/掩体——需先拿到地图几何与侦测事件。
- `#4/#6`（已完成）、`#7/#8`（已完成）不再处理。

### ④ 逆向 WG 经验/收益算法（封存，数据不足）

**已完成**
- 用 2060 局对 WG 经验分配公式做逆向拟合：舰种系数 K 分解（伤害类型/集中度/增援）、增援伤害回报、经验池、单船强度、存活率、XP 公式推导+验证。
- 核心文档：`docs/Q6_CLASS_K_ANALYSIS.md`、`docs/reinforcement-damage-analysis.md`、`docs/WOWS_OPERATIONS_ANALYSIS.md`、`docs/PROJECT_CONTEXT.md`（元文档/手记）。
- 设计文档：`WOWS_OPERATIONS_STATS_PLAN.md`（玩家评分）、`WOWS_OPERATIONS_DEV_PLAN.md`、`WOWS_OPERATIONS_SAMPLE_COLLECTOR.md`、`WOWS_WG_API_REFERENCE.md`。
- 输出：`output/WOWS_OPERATIONS_INTERIM.md`、`ops_xp_formula.md`、`ops_xp_pool.md`、`ops_xp_validation.md`、`ship_strength.md`、`survival_report.md`、`report_nga_{player,expert}.md`、`output/nga_publish/` 等。
- 工作区脚本：`scripts/analyze_ops_*.py`、`extract_ops_*.py`、`fit_{class_efficiency,damage_types,ship_strength,xp_pool}.py`、`recompute_k_damage_types.py`、`analyze_reinforcement*.py`、`analyze_damage_types.py`、`analyze_waves*.py`、`concentration_run*.py`、`check_conservation.py`。

**封存原因 / 未来**
- 用户提到「用更多样本」——当前 2060 局可能不足以支撑最终结论，且 WG API 批量缓存（`cache/`）已清理（`scripts/mass_collect.py` 可重建）。
- 未来：持续用 `extract_ops_replays.py` 落库扩样本 → 重建 `ops_efficiency_full.jsonl`/`replays.db` → 重跑拟合 → 复核/修订 XP 公式（含伤害类型/增援/集中度/经验池/单船强度），最终收敛到可发布的结论。

## 3. 常用运行入口

```powershell
# 方向③ 当前 rep 深度分析（--game 指向游戏安装）
cargo run -p replayshark -- --game D:/World_of_Warships performance --text "<回放>"
cargo run -p replayshark -- --game D:/World_of_Warships survival [--dims s1,s2,s3,s4] [--text] "<回放>"
cargo run -p replayshark -- --game D:/World_of_Warships report [--depth] "<回放>"

# 方向① 出生点背板 / 单船探针（见 SKILL.md）
python C:/Users/asdfg/.codex/skills/wows-map-spawn-atlas/scripts/render_map_spawns.py --map NavalBase --db C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite --replays D:/codexProject/wows-toolkit/replays D:/World_of_Warships/replays --game-dir D:/World_of_Warships --out-dir output/atlas
python C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts/probe_ship.py --map NavalBase --needle MOB_AIR_CARRIER_1 --db C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite --replays D:/codexProject/wows-toolkit/replays D:/World_of_Warships/replays --game-dir D:/World_of_Warships --out output/ship_spawn_probe.png

# 方向② 解析落库（见 skill SKILL.md）
python C:/Users/asdfg/.codex/skills/wows-replay-parser/scripts/extract_ops_replays.py D:/replays --db replays.db --constants-dir constants_cache --ship-cache ships_cache.json --workers 8

# 方向④ 数据集与拟合（见 docs/WOWS_OPERATIONS_DEV_PLAN.md）
```

## 4. 数据与缓存状态（2026-09-06 清理后）

**保留**（活跃方向①③ + 封存方向②④的原始数据/交付物）：
- 方向③：`target/`（48.8GB 构建缓存）、`crates/`、`docs/`。
- 方向①：`wows-replay-cache/cache/`（33.7GB）、`wows-ship-spawn-probe/{output,未标定,已标定}`、`output/{atlas,那莱}`。
- 方向②④数据：`replays/`（8GB 原始回放）、`replays.db`、`ops_efficiency_full.jsonl`、`ships_cache.json`、`ships_zh.json`、`output/{backboard,archive}`、`reports/`。
- `scripts/`、`crates/`、`tests/`、`assets/`、`site/`、`input/`、WOWS 相关 skill。

**已清理**（封存方向②④的可再生加工缓存）：
- `cache/`（WG API 批量缓存，415MB）—— `scripts/mass_collect.py` 可重建。
- `constants_cache/`（35 个已跟踪文件）—— `git rm` + 加入 `.gitignore`（commit `70ccc536`）。
- `scripts/__pycache__`、`output/__pycache__`。

工作树干净，分支 `codex/local-changes`。

## 5. 约定（AGENTS.md）

- 先修已确认 bug，再开新功能；新里程碑须在上个 bug/评审阻塞项清空（或用户明确顺延）后开。
- 提交前用新鲜 `v4_flash_worker` 子代理做对抗性评审（plaintext-handoff Hook 已配好，先读 `use-v4-flash-worker`）。
- 免跑 `cargo check --workspace`（rav1e/nasm 环境问题）；校验用 `cargo test -p wows-replay-insights --lib`（145）与 `cargo test -p wows-battle-world --lib`（43）。
- 提交信息不加 AI 署名；代码/注释 ASCII（中文仅限于 UI 字符串与文档）。
