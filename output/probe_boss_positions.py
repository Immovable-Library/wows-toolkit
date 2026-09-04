#!/usr/bin/env python3
"""Compare boss spawn positions: Kousotsu (C13) vs Gunkan (C14)."""

from __future__ import annotations

import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")
import cache_lib
import spawn_lib

CACHE = Path(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache")


def boss_create(arena: str, tag: bytes) -> tuple[float, float, float] | None:
    """First 0x05 create position of the entity whose pickle contains tag."""
    packets = cache_lib.load_packets(CACHE, arena)
    eid = None
    for clock, fd in cache_lib.iter_bot_pickles(packets):
        name = cache_lib.flat_get(fd, cache_lib.KEY_NAME)
        if isinstance(name, bytes):
            name = name.decode("utf-8", "replace")
        if name == tag.decode():
            eid = cache_lib.flat_get(fd, cache_lib.KEY_SHIP_ID)
            break
    if eid is None:
        return None
    for ptype, clock, payload in spawn_lib.packet_iter(packets):
        if ptype == 0x05 and len(payload) >= 26:
            peid = struct.unpack_from("<I", payload, 0)[0]
            if peid == eid:
                x, _y, z = struct.unpack_from("<fff", payload, 14)
                return (clock, x, z)
    return None


def main() -> None:
    con = sqlite3.connect(CACHE / "cache.sqlite")
    games = con.execute(
        "SELECT arena_key, bracket, build FROM arena "
        "WHERE family='Naval_Defense' ORDER BY bracket, arena_key"
    ).fetchall()
    tags = [
        b"IDS_OP_01_04_ATAKER_L11",
        b"IDS_OP_01_04_ATAKER_R11",
        b"IDS_OP_01_04_ATAKER_L12",
        b"IDS_OP_01_04_ATAKER_L13",
        b"IDS_OP_01_04_ATAKER_C11",
        b"IDS_OP_01_04_ATAKER_C12",
        b"IDS_OP_01_04_ATAKER_C14",
        b"IDS_OP_01_04_ATAKER_R12",
        b"IDS_OP_01_04_ATAKER_R13",
    ]
    # detect G games by presence of C14
    g_games = []
    for a, br, build in games:
        if boss_create(a, b"IDS_OP_01_04_ATAKER_C14") is not None:
            g_games.append((a, br, build))
    print("G games:", len(g_games))
    for a, br, build in g_games:
        pos = boss_create(a, b"IDS_OP_01_04_ATAKER_C14")
        print(f"{a} {br:6s} build={build} 武藏=({pos[1]:.1f},{pos[2]:.1f})")


if __name__ == "__main__":
    main()
