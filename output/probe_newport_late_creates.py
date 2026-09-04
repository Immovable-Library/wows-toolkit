#!/usr/bin/env python3
"""Inspect late 0x05 creates in one Newport BASE game: are they ships?"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")

import cache_lib
import spawn_lib

CACHE = Path(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache")
SHIPS = json.load(open(r"D:/codexProject/wows-toolkit/ships_cache.json", encoding="utf-8"))
SID_BYTES = {int(k): struct.pack("<I", int(k)) for k in SHIPS}


def ship_creates(packets: bytes, min_clock: float):
    """First create per eid with any known WG shipId, clock >= min_clock."""
    out = []
    seen = set()
    for ptype, clock, payload in spawn_lib.packet_iter(packets):
        if ptype != 0x05 or len(payload) < 26:
            continue
        eid = struct.unpack_from("<I", payload, 0)[0]
        if eid in seen:
            continue
        seen.add(eid)
        if clock < min_clock:
            continue
        hits = [sid for sid, b in SID_BYTES.items() if b in payload]
        if hits:
            x, _y, z = struct.unpack_from("<fff", payload, 14)
            out.append((eid, clock, x, z, hits[0]))
    return out


def main() -> None:
    import sqlite3

    con = sqlite3.connect(CACHE / "cache.sqlite")
    arenas = con.execute(
        "SELECT arena_key, bracket, duration_sec FROM arena "
        "WHERE family='Naval_Defense' ORDER BY duration_sec DESC"
    ).fetchall()

    print("== ship creates at clock>=900 (game time >= ~16:08) ==")
    for a, br, dur in arenas:
        packets = cache_lib.load_packets(CACHE, a)
        late = ship_creates(packets, 900.0)
        game_end = dur - 31.4
        if late:
            print(f"\n{a} {br} dur={dur:.0f}s (game end ~{int(game_end)}s)")
            for eid, clock, x, z, sid in late:
                info = SHIPS.get(str(sid), {})
                print(f"   eid={eid} clock={clock:.1f} pos=({x:.0f},{z:.0f}) "
                      f"sid={sid} {info.get('name')} {info.get('type')}")
        elif game_end > 950:
            print(f"\n{a} {br} dur={dur:.0f}s (game end ~{int(game_end)}s): no late ships")


if __name__ == "__main__":
    main()
