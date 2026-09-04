#!/usr/bin/env python3
"""Variant distribution of all Newport games, focusing on G boss games."""

from __future__ import annotations

import importlib.util
import sys

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-map-spawn-atlas/scripts")
spec = importlib.util.spec_from_file_location(
    "rm", r"C:/Users/asdfg/.codex/skills/wows-map-spawn-atlas/scripts/render_map_spawns.py"
)
rm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rm)
import cache_lib
from collections import Counter

con = cache_lib.connect(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite")
arenas = con.execute(
    "SELECT arena_key, bracket FROM arena WHERE family='Naval_Defense'"
).fetchall()
dist = Counter()
games = {}
for a, br in arenas:
    try:
        dr, boss = rm.naval_variant_of(con, a)
    except Exception as exc:
        dr, boss = "ERR", str(exc)
    dist[(br, dr, boss)] += 1
    games.setdefault((br, dr, boss), []).append(a)

print("== distribution (bracket, direction, boss) ==")
for k in sorted(dist, key=lambda k: (str(k[0]), str(k[1]), str(k[2]))):
    print(f"  {k}: {dist[k]}  {games[k]}")
