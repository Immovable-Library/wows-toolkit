#!/usr/bin/env python3
"""Track Mahan/Benson reinforcement ships after creation."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")
import cache_lib
import spawn_lib

CACHE = Path(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache")
MAHAN = struct.pack("<I", 4288559088)
BENSON = struct.pack("<I", 4286461936)


def main() -> None:
    arena = "a4021126262369607"
    packets = cache_lib.load_packets(CACHE, arena)
    eids = []
    for ptype, clock, payload in spawn_lib.packet_iter(packets):
        if ptype == 0x05 and clock >= 800.0 and len(payload) >= 26:
            if MAHAN in payload or BENSON in payload:
                eid = struct.unpack_from("<I", payload, 0)[0]
                eids.append((eid, clock, MAHAN in payload))
    print("reinforcement creates:", eids)
    for eid, c0, is_mahan in eids:
        print(f"\neid={eid} {'Mahan' if is_mahan else 'Benson'} created t={c0:.1f}")
        pos = {}
        for ptype, clock, payload in spawn_lib.packet_iter(packets):
            if ptype == 0x0A and len(payload) >= 20:
                peid = struct.unpack_from("<I", payload, 0)[0]
                if peid != eid:
                    continue
                x, _y, z = struct.unpack_from("<fff", payload, 8)
                if peid not in pos:
                    pos[peid] = []
                pos[peid].append((clock, x, z))
        track = pos.get(eid, [])
        for i in range(0, len(track), max(1, len(track) // 12)):
            t, x, z = track[i]
            print(f"   t={t:7.1f} pos=({x:7.1f},{z:7.1f})")


if __name__ == "__main__":
    main()
