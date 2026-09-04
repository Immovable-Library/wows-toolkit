#!/usr/bin/env python3
"""Extract per-victim damage and entity roster from operations replays.

One JSON line per match. Workers do the expensive decrypt/decompress and
return raw per-victim damage; the main process resolves ship names/classes
via the shared ship cache and emits the final record.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(r"C:/Users/asdfg/.codex/skills/wows-replay-parser/scripts")))
import extract_ops_replays as ex


PUBLIC = {
    "account_db_id": 0,
    "name": 1,
    "team_id": 6,
    "vehicle_type_id": 7,
    "max_health": 15,
    "is_alive": 21,
    "ships_killed": 32,
}
SHIFTING = ["raw_exp", "exp", "scouting_damage", "damage", "resources", "interactions"]

_MAP_KEYS = [
    ("Ridge", "Ridge"),
    ("NavalBase", "NavalBase"),
    ("Labyrinth", "Labyrinth"),
    ("Naval_Defense", "Naval_Defense"),
    ("Advance", "Advance"),
    ("Atoll", "Atoll"),
    ("LePVE", "LePVE"),
    ("USS_CL", "USS_CL"),
]


def map_family(scenario: str) -> str | None:
    if re.match(r"^WW2_OPERATION_[123]_", scenario):
        return "_".join(scenario.split("_")[:3])
    for code, key in _MAP_KEYS:
        if code in scenario:
            return key
    if "OP_01_01" in scenario:
        return "Ridge"
    if "Attack_On_Base" in scenario:
        return "NavalBase"
    if "OP_01_03" in scenario:
        return "Labyrinth"
    if scenario == "Defense":
        return "Naval_Defense"
    if "OP_02_03" in scenario:
        return "Advance"
    if "OP_02_02" in scenario:
        return "Atoll"
    if "OP_09" in scenario:
        return "LePVE"
    if "OP_10" in scenario:
        return "USS_CL"
    return None


def bracket_of(scenario: str) -> str | None:
    if re.match(r"^WW2_OPERATION_[123]_", scenario):
        m = re.search(r"(\d+LVL)", scenario)
        return m.group(1) if m else None
    if "_HIGH_LVL" in scenario:
        return "HIGH"
    if "_MEDIUM_LVL" in scenario:
        return "MEDIUM"
    return "BASE"


def is_target_scenario(scenario: str) -> bool:
    if "Flagship" in scenario:
        return False
    return map_family(scenario) is not None


def resolve_public_table(build, cache_dir):
    table = dict(PUBLIC)
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


def interaction_damage_indices(build, cache_dir):
    if build is None:
        return []
    f = Path(cache_dir) / ("%s.json" % build)
    if not f.exists():
        return []
    c = json.loads(f.read_text(encoding="utf-8"))
    veh = c.get("CLIENT_VEH_INTERACTION_DETAILS") or []
    return [i for i, name in enumerate(veh) if name.startswith("damage_")]


def _parse_one(args):
    path, build, table, dmg_idx = args
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
        entities[p["account_id"]] = p

    humans = [p for p in entities.values() if p["account_id"] > 0]
    if not humans:
        return None

    players = []
    for p in humans:
        inter = p.get("interactions") or {}
        victims = {}
        for victim_id, ival in inter.items():
            if not isinstance(ival, list):
                continue
            dmg = 0.0
            for i in dmg_idx:
                if i < len(ival) and isinstance(ival[i], (int, float)):
                    dmg += ival[i]
            if dmg > 0:
                try:
                    vid = int(victim_id)
                except (ValueError, TypeError):
                    continue
                victims[vid] = dmg
        players.append({
            "account_id": p["account_id"],
            "name": p.get("name"),
            "ship_id": p.get("vehicle_type_id"),
            "raw_exp": p.get("raw_exp"),
            "scouting_damage": p.get("scouting_damage"),
            "victims": victims,
        })

    battle_logic = common.get("battle_logic_info")
    tasks = battle_logic.get("tasks", []) if isinstance(battle_logic, dict) else []
    sec_total = sec_done = 0
    for t in tasks:
        if isinstance(t, dict) and t.get("category") == 2:
            sec_total += 1
            if t.get("targetValueAchieved") == 2:
                sec_done += 1

    winner = common.get("winner_team_id")
    human_teams = {p.get("team_id") for p in humans if p.get("team_id") is not None}
    self_team = next(iter(human_teams), None)
    is_win = None
    if winner is not None and self_team is not None:
        is_win = int(winner) == int(self_team)

    scenario = str(common.get("scenario_name") or meta.get("scenario") or "")
    return {
        "arena_id": common.get("arena_id") or results.get("arenaUniqueID"),
        "scenario": scenario,
        "family": map_family(scenario),
        "bracket": bracket_of(scenario),
        "is_win": is_win,
        "secondary_completed": sec_done,
        "secondary_total": sec_total,
        "team_raw": sum(p["raw_exp"] or 0 for p in players),
        "entities": [
            {
                "account_id": e["account_id"],
                "name": e.get("name"),
                "team_id": e.get("team_id"),
                "ship_id": e.get("vehicle_type_id"),
                "max_health": e.get("max_health"),
            }
            for e in entities.values()
        ],
        "players": players,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("replays", nargs="+")
    ap.add_argument("--out", default="output/wave_raw.jsonl")
    ap.add_argument("--constants-dir", default="constants_cache")
    ap.add_argument("--ship-cache", default="ships_cache.json")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)

    paths = ex.discover(args.replays)
    metas = {}
    targets = []
    for p in paths:
        try:
            m = ex.read_meta_only(p)
        except Exception:
            continue
        sc = str(m.get("scenario") or "")
        if is_target_scenario(sc):
            metas[p] = m
            targets.append(p)

    print("target replays:", len(targets), file=sys.stderr)

    regs = {}
    for p in targets:
        b, _ = ex.build_and_version(metas[p])
        if b not in regs:
            regs[b] = (b, resolve_public_table(b, args.constants_dir), interaction_damage_indices(b, args.constants_dir))

    jobs = [(p, *regs[ex.build_and_version(metas[p])[0]]) for p in targets]
    records = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(_parse_one, j): j[0] for j in jobs}
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                r = fut.result()
                if r:
                    records.append(r)
            except Exception as exc:
                print("SKIP", futs[fut], exc, file=sys.stderr)
            if done % 100 == 0:
                print("  parsed %d/%d" % (done, len(futs)), file=sys.stderr)

    # resolve ship classes / tiers once
    ship_ids = set()
    for r in records:
        for e in r["entities"]:
            if e.get("ship_id") is not None:
                ship_ids.add(int(e["ship_id"]))
        for p in r["players"]:
            if p.get("ship_id") is not None:
                ship_ids.add(int(p["ship_id"]))
    ship_info = ex.resolve_ship_info(ship_ids, args.ship_cache, True, "eu", ex.WG_APP_ID)

    def annotate(sid):
        e = ship_info.get(str(sid)) if sid is not None else None
        if not e:
            return None, None, None
        cls = ex.normalize_class(e.get("type"))
        return e.get("name"), e.get("tier"), cls

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for r in records:
            for e in r["entities"]:
                e["ship_name"], e["tier"], e["ship_class"] = annotate(e.get("ship_id"))
            for p in r["players"]:
                p["ship_name"], p["tier"], p["ship_class"] = annotate(p.get("ship_id"))
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("wrote %d matches -> %s" % (len(records), out), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
