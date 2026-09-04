# WOWS Replay 缓存分层架构 实现计划

> 状态：Phase 1/2/3 已实现、全量缓存已入库（2026-08-29）。修订 v2：实测修正 arena_id 来源、
> 新增「无战报包 rep」兜底；修订 v3：Tier2 默认只索引 05/0a/22/23（--index-all 全量补）。
> 目标：把「一次性解包所有 rep → 保存为可复用中间层 → 后续查询不再重新解密」落地成一套通用底座，
> 让出生点、轨迹、伤害、击杀等未来需求都从缓存派生，而不是每次重新解密。

## 1. 背景与动机

- 本机 `.wowsreplay`：约 7338 个，21.5 GB（`D:\codexProject\wows-toolkit\replays` 与
  `D:\World_of_Warships\replays`）。
- 单 rep 解密 + 解压 + 首轮解析已经优化到约 0.37s（`spawn_lib.read_replay` 用了 struct 版 XOR，
  `first_positions` 单趟扫描，`packet_index` + 二分查 clock）。
- 当前 `wows-ship-spawn-probe` / `wows-map-spawn-atlas` 两个 skill 每次运行都重新解密全部 rep。
  这是重复劳动；而且用户后续还会要轨迹、伤害、击杀等其它数据。
- 结论：真正该缓存的不是某张业务表，而是「解密后的包流」这个昂贵且可复用的中间层；业务表只是它上面的物化视图。

## 2. 三层架构

```text
Tier 1  包缓存（decrypted + decompressed packet stream）
        —— 一次性解出，永久复用；按 arena_key 去重（优先 arena_id，
           无 0x22 战报包时退化为包流哈希），zstd 再压缩。

Tier 2  包索引（每局一个：seq, clock, packet_type, payload_offset, payload_size）
        —— 随机访问包，避免全流重扫；v1 默认只索引 05/0a/22/23
           （实体创建/位置/战报/刷新生效），--index-all 可全量补。

Tier 3  业务表（spawns / positions / damage / kills / ...）
        —— 需要时从 Tier1/2 派生，幂等重建，可随时加新表。
```

原则：

1. 解密只做一次。所有后续解析都从 Tier1 读。
2. 业务表不做前瞻设计。第一版只建 `spawns`，未来按需加 `positions`、`damage` 等。
3. 去重键是 `arena_key`，优先取真实 `arena_id`：它藏在战报包（0x22）JSON 顶层
   `arenaUniqueID`（`commonList[0]` 是同一值），同一局所有视角一致，出生点分析只需每局
   保留一个代表 rep。拿不到 `arena_id` 的 rep（老版本、残段录制）退化为「解压后包流
   SHA-256」键，只去重完全相同的拷贝，绝不尝试合并不同视角（无法证明是同一局）。
4. 幂等：`INSERT OR IGNORE` + 唯一索引，重跑是空操作，支持增量追加。

## 3. 目录与文件规划

新建一个 skill（或并入现有 spawn skill）：

```text
C:\Users\asdfg\.codex\skills\wows-replay-cache\
  SKILL.md                         # 说明：解包落库、查询、增量更新
  scripts\
    extract_cache.py               # Phase 1：全量/增量解包 → 缓存 + 索引 + spawns 表
    query_cache.py                 # Phase 2：SQL 查询（probe / atlas 用）
    cache_lib.py                   # 共享：读缓存、读索引、建表、ship 中文名
  cache\                           # 运行时数据（不提交）
    <arena_key>.zst                # Tier1 包缓存（zstd），arena_key='a<arena_id>' 或 'f<包流哈希前16位>'
    cache.sqlite                   # Tier2 索引 + Tier3 业务表
```

复用已有代码（避免重写）：

- `C:\Users\asdfg\.codex\skills\wows-ship-spawn-probe\scripts\spawn_lib.py`
  —— 已经包含：`read_replay`（快速解密+解压）、`parse_idx`/`extract_minimap`、
  `packet_iter`、`first_positions`、`entity_creates`、`packet_index`/`clock_at`、
  `decode_blob`/`walk_flat_dicts`/`flat_get`/`extract_bots`、`load_mo`、`load_ship_zh`/`ship_name`。
