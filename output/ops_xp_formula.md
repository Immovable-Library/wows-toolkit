# Operations XP Allocation: Fitted Formula

## Data

- 465 operations matches, 3255 player-rows with resolved base XP.
- 152 current-ops matches (`WW2_OP(new)`) and 448 matches pooled with legacy
  (`PCVO(legacy_op)`).
- Per-player ship-equivalent efficiency rebuilt from the replay's
  `interactions` per-victim damage and each victim's `max_health`.

## Model

For a match with n players, each player's base-XP share is:

```
contribution_i = ship_eff_i + lambda * (scouting_damage_i / 100000)

XP_share_i = a / n + (1 - a) * K[class_i] * contribution_i
                         / sum_j (K[class_j] * contribution_j)
```

Then `base_XP_i = XP_share_i * team_base_XP`.

Where:
- `ship_eff_i` = ship-equivalent kills = sum over enemy ships of
  (damage to that ship / that ship's max HP). A sunk ship sums to about 1.0
  across attackers; a survivor sums to less than 1.0.
- `scouting_damage_i` = spotting damage.

## Fitted parameters

### Current operations only (`WW2_OP(new)`)

- equal-floor fraction `a` = 0.48
- spotting weight `lambda` = 1.9 per 100k spotting damage
- R^2 = 0.914

| class | K |
|---|---|
| DD | 1.00 |
| CL/CA | 1.22 |
| BB | 1.19 |
| CV | 0.44 |
| SS | 1.73 |

### Current + legacy pooled

- `a` = 0.50
- `lambda` = 1.4 per 100k spotting damage
- R^2 = 0.900

| class | K |
|---|---|
| DD | 1.00 |
| CL/CA | 1.25 |
| BB | 1.19 |
| CV | 0.50 |
| SS | 1.72 |

## Conclusion vs the video

1. The "submarine 1.75x efficiency" claim is confirmed: fitted K[SS] is
   1.72-1.73 vs DD. The video was right on the multiplier.
2. The video's other claim, "the task XP pool now averages", is also
   confirmed: about half the pool (`a` around 0.5) is distributed equally.
3. Carrier coefficient is the opposite of submarine: about 0.44-0.50x.
4. Cruisers and battleships get a small premium (about 1.19-1.25x).
