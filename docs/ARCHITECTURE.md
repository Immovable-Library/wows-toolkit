# WoWs Toolkit 架构与技术栈学习笔记

> 本文件是仓库的本地学习/记忆笔记，用来快速恢复上下文，不是发布文档。
> 生成时间：2026-08-23。

## 1. 项目概览

WoWs Toolkit 是一个 Rust monorepo，用于读取、解析、渲染和分析《World of Warships》的游戏数据、回放文件与资源包。

核心能力：

- 解析 `.wowsreplay` 回放文件（解密、解压、按 BigWorld 协议逐包解码）。
- 读取游戏安装目录的 `IDX/PKG` 资源包，并抽象成虚拟文件系统。
- 解析 `GameParams.data` 中的船只、装备、消耗品、技能、武器等游戏参数。
- 以 ECS 重建一场战斗的状态，产出战绩、命中、起火、击杀、聊天、占点等派生数据。
- 生成小地图时间轴、图片帧和视频导出。
- 提供 egui 桌面 GUI、CLI 工具、WASM Web 客户端。
- 支持多人实时协作观看回放小地图与战术板。

仓库当前是 Cargo workspace，版本约为 `1.0.2-beta2`，edition 2024，rust-version 1.97。

## 2. 技术栈总览

### 语言与基础

| 领域 | 选型 |
| --- | --- |
| 语言 | Rust，edition 2024，rust 1.97 |
| 工作区 | Cargo workspace，resolver 3 |
| 构建 | Cargo 用于日常开发；Buck2 是 CI 和发布的权威构建 |
| 版本控制 | jj-colocated，使用 `jj` 而非 `git` |
| 平台 | Windows、Linux、macOS，另有 WASM Web 客户端 |
| 错误处理 | `thiserror` + `rootcause` |
| 日志 | `tracing` / `tracing-subscriber` |
| 序列化 | `serde`、`serde_json`、`ciborium`、`rkyv` |
| 解析 | `winnow`、`pickled`、`roxmltree`、`toml` |

### UI 与渲染

| 领域 | 选型 |
| --- | --- |
| GUI 框架 | `egui` / `eframe` 0.35 |
| 后端 | `wgpu` 29（不是 glow） |
| 布局 | `egui_dock`、`egui_taffy` |
| 表格/绘图 | `egui_table`、`egui_plot` |
| 富文本/图表 | `egui_commonmark`、`egui_ltreeview`、`egui_palette` |
| 图标 | `egui-phosphor` |
| 2D 位图 | `image`、`tiny-skia`、`resvg` |
| 视频编码 | `openh264`、`rav1e`、`gpu-video`、VideoToolbox |
| 3D 装甲查看 | `nalgebra` + 自研 `viewport_3d` |

### 领域与数据

| 领域 | 选型 |
| --- | --- |
| ECS 战斗世界 | `bevy_ecs` 0.18.1 |
| 游戏资源 VFS | `vfs`、`memmap2`、`flate2` |
| GameParams | `pickled`（Python pickle）、`winnow`、`serde_json` |
| 3D 模型 | `gltf`、`gltf-json`、`image_dds`、`meshopt-rs` |
| SQLite | `sqlx` 0.8 |
| 时间 | `jiff` |
| 压缩 | `flate2`（zlib）、`ruzstd` |

### 网络与协作

| 领域 | 选型 |
| --- | --- |
| P2P 协作 | `iroh` 1.x，QUIC + NAT 穿透 |
| HTTP | `reqwest`、`hyper`、`tower`、`tower-http` |
| GitHub API | `octocrab` |
| Twitch | `twitch_api` |
| 协作序列化 | `rkyv` + zlib 帧 |

## 3. 仓库目录