- `C:\Users\asdfg\.codex\skills\wows-replay-parser\scripts\extract_ops_replays.py`
  —— `discover` / `read_meta_only` / `build_and_version`。

注意：`arena_id` 不在 meta 里，而在 `0x22` 战报包 JSON 顶层 `arenaUniqueID`
（`commonList[0]` 是同一值），必须完整解密后扫包提取；`read_meta_only` 只能拿 scenario 等元信息。

## 4. 数据模型（SQL DDL）

### 4.1 `arena` 元数据（每局一行）

```sql
CREATE TABLE IF NOT EXISTS arena (
  arena_key      TEXT PRIMARY KEY,      -- 'a<arena_id>' 或 'f<包流SHA-256前16位>'
  arena_id       INTEGER,               -- WG 局 ID；无 0x22 战报包时为 NULL（不用哨兵值）
  id_source      TEXT NOT NULL,         -- 'results_packet' | 'stream_hash'
  replay_path    TEXT NOT NULL,
  scenario       TEXT,
  family         TEXT,
  bracket        TEXT,
  build          INTEGER,
  duration_sec   REAL,
  parsed_at      TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_real_id ON arena(arena_id) WHERE arena_id IS NOT NULL;
```

### 4.2 `packet_index`（Tier 2，每局 N 行）

```sql
CREATE TABLE IF NOT EXISTS packet_index (
  arena_key       TEXT NOT NULL,
  seq             INTEGER NOT NULL,
  clock           REAL,
  packet_type     INTEGER,
  payload_offset  INTEGER,
  payload_size    INTEGER,
  PRIMARY KEY (arena_key, seq)
);
CREATE INDEX IF NOT EXISTS idx_pkt_type ON packet_index(arena_key, packet_type);
```

注意：Tier1 的包流按 `arena_key` 一个 blob 存在 `cache/<arena_key>.zst` 里，`payload_offset`
是相对「解压后的包流」的偏移。这样「我要某局所有 0x0a 包」= 一次索引扫描 + 按偏移切片。
索引行数按 `--index-types` 过滤（默认 05/0a/22/23，约省 60% 行）；以后需要别的包类型时
用 `--index-all` + `--rebuild-index` 从 Tier1 补全，不必重新解密 rep。

### 4.3 `spawns`（Tier 3，第一版唯一业务表）

```sql
CREATE TABLE IF NOT EXISTS spawns (
  arena_key       TEXT NOT NULL,
  entity_id       INTEGER NOT NULL,
  family          TEXT,
  bracket         TEXT,
  name            TEXT,
  display_name    TEXT,
  ship_id         INTEGER,
  ship_name       TEXT,
  team_id         INTEGER,
  max_health      REAL,
  is_initial      INTEGER,
  spawn_clock     REAL,
  first_seen_clock REAL,
  first_seen_x    REAL,
  first_seen_z    REAL,
  PRIMARY KEY (arena_key, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_spawn_family_bracket_name ON spawns(family, bracket, name);
CREATE INDEX IF NOT EXISTS idx_spawn_family_bracket ON spawns(family, bracket);
```

口径（务必写进 SKILL.md）：

- `first_seen_*` 是「首次被点亮位置」，不是服务端出生点；移动船的出生点要靠最早那撮聚类推断。
- `spawn_clock` 只是可观测的出生/注册时钟（开局 arena state = 0，中途 = 触发事件的 packet clock）。

## 5. 分阶段实现

### Phase 1：`extract_cache.py`（全量/增量解包落库）

输入：rep 目录；输出：`cache/<arena_key>.zst` + `cache.sqlite`。

每个 rep 的处理流程（复用 `spawn_lib.read_replay`；meta 里没有 `arena_id`）：

1. `read_replay` 解密+解压得到 meta + 包流；scenario 从 meta 取。
2. 从包流最后一个 `0x22` 战报包取顶层 `arenaUniqueID` 作为 `arena_id`：
   - 命中 → `arena_key='a'+str(arena_id)`、`id_source='results_packet'`；
   - 未命中（老版本 / 残段录制）→ 对解压后包流算 SHA-256，
     `arena_key='f'+sha256[:16]`、`id_source='stream_hash'`、`arena_id=NULL`。
