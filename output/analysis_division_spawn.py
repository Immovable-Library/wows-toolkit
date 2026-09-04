#!/usr/bin/env python3
"""Newport: does player spawn slot depend on division (prebattle_id)?"""

from __future__ import annotations

import json
import sqlite3
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")

import cache_lib
import spawn_lib

CACHE_DIR = Path(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache")
DB_PATH = CACHE_DIR / "cache.sqlite"

sys.path.insert(0, r"D:/codexProject/wows-toolkit/output")
import importlib.util

spec = importlib.util.spec_from_file_location(
    "ana", r"D:/codexProject/wows-toolkit/output/analysis_player_spawn_class.py"
)
ana = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ana)


def main() -> None:
    rows = json.load(open(r"D:/codexProject/wows-toolkit/output/player_spawn_class_rows.json", encoding="utf-8"))
    by_arena = defaultdict(list)
    for r in rows:
        by_arena[r["arena"]].append(r)

    con = sqlite3.connect(DB_PATH)
    arenas = con.execute(
        "SELECT arena_key, bracket, build FROM arena WHERE family='Naval_Defense' ORDER BY build"
    ).fetchall()

    out = []
    no_ppi = 0
    dup_ship_players = 0
    dup_games = []

    for arena_key, bracket, build in arenas:
        packets = cache_lib.load_packets(CACHE_DIR, arena_key)
        j = ana.battle_json(packets)
        if j is None:
            no_ppi += 1
            continue
        ppi = j["playersPublicInfo"]
        players = []
        for v in ppi.values():
            if isinstance(v, list) and len(v) > 14 and isinstance(v[1], str) and not v[1].startswith("IDS_"):
                players.append({"account": v[0], "name": v[1], "ship_id": v[7], "prebattle_id": v[8]})

        # Ship id uniqueness within the game.
        sid_counts = Counter(p["ship_id"] for p in players)
        dup = {sid for sid, n in sid_counts.items() if n > 1}
        if dup:
            dup_games.append((arena_key, dup))

        sid2player = {}
        for p in players:
            if p["ship_id"] not in dup:
                sid2player[p["ship_id"]] = p

        for r in by_arena.get(arena_key, []):
            p = sid2player.get(r["ship_id"])
            if p is None:
                dup_ship_players += 1
                continue
            rec = dict(r)
            rec["player_name"] = p["name"]
            rec["prebattle_id"] = p["prebattle_id"]
            out.append(rec)

    print(f"games: {len(arenas)}, with ppi: {len(arenas)-no_ppi}, "
          f"ambiguous-by-dup-ship rows dropped: {dup_ship_players}, games with dup shipId: {len(dup_games)}")
    for a, d in dup_games[:10]:
        print("  dup game:", a, d)

    json.dump(out, open(r"D:/codexProject/wows-toolkit/output/player_spawn_division_rows.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # --- analysis: division structure ---
    by_game = defaultdict(list)
    for r in out:
        by_game[r["arena"]].append(r)

    division_games = 0
    div_members = 0
    solo_members = 0
    div_size_counter = Counter()
    for a, rs in by_game.items():
        divs = defaultdict(list)
        for r in rs:
            divs[r["prebattle_id"]].append(r)
        has_div = any(pid != 0 and len(v) >= 2 for pid, v in divs.items())
        if has_div:
            division_games += 1
        for pid, v in divs.items():
            if pid != 0 and len(v) >= 2:
                div_members += len(v)
                div_size_counter[len(v)] += 1
            elif pid == 0:
                solo_members += len(v)

    print(f"\ngames with >=1 division: {division_games}/{len(by_game)}")
    print("division members:", div_members, "solo members:", solo_members)
    print("division size distribution (count of divisions):", dict(div_size_counter))

    # slot distance between division members (same game)
    slot_order = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]
    idx = {s: i for i, s in enumerate(slot_order)}
    dist_counter = Counter()
    div_slot_sets = []
    for a, rs in by_game.items():
        divs = defaultdict(list)
        for r in rs:
            divs[r["prebattle_id"]].append(r)
        for pid, v in divs.items():
            if pid == 0 or len(v) < 2:
                continue
            slots = sorted(idx[r["slot"]] for r in v)
            div_slot_sets.append((a, pid, tuple(r["slot"] for r in sorted(v, key=lambda x: idx[x["slot"]])), len(v)))
            for i in range(len(slots) - 1):
                dist_counter[slots[i + 1] - slots[i]] += 1
            if len(slots) == 2:
                dist_counter[("pair", slots[1] - slots[0])] += 1

    print("\nadjacent slot-gap between consecutive division members:", dict(dist_counter))

    print("\n== division slot layouts (division size x slot tuple) ==")
    layout = Counter((n, sl) for _a, _p, sl, n in div_slot_sets)
    for (n, sl), c in sorted(layout.items(), key=lambda kv: (-kv[0][0], kv[1])):
        print(f"  size {n}: {' '.join(sl)} x{c}")


if __name__ == "__main__":
    main()
