# 行动模式样本分析：初步结论

> 状态：初步拟合（小样本）
> 数据截止：2026-08-24
> 分析脚本：`scripts/analyze_ops_samples.py`

## 1. 数据

把 `ops_samples.jsonl`（开局前 `oper_solo` 服务器快照）和
`ops_results.jsonl`（本局结果）按 `(arena_id, account_id)` 关联：

- 有效样本：**72 行**
- 有效场次：**11 场**（每局至少有 3 个可排名玩家）

样本还很小，结论是方向性的，后续样本量上来后需要重新拟合。

## 2. 核心结论

**当前船的历史场均经验（`ship_avg_xp`）是最强的单一预测特征**，明显强于账号
场均经验、胜率和五星率。

单特征线性回归（R²）：

- 预测本局经验 `raw_xp`：`ship_avg_xp` 单独 R² = **0.435**
- 预测本局伤害 `damage`：`ship_avg_xp` 单独 R² = **0.341**

关键相关性（Pearson r）：

| 特征 -> 本局经验 | r | 特征 -> 本局伤害 | r |
|---|---|---|---|
| ship_avg_xp（当前船场均经验） | 0.659 | ship_avg_xp | 0.584 |
| account_avg_xp（账号场均经验） | 0.549 | account_avg_xp | 0.369 |
| account_win_rate（账号胜率） | 0.449 | account_win_rate | 0.251 |
| account_five_star（账号五星率） | 0.423 | account_five_star | 0.237 |
| account_battles（总场次） | ≈ -0.05 | account_battles | ≈ 0.00 |

把标签换成“局内 z-score”（消掉每局经验池/伤害池的差异）后，`ship_avg_xp` 对
`raw_xp_z` / `damage_z` 的相关性分别是 **0.645 / 0.640**。

## 3. 排名效果（更贴近“判断队友强弱”的目标）

每局内部用 `ship_avg_xp` 排序，看它能不能排对：

- 预测“本局经验第一”命中率：11 局命中 **7 局（64%）**
- 预测“本局伤害第一”命中率：11 局命中 **8 局（73%）**
- 局内排序 Spearman 秩相关：经验 **0.638**，伤害 **0.686**

## 4. 解读

1. `ship_avg_xp` 强于 `account_avg_xp`，因为当前船场均经验天然做了“同一条船、
   同 tier”的归一化，正好解决低级船/高级船经验总池不同的问题。
2. 胜率和五星率偏弱，符合预期：行动模式 7 人共享胜负和星数，团队稀释后对个人
   能力的区分度低。
3. 总场次几乎没有预测力，玩得多不等于玩得好。
4. 多特征回归相比单用 `ship_avg_xp` 提升有限；预测伤害时加入 `account_avg_xp`
   和 `ship_win_rate` 后 R² 从 0.341 提升到约 0.467。

## 5. 后续方向

- 量化评分的主干应该是 **per-ship 场均经验归一化**（对应 wows-numbers 的
  per-ship expected 思路），胜率/五星率作辅助或低权重。
- 攒到一个月样本（约 300 场）后重新拟合，参数会更稳定。
- 重跑分析：`python scripts/analyze_ops_samples.py`（默认读取 Windows 应用数据
  目录下的两个 log，也支持显式传入两个文件路径）。
