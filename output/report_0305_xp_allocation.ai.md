# 经验分配 + 舰种系数（AI 工具版）

```yaml
model: >
  contribution_i = ship_eff_i + lambda * (scouting_damage_i / 100000)
  XP_share_i = a / n + (1 - a) * K[class_i] * contribution_i
               / sum_j(K[class_j] * contribution_j)
ship_eff: sum over enemy ships (damage_to_ship / ship_max_health)
data_matches: 2060
scope: new 317 / legacy 1743
```

## 参数（合并拟合，CL/CA = 1.00 基准）

```yaml
a: 0.50
lambda: 1.2
R2: 0.91
K:
  CL/CA: 1.00
  DD: 0.83
  BB: 0.95
  CV: 0.43
  SS: 1.40
```

## DD 基准换算

```yaml
K_DD_baseline:
  DD: 1.00
  CL/CA: 1.20
  BB: 1.15
  CV: 0.52
  SS: 1.68
SS_vs_DD: 1.68
```

## 三档拟合

```yaml
new_only:        {DD: 0.811, CL/CA: 1.000, BB: 0.963, CV: 0.385, SS: 1.379, a: 0.48, lambda: 1.9, R2: 0.922}
legacy_only:     {DD: 0.834, CL/CA: 1.000, BB: 0.951, CV: 0.444, SS: 1.415, a: 0.50, lambda: 1.2, R2: 0.906}
new_plus_legacy: {DD: 0.830, CL/CA: 1.000, BB: 0.953, CV: 0.432, SS: 1.395, a: 0.50, lambda: 1.2, R2: 0.908}
```

## 击杀数独立贡献（frags）

```yaml
frags_effect:
  player_level_n: 14420
  within_match_demean: true
  class_dummies: true
  frags_only: {coef: 0.077, R2: 0.379}
  eff_scout_only: {R2: 0.618}
  eff_scout_frags: {frags_coef: 0.012, R2: 0.622}
  conclusion: kills carry no meaningful reward beyond ship_eff; last-hit bonus is negligible
pool_level:
  n: 2058
  team_frags_coef: -0.0013
  R2_with_team_dmg: 0.9687
  R2_with_team_frags: 0.9688
  conclusion: team frag count does not move the total XP pool
victim_tier_effect:
  player_level_n: 14420
  within_match_demean: true
  class_dummies: true
  ship_equivalent_share_coef:
    t4_5: 0.0100
    t6_7: 0.0149
    t8_9: 0.0124
    t10_11: 0.0145
  conclusion: no monotonic tier premium; reward is per ship-equivalent, independent of victim tier
noncombat_and_buildings:
  player_level_n: 14420
  within_match_demean: true
  class_dummies: true
  share_coef:
    eff_ship: 0.01313
    eff_noncombat: 0.00892
    scouting_per_100k: 0.01525
    building_damage_per_100k: 0.00745
    building_kill: 0.00255
  conclusion: >
    transports/torpedo boats count as ship-equivalent but at ~68% of a combat
    ship; building damage and building kills are near-zero contributors.
duration_effect:
  pool_level_n: 2058
  pool_R2_objective: 0.9576
  pool_R2_with_log_duration: 0.9577
  pool_log_duration_elasticity: -0.032
  player_level_n: 14406
  player_R2_base: 0.5279
  player_R2_with_log_duration: 0.5300
  player_log_duration_coef: -0.133
  per_map:
    n_scenarios: 28
    mean_coef: -0.080
    median_coef: -0.025
    weighted_mean_coef: 0.012
    n_negative: 19
    n_positive: 9
    note: large per-map coefficients are collinearity artifacts with stars/win
  conclusion: battle duration does not grow the XP pool; individual share is slightly diluted in longer matches
cherry_blossom_spawn:
  n_matches: 292
  team_eff_corr_team_raw: 0.466
  team_eff_corr_team_raw_full_star_win: 0.729
  pool_regression:
    r2_obj: 0.9631
    r2_with_team_eff: 0.9742
    team_eff_coef: 0.00595
  full_star_team_eff_range: [13.7, 62.9]
  duration_corr_team_eff: 0.06
  conclusion: more spawns (more team ship-equivalents) enlarge the pool at ~x1.006 per ship-equivalent; dragging time does not add spawns
killer_whale_waves:
  n_matches: 49
  team_eff_corr_team_raw: 0.527
  team_eff_corr_team_raw_full_star_win: 0.503
  pool_regression:
    r2_obj: 0.9504
    r2_with_team_eff: 0.9694
    team_eff_coef: 0.00738
  full_star_team_eff_range: [19.3, 35.5]
  team_frags_coef: -0.002
  conclusion: eating more of the five waves enlarges the pool via ship-equivalents, not raw frags
```

## 脚本 / 数据

- fit: `scripts/fit_class_efficiency.py --scope all`
- extract: `scripts/extract_ops_efficiency.py`
- data: `ops_efficiency_full.jsonl`
- result json: `output/class_efficiency_fit.json`
- frags analysis: `scripts/analyze_frags.py` -> `output/frags_analysis.json`
- victim tier analysis: `scripts/analyze_victim_tier.py` -> `output/victim_tier_analysis.json`
- noncombat/building analysis: `scripts/analyze_noncombat.py` -> `output/noncombat_analysis.json`
- duration analysis: `scripts/analyze_duration.py` -> `output/duration_analysis.json`
- per-map duration: `scripts/analyze_duration_per_map.py` -> `output/duration_per_map_analysis.json`
- cherry blossom spawn: `scripts/analyze_cherry_spawn.py` -> `output/cherry_spawn_analysis.json`
- killer whale waves: `scripts/analyze_cherry_spawn.py --tag NavalBase` -> `output/killerwhale_spawn_analysis.json`
