#!/usr/bin/env python3
"""Aggregate per-wave ship names and estimate per-wave reward coefficients.

Input: output/wave_raw.jsonl (from extract_wave_data.py).
Output: output/wave_ships.json and output/wave_coefs.json.

Reward-coefficient model (within-match demeaning):
  y_i = share_i - mean_match(share)
  predictors: total efficiency, per-wave efficiencies (reference wave dropped),
  scouting damage, and ship-class dummies (CL/CA reference).
The per-wave coefficient delta_k is the extra XP share per unit of that wave's
efficiency relative to the reference wave.
"""

from __future__ import annotations

import collections
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

import ship_zh


RAW = Path("output/wave_raw.jsonl")


def classify(name: str, scenario: str) -> str | None:
    n = name or ""
    if scenario.startswith("WW2_OPERATION"):
        if "_BOSS_DD_" in n:
            return "BOSS驱逐"
        if "_KEY_OBJECT_" in n:
            return "目标单位"
        if "_WAVE_ADD_" in n or "_ADD_WAVE_" in n:
            return "增援"
        m = re.search(r"_WAVE_(\d+)$", n)
        if not m:
            return None
        w = m.group(1)
        if w == "310":
            return "尾BOSS"
        if w == "36" and scenario.startswith("WW2_OPERATION_2"):
            return "尾BOSS"
        if w.startswith("0"):
            if w in ("011", "012", "013", "014"):
                return "第一波"
            if w in ("021", "022", "023", "024"):
                return "第二波"
            return None
        if w.startswith("1"):
            return "第三波"
        if w.startswith("2"):
            return "第四波"
        if w.startswith("3"):
            return "第五波"
        return None

    if "Ridge" in scenario:
        m = re.match(r"IDS_(\d)W\d+$", n)
        if not m:
            return None
        cn = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
        return "第" + cn[m.group(1)] + "波"
    if "NavalBase" in scenario:
        if "MOB_WARSHIP_" in n:
            return "主力波"
        if "MOB_VESSEL_" in n:
            return "运输船"
        if "MOB_AIR_CARRIER_" in n:
            return "航母"
        m = re.search(r"MOB_REINFORCEMENT_(\d)_", n)
        return ("增援" + m.group(1)) if m else None
    if "Labyrinth" in scenario:
        if n.startswith("IDS_OP_01_03_EN_") or "_EN_" in n:
            m = re.search(r"EN_(\d+)$", n)
            if m:
                code = m.group(1)
                if code[0] == "1" and len(code) == 2:
                    return "第一波"
                if code[0] == "2" and len(code) == 2:
                    return "第二波"
                if code[0] == "3" and len(code) == 2:
                    return "第三波"
                if code[0] == "4" and len(code) == 2:
                    return "第四波"
                if code.startswith("51") or code.startswith("52"):
                    return "第五波"
                if code[0] in ("6", "7"):
                    return "第六波"
                if code[0] == "9":
                    return "第七波"
                if code.startswith("C"):
                    return "第六波"
        if "_EV_" in n:
            return "特殊设施"
        return None
    if "Naval_Defense" in scenario:
        m = re.search(r"ATAKER_C(\d+)$", n)
        if m:
            return "第一波" if int(m.group(1)) <= 5 else "第二波"
        if "ATAKER_CR_" in n:
            return "第三波"
        if "ATAKER_L" in n:
            return "第四波"
        if "ATAKER_R" in n:
            return "第五波"
        return None
    if "Advance" in scenario:
        if "AT_ATTAKA_FR_" in n:
            return "第一波"
        if "AT_ATTAKA_GB_" in n:
            return "第二波"
        if "AT_ATTAKA_UR_" in n:
            return "第三波"
        if "AT_ATTAKA_US_" in n:
            return "第四波"
        if "AT_SHIP_DEFENDER_" in n:
            return "第五波"
        if "AT_TRANSPORT_E_" in n:
            return "敌方运输"
        if "AT_COMMUNICATION" in n:
            return "敌方运输·通讯舰"
        return None
    if "Atoll" in scenario:
        if "BOT_01_" in n:
            return "第一波"
        if "BOT_02_" in n:
            return "第二波"
        if "BOT_03_" in n:
            return "第三波"
        if "BOT_CRR_" in n or "DDG_" in n:
            return "第四波"
        if re.search(r"EN2\d$", n):
            return "第五波"
        if re.search(r"EN3\d$", n):
            return "第五波"
        if re.search(r"EN4\d$", n):
            return "第六波"
        if "INTRMDT_" in n:
            return "终局"
        return None
    if "LePVE" in scenario:
        m = re.search(r"OP_09_(\d+)$", n)
        if m:
            return "第一波" if int(m.group(1)) <= 10 else "第二波"
        if "FW_" in n:
            return "第三波"
        return None
    if "USS_CL" in scenario:
        m = re.search(r"EN_(\d+)$", n)
        if m:
            code = int(m.group(1))
            if 101 <= code <= 115:
                return "第一波"
            if 118 <= code <= 124:
                return "第二波"
            if 125 <= code <= 133:
                return "第三波"
        return None
    return None


