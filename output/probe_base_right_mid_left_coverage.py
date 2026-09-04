#!/usr/bin/env python3
"""Which ships in the BASE 右中左-K game lack manual confirmation?"""

from __future__ import annotations

import json
import sqlite3

DB = r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite"
CONFIRM = r"C:/Users/asdfg/.codex/skills/wows-map-spawn-atlas/confirmed_spawns.json"
ARENA = "a3716634545160731"  # the only BASE 右中左 K game


def main() -> None:
    con = sqlite3.connect(DB)
    ents = con.execute(
        "SELECT name, ship_name, spawn_clock, first_seen_x, first_seen_z, max_health "
        "FROM spawns WHERE arena_key=? ORDER BY spawn_clock",
        (ARENA,),
    ).fetchall()
    conf = json.load(open(CONFIRM, encoding="utf-8"))
    print(f"game entities: {len(ents)}")
    print("manual-confirm coverage (BASE):")
    missing = []
    for name, ship, clk, x, z, hp in ents:
        key = f"Naval_Defense/BASE/{name}"
        if key in conf:
            c = conf[key]
            pos = c.get("positions") or [{"x": c.get("x"), "z": c.get("z")}]
            print(f"  [OK] {name} {ship}  conf={pos}  obs=({x:.0f},{z:.0f}) clk={clk:.1f}")
        else:
            print(f"  [NO-CONF] {name} {ship}  obs=({x:.0f},{z:.0f}) clk={clk:.1f}")
            missing.append((name, ship, clk, x, z))
    print(f"\nno-confirm count: {len(missing)}")
    for m in missing:
        print("  ", m)


if __name__ == "__main__":
    main()