```text
crates/                 所有 Rust crate
docs/                   反向工程笔记、格式文档
scripts/                开发与发布脚本
build-support/          Buck2 构建支持、发布工具映射
toolchains/             固定工具链与 Windows 工具链配置
third-party/rust/       Buck2 第三方 crate 生成规则和 fixup
prelude/                Buck2 vendored prelude
tests/                  fixtures 等测试资产
assets/                 GUI 展示图片
site/                   项目站点
wix/                    Windows 安装器相关
game_versions.toml      已知游戏版本与 Steam depot manifest id
```

## 4. Crate 分层与职责

依赖方向大致是：底层纯类型/游戏数据 -> 解析 -> ECS/派生 -> 渲染/协议 -> GUI/CLI。

| Crate | 层级 | 职责 |
| --- | --- | --- |
| `wows-core` | 领域核心 | 轻量共享类型、ID newtype、单位 newtype、版本、Recognized 枚举 |
| `wowsunpack` | 游戏数据 | IDX/PKG VFS、GameParams、实体/RPC def、模型、装甲、弹道、导出 |
| `wows-replays` | 回放解析 | `.wowsreplay` 容器、Blowfish 解密、zlib、BigWorld 包解析、BattleController |
| `wows-battle-world` | 战斗状态 | bevy_ecs 实现，把解码后的包摄入为 ECS 世界，替换旧 BattleController |
| `wows-replay-insights` | 派生数据 | 战绩归一化、玩家 build、起火概率、个人评分、battle report |
| `minimap-renderer` | 渲染 | 小地图 DrawCommand、软件渲染、视频编码 |
| `wt-collab-protocol` | 协作协议 | 会话消息类型、rkyv 序列化、iroh token、结构校验 |
| `wt-collab-egui` | 协作 UI | 共享 egui 类型、变换、渲染、标注工具栏 |
| `wt-web` | Web 客户端 | WASM eframe 客户端、iroh 连接、资源加载 |
| `wt-translations` | 翻译 | 翻译 key、TextResolver trait、语言元数据 |
| `wows-toolkit-config` | 持久化 | SQLite schema、设置、回放索引、查询 |
| `wows-toolkit` | 桌面应用 | egui 应用、各 tab、后台任务、网络、装甲查看、协作宿主 |
| `replayshark` | CLI | 回放 dump/分析 CLI |
| `wows-data-mgr` | 数据管理 | 下载/注册游戏版本、Steam manifest、CAS dump |
| `wgcheck` | 独立解析 | WGCheck `.gch` 报告：DES + GZip + .NET BinaryFormatter |

## 5. 关键数据链路

### 5.1 回放解析链路

1. `wows-replays` 的 `ReplayFile` 读取容器。
2. 文件布局为 `magic | block_count | metadata block | encrypted packet stream`。
3. 元数据是 JSON，`ReplayMeta` 保存玩家、地图、版本、车辆等。
4. packet stream 使用固定 Blowfish key，ECB + previous-plaintext XOR 链解密。
5. 解密后再 zlib 解压，得到裸 BigWorld 包流。
6. `packet2` 按 `size | type | clock | payload` 逐包解析。
7. 包 ID 映射按版本门控，`MODERN_PACKET_LAYOUT_MIN_VERSION = 12.6.0`。
8. `analyzer::decoder::PacketDecoder` 把裸包转换为高层 `DecodedPacketPayload`。
9. `Analyzer` trait 定义 `process(packet)` 和 `finish()`。

旧实现是 `wows-replays` 内的 `analyzer::battle_controller::BattleController`；新实现是 `wows-battle-world`。

### 5.2 游戏资源链路

1. 游戏目录结构：
   - `bin/<build>/idx/*.idx`：索引。
   - `res_packages/*.pkg`：包体。
   - `content/GameParams.data`：游戏参数。
   - `content/assets.bin`：资源索引，叠加在 PKG VFS 上。
