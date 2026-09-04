#!/usr/bin/env python3
"""Timeline comparison: allied DD reinforcement vs key waves."""

from __future__ import annotations

import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")
import cache_lib
import spawn_lib

DB = r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite"
CACHE = Path(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache")
COUNTDOWN = 31.4
MAHAN = struct.pack("<I", 4288559088)
BENSON = struct.pack("<I", 4286461936)


def gt(clock: float) -> str:
    t = clock - COUNTDOWN
    m, s = divmod(max(0, t), 60)
    return f"{int(m)}:{int(s):02d}"


def main() -> None:
    con = sqlite3.connect(DB)
    arenas = con.execute(
        "SELECT arena_key, bracket FROM arena WHERE family='Naval_Defense' "
        "ORDER BY bracket, arena_key"
    ).fetchall()
    for a, br in arenas:
        rows = con.execute(
            "SELECT name, spawn_clock, first_seen_x, first_seen_z FROM spawns "
            "WHERE arena_key=? ORDER BY spawn_clock",
            (a,),
        ).fetchall()
        ev = {}
        for name, clk, x, z in rows:
            if name.endswith("_CR_33") or name.endswith("_CR_23"):
                ev.setdefault("wave1", clk)
            if name in ("IDS_OP_01_04_ATAKER_L12", "IDS_OP_01_04_ATAKER_R12"):
                ev.setdefault("wave5", clk)
            if name == "IDS_OP_01_04_ACR_ALLY_2":
                ev.setdefault("romeo", clk)
            if name in ("IDS_OP_01_04_ATAKER_L11", "IDS_OP_01_04_ATAKER_R11"):
                ev.setdefault("wave4", clk)
        # ally DD reinforcement: Mahan/Benson creates at clock >= 800
        packets = cache_lib.load_packets(CACHE, a)
        rein = None
        for ptype, clock, payload in spawn_lib.packet_iter(packets):
            if ptype == 0x05 and clock >= 800.0 and len(payload) >= 26:
                if MAHAN in payload or BENSON in payload:
                    rein = clock
                    break
        print(f"{a} {br:6s} w1={gt(ev.get('wave1',0))} w5={gt(ev.get('wave5',0))} "
              f"w4={gt(ev.get('wave4',0))} romeo={gt(ev.get('romeo',0))} "
              f"rein={gt(rein) if rein else '-'} "
              f"(w5->rein {int(rein - ev.get('wave5',0)) if rein and 'wave5' in ev else '-'}s)")


if __name__ == "__main__":
    main()
