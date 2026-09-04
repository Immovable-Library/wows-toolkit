#!/usr/bin/env python3
"""Compare task lists between reinforcement and non-reinforcement games."""

from __future__ import annotations

import json
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")
import cache_lib
import spawn_lib

CACHE = Path(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache")
COUNTDOWN = 31.4
MAHAN = struct.pack("<I", 4288559088)
BENSON = struct.pack("<I", 4286461936)


def battle_json(packets: bytes) -> dict | None:
    last = None
    for ptype, _c, payload in spawn_lib.packet_iter(packets):
        if ptype == 0x22 and len(payload) >= 4:
            (jl,) = struct.unpack_from("<I", payload, 0)
            try:
                j = json.loads(payload[4:4 + jl].decode("utf-8", "replace"))
            except Exception:
                j = None
            if isinstance(j, dict) and "playersPublicInfo" in j:
                last = j
    return last


def has_reinforcement(packets: bytes) -> float | None:
    for ptype, clock, payload in spawn_lib.packet_iter(packets):
        if ptype == 0x05 and clock >= 800.0 and len(payload) >= 26:
            if MAHAN in payload or BENSON in payload:
                return clock
    return None


def main() -> None:
    con = sqlite3.connect(CACHE / "cache.sqlite")
    arenas = con.execute(
        "SELECT arena_key, bracket FROM arena WHERE family='Naval_Defense' "
        "ORDER BY arena_key"
    ).fetchall()
    all_tasks = {}
    rein_games = []
    norein_games = []
    for a, br in arenas:
        packets = cache_lib.load_packets(CACHE, a)
        j = battle_json(packets)
        if not j:
            continue
        tasks = []
        for item in j.get("commonList") or []:
            if isinstance(item, dict):
                for t in item.get("tasks", []):
                    if isinstance(t, dict):
                        tasks.append(t)
        ids = sorted({t.get("id") for t in tasks if isinstance(t.get("id"), str)})
        for i in ids:
            all_tasks[i] = all_tasks.get(i, 0) + 1
        rein = has_reinforcement(packets)
        if rein:
            rein_games.append((a, br, rein, ids))
        else:
            norein_games.append((a, br, ids))

    print("== task ids present in reinforcement games ==")
    for a, br, rein, ids in rein_games:
        print(f"{a} {br} rein={rein-COUNTDOWN:.0f}s tasks={ids}")

    print("\n== task ids never/rarely in non-reinforcement games ==")
    from collections import Counter
    rein_set = Counter()
    norein_set = Counter()
    for _a, _br, _r, ids in rein_games:
        rein_set.update(ids)
    for _a, _br, ids in norein_games:
        norein_set.update(ids)
    for tid in sorted(all_tasks):
        if rein_set[tid] and norein_set[tid] == 0:
            print("  only in rein games:", tid, rein_set[tid])
        elif rein_set[tid] > 0 and norein_set[tid] > 0:
            print(f"  both: {tid} rein={rein_set[tid]} norein={norein_set[tid]}")


if __name__ == "__main__":
    main()
