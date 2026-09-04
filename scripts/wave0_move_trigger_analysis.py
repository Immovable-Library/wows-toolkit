#!/usr/bin/env python3
"""Test Foxtrot / King / Apache(Farragut) movement trigger: proximity vs spot vs damage."""

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
OUT = r"D:/codexProject/wows-toolkit/output/那莱/wave0_move_trigger.json"

TRANSPORT_SPAWNS = {
    (-411.4, 397.5), (-437.4, 428.5), (-381.4, 422.5),
    (-410.4, 450.5), (-409.4, 424.5),
}
SHIPS = {
    "IDS_OP_02_03_AT_ATTAKA_US_23": "Foxtrot",
    "IDS_OP_02_03_AT_ATTAKA_US_A1": "King",
    "IDS_OP_02_03_AT_ATTAKA_US_51": "Apache-Farragut",  # 11500 hp only
}


def main() -> None:
    con = sqlite3.connect(DB)
    arenas = [r[0] for r in con.execute("SELECT DISTINCT arena_key FROM spawns WHERE family='Advance'")]

    # damage from wave_raw.jsonl (per ship account)
    dmg = {}
    for ln in open(r"D:/codexProject/wows-toolkit/output/wave_raw.jsonl", encoding="utf-8"):
        d = json.loads(ln)
        if d.get("family") != "Advance":
            continue
        ak = "a%d" % d["arena_id"]
        aids = {}
        for e in d["entities"]:
            if e["name"] in SHIPS:
                key = e["name"]
                if key == "IDS_OP_02_03_AT_ATTAKA_US_51" and e.get("max_health") != 11500:
                    continue
                aids[key] = e["account_id"]
        dt = {}
        for p in d["players"]:
            for k, v in p.get("victims", {}).items():
                for nm, aid in aids.items():
                    if int(k) == aid:
                        dt[nm] = dt.get(nm, 0.0) + v
        dmg[ak] = dt

    results = []
    for ak in arenas:
        packets = cl.load_packets(CACHE_DIR, ak)
        players = set()
        pos = collections.defaultdict(list)
        eids = {}
        for nm in SHIPS:
            q = "SELECT entity_id, first_seen_clock FROM spawns WHERE arena_key=? AND name=?"
            args = [ak, nm]
            if nm == "IDS_OP_02_03_AT_ATTAKA_US_51":
                q += " AND max_health=11500"
            r = con.execute(q, args).fetchone()
            if r:
                eids[nm] = r
        for ptype, clock, payload in lib.packet_iter(packets):
            if ptype == 0x05 and len(payload) >= 26 and clock < 1.0:
                peid = struct.unpack_from("<I", payload, 0)[0]
                x, _y, z = struct.unpack_from("<fff", payload, 14)
                if (round(x, 1), round(z, 1)) not in TRANSPORT_SPAWNS and not (x == 0 and z == 0):
                    players.add(peid)
            elif ptype == 0x0A and len(payload) >= 20:
                peid = struct.unpack_from("<I", payload, 0)[0]
                if peid in players or any(peid == v[0] for v in eids.values()):
                    x, _y, z = struct.unpack_from("<fff", payload, 8)
                    pos[peid].append((clock, (x, z)))
        for nm, label in SHIPS.items():
            if nm not in eids:
                continue
            eid, fc = eids[nm]
            pts = pos.get(eid, [])
            if not pts:
                continue
            p0 = pts[0][1]
            onset = None
            for c, p in pts:
                if onset is None and math.hypot(p[0] - p0[0], p[1] - p0[1]) > 8:
                    onset = c
            best = None
            if onset is not None:
                ship_at = None
                for c, p in pts:
                    if abs(c - onset) <= 8:
                        ship_at = p
                        break
                if ship_at:
                    for peid, ppts in pos.items():
                        if peid == eid:
                            continue
                        for c, p in ppts:
                            if abs(c - onset) <= 8:
                                d = math.hypot(p[0] - ship_at[0], p[1] - ship_at[1])
                                if best is None or d < best:
                                    best = d
            results.append({
                "arena": ak,
                "ship": label,
                "onset": onset,
                "first_seen": fc,
                "min_player_dist": round(best, 1) if best is not None else None,
                "self_dmg": dmg.get(ak, {}).get(nm, 0.0),
            })
    con.close()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    by = collections.defaultdict(list)
    for r in results:
        by[r["ship"]].append(r)
    for ship, rows in by.items():
        moved = [r for r in rows if r["onset"] is not None]
        zero_dmg = [r for r in moved if r["self_dmg"] == 0]
        ds = sorted(r["min_player_dist"] for r in moved if r["min_player_dist"] is not None)
        delays = sorted(r["onset"] - r["first_seen"] for r in moved if r["first_seen"] is not None and r["onset"] - r["first_seen"] > 0)
        def q(v, p):
            return v[min(len(v) - 1, int(len(v) * p))]
        print("====", ship, "n=%d moved=%d" % (len(rows), len(moved)))
        print("  零伤害移动: %d/%d (%.0f%%)" % (len(zero_dmg), len(moved), 100 * len(zero_dmg) / len(moved) if moved else 0))
        if ds:
            print("  onset时最近玩家距离: med=%.0f (p25 %.0f p75 %.0f, max %.0f)" % (q(ds, .5), q(ds, .25), q(ds, .75), ds[-1]))
        if delays:
            print("  onset-首亮: med=%.1f (p90 %.1f)" % (q(delays, .5), q(delays, .9)))


if __name__ == "__main__":
    main()
