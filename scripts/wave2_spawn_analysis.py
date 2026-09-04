#!/usr/bin/env python3
"""Spawn-point and spawn-time analysis for the Narai wave-2 ships.

For each wave-2 ship, find per-arena stationary anchors (first position held
for >= 10s) and report spawn time distribution (replay clock, event-triggered).
"""

from __future__ import annotations

import collections
import json
import math
import sqlite3
import struct
import sys

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")
sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
import spawn_lib as lib  # noqa: E402
import cache_lib as cl  # noqa: E402

CACHE_DIR = r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache"
DB = r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite"
OUT = r"D:/codexProject/wows-toolkit/output/那莱/wave2_spawn_analysis.json"

TARGETS = {
    "IDS_OP_02_03_AT_SHIP_DEFENDER_1": "Alligator",
    "IDS_OP_02_03_AT_ATTAKA_GB_33": "Royal",
    "IDS_OP_02_03_AT_SHIP_DEFENDER_3": "Elephant",
    "IDS_OP_02_03_AT_ATTAKA_US_21": "Omega",
    "IDS_OP_02_03_AT_ATTAKA_UR_21": "Ingénieur",
    "IDS_OP_02_03_AT_ATTAKA_FR_21": "Commandant",
    "IDS_OP_02_03_AT_ATTAKA_US_PORT": "Little trouble",
}
DIST = 8.0
STILL = 10.0


def main() -> None:
    con = sqlite3.connect(DB)
    arenas = [r[0] for r in con.execute("SELECT DISTINCT arena_key FROM spawns WHERE family='Advance'")]
    results = {nm: [] for nm in TARGETS}
    for ak in arenas:
        rows = con.execute(
            "SELECT name, entity_id, spawn_clock, first_seen_clock FROM spawns "
            "WHERE arena_key=? AND name IN (%s)" % ",".join("?" * len(TARGETS)),
            (ak,) + tuple(TARGETS),
        ).fetchall()
        if not rows:
            continue
        emap = {n: (e, sc, fc) for n, e, sc, fc in rows}
        packets = cl.load_packets(CACHE_DIR, ak)
        pos = collections.defaultdict(list)
        eids = {v[0] for v in emap.values()}
        for ptype, clock, payload in lib.packet_iter(packets):
            if ptype == 0x0A and len(payload) >= 20:
                peid = struct.unpack_from("<I", payload, 0)[0]
                if peid in eids:
                    x, _y, z = struct.unpack_from("<fff", payload, 8)
                    pos[peid].append((clock, (x, z)))
        for nm, (eid, sc, fc) in emap.items():
            ps = pos.get(eid, [])
            anchor = None
            onset = None
            if ps:
                p0 = ps[0][1]
                t0 = ps[0][0]
                for c, p in ps:
                    if onset is None and math.hypot(p[0] - p0[0], p[1] - p0[1]) > DIST:
                        onset = c
                if onset is None or onset - t0 >= STILL:
                    anchor = p0
            results[nm].append({
                "arena": ak,
                "spawn_clock": sc,
                "first_seen": fc,
                "anchor_x": anchor[0] if anchor else None,
                "anchor_z": anchor[1] if anchor else None,
                "onset": onset,
                "n_pos": len(ps),
            })
    con.close()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    for nm, label in TARGETS.items():
        rows = results[nm]
        anchors = [(r["anchor_x"], r["anchor_z"]) for r in rows if r["anchor_x"] is not None]
        scs = sorted(r["spawn_clock"] for r in rows if r["spawn_clock"] is not None)
        fss = sorted(r["first_seen"] for r in rows if r["first_seen"] is not None)
        print("====", label)
        print("  n=%d anchored=%d" % (len(rows), len(anchors)))
        if scs:
            print("  spawn_clock: min=%.1f p10=%.1f med=%.1f p90=%.1f max=%.1f" % (
                scs[0], scs[len(scs)//10], scs[len(scs)//2],
                scs[min(len(scs)-1, int(len(scs)*.9))], scs[-1]))
        if fss:
            print("  first_seen: min=%.1f med=%.1f max=%.1f" % (fss[0], fss[len(fss)//2], fss[-1]))
        if anchors:
            xs = sorted(a[0] for a in anchors)
            zs = sorted(a[1] for a in anchors)
            print("  anchor x: med=%.1f (p25 %.1f p75 %.1f)   z: med=%.1f (p25 %.1f p75 %.1f)" % (
                xs[len(xs)//2], xs[len(xs)//4], xs[3*len(xs)//4],
                zs[len(zs)//2], zs[len(zs)//4], zs[3*len(zs)//4]))
            c = collections.Counter((round(a[0]), round(a[1])) for a in anchors)
            print("  top anchors:", c.most_common(4))


if __name__ == "__main__":
    main()