3. 若 `arena_key` 已在 `arena` 表，跳过（增量幂等；含 `stream_hash` 键的局）。
4. 包流 zstd 压缩写入 `cache/<arena_key>.zst`；同时一趟 `packet_iter` 生成 `packet_index` 行。
5. 从包流提取实体信息写 `spawns`：
   - 用 `first_positions` 拿每个 entity 的首坐标；
   - 用 arena state / `onNewPlayerSpawnedInBattle` 的 pickle 拿 name、entity_id、ship_id、spawn_clock、max_health、team_id；
   - `is_initial` 根据 bot 来自 arena state 还是 spawn event 判定。
6. 中文船名用 `load_ship_zh(ships_zh.json)` + `ship_name()` 现算并写进 `spawns.ship_name`。

无 `0x22` 的 rep（约 32%）依然有 EntityCreate/Position，可正常落 Tier2/3；只是
`arena_id` 留空，去重退化为「包流哈希」——只能识别完全相同的拷贝，不同视角无法合并，
每视角按独立 `arena_key` 存一份（数据安全优先于去重）。

CLI（并行用 `ProcessPoolExecutor`，worker 产出结果，主进程汇总写 SQLite；或先写临时 JSONL 再批量入库）：

```bash
python scripts/extract_cache.py \
  --replays "D:/codexProject/wows-toolkit/replays" "D:/World_of_Warships/replays" \
  --cache-dir "C:/Users/asdfg/.codex/skills/wows-replay-cache/cache" \
  --ship-zh "D:/codexProject/wows-toolkit/ships_zh.json" \
  --workers 8 \
  --limit 100
```

可选参数：`--only-family NavalBase`、`--rebuild-spawns`（只从 Tier1 重算 Tier3）、
`--index-types`（默认 `05,0a,22,23`，`*` 或 `--index-all` 全量）、
`--rebuild-index`（只从 Tier1 重算 Tier2 并自动 VACUUM）、
`--upgrade-ids`（对 `id_source='stream_hash'` 的局尝试从 arena-state pickle 回填真实
`arena_id`，命中后把 `f` 键迁移为 `a` 键：重命名 zst + 更新三张表主键；属 Phase 5
研究完成后的能力，Phase 1 只预留参数位）。

### Phase 2：`cache_lib.py` + `query_cache.py`（查询层）

`cache_lib.py` 提供：

```python
def load_packets(cache_dir, arena_key) -> bytes
def load_packet_index(db, arena_key, packet_type=None) -> list
def read_packet(packets, index_row) -> bytes
def query_spawn_points(db, family, name) -> list
def query_spawn_atlas(db, family, bracket) -> list
```

probe 查询：

```sql
SELECT first_seen_x, first_seen_z, first_seen_clock, display_name, ship_name
FROM spawns WHERE family=? AND name=?;
```

atlas 查询：

```sql
SELECT name, display_name, ship_name,
       MIN(spawn_clock) AS spawn_clock,
       AVG(first_seen_x) AS x, AVG(first_seen_z) AS z,
       COUNT(*) AS n
FROM spawns WHERE family=? AND bracket=?
GROUP BY name;
```

`query_cache.py` 是 CLI 包装，输出 JSON/CSV：

```bash
python scripts/query_cache.py --db cache/cache.sqlite --probe NavalBase MOB_AIR_CARRIER_1
python scripts/query_cache.py --db cache/cache.sqlite --atlas NavalBase
```

### Phase 3：改造 spawn 两个 skill 为「优先查库」

- 已实现：`probe_ship.py` / `render_map_spawns.py` 增加 `--db` 参数，命中缓存直接渲染
  （probe 用 `query_spawn_points`，atlas 用 `query_spawn_observations` 保留逐局浮动校验），
  未命中回退 `--replays` 实时解析。
- 注意：缓存模式的覆盖 = 已入库的局；atlas 某分房在缓存无样本时不会出现在输出，
  跑前需确认缓存分房覆盖齐全。

### Phase 4：增量更新

- `extract_cache.py` 重跑即增量：`arena_key` 已有则跳过（含 `stream_hash` 键的局）。
- 支持传入新增目录，只处理新文件。
- `--rebuild-spawns` 从 Tier1 重算 Tier3（不动 Tier1/2）。

### Phase 5（可选，按需再做）

