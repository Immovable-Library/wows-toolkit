#!/usr/bin/env python3
"""Probe Newport BASE games for late allied destroyer reinforcements."""

from __future__ import annotations

import sqlite3

DB = r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite"


def main() -> None:
    con = sqlite3.connect(DB)
    arenas = con.execute(
        "SELECT arena_key, build, duration_sec FROM arena "
        "WHERE family='Naval_Defense' AND bracket='BASE' ORDER BY build"
    ).fetchall()
    print(f"BASE games: {len(arenas)}")
    for r in arenas:
        print(r)

    for a, build, dur in arenas:
        ents = con.execute(
            "SELECT name, display_name, ship_name, team_id, is_initial, "
            "spawn_clock, first_seen_clock, max_health, first_seen_x, first_seen_z "
            "FROM spawns WHERE arena_key=? ORDER BY spawn_clock",
            (a,),
        ).fetchall()
        print(f"\n== {a} build={build} dur={dur:.1f}s entities={len(ents)}")
        for e in ents:
            print("   ", e)


if __name__ == "__main__":
    main()
