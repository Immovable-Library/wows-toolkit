#!/usr/bin/env python3
"""Test whether Defender/Sapper movement onset correlates with player proximity.

Player entities are the 0x05 creates at t < 1s whose positions are not one of
the five friendly transport spawn points. For each anchored+moved arena we
record, at onset time, the minimum player distance and the closest player
position relative to the ship.
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
BEH = r"D:/codexProject/wows-toolkit/output/那莱/defender_sapper_spawn_analysis.json"

TRANSPORT_SPAWNS = {
    (-411.4, 397.5), (-437.4, 428.5), (-381.4, 422.5),
    (-410.4, 450.5), (-409.4, 424.5),
}
SHIPS = {
    "Defender": "IDS_OP_02_03_AT_TRANSPORT_E_5",
    "Sapper": "IDS_OP_02_03_AT_SHIP_DEFENDER_4",
}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def main() -> None:
    beh = json.load(open(BEH, encoding="utf-8"))
    beh_by = collections.defaultdict(dict)
    for r in beh:
        beh_by[r["arena"]][r["ship"]] = r

    con = sqlite3.connect(DB)
    out = []
    for ship, ids_name in SHIPS.items():
        arenas = [ak for ak, ships in beh_by.items()
                  if ship in ships and ships[ship]["anchor_x"] is not None and ships[ship]["onset"] is not None]
        print(ship, "anchored+moved arenas:", len(arenas))
        for ak in arenas:
            eid = con.execute("SELECT entity_id FROM spawns WHERE arena_key=? AND name=?", (ak, ids_name)).fetchone()
            if not eid:
                continue
            eid = eid[0]
            onset = beh_by[ak][ship]["onset"]
            packets = cl.load_packets(CACHE_DIR, ak)
            players = set()
            pos = collections.defaultdict(list)
            for ptype, clock, payload in lib.packet_iter(packets):
                if ptype == 0x05 and len(payload) >= 26:
                    peid = struct.unpack_from("<I", payload, 0)[0]
                    x, _y, z = struct.unpack_from("<fff", payload, 14)
                    if clock < 1.0 and (round(x, 1), round(z, 1)) not in TRANSPORT_SPAWNS and not (x == 0 and z == 0):
                        players.add(peid)
                elif ptype == 0x0A and len(payload) >= 20:
                    peid = struct.unpack_from("<I", payload, 0)[0]
                    x, _y, z = struct.unpack_from("<fff", payload, 8)
                    if peid == eid or peid in players:
                        pos[peid].append((clock, (x, z)))
            # closest player position near onset (+-8s), and ship position at onset
            ship_pts = pos.get(eid, [])
            ship_at_onset = None
            for c, p in ship_pts:
                if abs(c - onset) <= 8:
                    ship_at_onset = p
                    break
            best = None
            for peid, pts in pos.items():
                if peid == eid:
                    continue
                for c, p in pts:
                    if abs(c - onset) <= 8:
                        d = dist(p, ship_at_onset) if ship_at_onset else None
                        if d is not None and (best is None or d < best[0]):
                            best = (d, p[0], p[1])
            if best and ship_at_onset:
                out.append({
                    "arena": ak,
                    "ship": ship,
                    "onset": round(onset, 1),
                    "min_dist": round(best[0], 1),
                    "closest_player_x": round(best[1], 1),
                    "closest_player_z": round(best[2], 1),
                    "ship_x": round(ship_at_onset[0], 1),
                    "ship_z": round(ship_at_onset[1], 1),
                })
    con.close()
    with open(r"D:/codexProject/wows-toolkit/output/那莱/defender_sapper_trigger_proximity.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    by = collections.defaultdict(list)
    for r in out:
        by[r["ship"]].append(r)
    for ship, rows in by.items():
        ds = sorted(r["min_dist"] for r in rows)
        print(ship, "n=%d  min_dist: min=%.0f p25=%.0f med=%.0f p75=%.0f max=%.0f" % (
            len(ds), ds[0], ds[len(ds)//4], ds[len(ds)//2], ds[3*len(ds)//4], ds[-1]))
        # relative position of closest player to ship
        rels = [(r["closest_player_x"] - r["ship_x"], r["closest_player_z"] - r["ship_z"]) for r in rows]
        dx = sorted(r[0] for r in rels)
        dz = sorted(r[1] for r in rels)
        print("   rel dx: med=%.0f (p25 %.0f p75 %.0f)   rel dz: med=%.0f (p25 %.0f p75 %.0f)" % (
            dx[len(dx)//2], dx[len(dx)//4], dx[3*len(dx)//4],
            dz[len(dz)//2], dz[len(dz)//4], dz[3*len(dz)//4]))


if __name__ == "__main__":
    main()