2. `wowsunpack::data::idx` 解析 IDX。
3. `IdxVfs` 用 `Prime` trait 解耦底层读取，支持内存 `BytesPkgSource` 与 `mmap`。
4. `game_data::build_game_vfs` 将 assets.bin 与 PKG VFS overlay。
5. `GameMetadataProvider` 从 GameParams pickle 中加载参数，并提供本地化、实体 spec 等。

### 5.3 战斗状态链路

1. `BattleWorld::new` 用回放元数据、资源 loader、常量构造 ECS world。
2. 一个 `PacketDecoder` 在整个回放生命周期复用。
3. `Analyzer::process` 每包：
   - 更新 `Clock`。
   - 可选清空当前帧 `ShotHitLog`。
   - `PacketDecoder::decode` 得到 `DecodedPacketPayload`。
   - 调用 `ingest::dispatch` 分发到对应模块。
4. ingest 模块按包类型拆分为：
   - `entities`：实体创建/离开/移除。
   - `positions`：位置、朝向、小地图更新。
   - `vehicles`：载具属性、炮塔、弹药。
   - `combat`：伤害、击杀、勋带。
   - `projectiles`：炮弹、鱼雷、命中。
   - `consumables`：消耗品。
   - `aviation`：飞机、巡逻队。
   - `zones`：占点、buff、天气区。
   - `hydrophone`：潜艇水听器。
   - `match_state`：比赛阶段、分数、结束。
   - `chat`：聊天。
5. ECS 中：
   - 组件描述每实体状态，如 `GameId`、`Transform3d`、`MinimapPlacement`、`VehicleState`、`Consumables`、`PlayerLink`。
   - 资源描述全局状态，如 `Clock`、`MatchState`、`TeamScores`、`DamageLedger`、`KillLog`、`EntityIndex`。
   - `EntityIndex`、`PlaneIndex`、`WardIndex` 提供 game id 到 ECS entity 的映射。
   - `ActiveShotOrder`、`ActiveTorpedoOrder`、`CapturePointOrder` 等维护顺序，不依赖 ECS 迭代顺序。
6. `view::QueryCache` 缓存读侧查询状态，减少每帧分配。
7. `BattleReport` 是最终只读战斗报告。

### 5.4 派生数据链路

`wows-replay-insights` 位于 `wows-replays`、`wowsunpack` 和 `wows-battle-world` 之上，提供：

- `build`：把玩家 state 解析为 `ResolvedBuild`，含消耗品、改装件、舰长技能。
- `battle_report`：生成 egui-free 的 `NormalizedBattleReport`。
- `fire_chance`：结合船体火区与 burn 历史计算有效起火概率。
- `personal_rating`：个人评分。

### 5.5 渲染链路

`minimap-renderer`：

1. 从 `BattleView` 读取战斗状态。
2. `MinimapRenderer` 把状态转换为高层 `DrawCommand`。
3. `DrawCommand` 已解析好颜色、透明度、坐标，渲染后端不需要重复游戏逻辑。
4. 后端实现 `RenderTarget`：
   - `ImageTarget`：软件位图渲染。
   - egui 后端：桌面 GUI 使用同一批 DrawCommand。
5. `VideoEncoder` 负责时间轴采样、帧编码、封装 MP4。
6. 编码后端：
   - GPU：Vulkan Video / gpu-video（Windows/Linux）、VideoToolbox（macOS）。
   - CPU：openh264、rav1e。

### 5.6 协作链路

`docs/RENDERER_SESSIONS.md` 详细描述：

- `iroh` 作为 QUIC + NAT 穿透传输。
- 拓扑为 mesh：host 作为初始 rendezvous 和身份来源，握手后所有 peer 直连。
- ALPN：`/wows-toolkit-collab/1` 或当前版本。
- 消息：`rkyv` 序列化，zlib 压缩，长度前缀帧。
- 权限在接收端本地执行；校验和权限是两层。
- host/co-host 发送权限、渲染选项、回放状态等 authority 消息。
- WASM 客户端只接收 `Frame`，使用相同的 `DrawCommand` 渲染，不解析本地回放。

