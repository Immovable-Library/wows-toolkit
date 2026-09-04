#!/usr/bin/env python3
"""Full per-map per-bracket wave analysis with composition variants.

Reads output/wave_raw.jsonl (which carries family + bracket) and writes:
  output/wave_ships_full.json     family -> bracket -> wave -> ships
  output/wave_coefs_full.json     family -> bracket -> reward coefficients
  output/wave_variants.json       family -> bracket -> wave -> variant pool
"""

from __future__ import annotations

import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

import analyze_waves as aw
import ship_zh


RAW = Path("output/wave_raw.jsonl")

WAVE_ORDER = [
    "第一波", "第二波", "第三波", "第四波", "第五波", "第六波", "第七波",
    "第八波", "第九波", "尾BOSS", "BOSS驱逐", "增援", "目标单位", "敌方运输",
    "运输船", "航母", "敌方运输·通讯舰", "特殊设施", "主力波", "终局",
    "增援1", "增援2", "增援3", "增援4", "增援5",
]

BRACKET_LABEL = {
    "BASE": "普通",
    "MEDIUM": "中等",
    "HIGH": "高等",
    "67LVL": "6~7",
    "89LVL": "8~9",
    "9LVL": "9",
    "1011LVL": "10~11",
}

BRACKET_ORDER = ["67LVL", "89LVL", "9LVL", "1011LVL", "BASE", "MEDIUM", "HIGH"]


def bracket_sort_key(br):
    if br in BRACKET_ORDER:
        return (0, BRACKET_ORDER.index(br))
    return (1, br)


def side_task_label(name):
    """Map a side-task entity id to its role name (fixed across maps)."""
    if not name:
        return None
    if name == "IDS_ART_KMLC_CRUISER":
        return "水雷舰 Hyaena"
    if name == "IDS_ART_CAKD_BOT":
        return "伏击者 Ambusher"
    if name.startswith("IDS_ART_CAKD_SUPPORT_DD_"):
        return "伏击者支援 Beta"
    if name.startswith("IDS_ART_CTBP_BOT_"):
        return "占领点位 Alpha"
    if name.startswith("IDS_ART_DTBP_BOT_"):
        return "防守点位 Gamma"
    if name.startswith("IDS_ART_GTPT_BOT_"):
        return "占点 Delta"
    if name.startswith("IDS_ART_KCST_ALLY_TOWER_"):
        return "侦察站（友方）"
    if name.startswith("IDS_ART_KCST_ENEMY_TOWER_"):
        return "侦察站（敌方）"
    if name == "IDS_ART_DTBP_ENEMY_PORT":
        return "港口"
    return None


