> **更新：** 舰种系数已补齐 95% 置信区间与「相同效率」口径的潜艇诊断，见 `WOWS_OPERATIONS_INTERIM.md`。

# Operations XP Formula: Validation and Final Coefficients

## Data

- Local replays + an independent replay-sharing-site scrape, deduplicated by
  arena and account.
- 2060 operations matches, 14420 player-rows with resolved base XP.
  - new operations (`WW2_OP(new)`): 317 matches
  - legacy operations (`PCVO(legacy_op)`): 1743 matches
- Class counts: BB 6217, CL/CA 5726, DD 1845, CV 260, SS 372.

## Model

```
contribution_i = ship_eff_i + lambda * (scouting_damage_i / 100000)

XP_share_i = a / n + (1 - a) * K[class_i] * contribution_i
                         / sum_j (K[class_j] * contribution_j)
```

`ship_eff_i` is ship-equivalent kills: for each enemy ship, add
(damage to that ship / its max HP).

## Three fits (CL/CA = 1.00 baseline)

| coefficient | new ops only<br>(317 matches) | legacy ops only<br>(1743 matches) | new + legacy<br>(2060 matches) |
|---|---|---|---|
| CL/CA | 1.000 | 1.000 | 1.000 |
| DD | 0.811 | 0.834 | 0.830 |
| BB | 0.963 | 0.951 | 0.953 |
| CV | 0.385 | 0.444 | 0.432 |
| SS | 1.379 | 1.415 | 1.395 |
| equal floor a | 0.48 | 0.50 | 0.50 |
| spotting lambda | 1.9 | 1.2 | 1.2 |
| R^2 | 0.922 | 0.906 | 0.908 |

The class coefficients are stable across the three scopes, so one unified
set is sufficient:

```
K: CL/CA = 1.00, DD = 0.83, BB = 0.95, CV = 0.43, SS = 1.40
a = 0.50, lambda = 1.2
```

## Submarine randomness effect

The new operations maps are more random, which weakens a submarine's ability
to memorize spawn patterns ("背板"). This shows up as lower submarine
contribution, not as a change in the class multiplier.

| metric (SS) | new ops | legacy ops | difference |
|---|---|---|---|
| efficiency share | 0.086 | 0.126 | -0.041 (about -46%) |
| ship-equivalent efficiency | 3.12 | 3.55 | -0.43 |
| damage | 108,893 | 169,580 | -36% |
| efficiency per 100k damage | 3.48 | 2.42 | +1.05 |

Submarines deal less damage and earn a smaller efficiency share in the random
maps. The higher efficiency-per-damage in new maps means they shift from
ambushing large ships (legacy, memorized torpedo runs) to picking off small
targets opportunistically.

This is already captured by the `contribution` term in the model, so the
class multiplier `K[SS]` stays about 1.38-1.42 in both map generations.

## Submarine 1.75x note

With CL/CA as the baseline, SS is about 1.38-1.42x. Relative to DD it is
about 1.66-1.67x, close to the community 1.75x figure.

The pure-proportional community formula `x = 1.75y/(1+0.75y)` matches subs
well in new operations (MAE 0.038 vs 0.050 no-bonus) but over-predicts in
legacy operations (MAE 0.064 vs 0.050) because it omits the equal floor.

