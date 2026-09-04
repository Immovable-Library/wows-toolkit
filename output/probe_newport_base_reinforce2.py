#!/usr/bin/env python3
"""Deep probe: look for allied DD reinforcements in Newport BASE replays."""

from __future__ import annotations

import json
import re
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")

import cache_lib
import spawn_lib

CACHE = Path(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache")


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


def main() -> None:
    con = sqlite3.connect(CACHE / "cache.sqlite")
    arenas = con.execute(
        "SELECT arena_key, build, duration_sec FROM arena "
        "WHERE family='Naval_Defense' AND bracket='BASE' ORDER BY build"
    ).fetchall()

    for a, build, dur in arenas:
        print(f"\n===== {a} build={build} dur={dur:.1f}s =====")
        packets = cache_lib.load_packets(CACHE, a)

        # 1) ALL 0x05 creates with clock and position (any entity)
        creates = []
        for ptype, clock, payload in spawn_lib.packet_iter(packets):
            if ptype == 0x05 and len(payload) >= 26:
                eid = struct.unpack_from("<I", payload, 0)[0]
                x, _y, z = struct.unpack_from("<fff", payload, 14)
                creates.append((eid, clock, x, z))
        print(f"total EntityCreate(0x05): {len(creates)}")

        # 2) every IDS_* token in the stream (unique)
        names = sorted(set(re.findall(rb"IDS_[A-Za-z0-9_]+", packets)))
        allied = [n.decode() for n in names if b"ALLY" in n or b"REIN" in n or b"SUPP" in n]
        print("IDS names:", len(names))
        print("ally-ish names:", allied)

        # 3) tasks in 0x22 commonList
        j = battle_json(packets)
        if j:
            cl = j.get("commonList") or []
            tasks = []
            for item in cl:
                if isinstance(item, dict) and "tasks" in item:
                    tasks.extend(item["tasks"])
                elif isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, dict) and "tasks" in sub:
                            tasks.extend(sub["tasks"])
            names_t = [t.get("name") or t.get("id") for t in tasks if isinstance(t, dict)]
            print("tasks:", names_t)
            rein = [n for n in names_t if n and ("REIN" in n.upper() or "ALLY" in n.upper() or "SUPP" in n.upper())]
            print("reinforcement-ish tasks:", rein)

        # 4) notify messages with 增援/reinforce keywords
        for needle in [b"reinforce", b"Reinforce", b"REINFORCE"]:
            cnt = packets.count(needle)
            if cnt:
                print(f"stream contains {needle!r}: {cnt} times")
                pos = packets.find(needle)
                print("   ctx:", packets[max(0, pos - 90):pos + 90])

    # all allied entities across every Newport arena
    print("\n===== ALLY entities across all Newport arenas =====")
    rows = con.execute(
        "SELECT name, display_name, ship_name, team_id, COUNT(*), "
        "MIN(spawn_clock), MAX(spawn_clock) FROM spawns "
        "WHERE family='Naval_Defense' GROUP BY name, display_name, team_id "
        "ORDER BY name"
    ).fetchall()
    for r in rows:
        print("  ", r)

    # very-late creates (clock > 700s) that are not player ships
    print("\n===== late EntityCreate probes (all Newport) =====")
    arenas_all = con.execute(
        "SELECT arena_key FROM arena WHERE family='Naval_Defense'"
    ).fetchall()
    for (a,) in arenas_all:
        packets = cache_lib.load_packets(CACHE, a)
        for ptype, clock, payload in spawn_lib.packet_iter(packets):
            if ptype == 0x05 and clock > 700.0 and len(payload) >= 26:
                eid = struct.unpack_from("<I", payload, 0)[0]
                x, _y, z = struct.unpack_from("<fff", payload, 14)
                # known player spawn slots
                slots = [(222, -410), (251, -343), (297, -490), (343, -261),
                         (400, -400), (410, -222), (490, -297), (505, -518)]
                near = any((x - sx) ** 2 + (z - sz) ** 2 < 900 for sx, sz in slots)
                if not near:
                    print(f"  {a} eid={eid} clock={clock:.1f} pos=({x:.0f},{z:.0f})")


if __name__ == "__main__":
    main()
