# WoWs Toolkit / 战舰世界工具集

战舰世界游戏数据、replay 与资源解析的单仓工具集。
A monorepo of tools for interacting with World of Warships game data, replays, and assets.

> 本分支（`codex/local-changes`）在 upstream 基础上增加了操作剧本经验分析模块。
> 上游项目：https://github.com/landaire/wows-toolkit

---

## 操作剧本经验分析（本分支新增）

利用 2060 局 replay 数据，对 WG 经验分配公式进行逆向拟合。

### 核心文档

| 文档 | 说明 |
|------|------|
| [docs/Q6_CLASS_K_ANALYSIS.md](docs/Q6_CLASS_K_ANALYSIS.md) | 舰种系数 K 的分解——伤害类型、集中度、增援 |
| [docs/reinforcement-damage-analysis.md](docs/reinforcement-damage-analysis.md) | 增援伤害与经验回报验证 |
| [docs/WOWS_OPERATIONS_ANALYSIS.md](docs/WOWS_OPERATIONS_ANALYSIS.md) | 样本分析初步结论 |
| [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) | 项目上下文与手记 |

### 设计文档

| 文档 | 说明 |
|------|------|
| [docs/WOWS_OPERATIONS_STATS_PLAN.md](docs/WOWS_OPERATIONS_STATS_PLAN.md) | 玩家评分方案 |
| [docs/WOWS_OPERATIONS_DEV_PLAN.md](docs/WOWS_OPERATIONS_DEV_PLAN.md) | 开发计划 |
| [docs/WOWS_OPERATIONS_SAMPLE_COLLECTOR.md](docs/WOWS_OPERATIONS_SAMPLE_COLLECTOR.md) | 样本采集器设计 |
| [docs/WOWS_WG_API_REFERENCE.md](docs/WOWS_WG_API_REFERENCE.md) | WG API 参考 |

### 分析脚本

| 脚本 | 用途 | 关联文档 |
|------|------|----------|
| [scripts/extract_ops_replays.py](scripts/extract_ops_replays.py) | replay 解析库（公共依赖） | 所有分析 |
| [scripts/extract_ops_efficiency.py](scripts/extract_ops_efficiency.py) | 提取 ship_eff 数据 | → `ops_efficiency_full.jsonl` |
| [scripts/analyze_ops_efficiency.py](scripts/analyze_ops_efficiency.py) | 经验分配回归（主入口） | Q6 |
| [scripts/analyze_damage_types.py](scripts/analyze_damage_types.py) | 分伤害类型回归 | Q6 |
| [scripts/concentration_run.py](scripts/concentration_run.py) | 伤害集中度 HHI 分析 | Q6 |
| [scripts/analyze_reinforcement7.py](scripts/analyze_reinforcement7.py) | 增援伤害分析（最终版） | 增援 |
| [scripts/analyze_ops_samples.py](scripts/analyze_ops_samples.py) | 船均经验预测 | 样本分析 |
| [scripts/fit_class_efficiency.py](scripts/fit_class_efficiency.py) | 舰种效率拟合 | Q6 |
| [scripts/fit_xp_pool.py](scripts/fit_xp_pool.py) | 经验池拟合 | — |
| [scripts/fit_ship_strength.py](scripts/fit_ship_strength.py) | 单船强度评估 | 单船强度 |
| [scripts/ci_allocation.py](scripts/ci_allocation.py) | 分配模型置信区间 | — |
| [scripts/ci_pool.py](scripts/ci_pool.py) | 经验池置信区间 | — |
| [scripts/plot_survival.py](scripts/plot_survival.py) | 存活率图表 | 存活率 |
| [scripts/plot_survival_rate_by_bracket.py](scripts/plot_survival_rate_by_bracket.py) | 分档位存活率 | 存活率 |

### 数据集

| 文件 | 说明 |
|------|------|
| `ops_efficiency_full.jsonl` | 2060 局完整数据集（主数据源） |
| `ships_cache.json` | 舰船信息缓存 |
| `constants_cache/` | replay 常量定义 |
| [output/damage_type_analysis.jsonl](output/damage_type_analysis.jsonl) | 伤害类型拆分中间数据 |
| [output/damage_type_results.json](output/damage_type_results.json) | 伤害类型回归结果 |

### 报告

| 文件 | 说明 |
|------|------|
| [output/nga_publish/](output/nga_publish/) | NGA 论坛发布帖（01 主帖 ~ 05 附录） |
| [output/ops_xp_formula.md](output/ops_xp_formula.md) | 经验公式 |
| [output/ops_xp_pool.md](output/ops_xp_pool.md) | 经验池 |
| [output/ops_xp_validation.md](output/ops_xp_validation.md) | 经验公式验证 |
| [output/WOWS_OPERATIONS_INTERIM.md](output/WOWS_OPERATIONS_INTERIM.md) | 中期报告 |
| [output/ship_strength.md](output/ship_strength.md) | 单船强度 |
| [output/ship_strength_full.md](output/ship_strength_full.md) | 单船强度（完整版） |
| [output/survival_report.md](output/survival_report.md) | 存活率报告 |
| [output/report_nga_player.md](output/report_nga_player.md) | 玩家向报告 |
| [output/report_nga_expert.md](output/report_nga_expert.md) | 专家向报告 |

