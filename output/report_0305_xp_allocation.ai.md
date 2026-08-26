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

## 脚本 / 数据

- fit: `scripts/fit_class_efficiency.py --scope all`
- extract: `scripts/extract_ops_efficiency.py`
- data: `ops_efficiency_full.jsonl`
- result json: `output/class_efficiency_fit.json`
