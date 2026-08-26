> **注意：** 败局倍数已由 x0.5 修正为 x0.44（95%CI x0.433-0.452）并补齐置信区间，见 `WOWS_OPERATIONS_INTERIM.md`。finish_type 在现有样本中与胜负完全共线，无法拆「超时 vs 被团灭」，详见中期报告 2.3。

# Operations Total XP Pool: Fitted Model

## Data

- 2060 operations matches (deduplicated), with per-match total base XP
  (`team_raw`), stars, secondary tasks, win/loss, and team efficiency.

## Terminology: stars are the secondary-task completion (capped at 5)

The "stars" rating (`stars_server`, 0-5) is what the secondary tasks earn;
it is capped at 5. The raw secondary-task count (`secondary_completed`,
category==2) can reach 6 or 7 on some maps, which is why "six secondary tasks
but only five stars" happens. In the pool model these two are the same
concept, so only the 0-5 star rating is used.

## Finding: the pool is objective-based, not performance-based

A regression of `log(team_raw)` on objective variables explains most of the
variance:

- scenario (map) fixed effects + stars + secondary + win: R^2 = 0.9595
- adding team efficiency / damage / inactive count: R^2 = 0.9709

Team performance adds only about 1 percentage point, so the pool is set by
objectives, not by how much the team kills.

## Pool vs stars (win)

| stars | mean team_raw | n |
|---|---|---|
| 0 (loss) | 2789 | 151 |
| 1 | 6668 | 23 |
| 2 | 7436 | 119 |
| 3 | 8175 | 276 |
| 4 | 8782 | 526 |
| 5 | 9577 | 958 |

Each star adds roughly +9% to the pool. A loss gives about half the base pool
of a win at the same completion level.

## Fitted coefficients (log scale)

| term | coef | effect |
|---|---|---|
| stars | +0.0865 | x1.09 per star |
| secondary completed | +0.0226 | redundant with stars, dropped |
| is_win | +0.8178 | x2.27 win vs loss |
| team efficiency | +0.0031 | x1.003 per ship-equivalent |
| team damage | ~0 | no effect |
| inactive players | -0.0283 | x0.972 per dead-weight |

## Approximate pool formula

```
team_raw ~ base[scenario] * (1.09 ^ stars) * (win ? 1 : 0.5)
```

`base[scenario]` is map-specific, roughly 7000 to 13000 depending on the
operation and flagships/random modifiers.

Secondary tasks are already represented by stars (0-5). Team efficiency is
minor; stars and win/loss dominate.

