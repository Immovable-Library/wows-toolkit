# Operations XP Allocation: Full Local Replay Verification

## Data

- 465 operations matches, 3255 player-rows with resolved base XP (`raw_exp`).
  - `WW2_OP(new)` current operations: 174 matches, 1218 rows.
  - `PCVO(legacy_op)` legacy operations: 291 matches, 2037 rows.
- Class counts: CL/CA 1426, BB 1274, DD 367, SS 129, CV 46.
- `raw_exp` confirmed as base XP: it equals the replay owner's
  `init_economics.exp`; legacy ops always have `exp == raw_exp`, and current
  ops add a first-win modifier on top of `exp` for 168 rows. Premium (1.65x)
  is not present in either replay field.

## 1. XP is performance driven, not flat

Within-match OLS on `log(raw_exp)` (match fixed effects via demeaning):

| term | coef | se | p |
|---|---|---|---|
| log(damage) | +0.29 | 0.024 | <0.001 |
| frags | +0.023 | 0.0028 | <0.001 |
| log(scouting) | +0.037 | 0.0054 | <0.001 |
| alive | +0.008 | 0.0081 | 0.33 |
| tier | -0.049 | 0.0073 | <0.001 |

Damage is the main driver, kills and spotting add on top, and being alive by
itself does not raise XP. Higher tier gets slightly less XP at equal damage
(diminishing returns, since higher tiers deal more damage).

## 2. Submarine premium is modest, not 1.75x

Matched-damage check (each sub vs the nearest surface ship in the same match):

- SS gets **1.10x** (median 1.08x) the base XP of a surface ship with the same
  damage, n=129.

Within-match OLS, class multiplier vs DD:

- current ops: SS **x1.10** (95% CI 1.02..1.19)
- current + legacy pooled: SS **x1.21** (95% CI 1.15..1.27)

This is a real but small premium, concentrated in a few ships:

| ship | n | mean share |
|---|---|---|
| I-56 | 21 | 0.178 |
| U-4501 | 11 | 0.164 |
| K-1 | 4 | 0.167 |
| Seal | 3 | 0.167 |
| Archerfish | 2 | 0.179 |
| Balao | 5 | 0.097 |
| S-1 | 3 | 0.084 |
| Alliance | 3 | 0.087 |

The video's "1.75x efficiency" is not supported. The "+13.6%" sub share
comment is closer to the observed upper bound.

## 3. Carrier coefficient is lower, not higher

- Matched-damage: CV gets **0.82x** the XP of a surface ship with the same
  damage, n=46.
- Within-match OLS vs DD: CV **x0.92..x0.94** (marginal; CV also has high
  scouting which adds XP back).

So the class coefficients differ in opposite directions: SS is slightly
positive, CV is negative.

## 4. No "tribute taken from surface ships"

- Surface ships' mean XP share is unchanged by sub presence: 0.144 (with sub)
  vs 0.143 (without sub).
- Sub's own mean share is 0.138, slightly below equal split (0.143).

The sub premium is absorbed by the pool rather than stealing a fixed slice
from surface ships.

## 5. Dead-weight / AFK lowers the pool, but by ~8-18%, not 30%

Proxy: died with 0 frags and under 10k damage. At the same star level:

- legacy ops, 5 stars: 9081 (none) vs 8259 (inactive), about -9%.
- legacy ops, 4 stars: 8854 vs 7266, about -18%.
- current ops, 4 stars: 8450 vs 7724, about -9%.

The direction matches the video, but the magnitude is smaller than the
claimed ~30%, and it is confounded with lower objective completion.

## Conclusion

1. The "submarine 1.75x efficiency" claim is not supported by local data; the
   actual submarine premium is about +10% (matched damage) to +21% (pooled),
   concentrated in strong subs such as I-56 and U-4501.
2. Carrier XP coefficient is lower than surface ships, the opposite of the
   submarine direction.
3. Subs do not meaningfully reduce surface ships' XP share.
4. AFK / instant death lowers the team XP pool, but by roughly 8-18%, not 30%.
