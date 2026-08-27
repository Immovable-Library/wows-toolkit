#!/usr/bin/env python3
"""Extract damage-type breakdown, achievements, ribbons, planes from ops replays.

Items 5-10 from the pending verification list.
"""
from __future__ import annotations

import collections
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_ops_replays as ex


PUBLIC_FIELDS = {
    "account_db_id": 0, "name": 1, "team_id": 6, "vehicle_type_id": 7,
    "max_health": 15, "is_alive": 21, "ships_killed": 32,
}
SHIFTING = ["raw_exp", "exp", "scouting_damage", "damage", "resources", "interactions",
            "achievements", "planes_killed_by_ship", "planes_killed_by_plane",
            "planes_killed_fighters", "planes_killed_bombers"]


def is_operation(sc):
    return (
        sc.startswith("WW2_OPERATION")
        or sc.startswith("PCVO")
        or sc.startswith("OP_")
        or sc.startswith("Attack_On_Base")
        or sc == "Defense"
        or sc.startswith("Dunkirk")
        or sc.startswith("USS_CL")
    )


def resolve_public_table(build, cache_dir):
    table = dict(PUBLIC_FIELDS)
    if build is None:
        return table
    f = Path(cache_dir) / ("%s.json" % build)
    if not f.exists():
        return table
    c = json.loads(f.read_text(encoding="utf-8"))
    pub = c.get("CLIENT_PUBLIC_RESULTS_INDICES") or {}
    for k in SHIFTING:
        if k in pub and pub[k] is not None:
            table[k] = pub[k]
    return table


def build_damage_category_map(build, cache_dir):
    """Map each damage_* field index to a category."""
    f = Path(cache_dir) / ("%s.json" % build)
    if not f.exists():
        return {}
    c = json.loads(f.read_text(encoding="utf-8"))
    veh = c.get("CLIENT_VEH_INTERACTION_DETAILS") or []
    mapping = {}
    for i, name in enumerate(veh):
        if not name.startswith("damage_"):
            continue
        if name in ("damage_fire", "damage_flood"):
            mapping[i] = "dot"
        elif "_tpd_" in name or name.startswith("damage_tpd"):
            mapping[i] = "torpedo"
        elif "_bomb" in name or name.startswith("damage_bomb") or name.startswith("damage_dbomb") or name.startswith("damage_tbomb"):
            mapping[i] = "bomb"
        elif "_rocket" in name or "_skip" in name or "_wave" in name or "_laser" in name or "_mine" in name or "_ram" in name:
            mapping[i] = "other"
        elif "_planes" in name or "_airdefense" in name:
            mapping[i] = "other"
        elif "_main_" in name or "_atba_" in name:
            mapping[i] = "direct"
        else:
            mapping[i] = "other"
    return mapping


def build_ribbon_map(build, cache_dir):
    """Map ribbon field indices to names."""
    f = Path(cache_dir) / ("%s.json" % build)
    if not f.exists():
        return {}
    c = json.loads(f.read_text(encoding="utf-8"))
    pub = c.get("CLIENT_PUBLIC_RESULTS_INDICES") or {}
    mapping = {}
    for k, idx in pub.items():
        if k.startswith("RIBBON_") and isinstance(idx, int):
            mapping[idx] = k
    return mapping


def parse_game(path, build, ver, table, dmg_cat_map, ribbon_map):
    meta, packets = ex.read_replay(path)
    results = ex.find_battle_results(packets)
    if results is None:
        return None

    common = ex.resolve_common(results.get("commonList") or [])
    ppi = results.get("playersPublicInfo") or {}

    entities = {}
    for dbid, arr in ppi.items():
        if not isinstance(arr, list):
            continue
        p = {k: arr[idx] for k, idx in table.items() if idx < len(arr)}
        if p.get("account_db_id") is None:
            continue
        p["account_id"] = int(p["account_db_id"])
        p["label"] = str(arr[1]) if len(arr) > 1 else ""
        p["ship_id"] = p.get("vehicle_type_id")

        # achievements
        ach_idx = table.get("achievements")
        if ach_idx is not None and ach_idx < len(arr):
            ach_val = arr[ach_idx]
            if isinstance(ach_val, list):
                p["achievements"] = [str(a) for a in ach_val]
            else:
                p["achievements"] = []
        else:
            p["achievements"] = []

        # ribbons
        ribbons = {}
        for idx, name in ribbon_map.items():
            if idx < len(arr):
                ribbons[name] = arr[idx] if isinstance(arr[idx], (int, float)) else 0
        p["ribbons"] = ribbons

        # planes
        for pk in ["planes_killed_by_ship", "planes_killed_by_plane",
                     "planes_killed_fighters", "planes_killed_bombers"]:
            pk_idx = table.get(pk)
            if pk_idx is not None and pk_idx < len(arr):
                p[pk] = arr[pk_idx] if isinstance(arr[pk_idx], (int, float)) else 0
            else:
                p[pk] = 0

        entities[p["account_id"]] = p

    humans = [p for p in entities.values() if p["account_id"] > 0]
    if not humans:
        return None

    # compute damage type efficiency
    for p in entities.values():
        inter = p.get("interactions") or {}
        eff = {"direct": 0.0, "torpedo": 0.0, "dot": 0.0, "bomb": 0.0, "other": 0.0, "total": 0.0}
        for victim_id, ival in inter.items():
            if not isinstance(ival, list):
                continue
            dmg_by_cat = {"direct": 0.0, "torpedo": 0.0, "dot": 0.0, "bomb": 0.0, "other": 0.0}
            for i, cat in dmg_cat_map.items():
                if i < len(ival) and isinstance(ival[i], (int, float)):
                    dmg_by_cat[cat] += ival[i]
            total_dmg = sum(dmg_by_cat.values())
            if total_dmg <= 0:
                continue
            victim = entities.get(int(victim_id))
            if victim is None:
                continue
            if victim.get("team_id") == p.get("team_id"):
                continue
            hp = victim.get("max_health")
            if not hp:
                continue
            for cat in dmg_by_cat:
                eff[cat] += dmg_by_cat[cat] / float(hp)
            eff["total"] += total_dmg / float(hp)
        p["eff_by_type"] = eff

    winner = common.get("winner_team_id")
    human_teams = {p.get("team_id") for p in humans if p.get("team_id") is not None}
    self_team = next(iter(human_teams), None)
    is_win = None
    if winner is not None and self_team is not None:
        is_win = int(winner) == int(self_team)

    return {
        "source": os.path.basename(path),
        "build": build,
        "arena_id": common.get("arena_id") or results.get("arenaUniqueID"),
        "scenario": common.get("scenario_name") or meta.get("scenario") or "",
        "duration_sec": common.get("duration_sec"),
        "is_win": is_win,
        "humans": [p for p in humans],
    }


