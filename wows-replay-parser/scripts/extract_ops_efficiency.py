#!/usr/bin/env python3
"""Extract per-player ship-equivalent efficiency from operations replays.

Efficiency is the community's "damage proportion" metric: for each enemy ship
you damaged, add (your damage to it) / (its max HP). Sunk and non-sunk ships
use the same rule; a sunk ship sums to ~1.0 across attackers, a survivor sums
to less than 1.0 and the leftover HP is uncredited.

The per-victim damage comes from the battle results JSON:
  playersPublicInfo[attacker].interactions[victim] = [...270 ints...]
indexed by CLIENT_VEH_INTERACTION_DETAILS (64 damage_* fields). The victim max
HP is playersPublicInfo[victim].max_health (index 15).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_ops_replays as ex


PUBLIC_FIELDS = {
    "account_db_id": 0, "name": 1, "team_id": 6, "vehicle_type_id": 7,
    "max_health": 15, "is_alive": 21, "ships_killed": 32,
}
SHIFTING = ["raw_exp", "exp", "scouting_damage", "damage", "resources", "interactions"]


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


def op_family(sc):
    if sc.startswith("WW2_OPERATION"):
        return "WW2_OP(new)"
    return "PCVO(legacy_op)"


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


def interaction_damage_indices(build, cache_dir):
    if build is None:
        return []
    f = Path(cache_dir) / ("%s.json" % build)
    if not f.exists():
        return []
    c = json.loads(f.read_text(encoding="utf-8"))
    veh = c.get("CLIENT_VEH_INTERACTION_DETAILS") or []
    return [i for i, name in enumerate(veh) if name.startswith("damage_")]


def parse_game(path, reg):
    build, ver, table, dmg_idx = reg
    meta, packets = ex.read_replay(path)
    results = ex.find_battle_results(packets)
    if results is None:
        return None

    common = ex.resolve_common(results.get("commonList") or [])
    ppi = results.get("playersPublicInfo") or {}
    # resolve all entities (humans and bots)
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

    for p in entities.values():
        inter = p.get("interactions") or {}
        eff = 0.0
        sum_dmg = 0.0
        n_victim = 0
        for victim_id, ival in inter.items():
            if not isinstance(ival, list):
                continue
            dmg = 0.0
            for i in dmg_idx:
                if i < len(ival) and isinstance(ival[i], (int, float)):
                    dmg += ival[i]
            if dmg <= 0:
                continue
            victim = entities.get(int(victim_id))
            if victim is None:
                continue
            # only count enemy ships
            if victim.get("team_id") == p.get("team_id"):
                continue
            hp = victim.get("max_health")
            if not hp:
                continue
            eff += dmg / float(hp)
            sum_dmg += dmg
            n_victim += 1
        p["efficiency"] = eff
        p["sum_dmg_check"] = sum_dmg
        p["n_victims"] = n_victim

    private = ex.resolve_private(results.get("privateDataList") or [])
    pve = private.get("pve_details") or {}
    stars_server = pve.get("cur_tasks_completed") if isinstance(pve, dict) else None

    battle_logic = common.get("battle_logic_info")
    tasks = battle_logic.get("tasks", []) if isinstance(battle_logic, dict) else []
    sec_total = 0
    sec_done = 0
    if isinstance(tasks, list):
        for t in tasks:
            if isinstance(t, dict) and t.get("category") == 2:
                sec_total += 1
                if t.get("targetValueAchieved") == 2:
                    sec_done += 1

    winner = common.get("winner_team_id")
    human_teams = {p.get("team_id") for p in humans if p.get("team_id") is not None}
    self_team = next(iter(human_teams), None)
    is_win = is_loss = is_draw = None
    if winner is not None and self_team is not None:
        is_draw = int(winner) < 0
        is_win = int(winner) == int(self_team)
        is_loss = not is_win and not is_draw

    return {
        "source": os.path.basename(path),
        "build": build,
        "client_version": ver,
        "arena_id": common.get("arena_id") or results.get("arenaUniqueID"),
        "scenario": common.get("scenario_name") or meta.get("scenario") or "",
        "scenario_family": op_family(common.get("scenario_name") or ""),
        "map_kind": ex.map_kind(common.get("scenario_name") or ""),
        "bracket": ex.bracket_of(common.get("scenario_name") or ""),
        "difficulty": ex.difficulty_of(common.get("scenario_name") or ""),
        "duration_sec": common.get("duration_sec"),
        "stars_server": stars_server,
        "secondary_completed": sec_done,
        "secondary_total": sec_total,
        "is_win": is_win,
        "is_loss": is_loss,
        "is_draw": is_draw,
        "finish_type": ex.FINISH_REASONS.get(str(common.get("win_type_id"))),
        "win_type_id": common.get("win_type_id"),
        "humans": [p for p in humans],
    }


def emit(rows, ship_info):
    for g in rows:
        hs = g["humans"]
        n_players = len(hs)
        team_raw = sum(h.get("raw_exp") or 0 for h in hs)
        team_eff = sum(h.get("efficiency") or 0 for h in hs)
        team_dmg = sum(h.get("damage") or 0 for h in hs)
        team_frags = sum(h.get("ships_killed") or 0 for h in hs)
        for h in hs:
            sid = h.get("vehicle_type_id")
            e = ship_info.get(str(sid)) if sid is not None else None
            st = e.get("type") if e else None
            yield {
                "source": g["source"],
                "build": g["build"],
                "client_version": g["client_version"],
                "arena_id": g["arena_id"],
                "scenario": g["scenario"],
                "scenario_family": g["scenario_family"],
                "map_kind": g["map_kind"],
                "bracket": g["bracket"],
                "difficulty": g["difficulty"],
                "duration_sec": g["duration_sec"],
                "stars_server": g["stars_server"],
                "secondary_completed": g["secondary_completed"],
                "secondary_total": g["secondary_total"],
                "is_win": g["is_win"],
                "is_loss": g["is_loss"],
                "is_draw": g["is_draw"],
                "finish_type": g["finish_type"],
                "win_type_id": g["win_type_id"],
                "n_players": n_players,
                "account_id": h["account_id"],
                "name": h.get("name"),
                "ship_id": sid,
                "ship_name": e.get("name") if e else None,
                "ship_type": st,
                "ship_class": ex.normalize_class(st),
                "tier": e.get("tier") if e else None,
                "raw_exp": h.get("raw_exp"),
                "exp": h.get("exp"),
                "damage": h.get("damage"),
                "frags": h.get("ships_killed"),
                "scouting_damage": h.get("scouting_damage"),
                "is_alive": h.get("is_alive"),
                "max_health": h.get("max_health"),
                "efficiency": h.get("efficiency"),
                "sum_dmg_check": h.get("sum_dmg_check"),
                "n_victims": h.get("n_victims"),
                "team_raw": team_raw,
                "team_eff": team_eff,
                "team_damage": team_dmg,
                "team_frags": team_frags,
            }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("replays", nargs="+")
    ap.add_argument("--out", default="ops_efficiency.jsonl")
    ap.add_argument("--constants-dir", default="constants_cache")
    ap.add_argument("--ship-cache", default="ships_cache.json")
    ap.add_argument("--region", default="eu")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)

    paths = ex.discover(args.replays)
    if not paths:
        print("no replays", file=sys.stderr)
        return 2

    # pre-scan: keep only operations scenarios
    targets = []
    metas = {}
    for p in paths:
        try:
            m = ex.read_meta_only(p)
            sc = str(m.get("scenario") or "")
            b, _ = ex.build_and_version(m)
            if is_operation(sc) and b is not None and b >= 9129736:
                targets.append(p)
                metas[p] = m
        except Exception:
            continue
    print("ops replays matched:", len(targets), file=sys.stderr)

    # group by build to pick per-build tables
    regs = {}
    for p in targets:
        b, v = ex.build_and_version(metas[p])
        if b not in regs:
            regs[b] = (b, v, resolve_public_table(b, args.constants_dir), interaction_damage_indices(b, args.constants_dir))

    games = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(parse_game, p, regs[ex.build_and_version(metas[p])[0]]): p for p in targets}
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                g = fut.result()
                if g:
                    games.append(g)
            except Exception as exc:
                print("SKIP", futs[fut], exc, file=sys.stderr)
            if done % 100 == 0:
                print("  parsed %d/%d" % (done, len(futs)), file=sys.stderr)
    games.sort(key=lambda g: g["source"])

    ship_ids = set()
    for g in games:
        for h in g["humans"]:
            if h.get("vehicle_type_id") is not None:
                ship_ids.add(int(h["vehicle_type_id"]))
    ship_info = ex.resolve_ship_info(ship_ids, args.ship_cache, True, args.region, ex.WG_APP_ID)

    rows = list(emit(games, ship_info))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    fam = collections.Counter(r["scenario_family"] for r in rows)
    cls = collections.Counter(r["ship_class"] for r in rows)
    print("wrote %d player-rows -> %s" % (len(rows), out), file=sys.stderr)
    print("family:", dict(fam), file=sys.stderr)
    print("class:", dict(cls), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