### 技能

| 技能 | 说明 |
|------|------|
| [skills/wows-replay-parser/](skills/wows-replay-parser/) | replay 解析 |
| [skills/wows-scoreboard-extract/](skills/wows-scoreboard-extract/) | 战绩截图 OCR 提取 |
| [wows-scoreboard-extract/battle_results/](wows-scoreboard-extract/battle_results/) | 社区战绩截图（新数据源） |

---

## 上游项目 / Upstream

<p>
  <img src="assets/replay_inspector.png" alt="Replay Inspector" width="800">
</p>
<p>
  <img src="assets/armor_viewer.png" alt="Armor Viewer" width="800">
</p>

### Crates / 子包

| Crate | 说明 | CLI 二进制 |
|-------|------|-----------|
| [`wows-toolkit`](crates/wows-toolkit) | GUI 应用：replay 浏览、资源提取、装甲查看 | `wows_toolkit` |
| [`wowsunpack`](crates/wowsunpack) | 游戏资源解包（IDX/PKG、GameParams） | `wowsunpack` |
| [`wows-replays`](crates/wows-replays) | replay 解析核心库 | — |
| [`minimap-renderer`](crates/minimap-renderer) | 小地图渲染（图片/视频） | `minimap_renderer` |
| [`replayshark`](crates/replayshark) | replay 导出与分析 CLI | `replayshark` |

### 文档 / Documentation

逆向笔记与格式规范：

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 架构
- [docs/BALLISTICS.md](docs/BALLISTICS.md) — 弹道、穿透、溅射
- [docs/MODELS.md](docs/MODELS.md) — `.geometry` 格式
- [docs/FIRE_CHANCE.md](docs/FIRE_CHANCE.md) — 点火概率
- [docs/BIGWORLD_PROTOCOL.md](docs/BIGWORLD_PROTOCOL.md) — BigWorld 协议
- [docs/RENDERER_SESSIONS.md](docs/RENDERER_SESSIONS.md) — 渲染会话
- [docs/TEAM_ADVANTAGE_SCORING.md](docs/TEAM_ADVANTAGE_SCORING.md) — 团队优势评分
- [docs/vortex_api_postman_reference.md](docs/vortex_api_postman_reference.md) — Vortex API
- [docs/format_templates/](docs/format_templates/) — 010 Editor 二进制模板

### 社区 / Community

有问题或想讨论功能，欢迎在 GitHub 开 issue，或加入 [项目网站](https://landaire.github.io/wows-toolkit/) 上的 Discord。

### 预编译 / Pre-Built

Windows 预编译包：https://github.com/landaire/wows-toolkit/releases/latest
下载 `wows-toolkit_v(VERSION)_x86_64-pc-windows-gnu.zip`，解压即用。其他平台需自行编译。

### 使用 / Usage

1. 启动应用
2. 在设置中指定战舰世界目录（默认 `C:\Games\World_of_Warships`）
3. 使用各项功能

本工具不是外挂，不修改游戏文件。它被动读取游戏资源用于 replay 解析。

### 功能 / Features

- 读取 replay 并显示伤害、存活时间、点亮伤害、潜在伤害等
- 点击玩家行的"Actions"按钮可在浏览器中查看配装
- 浏览和提取打包的游戏文件
- 自动将**配装**（非原始 replay）发送至 shipbuilds.com 用于配装统计（仅限随机和排位，可在设置中关闭）

### 开发者 / For Developers

#### Cargo 构建

```bash
rustup update
cargo run --release -p wows_toolkit

# CLI 工具
cargo build --release -p wowsunpack
cargo build --release -p wows_minimap_renderer --features bin
cargo build --release -p replayshark
```

Linux 依赖：`sudo apt-get install libxcb-render0-dev libxcb-shape0-dev libxcb-xfixes0-dev libxkbcommon-dev libssl-dev libgtk-3-dev`

Fedora：`dnf install clang clang-devel clang-tools-extra libxkbcommon-devel pkg-config openssl-devel libxcb-devel gtk3-devel atk fontconfig-devel`

#### NASM（可选）

minimap renderer 的 AV1 编码器（rav1e）在启用 `cpu-av1-asm` feature 时需要 NASM 以获得 ~3x 性能提升。

| 需求 | 操作 |
|------|------|
| 默认构建，完整 AV1 性能 | 安装 NASM |
| 默认构建，无 NASM | `--no-default-features --features bin,vulkan,videotoolbox,cpu,cpu-av1,arc` |
| 跳过 AV1 | `--no-default-features --features bin,vulkan,cpu,arc` |

安装 NASM：Windows `winget install -e --id NASM.NASM`，Linux `sudo apt-get install nasm`，macOS `brew install nasm`

#### Buck2 构建

```bash
./setup.sh     # macOS/Linux (需要 nix)
.\setup.ps1    # Windows (管理员权限)

buck2 build //:wows_toolkit
buck2 build -c native_build.mode=release //:wows_toolkit
```

#### Nix

```bash
nix develop
nix build .#wowsunpack
nix build .#minimap-renderer
nix build .#replayshark
```
