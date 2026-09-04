#!/usr/bin/env python3
"""Dump packet context right before the allied DD reinforcement."""

from __future__ import annotations

import re
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
    for arena in ["a4021126262369607", "a7766887487887401", "a6311486288580385"]:
        packets = cache_lib.load_packets(CACHE, arena)
        rein_clock = None
        for ptype, clock, payload in spawn_lib.packet_iter(packets):
            if ptype == 0x05 and clock >= 800.0 and len(payload) >= 26:
                if MAHAN in payload or BENSON in payload:
                    rein_clock = clock
                    break
        if rein_clock is None:
            continue
        print(f"\n===== {arena} reinforcement at clock {rein_clock:.1f} =====")
        # print every packet from rein-5s to rein+2s with type, size, IDS strings
        for ptype, clock, payload in spawn_lib.packet_iter(packets):
            if rein_clock - 5.0 <= clock <= rein_clock + 2.0:
                ids = sorted(set(re.findall(rb"IDS_[A-Za-z0-9_]+", payload)))
                mark = " <<< REIN" if (ptype == 0x05 and (MAHAN in payload or BENSON in payload)) else ""
                print(f"  t={clock:8.1f} type=0x{ptype:02x} len={len(payload):5d} ids={[d.decode() for d in ids][:6]}{mark}")


if __name__ == "__main__":
    main()
