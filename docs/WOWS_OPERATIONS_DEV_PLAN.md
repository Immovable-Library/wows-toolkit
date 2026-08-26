# 剧情 Operations PR 开发计划

本文件是项目长期开发计划，记录目标、当前结论、待办和关键产物。每次继续工作先读这里。

## 1. 目标总览

1. **主目标：剧情 PR 算法**。做一套类似 PvP PR 的剧情评分，在开战前对玩家量化评分。要求两个独立输出：账号总数据评分、本次所开船的评分。
2. **中间产物：rep 解析 skill**。批量解析某玩家的 replay，分析其战斗表现。
3. **社区疑问：航母/潜艇经验系数**。航母和潜艇的经验系数是否与其他舰种不同，系数如何计算、差额如何分配。
4. **总经验池机制**。剧情模式总经验池如何计算；次要任务未完成、挂机、暴毙、表现差如何影响总池子。
5. **效率分配 + 潜艇 1.75**。公认说法是经验按"个人效率占全队总效率"按比例分配；有玩家指出潜艇效率额外乘 1.75（参考 B 站视频 BV1PGfpBSEje）。

## 2. 当前状态

| # | 目标 | 状态 | 已拿到的结果 | 剩余工作 |
|---|---|---|---|---|
| 1 | 剧情 PR 算法 | 进行中 | 初版公式 `Rating = 700*rXP + 0*rS + 0*rW`，`rXP = 该船场均经验 / 该船期望经验`；733 船强度表；8月 143 局验证排名 Spearman≈0.62、经验 Pearson≈0.64 / R²≈0.25 | 精度仍一般；新 XP 模型尚未反哺进 PR |
| 2 | rep 解析 skill | 已完成（可增强） | skill + 解析器 + 玩家报告可用；已扩展 per-target 伤害到船等价效率提取 | 可选：把效率提取并进 skill 文档 |
| 3 | CV/SS 经验系数 | 已完成 | CL/CA 基准：DD 0.83 / BB 0.95 / CV 0.43 / SS 1.40；SS 相对 DD≈1.67 | 基本无 |
| 4 | 总经验池机制 | 基本完成 | 池子主要由 场景+星级+胜负 决定（R²0.96）；每星约 +9%，败局约半池；次要任务和队伍效率影响很小 | 可细化败局/超时等 finish_type 的独立惩罚 |
| 5 | 效率分配 + 潜艇 1.75 | 已完成 | 经验占比 = 均分地板 + 舰种加权效率；潜艇 1.75 实测≈1.72（相对 DD） | 基本无 |

## 3. 关键结论与公式

### 3.1 口径约定

- 用户 uomouse，欧服，account_id = 566060956；好友 SKmon，亚服，account_id = 2018689466。
- 高账倍率 = 1.65。1.5 是随机 PvP 胜方加成，与剧情无关。
- replay 的 `raw_exp` 就是基础经验（不吃高账/首胜）；WG API 的 `oper_solo.xp` 含高账，要除以 1.65。
- 结算面板经验统一用基础经验口径。

### 3.2 初版 PR 公式

```
rXP = 该船场均基础经验 / 该船期望基础经验
Rating = 700*rXP + 0*rS + 0*rW
```

- `rS`（五星率）、`rW`（胜率）在公式里保留，但权重置 0，因为团队稀释严重、对排名无帮助。
- 期望值来自 `output/ship_strength_full.json` 的 `abs_xp_avg`。
- 验证结论（8月）：船级原始 XP 排名 Spearman 0.616，归一化 0.582；经验预测 Pearson 0.639、R² 0.252，系统性低估约 10%。

### 3.3 经验分配模型（本轮核心新发现）

对一局 n 名玩家：

```
贡献_i = 船等价效率_i + lambda * (点亮伤害_i / 100000)
经验占比_i = a/n + (1-a) * K[舰种_i] * 贡献_i / sum_j(K[舰种_j] * 贡献_j)
```

- `船等价效率_i` = 吃船比例 = 对每艘敌舰累加（你对它造成的伤害 / 它的最大血量）。
- 均分地板 `a ≈ 0.48-0.50`，点亮权重 `lambda ≈ 1.2-1.9`。
- 舰种系数（CL/CA = 1.00 基准，三档拟合稳定）：
  - CL/CA 1.00，DD 0.83，BB 0.95，CV 0.43，SS 1.40。
  - SS 相对 DD ≈ 1.67，贴近社区 1.75。
