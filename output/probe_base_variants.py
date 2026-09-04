#!/usr/bin/env python3
"""Print Naval_Defense BASE game variants (direction/boss)."""

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

con = cache_lib.connect(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite")
arenas = con.execute(
    "SELECT arena_key FROM arena WHERE family='Naval_Defense' AND bracket='BASE'"
).fetchall()
for (a,) in arenas:
    try:
        dr, boss = rm.naval_variant_of(con, a)
    except Exception as exc:
        dr, boss = "ERR", str(exc)
    print(a, dr, boss)
