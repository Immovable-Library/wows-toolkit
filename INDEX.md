# 项目索引

## 操作剧本经验分析（核心工作）

### 主文档

| 文档 | 说明 | 关联脚本 |
|------|------|----------|
| [docs/Q6_CLASS_K_ANALYSIS.md](docs/Q6_CLASS_K_ANALYSIS.md) | Q6：舰种系数 K 的分解——伤害类型、集中度、增援 | `scripts/analyze_damage_types.py` · `scripts/concentration_run.py` · `scripts/analyze_reinforcement7.py` |
| [docs/reinforcement-damage-analysis.md](docs/reinforcement-damage-analysis.md) | 增援伤害与经验回报验证（修正版） | `scripts/analyze_reinforcement.py` ~ `scripts/analyze_reinforcement7.py` |
| [docs/WOWS_OPERATIONS_ANALYSIS.md](docs/WOWS_OPERATIONS_ANALYSIS.md) | 行动模式样本分析初步结论 | `scripts/analyze_ops_samples.py` |
| [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) | 项目上下文与手记 | — |

### 设计文档

| 文档 | 说明 |
|------|------|
| [docs/WOWS_OPERATIONS_STATS_PLAN.md](docs/WOWS_OPERATIONS_STATS_PLAN.md) | 玩家评分方案设计 |
| [docs/WOWS_OPERATIONS_DEV_PLAN.md](docs/WOWS_OPERATIONS_DEV_PLAN.md) | 开发计划 |
| [docs/WOWS_OPERATIONS_SAMPLE_COLLECTOR.md](docs/WOWS_OPERATIONS_SAMPLE_COLLECTOR.md) | 样本采集器设计 |
| [docs/WOWS_WG_API_REFERENCE.md](docs/WOWS_WG_API_REFERENCE.md) | WG API 参考 |

### 核心脚本

| 脚本 | 用途 | 关联文档 |
|------|------|----------|
| `scripts/extract_ops_replays.py` | replay 解析库（公共依赖） | 所有分析脚本 |
| `scripts/extract_ops_efficiency.py` | 从 replay 提取 ship_eff 数据 | → `ops_efficiency_full.jsonl` |
| `scripts/analyze_ops_efficiency.py` | 经验分配回归（主入口） | [docs/Q6_CLASS_K_ANALYSIS.md](docs/Q6_CLASS_K_ANALYSIS.md) |
| `scripts/analyze_damage_types.py` | 分伤害类型回归 | [docs/Q6_CLASS_K_ANALYSIS.md](docs/Q6_CLASS_K_ANALYSIS.md) |
| `scripts/concentration_run.py` | 伤害集中度 HHI 分析 | [docs/Q6_CLASS_K_ANALYSIS.md](docs/Q6_CLASS_K_ANALYSIS.md) |
| `scripts/analyze_reinforcement7.py` | 增援伤害分析（最终版） | [docs/reinforcement-damage-analysis.md](docs/reinforcement-damage-analysis.md) |
| `scripts/analyze_reinforcement.py` ~ `analyze_reinforcement6.py` | 增援伤害分析（过程版本） | [docs/reinforcement-damage-analysis.md](docs/reinforcement-damage-analysis.md) |
| `scripts/analyze_ops_samples.py` | 样本分析（船均经验预测） | [docs/WOWS_OPERATIONS_ANALYSIS.md](docs/WOWS_OPERATIONS_ANALYSIS.md) |
| `scripts/fit_class_efficiency.py` | 舰种效率拟合 | [docs/Q6_CLASS_K_ANALYSIS.md](docs/Q6_CLASS_K_ANALYSIS.md) |
| `scripts/fit_xp_pool.py` | 经验池拟合 | — |
| `scripts/fit_ship_strength.py` | 单船强度评估 | [output/ship_strength.md](output/ship_strength.md) |
| `scripts/ci_allocation.py` | 分配模型置信区间 | — |
| `scripts/ci_pool.py` | 经验池置信区间 | — |
| `scripts/plot_survival.py` | 存活率图表 | [output/survival_report.md](output/survival_report.md) |
| `scripts/plot_survival_rate_by_bracket.py` | 分档位存活率 | [output/survival_report.md](output/survival_report.md) |

