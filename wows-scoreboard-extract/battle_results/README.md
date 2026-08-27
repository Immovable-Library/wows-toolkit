# 战绩结算数据

本目录用于存放《战舰世界》结算界面截图，以及每张截图对应的背景描述。

## 目录约定

- `screenshots/`：结算界面原始截图（“我的团队”/赛后战绩表）。
- `descriptions/`：与截图同名的 `.md` 描述文件，记录对局背景（模式、地图、日期、阵容、备注等）。

## 命名建议

截图和描述使用同一基名，例如：

```text
screenshots/2026-08-27_ops_team.png
descriptions/2026-08-27_ops_team.md
```

## 提取流程

1. 将结算截图放入 `screenshots/`。
2. 在 `descriptions/` 中补充对应的背景描述（可选）。
3. 使用 `wows-scoreboard-extract` 技能或 `scripts/segment_rows.py` 提取表格。
