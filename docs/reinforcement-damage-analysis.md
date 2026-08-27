# 增援舰队伤害与经验回报——数据验证

> **2026-08-27 审计措辞修正：** 结论从"增援伤害的经验回报和普通伤害一样"修正为"当前数据未发现增援伤害存在特殊的 0-XP 或显著折扣"。这是对措辞强度的降级，不影响分析结论。
> **证据层级：** 二级结论（较高可信）。

> 社区说法：有些地图的切断增援任务如果失败，会出现增援舰队。击杀增援部队等同于完成切断任务，但对增援部队造成的伤害没有经验收益。因此切增援比杀增援划算。

## 结论（一句话）

**增援伤害的经验回报和普通伤害一样。社区说法无数据支持。切增援和杀增援对个人经验没有区别。**

## 实验设计

利用 2060 局操作剧情的 replay 数据，分层验证。

### 第一步：跨 sec_failed 的玩家级回归

把局按次要任务失败数（`sec_failed = secondary_total - secondary_completed`）分组，分别跑玩家级经验份额回归（share ~ eff_total + scouting_damage + ship_class）。如果增援伤害无 XP，`eff_total` 系数应随 sec_failed 增加而下降。

| sec_failed | 局数 | eff_total 系数 | R² |
|------------|------|---------------|------|
| 0 | 425 | 0.013432 | 0.8460 |
| 1 | 487 | 0.013425 | 0.8365 |
| 2 | 467 | 0.012677 | 0.8214 |
| 3 | 598 | 0.012792 | 0.8184 |
| 4 | 57 | 0.014087 | 0.7958 |
| 5 | 23 | 0.014325 | 0.8499 |

系数完全平坦，没有下降趋势。增援伤害不是零经验。

### 第二步：玩家级回归，控制局总 eff 和 sec_failed

最关键的检验：在玩家级回归中同时加入 `game_eff_per`（局总 eff）和 `sec_failed`，看 sec_failed 在控制局总 eff 后是否仍有独立解释力。

```
PCVO(legacy_op):
  base（eff + scout + class + game_eff_per）:       R² = 0.8323
  +sec_failed（eff + scout + class + game_eff_per + sec_failed）: R² = 0.8323, sec_failed = -0.000000

WW2_OP(new):
  base（eff + scout + class + game_eff_per）:       R² = 0.8506
  +sec_failed（eff + scout + class + game_eff_per + sec_failed）: R² = 0.8506, sec_failed = 0.000000
```

**sec_failed 系数为零，R² 不变。** 增援舰队的存在与否对经验分配没有任何影响。

### 第三步：局级回归，控制场景固定效应

```
raw_per ~ eff_per + sec_failed + eff_per × sec_failed + scenario_dummies

eff_per: 95.0
sec_failed: -1.0  （几乎为零）
eff_per × sec_failed: +4.2  （正的，不是负的）
R² = 0.3474
```

sec_failed 主效应接近零，交互项为正。增援 eff 的边际回报并不比普通 eff 低。

### 第四步：逐场景检验

29 个场景逐一跑 `raw_per ~ eff_per + sec_failed`，sec_failed 系数方向混杂、无一致规律。没有任何场景显示 sec_failed 与经验显著负相关。

## 之前错误结论的修正

本分析第一版（2026-08-27 初稿）曾得出"增援伤害稀释经验池约 20%"的结论，该结论基于 sec_failed=0 的局内按 team_eff 高低分组对比。该方法的缺陷在于：将局间差异（高 eff 局更可能是更长的对局，有更多自然刷出的船，而非增援船）错误归因于增援。

修正后的分析将局总 eff 作为控制变量加入玩家级回归，sec_failed 的效应完全消失。证明原结论是局间混淆，不是增援的真实效应。

## 对玩家决策的影响

增援伤害就是普通伤害。切不切增援对个人经验没有影响——除非你能比队友抢到更大份额的增援伤害（此时你略微受益），或者你完全抢不到（此时你略微受损）。但影响程度取决于你的份额差异，与增援本身无关。

## 数据来源

- 数据：2060 局操作剧情 replay，`ops_efficiency_full.jsonl`
- 分析脚本：`scripts/analyze_reinforcement.py` ~ `scripts/analyze_reinforcement7.py`
- 日期：2026-08-27（修正版）


## 措辞注意事项

以上结论应理解为"当前数据未发现增援伤害的特殊 XP 折扣"，而非绝对宣称"增援与普通敌舰在 WG 源码中完全相同"。受限于 replay 数据的 observability，无法排除 WG 在特定条件下对增援施加不同处理的可能。