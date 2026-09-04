#!/usr/bin/env python3
"""Analyze Newport player spawn slot vs ship class.

Player ship entities are 0x05 EntityCreate packets at clock ~0 sitting on the
8 fixed candidate spawn slots. The WG shipId is embedded in each create
payload, so we can map entity -> shipId -> ships_cache type per game and
aggregate per-slot class distributions across all cached Newport replays.
"""

from __future__ import annotations

import json
import sqlite3
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")

import cache_lib
import spawn_lib

CACHE_DIR = Path(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache")
DB_PATH = CACHE_DIR / "cache.sqlite"
SHIPS = json.load(open(r"D:/codexProject/wows-toolkit/ships_cache.json", encoding="utf-8"))

CANDIDATES = {
    "P1": (222.0, -410.0),
    "P2": (251.0, -343.0),
    "P3": (297.0, -490.0),
    "P4": (343.0, -261.0),
    "P5": (400.0, -400.0),
    "P6": (410.0, -222.0),
    "P7": (490.0, -297.0),
    "P8": (505.0, -518.0),
}
SLOT_ORDER = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]


def nearest_slot(x: float, z: float, tol: float = 15.0) -> str | None:
    best, bd = None, 1e9
    for name, (sx, sz) in CANDIDATES.items():
        d = (x - sx) ** 2 + (z - sz) ** 2
        if d < bd:
            bd, best = d, name
    return best if bd < tol * tol else None


