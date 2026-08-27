# 剧情（Operations）数据分析 · 中期结果（可发布版）

> **2026-08-27 审计措辞修正：** 舰种系数 K 应理解为"经验性舰种相对贡献权重"，不应称为 WG 内部固定变量。
> **证据层级：** 一级（高可信）——XP pool 二层结构、target-HP normalization、舰种 multiplier 存在性、约 50% 均分属性。二级（较高可信）——SS 相对 DD 约 1.68、CV 约 0.43、败局约 x0.44、每星约 +9%。三级（探索性）——HHI 解释 DD 残余系数的约 47%、damage type 效率差异（DOT 方向分数据源）。

> 更新 2026-08-26。主线「剧情 PR 公式」已暂停；本报告冻结并发布其余四点结论。
> 口径约定：经验一律用基础经验（`raw_exp`，不含高账 1.65 倍与首胜加成）。
> 分析数据：本地回放 + 回放分享站抓取，按 `arena_id + account_id` 去重后 2060 局 / 14420 人。

## 0. 结论速览（TL;DR）

1. 单局经验分配 = 均分地板 + 舰种加权的「吃船效率」，拟合 R2 约 0.91。
2. 舰种系数 K（经验性舰种相对贡献权重，CL/CA = 1.00 基准，95%CI）：DD 0.83、CL/CA 1.00、BB 0.95、CV 0.43、SS 1.40。
3. 社区「潜艇 1.75x」是「相对 DD 的效率权重」：实测 SS/DD = 1.68 [1.58, 1.78]，包含 1.75，结论成立；「同伤害」口径下潜艇只多约 +10%，是两个不同问题，二者不矛盾。
4. 总经验池是目标导向（R2 约 0.96）：每颗星 +9%，败局约 x0.44，常态场景基线约 7500-10000（旗舰限时更高，另计）。
5. `wows-replay-parser` skill 已并入「吃船效率」提取脚本与文档。
6. 数据局限：抓取回放赢局偏多（仅 151 败局），且无超时败局样本，败局惩罚无法按结束方式再细分。

---

## 1. 经验分配模型（目标 3「CV/SS 系数」+ 目标 5「效率分配」）

### 1.1 模型

对一局 n 名玩家：

```
contrib_i = 吃船效率_i + lambda * (点亮伤害_i / 100000)
XP_share_i = a / n + (1-a) * K[class_i] * contrib_i / sum_j(K[class_j] * contrib_j)
base_XP_i = XP_share_i * team_base_XP
```

- 吃船效率 = 对每艘敌舰累加 (你对其伤害 / 其最大血量)；击沉船合计约 1，存活船按比例计。
- `a` 是「均分地板」：约一半经验按人头平分，另一半按加权效率分。
- `K[class]` 是舰种在效率这一项上的权重，CL/CA 基准 1.00。

### 1.2 最终系数（含 95% 置信区间）

| 地域 | n 局 | a | lambda | R2 | DD | CL/CA | BB | CV | SS |
|---|---|---|---|---|---|---|---|---|---|
| 新剧情 only | 317 | 0.48 | 1.9 | 0.922 | 0.811 | 1.000 | 0.963 | 0.385 | 1.379 |
| 老剧情 only | 1743 | 0.50 | 1.2 | 0.906 | 0.834 | 1.000 | 0.951 | 0.444 | 1.415 |
| 合成 | 2060 | 0.50 | 1.2 | 0.908 | 0.830 | 1.000 | 0.953 | 0.432 | 1.395 |

合成口径 95% 置信区间（match 聚类 bootstrap，500 次）：

| 舰种 | K | 95% CI |
|---|---|---|
| DD | 0.830 | [0.813, 0.844] |
| CL/CA | 1.000 | 基准 |
| BB | 0.953 | [0.944, 0.961] |
| CV | 0.432 | [0.407, 0.462] |
| SS | 1.395 | [1.332, 1.449] |

### 1.3 潜艇 1.75x：到底成不成立

两个数字不矛盾，因为它们问的不是同一件事：

- 社区说法是把潜艇「效率」在分配里额外加权，且以 DD 为基准。
  实测 **SS/DD = 1.395 / 0.830 = 1.68，CI [1.58, 1.78]**，包含 1.75。**结论成立**。
- 早期本地 465 局分析的「SS 只多 +10%」用的是「相同**伤害**」配对，属于原始伤害口径；
  潜艇效率与伤害不成正比，所以这一口径低估了它的真实权重。
- 直接在**相同吃船效率**下配对（非参数）：潜艇的楼层外经验份额约是水面舰的
  1.40-1.48 倍（合成中位数 1.403，n=300），与 K[SS]/K[水面均值] 一致。

因此发布口径统一为：**潜艇的相对 DD 效率加成约 1.68（CI 1.58-1.78），社区 1.75x 在该区间内**。

---

## 2. 总经验池（目标 4）

### 2.1 模型

```
team_raw ~ base[scenario] * 1.09^stars * (win ? 1 : 0.44)
```