def main() -> int:
    matches = []
    with open(RAW, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                matches.append(json.loads(line))

    # group key: (family, bracket)
    ship_agg = collections.defaultdict(
        lambda: collections.defaultdict(
            lambda: collections.defaultdict(
                lambda: collections.defaultdict(lambda: [0, 0.0, set()])
            )
        )
    )
    variant_agg = collections.defaultdict(
        lambda: collections.defaultdict(
            lambda: collections.defaultdict(collections.Counter)
        )
    )
    variant_ships = collections.defaultdict(
        lambda: collections.defaultdict(
            lambda: collections.defaultdict(dict)
        )
    )
    variant_arenas = collections.defaultdict(
        lambda: collections.defaultdict(
            lambda: collections.defaultdict(
                lambda: collections.defaultdict(set)
            )
        )
    )
    side_task_ships = collections.defaultdict(
        lambda: collections.defaultdict(
            lambda: collections.defaultdict(
                lambda: collections.defaultdict(lambda: [0, 0.0])
            )
        )
    )

    for r in matches:
        family = r.get("family")
        bracket = r.get("bracket")
        if not family or not bracket:
            continue
        sc = r["scenario"]
        arena = r["arena_id"]
        enemy = [e for e in r["entities"] if e.get("team_id") == 1]
        waves_for_ent = {}
        wave_ships = collections.defaultdict(list)
        for e in enemy:
            stl = side_task_label(e.get("name") or "")
            if stl:
                sid = e.get("ship_id")
                sn = ship_zh.zh_name(sid, e.get("ship_name")) or ("未识别#" + str(sid))
                cell = side_task_ships[family][bracket][stl][sn]
                cell[0] += 1
                cell[1] = e.get("max_health") or 0
            lab = aw.classify(e.get("name") or "", sc)
            if lab is None:
                continue
            sid = e.get("ship_id")
            waves_for_ent[e["account_id"]] = lab
            hp = e.get("max_health") or 0
            sn = ship_zh.zh_name(sid, e.get("ship_name")) or ("未识别#" + str(sid))
            cell = ship_agg[family][bracket][lab][sn]
            cell[0] += 1
            cell[1] = hp
            cell[2].add(e.get("ship_class") or "?")
            wave_ships[lab].append(sid)

        for lab, sids in wave_ships.items():
            key = tuple(sorted(set(sids)))
            variant_agg[family][bracket][lab][key] += 1
            variant_arenas[family][bracket][lab][key].add(arena)
            if key not in variant_ships[family][bracket][lab]:
                variant_ships[family][bracket][lab][key] = [
                    {"ship_id": int(s), "ship": ship_zh.zh_name(s) or ("未识别#" + str(s))}
                    for s in sorted(set(sids))
                ]

        players = r.get("players") or []
        team_raw = r.get("team_raw") or 0
        if not players or team_raw <= 0:
            continue
        for p in players:
            eff = collections.Counter()
            for vid, dmg in (p.get("victims") or {}).items():
                try:
                    vid_int = int(vid)
                except (ValueError, TypeError):
                    continue
                lab = waves_for_ent.get(vid_int)
                if lab is None:
                    continue
                ent = next((e for e in enemy if e["account_id"] == vid_int), None)
                hp = (ent.get("max_health") or 0) if ent else 0
                if hp > 0:
                    eff[lab] += dmg / hp
            p["_eff"] = dict(eff)
            p["_share"] = (p.get("raw_exp") or 0) / team_raw
            p["_scout"] = (p.get("scouting_damage") or 0) / 100000.0

    # ---- ordered waves per group ----
    groups = sorted(
        {(f, b) for f, bm in ship_agg.items() for b in bm},
        key=lambda fb: (fb[0], bracket_sort_key(fb[1])),
    )

    ships_out = {}
    variants_out = {}
    coefs_out = {}

    class_list = ["DD", "BB", "CV", "SS"]

    for family, bracket in groups:
        waves = ship_agg[family][bracket]
        order = [w for w in WAVE_ORDER if w in waves]
        for w in waves:
            if w not in order:
                order.append(w)

        ships_out.setdefault(family, {})[bracket] = {
            lab: [
                {"ship": sn, "count": cell[0], "hp": cell[1], "class": sorted(cell[2])}
                for sn, cell in sorted(waves[lab].items(), key=lambda kv: -kv[1][0])
            ]
            for lab in order
        }

        variants_out.setdefault(family, {})[bracket] = {}
        for lab in order:
            vlist = []
            for key, cnt in variant_agg[family][bracket][lab].most_common():
                vlist.append({
                    "ships": variant_ships[family][bracket][lab][key],
                    "matches": len(variant_arenas[family][bracket][lab][key]),
                })
            variants_out[family][bracket][lab] = vlist

        # ---- reward regression (per-player rows, grouped by arena) ----
        rows = []
        for r in matches:
            if r.get("family") != family or r.get("bracket") != bracket:
                continue
            team_raw = r.get("team_raw") or 0
            if team_raw <= 0:
                continue
            for p in r.get("players", []):
                rows.append({
                    "arena": r["arena_id"],
                    "share": (p.get("raw_exp") or 0) / team_raw,
                    "eff": p["_eff"],
                    "total": sum(p["_eff"].values()),
                    "scout": (p.get("scouting_damage") or 0) / 100000.0,
                    "class": p.get("ship_class") or "CL/CA",
                })
        n = len(rows)
        if n >= 20:
            arena_idx = collections.defaultdict(list)
            for i, row in enumerate(rows):
                arena_idx[row["arena"]].append(i)
            y = np.array([row["share"] for row in rows])

            def demean(col):
                out = np.array(col, dtype=float)
                for idxs in arena_idx.values():
                    m = sum(col[i] for i in idxs) / len(idxs)
                    for i in idxs:
                        out[i] = col[i] - m
                return out

            yd = demean(y)

            def fit(term_vals, term_names):
                X = np.column_stack([demean(v) for v in term_vals])
                keep = [k for k in range(X.shape[1]) if np.std(X[:, k]) > 1e-12]
                X = X[:, keep]
                names = [term_names[k] for k in keep]
                coef, *_ = np.linalg.lstsq(X, yd, rcond=None)
                resid = yd - X @ coef
                dof = n - X.shape[1]
                try:
                    bread = np.linalg.inv(X.T @ X)
                    meat = np.zeros_like(bread)
                    for idxs in arena_idx.values():
                        Xg = X[idxs]
                        eg = resid[idxs]
                        meat += Xg.T @ (np.outer(eg, eg)) @ Xg
                    cov = bread @ meat @ bread
                    se = np.sqrt(np.diag(cov))
                except np.linalg.LinAlgError:
                    cov = np.full((X.shape[1], X.shape[1]), float("nan"))
                    se = np.full(X.shape[1], float("nan"))
                r2 = 1 - float((resid @ resid) / (yd @ yd)) if (yd @ yd) > 0 else float("nan")
                return coef, se, cov, names, r2

            base_vals = [
                [row["total"] for row in rows],
                [row["scout"] for row in rows],
            ] + [[1.0 if row["class"] == c else 0.0 for row in rows] for c in class_list]
            base_names = ["total", "scout"] + [f"class:{c}" for c in class_list]
            _, _, _, _, r2_base = fit(base_vals, base_names)

            out_waves = []
            for lab in order:
                eff_k = [row["eff"].get(lab, 0.0) for row in rows]
                eff_o = [row["total"] - row["eff"].get(lab, 0.0) for row in rows]
                vals = [eff_k, eff_o, [row["scout"] for row in rows]] + [[1.0 if row["class"] == c else 0.0 for row in rows] for c in class_list]
                names = ["eff_k", "eff_other", "scout"] + [f"class:{c}" for c in class_list]
                coef, se, cov, names_kept, r2 = fit(vals, names)
                pos = {name: j for j, name in enumerate(names_kept)}
                if "eff_k" not in pos or "eff_other" not in pos:
                    out_waves.append({"wave": lab, "relative": None, "se": None, "t": None, "n_eff": None, "note": "样本不足/无方差"})
                    continue
                jk, jo = pos["eff_k"], pos["eff_other"]
                bk, bo = coef[jk], coef[jo]
                rel = bk / bo if bo else float("nan")
                if bo and np.isfinite(cov[jk, jk]):
                    var_rel = (1 / bo ** 2) * cov[jk, jk] + (bk ** 2 / bo ** 4) * cov[jo, jo] - 2 * bk / bo ** 3 * cov[jk, jo]
                    se_rel = math.sqrt(max(0.0, var_rel)) if var_rel >= 0 else float("nan")
                    t = (rel - 1.0) / se_rel if se_rel else float("nan")
                else:
                    se_rel = float("nan")
                    t = float("nan")
                out_waves.append({
                    "wave": lab,
                    "relative": float(rel),
                    "se": float(se_rel),
                    "t": float(t),
                    "n_eff": int(sum(1 for v in eff_k if v > 0)),
                })

            coefs_out.setdefault(family, {})[bracket] = {
                "n_players": n,
                "n_matches": len(arena_idx),
                "r2_base": float(r2_base),
                "waves": out_waves,
            }

        print("== %s %s" % (family, bracket), file=sys.stderr)

    Path("output/wave_ships_full.json").write_text(json.dumps(ships_out, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("output/wave_coefs_full.json").write_text(json.dumps(coefs_out, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("output/wave_variants.json").write_text(json.dumps(variants_out, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("output/side_tasks.json").write_text(json.dumps(side_task_ships, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote wave_ships_full.json, wave_coefs_full.json, wave_variants.json, side_tasks.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