### 数据集

| 文件 | 说明 |
|------|------|
| `ops_efficiency_full.jsonl` | 2060 局操作剧本完整数据集（主要数据源） |
| `ships_cache.json` | 舰船信息缓存（类型、等级、名称） |
| `constants_cache/` | 各版本 replay 常量定义 |
| `output/damage_type_analysis.jsonl` | 伤害类型拆分中间数据 |
| `output/damage_type_results.json` | 伤害类型拆分回归结果 |

### 技能

| 技能 | 说明 |
|------|------|
| `skills/wows-replay-parser/` | replay 解析技能（提取 ship_eff、舰种、场景等） |
| `skills/wows-scoreboard-extract/` | 战绩截图 OCR 提取技能 |

---

## NGA 发布与报告

| 文件 | 说明 |
|------|------|
| [output/nga_publish/](output/nga_publish/) | NGA 论坛发布帖（01 主帖 ~ 05 附录） |
| [output/report_nga_player.md](output/report_nga_player.md) | 玩家向报告 |
| [output/report_nga_expert.md](output/report_nga_expert.md) | 专家向报告 |
| [output/report_02_rep_parser.*.md](output/) | 02 号报告：replay 解析（三版本） |
| [output/report_0305_xp_allocation.*.md](output/) | 03-05 号报告：经验分配（三版本） |
| [output/report_04_xp_pool.*.md](output/) | 04 号报告：经验池（三版本） |
| [output/report_pool_coef.md](output/report_pool_coef.md) | 经验池系数报告 |
| [output/WOWS_OPERATIONS_INTERIM.md](output/WOWS_OPERATIONS_INTERIM.md) | 中期报告 |
| [output/ops_xp_formula.md](output/ops_xp_formula.md) | 经验公式 |
| [output/ops_xp_pool.md](output/ops_xp_pool.md) | 经验池 |
| [output/ops_xp_validation.md](output/ops_xp_validation.md) | 经验公式验证 |
| [output/ops_enemy_mapping.md](output/ops_enemy_mapping.md) | 敌舰映射 |
| [output/ops_scenario_mapping_verified.md](output/ops_scenario_mapping_verified.md) | 场景映射验证 |
| [output/ship_strength.md](output/ship_strength.md) | 单船强度 |
| [output/ship_strength_full.md](output/ship_strength_full.md) | 单船强度（完整版） |
| [output/survival_report.md](output/survival_report.md) | 存活率报告 |

---

## 上游项目文档

| 文档 | 说明 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 项目架构 |
| [docs/MODELS.md](docs/MODELS.md) | 模型格式 |
| [docs/BALLISTICS.md](docs/BALLISTICS.md) | 弹道 |
| [docs/FIRE_CHANCE.md](docs/FIRE_CHANCE.md) | 点火概率 |
| [docs/BIGWORLD_PROTOCOL.md](docs/BIGWORLD_PROTOCOL.md) | BigWorld 协议 |
| [docs/RENDERER_SESSIONS.md](docs/RENDERER_SESSIONS.md) | 渲染会话 |
| [docs/TEAM_ADVANTAGE_SCORING.md](docs/TEAM_ADVANTAGE_SCORING.md) | 团队优势评分 |
| [docs/vortex_api_postman_reference.md](docs/vortex_api_postman_reference.md) | Vortex API 参考 |
| [docs/format_templates/](docs/format_templates/) | 二进制格式模板 |

---

## 其他

| 文件 | 说明 |
|------|------|
| `scripts/skill_grids.json` | 技能网格数据 |
| `scripts/skill_grids_extract.py` | 技能网格提取 |
| `wows-scoreboard-extract/battle_results/` | 社区战绩截图数据（新数据源） |
| `scripts/probe_noclose.ps1` | 探针脚本 |
| `scripts/sample_mem.ps1` | 内存采样 |
