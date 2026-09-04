#!/usr/bin/env python3
"""Split the two Apache (ATTAKA_US_51) entries in the Narai calibration stats.

Same callsign/IDS name, two ships: Farragut (11500 hp, initial) and Jervis
(14300 hp, final reinforcement). Recomputes per-group stats from the cache and
renders one scatter PNG per ship.
"""

from __future__ import annotations

import collections
import json
import sqlite3
import statistics
import sys

sys.path.insert(0, r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")
import spawn_lib as lib  # noqa: E402
import probe_ship  # noqa: E402

DB = r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite"
STATS = r"D:/codexProject/wows-toolkit/output/那莱/标定统计.json"
OUT_DIR = r"D:/codexProject/wows-toolkit/output/那莱/散点图/spawn_probe_Advance/未标定"
GAME_DIR = r"D:/World_of_Warships"
BUILD = 13015811
SPACE = 1000
NAME = "IDS_OP_02_03_AT_ATTAKA_US_51"

GROUPS = [
    (11500, "波0", "法拉格特", "Apache（法拉格特，开局）"),
    (14300, "波4", "杰维斯", "Apache（杰维斯，增援）"),
]


def cluster_stats(pts: list[tuple[float, float]]) -> tuple[float, float, int, str]:
    if not pts:
        return 0.0, 0.0, 0, ""
    grid = collections.Counter((round(x / 20) * 20, round(z / 20) * 20) for x, z in pts)
    (cx, cz), _ = grid.most_common(1)[0]
    n = sum(1 for x, z in pts if abs(x - cx) <= 50 and abs(z - cz) <= 50)
    return cx, cz, n, lib.cell_of(cx, cz, SPACE)


def main() -> None:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT max_health, spawn_clock, first_seen_clock, first_seen_x, first_seen_z "
        "FROM spawns WHERE family='Advance' AND name=? AND max_health IN (11500, 14300)",
        (NAME,),
    ).fetchall()
    con.close()

    stats = json.load(open(STATS, encoding="utf-8"))
    stats["ships"] = [s for s in stats["ships"] if s["name"] != NAME]

    for hp, wave, ship_cn, disp in GROUPS:
        grp = [r for r in rows if r[0] == hp]
        scs = sorted(r[1] for r in grp)
        fss = sorted(r[2] for r in grp if r[2] is not None)
        pts = [(r[3], r[4]) for r in grp if r[3] is not None and r[4] is not None]
        early = sorted(grp, key=lambda r: r[2] if r[2] is not None else 9e9)[:20]
        early = [(r[3], r[4]) for r in early if r[3] is not None and r[4] is not None]
        ex = statistics.mean(p[0] for p in early) if early else 0.0
        ez = statistics.mean(p[1] for p in early) if early else 0.0
        cx, cz, cn, cell = cluster_stats(pts)
        png = r"%s\%s_%s_Apache.png" % (OUT_DIR, wave, ship_cn)
        probe_points = [(NAME, r[2], r[3], r[4], disp) for r in grp if r[3] is not None and r[4] is not None]
        probe_ship.render(probe_points, BUILD, GAME_DIR, "Advance", "%s 首次被点亮位置 ×%d" % (disp, len(probe_points)), png)
        stats["ships"].append({
            "wave": wave,
            "name": NAME,
            "display_name": disp,
            "ship_name": ship_cn,
            "max_health": hp,
            "n": len(grp),
            "n_pos": len(pts),
            "spawn_clock_median": round(scs[len(scs) // 2], 1),
            "spawn_clock_min": round(scs[0], 1),
            "spawn_clock_max": round(scs[-1], 1),
            "first_seen_clock_min": round(fss[0], 1),
            "first_seen_clock_max": round(fss[-1], 1),
            "early20_mean_x": round(ex, 1),
            "early20_mean_z": round(ez, 1),
            "cluster_x": cx,
            "cluster_z": cz,
            "cluster_n": cn,
            "cell": cell,
            "png": png,
        })

    stats["ships"].sort(key=lambda s: (s["wave"], s["display_name"]))
    json.dump(stats, open(STATS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for s in stats["ships"]:
        if s.get("max_health") in (11500, 14300):
            print("%-32s n=%d spawn=%s first_seen=%s~%s cluster=(%s,%s,%d) %s" % (
                s["display_name"], s["n"], s["spawn_clock_median"], s["first_seen_clock_min"],
                s["first_seen_clock_max"], s["cluster_x"], s["cluster_z"], s["cluster_n"], s["png"].split("\\")[-1]))


if __name__ == "__main__":
    main()