## 6. 桌面应用架构

`wows-toolkit` 主 crate 组织：

- `main.rs`：启动、CLI、GPU 探测、渲染模式选择、加固策略、panic handler。
- `app.rs`：`WowsToolkitApp`，egui 顶层应用与 dock tab 分发。
- `tab_state.rs`：跨 tab 的共享状态、持久化状态、后台任务。
- `ui/`：
  - `replay_parser`：回放列表、行、排序、workspace。
  - `file_unpacker`：资源包浏览/解包。
  - `settings_tab`：设置。
  - `player_tracker`：玩家追踪。
  - `mod_manager`：mod 管理。
  - `search_tab` / `query_bar`：回放库查询。
  - `theme`：主题系统。
- `replay/`：
  - 回放渲染、时间轴、小地图视图、realtime armor viewer。
- `armor_viewer/`：装甲模型、弹道、穿透、splash。
- `viewport_3d/`：通用 3D 相机、拾取、gizmo。
- `collab/`：桌面协作宿主 peer task、session state。
- `task/`：后台任务，如扫描、下载、上传、网络、回放加载。
- `data/`：设置、回放索引、build data、session stats。
- `db/`：SQLite 读写和 RON 迁移。
- `gpu/`：GPU 探测与选择。
- `hardening/`：Windows 进程加固、模块列表、Code Integrity Guard。

主 tab：

```text
Unpacker
Replays(Live + directory workspaces)
Settings
PlayerTracker
ModManager
ArmorViewer
Stats
Search
```

## 7. 持久化

数据库：`wows_toolkit.db`，由 `wows-toolkit-config` 管理，使用 `sqlx` 嵌入式迁移。

主要表：

- `settings`：JSON key-value 设置。
- `session_stats`：每场战斗的会话统计。
- `sent_replays`：已发送回放去重。
- `chart_configs`：图表配置。
- `armor_viewer_defaults`：装甲查看器默认状态。
- `render_options`：渲染选项。
- `dock_layouts`：dock 布局。
- `mod_manager`：mod 管理器状态。
- `cap_layouts`：占点布局，rkyv blob。
- 回放索引：
  - `index_source`
  - `indexed_match`
  - `replay_record`
  - `indexed_vehicle`
- `twitch_observation`：Twitch 观测。
- `raw_upload_first_seen`：上传宽限窗口。

## 8. 游戏版本与数据管理

`wows-data-mgr` 负责：

- `download_repo`：从 `landaire/wows-replay-data` 下载游戏数据 dump。
- `manifest`：`game_versions.toml` 的 Steam depot manifest 解析。
- `registry`：本地版本注册表。
- `cas` / `cas_vfs`：内容寻址存储，跨版本共享内容对象。
- `dump` / `builds`：旧式 dump 与 CAS dump 兼容。
- `constants`：从 GitHub 拉取版本常量。

游戏数据测试可用 `WOWS_GAME_DATA` 环境变量或 `wows-data-mgr download --latest` 准备。

## 9. 值得注意的设计选择

### 9.1 强类型 newtype 与单位

仓库大量使用 newtype 区分容易混淆的值：

- `EntityId`、`AvatarId`、`PlayerId`、`AccountId`、`GameParamId`。
- `TeamId`、`ArenaId`、`ShotId`、`GunId`。
- `Meters`、`BigWorldDistance`、`WorldDistance`、`ShipModelDistance`、`Km`、`Millimeters`。
- `Degrees`、`Radians`。
- `Seconds`、`MetersPerSecond`。

单位换算尤其重要：

- GameParams 的 BigWorld 单位约 `1 unit = 30 m`。
- replay packet 的 world 单位约 `1 unit = 15 m`。
- ship model 单位约 `1 unit = 15 m`。

### 9.2 `Recognized<T, R>`

