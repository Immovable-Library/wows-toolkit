#!/usr/bin/env python3
"""Analyze when the enemy transports of Advance (Narai) start moving.

For every cached Advance arena, extract the first Position that is more than
DIST meters away from the known stationary spawn point of each enemy transport
and the communications ship. Writes a JSON summary plus per-ship statistics.
"""

from __future__ import annotations

import collections
import json
import math
import sqlite3
import struct
import sys

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
import cache_lib as cl  # noqa: E402

CACHE_DIR = r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache"
DB = r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite"
OUT = r"D:/codexProject/wows-toolkit/output/那莱/transport_motion_analysis.json"

# Known stationary spawn points (consensus of all arenas where the ship was
# observed sitting still at the same spot).
TARGETS = {
    "IDS_OP_02_03_AT_TRANSPORT_E_1": (-45.4, -431.4),
    "IDS_OP_02_03_AT_TRANSPORT_E_2": (-151.4, -429.8),
    "IDS_OP_02_03_AT_TRANSPORT_E_3": (9.9, -431.1),
    "IDS_OP_02_03_AT_TRANSPORT_E_4": (22.0, -395.2),
    "IDS_OP_02_03_AT_COMMUNICATION": (-81.3, -331.8),
}
DIST = 8.0


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def main() -> None:
    con = sqlite3.connect(DB)
    arenas = [r[0] for r in con.execute("SELECT DISTINCT arena_key FROM spawns WHERE family='Advance'")]
    print("arenas:", len(arenas))

    results = []
    for ak in arenas:
        spawn_rows = con.execute(
            "SELECT name, entity_id, spawn_clock, first_seen_clock FROM spawns WHERE arena_key=?", (ak,)
        ).fetchall()
        emap = {n: e for n, e, _, _ in spawn_rows}
        smap = {n: (sc, fc) for n, _, sc, fc in spawn_rows}
        idx = con.execute(
            "SELECT packet_type, clock, payload_offset, payload_size FROM packet_index "
            "WHERE arena_key=? AND packet_type IN (5, 10) ORDER BY seq",
            (ak,),
        ).fetchall()
        packets = cl.load_packets(CACHE_DIR, ak)
        pos = collections.defaultdict(list)
        for ptype, clock, off, size in idx:
            payload = packets[off : off + size]
            if ptype == 5 and len(payload) >= 26:
                eid = struct.unpack_from("<I", payload, 0)[0]
                x, _y, z = struct.unpack_from("<fff", payload, 14)
                if eid in emap.values():
                    pos[eid].append((clock, (x, z)))
            elif ptype == 10 and len(payload) >= 20:
                eid = struct.unpack_from("<I", payload, 0)[0]
                x, _y, z = struct.unpack_from("<fff", payload, 8)
                if eid in emap.values():
                    pos[eid].append((clock, (x, z)))
        inv = {e: n for n, e in emap.items()}
        for eid, pts in pos.items():
            nm = inv[eid]
            if nm not in TARGETS:
                continue
            sp = TARGETS[nm]
            onset = None
            first_seen = None
            for c, p in pts:
                if first_seen is None:
                    first_seen = c
                if onset is None and dist(p, sp) > DIST:
                    onset = c
            results.append(
                {
                    "arena": ak,
                    "ship": nm.split("_")[-1],
                    "spawn_clock": smap[nm][0],
                    "first_seen": first_seen,
                    "onset": onset,
                    "n_pos": len(pts),
                }
            )
    con.close()

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("wrote", OUT, len(results))

    by = collections.defaultdict(list)
    for r in results:
        by[r["ship"]].append(r)
    for nm in by:
        vals = [r for r in by[nm] if r["onset"] is not None]
        seen = [r for r in by[nm] if r["first_seen"] is not None]
        on = sorted(r["onset"] for r in vals)
        fs = sorted(r["first_seen"] for r in seen)
        delay = sorted(r["onset"] - r["first_seen"] for r in vals if r["first_seen"] is not None)
        print(nm, "arenas=%d seen=%d onset_det=%d" % (len(by[nm]), len(seen), len(vals)))
        if on:
            print("   onset: min=%.0f p10=%.0f med=%.0f p90=%.0f max=%.0f" % (
                on[0], on[min(len(on) - 1, int(len(on) * 0.1))], on[len(on) // 2],
                on[min(len(on) - 1, int(len(on) * 0.9))], on[-1]))
        if delay:
            print("   onset-first_seen: min=%.0f med=%.0f max=%.0f" % (delay[0], delay[len(delay) // 2], delay[-1]))
        if fs:
            print("   first_seen: min=%.0f med=%.0f max=%.0f" % (fs[0], fs[len(fs) // 2], fs[-1]))


if __name__ == "__main__":
    main()