- 拟合 R² ≈ 0.91-0.93，跨 2060 局（新 317 / 老 1743）验证通过。

### 3.4 潜艇 1.75 与随机性

- 视频的 1.75 是相对驱逐的系数，实测 ≈1.72，方向正确。
- 视频的纯比例公式 `x = 1.75y/(1+0.75y)` 忽略均分地板，老剧情会高估，新剧情表现尚可。
- 新剧情地图随机性更强，削弱潜艇背板能力：潜艇效率占比从老剧情 12.6% 降到新剧情 8.6%，伤害 17 万降到 11 万。这只影响"贡献量"，不影响 K[SS]（1.38-1.42 稳定）。

### 3.5 总经验池公式

```
team_raw ~ base[scenario] * (1.09 ^ stars) * (win ? 1 : 0.5)
```

- 池子是客观目标导向，不是队伍伤害导向：场景固定效应 + 星级 + 胜负 + 次要任务解释 R²=0.96，加入队伍效率/伤害只提升到 0.97。
- "星星"（0-5）= 次要任务完成度的封顶评级；部分地图次要任务可到 6-7 个，但星级封顶 5。所以池子公式只用星星，不再单列次要任务。
- 每颗星约 +9%；败局池子约为胜局的 0.5 倍；队伍效率每船等价约 +0.3%（可忽略）；每名挂机/暴毙玩家约 -3%。
- `base[scenario]` 是地图专属基线，约 7000-13000（Flagships/Random 等高难变体更高）。

## 4. 下一步（按优先级）

1. **（已完成初版，见 3.5）**总经验池公式。剩余可做：拆解败局/超时等 `finish_type` 的独立惩罚。
2. **把 XP 模型反哺 PR 公式（目标 1）**。用舰种系数修正"该船期望经验"，或把"场均经验"反解成"场均效率"再评分，提高排名/经验预测精度。
3. **把效率提取并入 rep 解析 skill（目标 2）**。更新 `skills/wows-replay-parser/SKILL.md` 和脚本。
4. 可选：给舰种系数 K 算置信区间；清理 `docs/WOWS_OPERATIONS_STATS_PLAN.md` 8.6 节过期的账号级示例（应改为船级/uomouse 示例）。

## 5. 关键产物索引

- 强度表拟合：`scripts/fit_ship_strength.py`，输出 `output/ship_strength_full.json`
- PR 验证：`scripts/verify_pr_formula.py`、`scripts/verify_rank.py`、`scripts/verify_aug.py`
- rep 解析 skill：`skills/wows-replay-parser/SKILL.md`、`scripts/extract_ops_replays.py`、`scripts/player_report.py`
- 效率提取：`scripts/extract_ops_efficiency.py`
- 舰种系数拟合：`scripts/fit_class_efficiency.py`
- 潜艇随机性检查：`scripts/check_sub_randomness.py`
- PVE 常量补齐：`scripts/fetch_pve_constants.py`
- 报告：`output/ops_xp_formula.md`、`output/ops_xp_validation.md`、`output/class_efficiency_fit.json`
- 数据：`cache/ship_strength_cache.json`、`ops_efficiency.jsonl`（本地 465 局）、`ops_efficiency_pve.jsonl`（抓取 1803 局）、`replays.db`

## 6. 分主题报告（每主题三版本：player / expert / ai）

- 目标 2 rep 解析 skill：
  - `output/report_02_rep_parser.player.md`
  - `output/report_02_rep_parser.expert.md`
  - `output/report_02_rep_parser.ai.md`
- 目标 3+5 经验分配 + 舰种系数：
  - `output/report_0305_xp_allocation.player.md`
  - `output/report_0305_xp_allocation.expert.md`
  - `output/report_0305_xp_allocation.ai.md`
- 目标 4 总经验池：
  - `output/report_04_xp_pool.player.md`
  - `output/report_04_xp_pool.expert.md`
  - `output/report_04_xp_pool.ai.md`
  - 基础池子全表：`output/pool_table.json`（生成脚本 `scripts/gen_pool_table.py`）
- 剧情名 + 分房映射：`output/ops_name_table.json`（生成脚本 `scripts/gen_ops_name_table.py`）
- 新剧情映射校验（敌方 bot 阵容）：`scripts/check_ww2_bots.py`
