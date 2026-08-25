---
name: wows-replay-parser
description: 解析本机 World of Warships .wowsreplay 文件（剧情/随机/联合/非对称/乱斗/活动等），
  输出人均一行 JSONL 并幂等追加进 SQLite；可按玩家生成解析报告。
  当用户要求“解析 replay、落库、追加朋友给的 rep、生成某玩家的解析报告”时使用本 skill。
---

# wows-replay-parser

把本地 `.wowsreplay` 文件解析成结构化数据并落库（SQLite），可再按玩家出报告。零编译，纯 Python。

## 依赖

```bash
pip install cryptography
```

其余全是标准库。舰船名/等级/舰种解析走 WG 百科 API（需联网，一次性批量请求 + 本地缓存），可关闭。

## 工作流程

本目录结构：

- `scripts/extract_ops_replays.py` —— 解析 + 落库主脚本
- `scripts/player_report.py` —— 玩家解析报告生成器
- `constants_cache/` —— 各 build 的字段索引表（13.10+ 已内置；脚本可自动从 `padtrack/wows-constants` 抓取缺失 build）

### 1. 解析并落库（幂等追加）

```bash
python scripts/extract_ops_replays.py "D:\replays" \
  --db replays.db --out replays_parsed.jsonl \
  --constants-dir constants_cache \
  --ship-cache ships_cache.json --workers 8
```

- 目录会**递归逐层**扫描所有 `.wowsreplay`。
- 默认**追加 + 去重**：按 `arena_id`（场次唯一 ID）+ `account_id` 去重，同一份 rep 重跑是空操作；`--overwrite` 才清空重建。
- 输出：`--out` 的 JSONL（人均一行）+ `--db` 的 SQLite（表 `rows`，唯一索引 `(arena_id, account_id)`）。

### 2. 生成玩家报告

```bash
python scripts/player_report.py --db replays.db --player SKmon --out reports\SKmon_report.md
# 可选过滤：
#   --family pvp / ops / coop / ...（scenario_family 子串匹配）
#   --match-group pvp / brawl / cooperative / ...
```

## 关键参数

| 参数 | 说明 |
|---|---|
| `--db` | SQLite 输出，默认 `replays.db`，`INSERT OR IGNORE` 幂等 |
| `--out` | JSONL 输出，默认 `replays_parsed.jsonl`，追加写 |
| `--constants-dir` | per-build 索引表缓存目录，默认 `constants_cache` |
| `--no-fetch` | 不从 GitHub 抓索引（离线跑已有缓存） |
| `--no-resolve-ships` | 跳过 WG 舰船名解析 |
| `--ship-cache` | ship_id→船名缓存文件，默认 `ships_cache.json` |
| `--workers` | 多进程数，默认 CPU 核数 |
| `--overwrite` | 清空 JSONL 和 DB 重建（默认追加） |

## 输出字段（人均一行）

局级：`source build client_version fields_resolved match_group scenario_family ts arena_id
scenario map_kind bracket difficulty is_win is_loss is_draw stars_server team_damage team_exp ...`
个人：`account_id name ship_id ship_name tier ship_class damage frags exp raw_exp
scouting_damage is_alive ...`

## 重要边界（务必先读）

1. **字段索引随版本变**：`damage/exp` 索引在 13.10→15.7 间漂移（412→426）。脚本按 build 选索引。
2. **版本覆盖三档**：
   - `>= 13.10`：damage/exp/raw_exp/星级 全量正确；
   - `12.6 ~ 13.8`：只有稳定字段（船/队/击杀/存活/胜负/星级），`damage/exp` 置空且 `fields_resolved=false`；
   - `< 12.6`（12.4/12.5）：无独立战报包（0x22 是 `NestedPropertyUpdate`），JSON 路线解析不了。
3. 新 build（朋友其它区服/新版本）：会自动抓索引；抓不到会降级并打印 unresolved 提示，把该 build 的常量补进 `constants_cache/<build>.json` 即可。
4. 败局会令 `stars_server=0`；机械完成数在 `secondary_completed`，二者含义不同。

## 示例：追加朋友 rep + 出报告

```bash
# 追加
python scripts/extract_ops_replays.py "D:\replays\skmon" --db ..\replays.db --workers 4
# 报告
python scripts/player_report.py --db ..\replays.db --player SKmon
```