def main():
    root = Path("replays")
    paths = []
    for dp, _, fns in os.walk(root):
        for f in fns:
            if f.endswith(".wowsreplay"):
                paths.append(Path(dp) / f)

    # pre-scan: operations only
    targets = []
    metas = {}
    for p in paths:
        try:
            m = ex.read_meta_only(str(p))
            sc = str(m.get("scenario") or "")
            b, v = ex.build_and_version(m)
            if is_operation(sc) and b is not None and b >= 9129736:
                targets.append(str(p))
                metas[str(p)] = (b, v)
        except Exception:
            continue
    print("ops replays: %d" % len(targets), file=sys.stderr)

    # group by build
    regs = {}
    for p in targets:
        b, v = metas[p]
        if b not in regs:
            regs[b] = (b, v,
                        resolve_public_table(b, "constants_cache"),
                        build_damage_category_map(b, "constants_cache"),
                        build_ribbon_map(b, "constants_cache"))

    games = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futs = {}
        for p in targets:
            b, v = metas[p]
            reg = regs[b]
            futs[pool.submit(parse_game, p, *reg)] = p
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                g = fut.result()
                if g:
                    games.append(g)
            except Exception as exc:
                print("SKIP", futs[fut], exc, file=sys.stderr)
            if done % 50 == 0:
                print("  parsed %d/%d" % (done, len(futs)), file=sys.stderr)
    print("parsed %d games" % len(games), file=sys.stderr)

    # emit rows
    rows = []
    for g in games:
        hs = g["humans"]
        team_raw = sum(h.get("raw_exp") or 0 for h in hs)
        for h in hs:
            eff = h.get("eff_by_type", {})
            ribbons = h.get("ribbons", {})
            rows.append({
                "arena_id": g["arena_id"],
                "scenario": g["scenario"],
                "is_win": g["is_win"],
                "account_id": h["account_id"],
                "ship_id": h.get("vehicle_type_id"),
                "label": h.get("label", ""),
                "raw_exp": h.get("raw_exp"),
                "scouting_damage": h.get("scouting_damage") or 0,
                "team_raw": team_raw,
                "eff_total": eff.get("total", 0),
                "eff_direct": eff.get("direct", 0),
                "eff_torpedo": eff.get("torpedo", 0),
                "eff_dot": eff.get("dot", 0),
                "eff_bomb": eff.get("bomb", 0),
                "eff_other": eff.get("other", 0),
                "achievements": h.get("achievements", []),
                "n_achievements": len(h.get("achievements", [])),
                "ribbon_base_capture": ribbons.get("RIBBON_BASE_CAPTURE", 0),
                "ribbon_base_defense": ribbons.get("RIBBON_BASE_DEFENSE", 0),
                "ribbon_plane": ribbons.get("RIBBON_PLANE", 0),
                "ribbon_building_kill": ribbons.get("RIBBON_BUILDING_KILL", 0),
                "ribbon_demining_mine": ribbons.get("RIBBON_DEMINING_MINE", 0),
                "ribbon_demining_minefield": ribbons.get("RIBBON_DEMINING_MINEFIELD", 0),
                "ribbon_drop": ribbons.get("RIBBON_DROP", 0),
                "ribbon_citadel": ribbons.get("RIBBON_CITADEL", 0),
                "ribbon_burn": ribbons.get("RIBBON_BURN", 0),
                "ribbon_flood": ribbons.get("RIBBON_FLOOD", 0),
                "planes_killed_by_ship": h.get("planes_killed_by_ship", 0),
                "planes_killed_by_plane": h.get("planes_killed_by_plane", 0),
                "planes_killed_fighters": h.get("planes_killed_fighters", 0),
                "planes_killed_bombers": h.get("planes_killed_bombers", 0),
            })

    out_path = Path("output/damage_type_analysis.jsonl")
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote %d rows -> %s" % (len(rows), out_path), file=sys.stderr)


if __name__ == "__main__":
    main()
