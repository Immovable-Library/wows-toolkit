#!/usr/bin/env python3
"""Test what triggers the Narai wave-1 spawn (Cuirassier / Alpha / Bravo).

Wave-1 spawn time comes from the cache spawn_clock (the unique 0x08 roster
packet). We compare it against (a) friendly transport A_1 movement onset and
(b) player positions at the spawn moment, to test event-trigger hypotheses.
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
OUT = r"D:/codexProject/wows-toolkit/output/那莱/wave1_spawn_trigger.json"

TRANSPORT_SPAWNS = {
    (-411.4, 397.5), (-437.4, 428.5), (-381.4, 422.5),
    (-410.4, 450.5), (-409.4, 424.5),
}
WAVE1_SPAWN = (-520.0, 100.0)
A1_SPAWN = (-411.4, 397.5)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def main() -> None:
    con = sqlite3.connect(DB)
    arenas = [r[0] for r in con.execute(
        "SELECT DISTINCT arena_key FROM spawns WHERE family='Advance' AND name='IDS_OP_02_03_AT_ATTAKA_FR_11'")]
    out = []
    for ak in arenas:
        rows = {n: e for n, e, _ in con.execute(
            "SELECT name, entity_id, spawn_clock FROM spawns WHERE arena_key=? AND name IN (?, ?, ?)",
            (ak, "IDS_OP_02_03_AT_ATTAKA_FR_11", "IDS_OP_02_03_AT_TRANSPORT_A_1",
             "IDS_OP_02_03_AT_TRANSPORT_E_1")).fetchall()}
        fr11 = con.execute(
            "SELECT spawn_clock FROM spawns WHERE arena_key=? AND name='IDS_OP_02_03_AT_ATTAKA_FR_11'",
            (ak,)).fetchone()
        if not fr11:
            continue
        spawn = fr11[0]
        a1_eid = rows.get("IDS_OP_02_03_AT_TRANSPORT_A_1")
        fr_eid = rows.get("IDS_OP_02_03_AT_ATTAKA_FR_11")
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
                if peid == a1_eid or peid == fr_eid or peid in players:
                    pos[peid].append((clock, (x, z)))
        # closest player to wave-1 spawn at spawn time
        best = None
        for peid, pts in pos.items():
            if peid == a1_eid or peid == fr_eid:
                continue
            for c, p in pts:
                if abs(c - spawn) <= 3:
                    d = dist(p, WAVE1_SPAWN)
                    if best is None or d < best[0]:
                        best = (d, p[0], p[1])
        # A_1 position at spawn time and its movement onset
        a1_at = None
        a1_onset = None
        if a1_eid and pos.get(a1_eid):
            pts = pos[a1_eid]
            for c, p in pts:
                if a1_at is None and abs(c - spawn) <= 3:
                    a1_at = p
            for c, p in pts:
                if a1_onset is None and dist(p, A1_SPAWN) > 8:
                    a1_onset = c
        out.append({
            "arena": ak,
            "spawn": round(spawn, 2),
            "closest_player_dist": round(best[0], 1) if best else None,
            "closest_player_x": round(best[1], 1) if best else None,
            "closest_player_z": round(best[2], 1) if best else None,
            "a1_z_at_spawn": round(a1_at[1], 1) if a1_at else None,
            "a1_onset": round(a1_onset, 1) if a1_onset else None,
        })
    con.close()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    import statistics
    valid = [r for r in out if r["spawn"] > 1.0]  # exclude pre-start anomalies
    print("arenas:", len(out), "valid (spawn>1):", len(valid))
    sp = sorted(r["spawn"] for r in valid)
    print("spawn: p10=%.1f med=%.1f p90=%.1f" % (sp[len(sp)//10], sp[len(sp)//2], sp[min(len(sp)-1, int(len(sp)*.9))]))
    cp = [r for r in valid if r["closest_player_dist"] is not None]
    ds = sorted(r["closest_player_dist"] for r in cp)
    print("closest player dist to wave1 spawn: med=%.0f (p25 %.0f p75 %.0f)" % (
        ds[len(ds)//2], ds[len(ds)//4], ds[3*len(ds)//4]))
    zs = sorted(r["closest_player_z"] for r in cp)
    print("closest player z: p10=%.0f med=%.0f p90=%.0f" % (
        zs[len(zs)//10], zs[len(zs)//2], zs[min(len(zs)-1, int(len(zs)*.9))]))
    a1o = [(r["spawn"], r["a1_onset"]) for r in valid if r["a1_onset"] is not None]
    if len(a1o) >= 10:
        xs = [a for a, _ in a1o]
        ys = [b for _, b in a1o]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        cov = sum((a-mx)*(b-my) for a, b in zip(xs, ys))
        sx = (sum((a-mx)**2 for a in xs))**0.5
        sy = (sum((b-my)**2 for b in ys))**0.5
        print("corr(spawn, A1_onset) = %.2f (n=%d)" % (cov/(sx*sy), len(a1o)))
    az = [(r["spawn"], r["a1_z_at_spawn"]) for r in valid if r["a1_z_at_spawn"] is not None]
    if len(az) >= 10:
        zs2 = sorted(b for _, b in az)
        print("A1 z at spawn time: p10=%.0f med=%.0f p90=%.0f" % (
            zs2[len(zs2)//10], zs2[len(zs2)//2], zs2[min(len(zs2)-1, int(len(zs2)*.9))]))


if __name__ == "__main__":
    main()