- 场景固定效应 + 星级 + 胜负即解释 R2 = 0.9595；加入队伍效率/伤害仅增至 0.9709。
- 每星 +9%（95%CI x1.086-1.095）。
- 败局约为胜局的 x0.44（95%CI x0.433-0.452），不是此前文稿里的 x0.5。
- 场景基线 `base[scenario]`：常态约 7500-10000；旗舰(Flagships)为限时模式，约 11800-14006，不计入常态。

### 2.2 系数置信区间（match 聚类 bootstrap，500 次）

| 项 | coef | 95% CI | 倍数 |
|---|---|---|---|
| stars | 0.0865 | [0.0829, 0.0903] | 每星 x1.090 |
| secondary_completed | 0.0226 | [0.0185, 0.0264] | 与星级冗余，弃用 |
| is_win | 0.8178 | [0.7947, 0.8367] | 胜 vs 负 x2.263；负 vs 胜 x0.442 |
| team_eff（每船等效） | 0.0031 | - | x1.003，可忽略 |
| n_inactive（挂机/暴毙合并口径） | -0.0283 | - | 每人 x0.972 |

挂机与暴毙应拆开：replay 看不到队友的服务器 `is_afk`/`is_ineffective` 标志，只能行为近似。零伤害+零击杀+零点亮且早死（挂机/逃兵）约让池子 ×0.927（-7.5%）；有少量输出但早死（暴毙）约 ×0.970（-3%）。样本里真正零贡献局仅 5/2060，故“挂机扣 1/7（-14.3%）”未证实。见 `scripts/analyze_afk_death.py`。

### 2.3 finish_type 无法再细分的说明

样本里 `finish_type` 只有两类，且与胜负完全共线：

| finish_type | is_win | n |
|---|---|---|
| PROTECTED_TARGETS_DESTROYED | 胜 | 1907 |
| BASE（基地/目标被毁） | 负 | 151 |

没有 TIMEOUT（13）/ SCORE_ON_TIMEOUT（18）样本，抓取源又偏赢局（151/2058 败局）。
因此「败局粉饰数据按超时 vs 被团灭分开」在当前数据下不可做；x0.44 是败局整体惩罚，
待补充足量超时败局后再拆。

---

## 3. rep 解析 skill（目标 2）

`skills/wows-replay-parser` 已并入「吃船效率」提取：

- 新增 `skills/wows-replay-parser/scripts/extract_ops_efficiency.py`（与仓库根 `scripts/extract_ops_efficiency.py` 同源）。
- `SKILL.md` 增加一节，说明如何输出 `efficiency` / `sum_dmg_check` / `n_victims` 及本局 `team_raw` / `team_eff` 等聚合字段。
- 运行：`python scripts/extract_ops_efficiency.py "D:\replays" --out ops_efficiency.jsonl --constants-dir constants_cache --ship-cache ships_cache.json --workers 8`。

该脚本是 PR / 经验分配分析的数据源头，现可在 skill 语境下独立复现。

---

## 4. 数据与口径

- 来源A（本地个人）：458 局（`D:\World_of_Warships\replays`），用于最初的效率描述与随机性检查。
- 来源B（抓取）：replayswows.com 分享站 PVE 回放，与本地合并去重后 2060 局。
- Q6 伤害类型/HHI 复核：直接合并个人 448 局 + 抓取 1620 局，去重后 2068 局 / 14476 行，见 `docs/Q6_CLASS_K_ANALYSIS.md`。
- 经验口径：`raw_exp`（回放 `init_economics.exp`），不含高账 1.65x 与首胜；WG API `oper_solo.xp` 含高账，需 /1.65 对齐。
- 舰种数（合成）：BB 6217、CL/CA 5726、DD 1845、CV 260、SS 372。

## 5. 复现

```text
python scripts/ci_allocation.py    # 分配模型 K + bootstrap CI + 匹配效率诊断 -> output/allocation_ci.json
python scripts/ci_pool.py          # 经验池 finish_type 交叉表 + bootstrap CI       -> output/pool_fit.json
python scripts/fit_class_efficiency.py --scope all  # 原网格搜索基线
python scripts/fit_xp_pool.py      # 原池子描述基线
```

依赖仅 numpy + 标准库（无需 scipy）。

## 6. 已暂停：剧情 PR 公式（目标 1）

主线 PR 公式本次不做推进，仍停留在初版 `Rating = 700 * (该船场均经验 / 该船期望经验)`。
本报告产出的 K 系数与经验池公式是下一步把 XP 模型反哺 PR 的输入；反哺工作留待后续，不阻塞本次中期交付。

---

## 关键产物索引

- 本报告：`output/WOWS_OPERATIONS_INTERIM.md`
- 分配模型 CI 结果：`output/allocation_ci.json`（生成 `scripts/ci_allocation.py`）
- 经验池 CI 结果：`output/pool_fit.json`（生成 `scripts/ci_pool.py`）
- 舰种系数基线：`output/class_efficiency_fit.json`（`scripts/fit_class_efficiency.py`）
- 经验池/基础池子表：`output/ops_xp_pool.md`、`output/pool_table.json`
