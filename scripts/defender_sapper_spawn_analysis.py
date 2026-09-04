#!/usr/bin/env python3
"""Determine spawn point and spawn time for Defender (E_5) and Sapper (SHIP_DEFENDER_4).

Both are warships, not transports: they move. The spawn point is inferred from
arenas where the ship was observed stationary for >= 30 s right after its first
position packet (the earliest such cluster). Spawn time comes from the cache
spawn_clock (first appearance of the bot pickle in the packet stream).
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
OUT = r"D:/codexProject/wows-toolkit/output/那莱/defender_sapper_spawn_analysis.json"

TARGETS = {
    "IDS_OP_02_03_AT_TRANSPORT_E_5": "Defender",
    "IDS_OP_02_03_AT_SHIP_DEFENDER_4": "Sapper",
}
DIST = 8.0
STILL_S = 30.0


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def main() -> None:
    con = sqlite3.connect(DB)
    arenas = [r[0] for r in con.execute("SELECT DISTINCT arena_key FROM spawns WHERE family='Advance'")]
    results = []
    for ak in arenas:
        rows = con.execute(
            "SELECT name, entity_id, spawn_clock, first_seen_clock, first_seen_x, first_seen_z "
            "FROM spawns WHERE arena_key=? AND name IN (?, ?)",
            (ak, "IDS_OP_02_03_AT_TRANSPORT_E_5", "IDS_OP_02_03_AT_SHIP_DEFENDER_4"),
        ).fetchall()
        if not rows:
            continue
        emap = {n: (e, sc, fc, fx, fz) for n, e, sc, fc, fx, fz in rows}
        idx = con.execute(
            "SELECT packet_type, clock, payload_offset, payload_size FROM packet_index "
            "WHERE arena_key=? AND packet_type IN (5, 10) ORDER BY seq",
            (ak,),
        ).fetchall()
        packets = cl.load_packets(CACHE_DIR, ak)
        pos = collections.defaultdict(list)
        creates = collections.defaultdict(list)
        eids = {v[0] for v in emap.values()}
        for ptype, clock, off, size in idx:
            payload = packets[off : off + size]
            if ptype == 5 and len(payload) >= 26:
                eid = struct.unpack_from("<I", payload, 0)[0]
                if eid in eids:
                    x, _y, z = struct.unpack_from("<fff", payload, 14)
                    creates[eid].append((clock, (x, z)))
            elif ptype == 10 and len(payload) >= 20:
                eid = struct.unpack_from("<I", payload, 0)[0]
                if eid in eids:
                    x, _y, z = struct.unpack_from("<fff", payload, 8)
                    pos[eid].append((clock, (x, z)))
        for nm, (eid, sc, fc, fx, fz) in emap.items():
            ps = pos.get(eid, [])
            cs = creates.get(eid, [])
            anchor = None
            onset = None
            first_seen = ps[0][0] if ps else (cs[0][0] if cs else None)
            if ps:
                p0 = ps[0][1]
                t0 = ps[0][0]
                moved_at = None
                for c, p in ps:
                    if moved_at is None and dist(p, p0) > DIST:
                        moved_at = c
                if moved_at is None or moved_at - t0 >= STILL_S:
                    anchor = p0
                onset = moved_at
            results.append(
                {
                    "arena": ak,
                    "ship": TARGETS[nm],
                    "spawn_clock": sc,
                    "first_seen": first_seen,
                    "first_seen_x": fx,
                    "first_seen_z": fz,
                    "anchor_x": anchor[0] if anchor else None,
                    "anchor_z": anchor[1] if anchor else None,
                    "onset": onset,
                    "n_pos": len(ps),
                    "create": [(round(c, 1), (round(p[0], 1), round(p[1], 1))) for c, p in cs[:2]],
                }
            )
    con.close()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    by = collections.defaultdict(list)
    for r in results:
        by[r["ship"]].append(r)
    for ship in ("Defender", "Sapper"):
        vals = by[ship]
        anchors = [(r["anchor_x"], r["anchor_z"]) for r in vals if r["anchor_x"] is not None]
        fs = sorted(r["first_seen"] for r in vals if r["first_seen"] is not None)
        scs = sorted(r["spawn_clock"] for r in vals)
        ons = sorted(r["onset"] for r in vals if r["onset"] is not None)
        print(ship, "arenas=%d" % len(vals))
        print("  spawn_clock: min=%.1f med=%.1f max=%.1f" % (scs[0], scs[len(scs) // 2], scs[-1]))
        if fs:
            print("  first_seen: min=%.1f med=%.1f max=%.1f" % (fs[0], fs[len(fs) // 2], fs[-1]))
        if anchors:
            xs = sorted(a[0] for a in anchors)
            zs = sorted(a[1] for a in anchors)
            print("  anchors n=%d: x med=%.1f (min %.1f max %.1f)  z med=%.1f (min %.1f max %.1f)"
                  % (len(anchors), xs[len(xs) // 2], xs[0], xs[-1], zs[len(zs) // 2], zs[0], zs[-1]))
            # most common rounded anchor
            c = collections.Counter((round(a[0]), round(a[1])) for a in anchors)
            print("  top anchors:", c.most_common(6))
        if ons:
            print("  onset: min=%.1f med=%.1f max=%.1f" % (ons[0], ons[len(ons) // 2], ons[-1]))


if __name__ == "__main__":
    main()
