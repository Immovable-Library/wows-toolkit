# rep 解析 skill（机制研究者 / 社区开发者版）

## 位置与入口

- Skill 文档：`skills/wows-replay-parser/SKILL.md`
- 主解析脚本：`scripts/extract_ops_replays.py`
- 玩家报告生成：`scripts/player_report.py`
- 效率扩展：`scripts/extract_ops_efficiency.py`

## 解析链路

1. 读取 12 字节 header（magic, block_count, meta_len）+ JSON metadata。
2. 定位加密 packet 流，用常量 Blowfish key 做 ECB 解密。
3. XOR 链式解密 + zlib 解压得到 packet 字节流。
4. 在流中找 type `0x22` 的 BattleResults packet，解析为 UTF-8 JSON。
5. 用 per-build 常量表解析位置数组：
   - `COMMON_RESULTS`（局级）
   - `CLIENT_PUBLIC_RESULTS_INDICES`（每人公开 538 字段）
   - `PLAYER_PRIVATE_RESULTS_INDICES`（私有 54 字段）
   - `CLIENT_VEH_INTERACTION_DETAILS`（分目标交互数组）

## 版本覆盖

| 版本 | 覆盖 |
|---|---|
| >= 13.10 | damage / exp / raw_exp / 星级 全量 |
| 12.6 - 13.8 | 仅稳定字段，damage/exp 置空，`fields_resolved=false` |
| < 12.6 | 0x22 是 NestedPropertyUpdate，JSON 路线解析不了 |

缺失 build 的常量从 `padtrack/wows-constants` 拉取并缓存到 `constants_cache/`。

## 输出与去重

- JSONL：每人一行。
- SQLite：表 `rows`，唯一索引 `(arena_id, account_id)`，`INSERT OR IGNORE` 幂等追加。

## 效率扩展（船等价效率）

`extract_ops_efficiency.py` 额外从 battle results 的
`playersPublicInfo[attacker].interactions[victim]` 提取分目标伤害：

```
ship_eff_i = sum over enemy ships ( damage_i_to_ship / ship_max_health )
```

- 分目标伤害 = 该 victim 数组里 `CLIENT_VEH_INTERACTION_DETAILS` 的 64 个
  `damage_*` 字段求和；已验证与公开总 `damage` 逐字节一致。
- victim max_health 取自 `playersPublicInfo[victim].max_health`（索引 15）。
- 只统计敌方（team_id 不同）。

## 主要输出字段

`account_id, name, ship_id, ship_name, tier, ship_class, damage, frags,
scouting_damage, is_alive, raw_exp, exp, efficiency, team_raw, team_eff,
stars_server, secondary_completed, secondary_total, is_win, finish_type,
bracket, difficulty, scenario`