def main() -> int:
    matches = []
    with open(RAW, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                matches.append(json.loads(line))

    ship_agg = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, set()])))

    # per-scenario ordered wave labels (reference wave is first)
    scenario_waves = collections.defaultdict(dict)

    for r in matches:
        sc = r["scenario"]
        entities = r["entities"]
        enemy = [e for e in entities if e.get("team_id") == 1]
        waves_for_ent = {}
        for e in enemy:
            lab = classify(e.get("name") or "", sc)
            if lab is None:
                continue
            waves_for_ent[e["account_id"]] = lab
            hp = e.get("max_health") or 0
            sn = ship_zh.zh_name(e.get("ship_id"), e.get("ship_name")) or ("未识别#" + str(e.get("ship_id")))
            cell = ship_agg[sc][lab][sn]
            cell[0] += 1
            cell[1] = hp
            cell[2].add(e.get("ship_class") or "?")

        players = r["players"]
        if not players:
            continue
        team_raw = r.get("team_raw") or 0
        if team_raw <= 0:
            continue
        # build per-player per-wave efficiency
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

    # collect ordered wave labels per scenario (by first-seen order, then stable)
    wave_order = {}
    for sc, waves in ship_agg.items():
        order = []
        for lab in ("第一波", "第二波", "第三波", "第四波", "第五波", "第六波", "第七波", "尾BOSS", "BOSS驱逐", "增援", "目标单位", "敌方运输", "敌方运输·通讯舰", "运输船", "航母", "特殊设施", "主力波", "终局", "增援1", "增援2", "增援3", "增援4", "增援5"):
            if lab in waves:
                order.append(lab)
        for lab in waves:
            if lab not in order:
                order.append(lab)
        wave_order[sc] = order

    # ship aggregation -> plain dict
    ships_out = {}
    for sc, waves in ship_agg.items():
        ships_out[sc] = {}
        for lab in wave_order[sc]:
            items = []
            for sn, cell in sorted(waves[lab].items(), key=lambda kv: -kv[1][0]):
                items.append({"ship": sn, "count": cell[0], "hp": cell[1], "class": sorted(cell[2])})
            ships_out[sc][lab] = items

    # regression per scenario: each wave vs the pooled "other" enemies
    class_list = ["DD", "BB", "CV", "SS"]
    coefs_out = {}
    for sc in sorted(wave_order):
        waves = wave_order[sc]
        if not waves:
            continue

        rows = []
        for r in matches:
            if r["scenario"] != sc:
                continue
            team_raw = r.get("team_raw") or 0
            if team_raw <= 0:
                continue
            for p in r["players"]:
                rows.append({
                    "arena": r["arena_id"],
                    "share": (p.get("raw_exp") or 0) / team_raw,
                    "eff": p["_eff"],
                    "total": sum(p["_eff"].values()),
                    "scout": (p.get("scouting_damage") or 0) / 100000.0,
                    "class": p.get("ship_class") or "CL/CA",
                })
        n = len(rows)
        if n < 20:
            continue
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
        for lab in waves:
            eff_k = [row["eff"].get(lab, 0.0) for row in rows]
            eff_o = [row["total"] - row["eff"].get(lab, 0.0) for row in rows]
            vals = [eff_k, eff_o, [row["scout"] for row in rows]] + [[1.0 if row["class"] == c else 0.0 for row in rows] for c in class_list]
            names = ["eff_k", "eff_other", "scout"] + [f"class:{c}" for c in class_list]
            coef, se, cov, names_kept, r2 = fit(vals, names)
            pos = {name: j for j, name in enumerate(names_kept)}
            if "eff_k" not in pos or "eff_other" not in pos:
                out_waves.append({"wave": lab, "relative": None, "se": None, "t": None, "n_eff": None, "note": "样本不足/无方差"})
                continue
            jk = pos["eff_k"]
            jo = pos["eff_other"]
            bk = coef[jk]
            bo = coef[jo]
            rel = bk / bo if bo else float("nan")
            if bo and np.isfinite(cov[jk, jk]):
                var_rel = (1 / bo ** 2) * cov[jk, jk] + (bk ** 2 / bo ** 4) * cov[jo, jo] - 2 * bk / bo ** 3 * cov[jk, jo]
                se_rel = math.sqrt(max(0.0, var_rel)) if var_rel >= 0 else float("nan")
                t = (rel - 1.0) / se_rel if se_rel else float("nan")
            else:
                se_rel = float("nan")
                t = float("nan")
            n_eff = sum(1 for v in eff_k if v > 0)
            out_waves.append({
                "wave": lab,
                "relative": float(rel),
                "se": float(se_rel),
                "t": float(t),
                "n_eff": int(n_eff),
                "beta_k": float(bk),
                "beta_other": float(bo),
            })

        coefs_out[sc] = {
            "n_players": n,
            "n_matches": len(arena_idx),
            "r2_base": float(r2_base),
            "waves": out_waves,
        }
        print("== %s (n=%d, matches=%d, R2_base=%.3f)" % (sc, n, len(arena_idx), r2_base))
        for w in out_waves:
            if w.get("relative") is None:
                print("    %-8s %s" % (w["wave"], w["note"]))
            else:
                print("    %-8s rel=%.3f se=%.3f t=%+.2f (n_eff=%d)" % (w["wave"], w["relative"], w["se"], w["t"], w["n_eff"]))

    Path("output/wave_ships.json").write_text(json.dumps(ships_out, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("output/wave_coefs.json").write_text(json.dumps(coefs_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote output/wave_ships.json and output/wave_coefs.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