def battle_json(packets: bytes) -> dict | None:
    last = None
    for ptype, _clock, payload in spawn_lib.packet_iter(packets):
        if ptype == 0x22 and len(payload) >= 4:
            (jlen,) = struct.unpack_from("<I", payload, 0)
            if 4 + jlen <= len(payload):
                try:
                    j = json.loads(payload[4:4 + jlen].decode("utf-8", "replace"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    j = None
                if isinstance(j, dict) and "playersPublicInfo" in j:
                    last = j
    return last


def player_ship_ids(j: dict) -> list[int]:
    """WG shipIds of the 7 human players from battle results."""
    ppi = j.get("playersPublicInfo", {})
    out = []
    for v in ppi.values():
        if isinstance(v, list) and len(v) > 7 and isinstance(v[1], str):
            if not v[1].startswith("IDS_"):
                out.append(v[7])
    return list(dict.fromkeys(out))


def player_creates(packets: bytes, ship_ids: list[int]) -> list[dict]:
    """(eid, slot, x, z, shipId, clock) for player entities on candidate slots."""
    sid_bytes = {sid: struct.pack("<I", sid) for sid in ship_ids}
    out = []
    for ptype, clock, payload in spawn_lib.packet_iter(packets):
        if ptype != 0x05 or clock > 2.0 or len(payload) < 26:
            continue
        eid = struct.unpack_from("<I", payload, 0)[0]
        x, _y, z = struct.unpack_from("<fff", payload, 14)
        slot = nearest_slot(x, z)
        if slot is None:
            continue
        hits = [sid for sid in ship_ids if sid_bytes[sid] in payload]
        if len(hits) == 1:
            out.append({"eid": eid, "slot": slot, "x": x, "z": z, "ship_id": hits[0], "clock": clock})
        elif len(hits) > 1:
            out.append({"eid": eid, "slot": slot, "x": x, "z": z, "ship_id": hits, "clock": clock, "ambiguous": True})
    return out


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    arenas = con.execute(
        "SELECT arena_key, bracket, build, duration_sec FROM arena WHERE family='Naval_Defense' ORDER BY build"
    ).fetchall()

    rows = []
    problems = []
    per_bracket = defaultdict(lambda: {"games": 0, "players": 0, "slots": Counter(), "classes": Counter()})
    per_slot_class = Counter()
    per_slot = Counter()
    slot_class_by_bracket = Counter()
    slot_name_by_bracket = Counter()
    ambiguous = 0
    no_battle = 0

    for arena_key, bracket, build, dur in arenas:
        try:
            packets = cache_lib.load_packets(CACHE_DIR, arena_key)
        except Exception as exc:
            problems.append((arena_key, f"load: {exc}"))
            continue

        j = battle_json(packets)
        if j is None:
            no_battle += 1
            ship_ids = [int(k) for k in SHIPS]
        else:
            ship_ids = player_ship_ids(j)
        if not ship_ids:
            problems.append((arena_key, "no player ship ids"))
            continue

        creates = player_creates(packets, ship_ids)
        amb = [c for c in creates if c.get("ambiguous")]
        ambiguous += len(amb)
        valid = [c for c in creates if not c.get("ambiguous")]

        # Deduplicate by eid (first create wins; player ships created once).
        seen = set()
        uniq = []
        for c in sorted(valid, key=lambda c: c["clock"]):
            if c["eid"] not in seen:
                seen.add(c["eid"])
                uniq.append(c)

        # Fallback without battle results: search all known ship ids.
        if j is None:
            all_hits = []
            for ptype, clock, payload in spawn_lib.packet_iter(packets):
                if ptype != 0x05 or clock > 2.0 or len(payload) < 26:
                    continue
                eid = struct.unpack_from("<I", payload, 0)[0]
                x, _y, z = struct.unpack_from("<fff", payload, 14)
                slot = nearest_slot(x, z)
                if slot is None:
                    continue
                hits = [sid for sid in ship_ids if struct.pack("<I", sid) in payload]
                if len(hits) == 1 and eid not in seen:
                    seen.add(eid)
                    uniq.append({"eid": eid, "slot": slot, "x": x, "z": z, "ship_id": hits[0], "clock": clock})

        if not uniq:
            problems.append((arena_key, "no player creates on candidate slots"))
            continue

        stats = per_bracket[bracket]
        stats["games"] += 1
        stats["players"] += len(uniq)
        for c in uniq:
            sid = c["ship_id"]
            info = SHIPS.get(str(sid)) or SHIPS.get(sid)
            cls = info["type"] if info else "Unknown"
            rows.append({
                "arena": arena_key,
                "bracket": bracket,
                "build": build,
                "slot": c["slot"],
                "x": round(c["x"], 1),
                "z": round(c["z"], 1),
                "ship_id": sid,
                "class": cls,
                "name": info["name"] if info else None,
                "tier": info["tier"] if info else None,
            })
            stats["slots"][c["slot"]] += 1
            stats["classes"][cls] += 1
            per_slot[c["slot"]] += 1
            per_slot_class[(c["slot"], cls)] += 1
            slot_class_by_bracket[(bracket, c["slot"], cls)] += 1
            slot_name_by_bracket[(bracket, c["slot"], info["name"] if info else "Unknown")] += 1

    print(f"arenas: {len(arenas)}, analyzed: {sum(s['games'] for s in per_bracket.values())}, "
          f"no-battle(fallback): {no_battle}, ambiguous creates: {ambiguous}, problems: {len(problems)}")
    for p in problems[:20]:
        print("  problem:", p)

    print("\n== per bracket ==")
    for br in ["BASE", "MEDIUM", "HIGH"]:
        s = per_bracket[br]
        if s["games"] == 0:
            continue
        print(f"{br}: games={s['games']}, players={s['players']}, avg={s['players']/s['games']:.2f}")
        print("  classes:", dict(s["classes"]))
        print("  slots:", {k: s["slots"][k] for k in SLOT_ORDER})

    print("\n== slot x class (all brackets) ==")
    header = "slot |" + " |".join(f"{cls:>12}" for cls in ["Battleship", "Cruiser", "Destroyer", "AirCarrier", "Submarine", "Unknown"])
    print(header)
    for sl in SLOT_ORDER:
        cells = [str(per_slot_class.get((sl, cls), 0)) for cls in
                 ["Battleship", "Cruiser", "Destroyer", "AirCarrier", "Submarine", "Unknown"]]
        print(f"{sl:4} |" + " |".join(f"{c:>12}" for c in cells))
    print("total|" + " |".join(f"{sum(per_slot_class.get((s, cls), 0) for s in SLOT_ORDER):>12}" for cls in
                               ["Battleship", "Cruiser", "Destroyer", "AirCarrier", "Submarine", "Unknown"]))

    print("\n== slot x class per bracket ==")
    for br in ["BASE", "MEDIUM", "HIGH"]:
        s = per_bracket[br]
        if s["games"] == 0:
            continue
        print(f"-- {br} --")
        header = "slot |" + " |".join(f"{cls:>12}" for cls in ["Battleship", "Cruiser", "Destroyer", "AirCarrier", "Submarine", "Unknown"])
        print(header)
        for sl in SLOT_ORDER:
            cells = [str(slot_class_by_bracket[(br, sl, cls)]) for cls in
                     ["Battleship", "Cruiser", "Destroyer", "AirCarrier", "Submarine", "Unknown"]]
            if any(int(c) for c in cells):
                print(f"{sl:4} |" + " |".join(f"{c:>12}" for c in cells))

    print("\n== slot x top ship names (all brackets) ==")
    name_by_slot = Counter()
    for c in rows:
        name_by_slot[(c["slot"], c["name"])] += 1
    for sl in SLOT_ORDER:
        top = sorted(((n, cnt) for (slot, n), cnt in name_by_slot.items() if slot == sl), key=lambda t: -t[1])[:6]
        if top:
            print(f"{sl}: " + ", ".join(f"{n}x{cnt}" for n, cnt in top))

    print("\n== slot x tier (all brackets) ==")
    tier_by_slot = Counter((c["slot"], c["tier"]) for c in rows)
    for sl in SLOT_ORDER:
        t = sorted(((tier, n) for (slot, tier), n in tier_by_slot.items() if slot == sl and tier is not None), key=lambda x: x[0])
        if t:
            print(f"{sl}: " + ", ".join(f"T{tier}x{n}" for tier, n in t))

    with open(r"D:/codexProject/wows-toolkit/output/player_spawn_class_rows.json", "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print("\nrows written:", len(rows))


if __name__ == "__main__":
    main()