- 研究 arena-state pickle 是否携带 `arenaUniqueID`，可为 `stream_hash` 局回填真实局 ID
  并升级为 `a` 键（`--upgrade-ids`）。
- 建 `positions(arena_key, entity_id, clock, x, z, yaw)` 轨迹表。
- 建 `damage` / `kills` / `ribbons` 表。
- 若要「真正全量事件」，用主项目 `wows-replays` crate 的 `DecodedPacketPayload` 全量解码并导出
  JSONL/二进制，取代 Python 的按需解析（更重，但最通用）。

## 6. 规模与耗时估算

- 实测（2026-08-29 全量扫描 7338 个 rep）：4988 个含 `0x22` 战报包 → 4532 局
  （456 份重复均为同一文件拷贝）；2350 个无 `0x22`（1991 个 0.6/0.9.x、311 个 12.x、
  48 个 13~15.x 残段录制）。全部去重后约 6882 个唯一文件。
- Tier1 解压后单局约 9~14 MB，zstd 后约 3~5 MB → 全量缓存约 21~34 GB
  （可按需只缓存现代版本，旧版本先跳过）。
- Tier2 `packet_index` 全量索引约 10+ 亿行、百 GB 级，不可行；默认只索引
  05/0a/22/23 后行数降至约 40%（实测 97 局 704MB，全量预计约 40~60 GB，仍偏大，
  可再按需收窄或拆分）。
- 实测全量（2026-08-29）：7338 文件 → 6879 局（results_packet 4532 / stream_hash 2347），
  索引 4.88 亿行（55.8 GB），spawns 11.9 万行，全程 0 错误，约 30 分钟。
- 全量解包：单线程约 45 分钟；8 进程约 5~7 分钟（含包流哈希，实测）。
- Tier3 `spawns` 约 10~12 万行，几十 MB 量级。

## 7. 关键实现细节（容易踩坑）

1. arena_id 只在 `0x22` 战报包 JSON 顶层（`arenaUniqueID`，`commonList[0]` 同一值），meta
   里没有，必须完整解密后扫包。去重时同一局多个 rep 的 arena_id 相同但包流视角不同，
   只保留第一个（或包数量最多的）。
2. ROOT_PARENT 常量：idx 解析里根哨兵是 `0xDBB1A1D1B108B927`，别写错。
3. zlib 解压是 raw deflate：`zlib.decompress(raw, -15)`。
4. 包流帧格式：`[size u32][type u32][clock f32][payload size]`，头 12 字节。
5. 首次被点亮：优先第一个 `0x0a Position`，没有则退第一个 `0x05 EntityCreate`；用 `first_positions` 单趟做。
6. 中文船名：`ships_zh.json` + `SPECIAL_ZH` 优先，查不到落英文或 `未识别#id`。
7. 多进程写 SQLite：worker 只产出结果，主进程统一写；或 worker 写临时 JSONL，最后批量 upsert。
8. 幂等：`INSERT OR IGNORE`，主键 `(arena_key, entity_id)` / `(arena_key, seq)`。
9. 无 `0x22` 的 rep（约 32%）：老版本 0.6/0.9.x、12.x 无独立战报包；13~15.x 的残段是录制在
   战报前中断。它们仍有 EntityCreate/Position，可正常落库，但只能用包流 SHA-256 做键
   （只去重拷贝）。不要用 dateTime+地图+场景做去重键：dateTime 是各客户端本地时间，
   跨时区会误合并不同局。

## 8. 验收标准

1. `extract_cache.py --limit 100` 能在 1 分钟内跑完 NavalBase 样本并生成 cache + sqlite。
2. `query_cache.py --probe NavalBase MOB_AIR_CARRIER_1` 结果与实时解析的 Fury 首次点一致。
3. `query_cache.py --atlas NavalBase` 能还原 David(D9)/Albert(G10)/运输船(H9) 等已知点。
4. 重跑 `extract_cache.py` 是增量：已解析的 `arena_key` 跳过，只补新增。
5. 混入无 `0x22` 的 rep（老版本 / 残段）也能落库：`id_source='stream_hash'`、`arena_id`
   为空，且重跑增量同样生效。
6. 新加一个数据需求时，只需加一个 Tier3 表 + 一个 extractor，不需要改 Tier1/2。