未知枚举值会保留 raw 值，而不是在解析时静默丢弃。例如新的 `GameMode`、`Ribbon`、`VisibilityFlags` unknown bits 都可暴露给调用者。

### 9.3 版本门控包布局

12.6.0 前后 BigWorld 包 ID 表不同，`PacketTypeId::from_raw_for_version` 显式处理。

### 9.4 sans-io 解析

`wows-replays` 和 `wowsunpack` 的纯解析路径不依赖文件系统，可编译到 wasm；VFS/内存映射由 feature 单独开启。

### 9.5 `arc` feature 统一智能指针

`wows-core`、`wowsunpack`、`wows-replays` 都通过 `arc` feature 切换 `Rc`/`Arc`，使共享数据既能单线程使用，也能在 GUI/线程中使用。

### 9.6 ECS 迁移策略

`wows-battle-world` 用 `bevy_ecs` 替代旧 `BattleController`。关键点：

- 不依赖 ECS archetype 迭代顺序，需要稳定的顺序时用显式 Vec 资源。
- `EntityIndex` 等资源负责外部 game id 到 ECS entity 的映射。
- 写侧 ingest 和读侧 `view::QueryCache` 分离。
- `PresenceLog` 用于保守地判断一个实体在某个时间窗口是否被客户端持续观测到，避免把未观测状态当作证据。

### 9.7 渲染后端抽象

`DrawCommand` 是渲染器和后端之间的稳定中间表示。同一套逻辑可以输出图片、GUI 画布和 WASM 协作帧。

### 9.8 内容寻址数据下载

`wows-data-mgr` 用 CAS 让相邻游戏版本共享相同内容对象，避免重复下载，并支持损坏检测和缓存校验。

## 10. 反向工程文档入口

学习时优先看：

- `docs/BIGWORLD_PROTOCOL.md`：BigWorld 包协议、可观测字段、布局修正。
- `docs/MODELS.md`：`.geometry` 模型格式。
- `docs/BALLISTICS.md`：弹道、穿透、溅射机制。
- `docs/FIRE_CHANCE.md`：起火概率分析。
- `docs/TEAM_ADVANTAGE_SCORING.md`：队伍优势评分算法。
- `docs/RENDERER_SESSIONS.md`：协作会话协议与实现。
- `docs/format_templates/`：010 Editor 模板。

## 11. 建议的代码阅读顺序

1. 先读 `crates/wows-core`，理解共享类型与单位。
2. 读 `crates/wows-replays/src/wowsreplay.rs` 与 `packet2.rs`，理解回放容器和包流。
3. 读 `crates/wows-replays/src/analyzer/decoder/decode.rs`，理解包到业务 payload 的转换。
4. 读 `crates/wowsunpack/src/data/idx_vfs.rs` 与 `game_data.rs`，理解 VFS。
5. 读 `crates/wows-battle-world/src/world.rs`、`ingest/mod.rs`、`components.rs`、`resources.rs`。
6. 读 `crates/wows-replay-insights`，理解派生报告。
7. 读 `crates/minimap-renderer/src/draw_command.rs`、`renderer.rs`、`video.rs`。
8. 读 `crates/wows-toolkit/src/app.rs` 与 `ui/`，理解 GUI 如何串联后台任务。
9. 读协作链路时从 `crates/wt-collab-protocol/src/protocol.rs` 开始。

## 12. 快速命令

```powershell
# 运行桌面 GUI
cargo run --release -p wows_toolkit

# 构建 CLI
cargo build --release -p wowsunpack
cargo build --release -p wows_minimap_renderer --features bin
cargo build --release -p replayshark

# 测试
cargo test --workspace

# 需要游戏数据时准备数据
cargo run -p wows-data-mgr -- download --latest
cargo run -p wows-data-mgr -- register --path <WoWS目录>
cargo run -p wows-data-mgr -- list
```

版本控制使用 `jj`，不要直接以 `git` 作为权威操作界面。
