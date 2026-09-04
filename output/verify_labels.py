#!/usr/bin/env python3
"""Verify generated labels for unconfirmed Newport ships."""

from __future__ import annotations

import importlib.util
import sqlite3
import statistics
import sys

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")
sys.path.insert(0, r"D:/codexProject/wows-toolkit/output")
spec = importlib.util.spec_from_file_location(
    "rm", r"C:/Users/asdfg/.codex/skills/wows-map-spawn-atlas/scripts/render_map_spawns.py"
)
rm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rm)
import spawn_lib as lib

ship_zh = lib.load_ship_zh(r"D:/codexProject/wows-toolkit/ships_zh.json")
con = sqlite3.connect(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite")
rows = con.execute(
    "SELECT name, ship_id, spawn_clock FROM spawns "
    "WHERE arena_key=? AND name IN (?, ?, ?, ?, ?, ?, ?, ?) ORDER BY spawn_clock",
    (
        "a3716634545160731",
        "IDS_OP_01_04_ATAKER_CR_33",
        "IDS_OP_01_04_ATAKER_CR_34",
        "IDS_OP_01_04_ATAKER_CR_35",
        "IDS_OP_01_04_ATAKER_CR_36",
        "IDS_OP_01_04_ATAKER_L6",
        "IDS_OP_01_04_ATAKER_L7",
        "IDS_OP_01_04_ATAKER_CR_17",
        "IDS_OP_01_04_ATAKER_L8",
    ),
).fetchall()
for name, sid, clk in rows:
    ship = lib.ship_name(ship_zh, sid)
    wave = rm.wave_of(statistics.median([clk]))
    label = f"{wave} {ship}"
    if wave == "波1":
        label = f"{wave} {ship} 19:55"
    print(name, "->", repr(label))
