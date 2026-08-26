# rep 解析 skill（AI 工具版）

```yaml
name: wows-replay-parser
type: local replay parsing skill
entry: skills/wows-replay-parser/SKILL.md
scripts:
  - scripts/extract_ops_replays.py
  - scripts/player_report.py
  - scripts/extract_ops_efficiency.py
```

## 命令

```bash
python scripts/extract_ops_replays.py "D:/replays" --db replays.db --out replays_parsed.jsonl --constants-dir constants_cache --workers 8
python scripts/extract_ops_efficiency.py "D:/replays" --out ops_efficiency.jsonl --workers 8
```

## 输入 / 输出

- input: `.wowsreplay` files (recursive)
- output1: JSONL, one row per player per match
- output2: SQLite `replays.db`, table `rows`, unique index `(arena_id, account_id)`

## 版本覆盖

- `>= 13.10`: full fields
- `12.6 - 13.8`: stable fields only, damage/exp = None, fields_resolved = false
- `< 12.6`: not parseable via JSON route

## 字段（效率扩展版，每行）

`source, build, client_version, arena_id, scenario, scenario_family, map_kind, bracket, difficulty, duration_sec, stars_server, secondary_completed, secondary_total, is_win, is_loss, is_draw, finish_type, win_type_id, n_players, account_id, name, ship_id, ship_name, ship_type, ship_class, tier, raw_exp, exp, damage, frags, scouting_damage, is_alive, max_health, efficiency, sum_dmg_check, n_victims, team_raw, team_eff, team_damage, team_frags`

## 关键数据文件

- `ops_efficiency_full.jsonl` - 2060 局全字段（本地 + 抓取，去重后）
- `replays.db` - 本地 replay 解析库
- `constants_cache/*.json` - per-build 字段索引

## 依赖

- `pip install cryptography`
