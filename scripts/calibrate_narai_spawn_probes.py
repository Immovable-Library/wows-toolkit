#!/usr/bin/env python3
"""Batch per-ship spawn probes for Narai (Advance, BASE) from the replay cache.

Renders one scatter plot per enemy ship (first-detected position across all
cached arenas) and writes a calibration worksheet. Data path is identical to
wows-ship-spawn-probe/probe_ship.py (cache query + first Position/EntityCreate
fallback); only the minimap is extracted once instead of per ship.

Output layout mirrors the Killer Whale calibration:
  output/那莱/散点图/spawn_probe_Advance/未标定/<波次>_<船名>_<呼号>.png
"""

from __future__ import annotations

import io
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROBE_SCRIPTS = Path(r"C:/Users/asdfg/.codex/skills/wows-ship-spawn-probe/scripts")
CACHE_SCRIPTS = Path(r"C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts")
for _p in (PROBE_SCRIPTS, CACHE_SCRIPTS):
    sys.path.insert(0, str(_p))

import spawn_lib as lib  # noqa: E402
import probe_ship  # noqa: E402
import cache_lib as cl  # noqa: E402

DB = r"C:/Users/asdfg/.codex/skills/wows-replay-cache/cache/cache.sqlite"
GAME_DIR = r"D:/World_of_Warships"
FAMILY = "Advance"
BRACKET = "BASE"
MAP_NAME = "Advance"
OUT_DIR = Path(r"D:/codexProject/wows-toolkit/output/那莱/散点图/spawn_probe_Advance/未标定")
WS_MD = Path(r"D:/codexProject/wows-toolkit/output/那莱/标定工作表.md")
WS_JSON = Path(r"D:/codexProject/wows-toolkit/output/那莱/标定统计.json")

CLUSTER_R = 50.0
EARLY_N = 20
GRID = 20.0

# Transport call signs without a ships_zh entry; use the Killer Whale naming.
TRANSPORT_ZH = {
    "Assault transport No.1": "运输船（剧情专用）",
    "Assault transport No.2": "运输船（剧情专用）",
    "Assault transport No.3": "运输船（剧情专用）",
    "Assault transport No.4": "运输船（剧情专用）",
    "Lead transport": "运输船（剧情专用）",
    "Communications Ship": "运输船（剧情专用）",
}


def wave_label(ids_name: str, spawn_median: float) -> str:
    if "TRANSPORT_E" in ids_name or "COMMUNICATION" in ids_name:
        return "波0"
    if ids_name in (
        "IDS_OP_02_03_AT_ATTAKA_US_21",  # Omega
        "IDS_OP_02_03_AT_ATTAKA_UR_21",  # Ingénieur
        "IDS_OP_02_03_AT_ATTAKA_FR_21",  # Commandant
        "IDS_OP_02_03_AT_ATTAKA_US_PORT",  # Little trouble
    ):
        return "波3"
    if ids_name == "IDS_OP_02_03_AT_ATTAKA_US_51":  # Apache: Farragut(波0) / Jervis(波5)
        return "波0" if spawn_median < 100 else "波5"
    if ids_name in (
        "IDS_OP_02_03_AT_ATTAKA_US_43",  # Quebec
        "IDS_OP_02_03_AT_ATTAKA_FR_23",  # General
    ):
        return "波5"
    if ids_name in (
        "IDS_OP_02_03_AT_ATTAKA_US_41",  # Cherokee
        "IDS_OP_02_03_AT_ATTAKA_US_40_ATLANTA",  # Gun
        "IDS_OP_02_03_AT_ATTAKA_UR_44",  # Uporniy
    ):
        return "波6"
    if spawn_median < 1.0:
        return "波0"
    if spawn_median < 60.0:
        return "波1"
    if spawn_median < 310.0:
        return "波2"
    if spawn_median < 700.0:
        return "波4"
    return "波6"


def resolve_build(game_dir: str, build: int, idx_base: str) -> int:
    p = Path(game_dir) / "bin" / str(build) / "idx" / (idx_base + ".idx")
    if p.exists():
        return build
    cand = lib._find_idx_any_build(game_dir, idx_base)
    return int(cand.parent.parent.name) if cand else build


def densest_cluster(pts):
    grid = Counter()
    for x, z in pts:
        grid[(round(x / GRID), round(z / GRID))] += 1
    (gx, gz), _ = grid.most_common(1)[0]
    cx, cz = gx * GRID, gz * GRID
    n = sum(1 for x, z in pts if (x - cx) ** 2 + (z - cz) ** 2 <= CLUSTER_R ** 2)
    return round(cx, 1), round(cz, 1), n


def render(points, png_bytes, space_size, label, out) -> None:
    """Mirror probe_ship.render visuals with a pre-extracted minimap."""
    base = Image.new("RGBA", (lib.NATIVE_MINIMAP, lib.NATIVE_MINIMAP), (156, 200, 230, 255))
    land = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    img = Image.alpha_composite(base, land)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
        font_small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 11)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    cell = lib.NATIVE_MINIMAP // 10
    for k in range(1, 10):
        draw.line([(k * cell, 0), (k * cell, lib.NATIVE_MINIMAP)], fill=(255, 255, 255, 120), width=1)
        draw.line([(0, k * cell), (lib.NATIVE_MINIMAP, k * cell)], fill=(255, 255, 255, 120), width=1)
    for k in range(10):
        draw.text((k * cell + cell / 2 - 4, 1), chr(ord("A") + k), fill="white", font=font_small, stroke_width=1, stroke_fill="black")
        draw.text((1, k * cell + cell / 2 - 5), str(k + 1), fill="white", font=font_small, stroke_width=1, stroke_fill="black")

    for _name, clock, x, z, disp in points:
        px, py = lib.to_px(x, z, space_size)
        r = 5
        draw.ellipse([px - r, py - r, px + r, py + r], fill=(230, 60, 40, 220), outline="white", width=1)

    draw.text((6, 6), "%s 首次被点亮位置 ×%d" % (label, len(points)),
              fill=(180, 20, 0), font=font, stroke_width=2, stroke_fill="black")

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def fmt_range(lo, hi, nd=1):
    if lo is None or hi is None:
        return "-"
    return f"{lo:.{nd}f}~{hi:.{nd}f}"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db = cl.connect(DB)
    rows = db.execute(
        "SELECT name, display_name, ship_name, COUNT(*), "
        "SUM(first_seen_x IS NOT NULL), "
        "MIN(spawn_clock), MAX(spawn_clock), "
        "MIN(first_seen_clock), MAX(first_seen_clock) "
        "FROM spawns WHERE family=? AND bracket=? "
        "GROUP BY name ORDER BY MIN(spawn_clock), name",
        (FAMILY, BRACKET),
    ).fetchall()
    coverage = db.execute(
        "SELECT a.scenario, COUNT(DISTINCT s.arena_key) "
        "FROM arena a JOIN spawns s ON s.arena_key=a.arena_key "
        "WHERE a.family=? AND a.bracket=? GROUP BY a.scenario",
        (FAMILY, BRACKET),
    ).fetchall()
    total_arenas = db.execute(
        "SELECT COUNT(*) FROM arena WHERE family=? AND bracket=?", (FAMILY, BRACKET)
    ).fetchone()[0]
    build = cl.query_arena_build(db, FAMILY) or 0
    db.close()

    used_build = resolve_build(GAME_DIR, build, lib.MAP_IDX[MAP_NAME])
    png_bytes, space_size = lib.extract_minimap(GAME_DIR, used_build, MAP_NAME)

    ships = []
    skipped = []
    for name, disp, ship_cn, n, npos, sp_min, sp_max, fs_min, fs_max in rows:
        if not npos:
            skipped.append((name, disp, ship_cn, n, npos))
            continue
        pts = [p for p in probe_ship.collect_from_cache(DB, FAMILY, disp)
               if p["first_seen_x"] is not None and p["display_name"] == disp]
        if not pts:
            skipped.append((name, disp, ship_cn, n, npos))
            continue
        ship_cn = TRANSPORT_ZH.get(disp, ship_cn)
        spawns = sorted(float(p["spawn_clock"]) for p in pts)
        sp_med = statistics.median(spawns)
        wave = wave_label(name, sp_med)
        early = sorted(
            pts,
            key=lambda p: p["first_seen_clock"]
            if p["first_seen_clock"] is not None
            else float("inf"),
        )[:EARLY_N]
        early = [p for p in early if p["first_seen_clock"] is not None]
        ex = [float(p["first_seen_x"]) for p in early]
        ez = [float(p["first_seen_z"]) for p in early]
        cx, cz, cn = densest_cluster(
            [(float(p["first_seen_x"]), float(p["first_seen_z"])) for p in pts]
        )
        label = f"{wave} {ship_cn} {disp}"
        out = OUT_DIR / f"{wave}_{ship_cn}_{disp}.png"
        render(
            [(p["arena_key"], p["first_seen_clock"], p["first_seen_x"],
              p["first_seen_z"], p["display_name"]) for p in pts],
            png_bytes, space_size, label, out,
        )
        ships.append({
            "wave": wave,
            "name": name,
            "display_name": disp,
            "ship_name": ship_cn,
            "n": n,
            "n_pos": len(pts),
            "spawn_clock_median": round(sp_med, 2),
            "spawn_clock_min": sp_min,
            "spawn_clock_max": sp_max,
            "first_seen_clock_min": fs_min,
            "first_seen_clock_max": fs_max,
            "early20_mean_x": round(statistics.mean(ex), 1),
            "early20_mean_z": round(statistics.mean(ez), 1),
            "cluster_x": cx,
            "cluster_z": cz,
            "cluster_n": cn,
            "cell": lib.cell_of(cx, cz, space_size),
            "png": str(out),
        })

    ships.sort(key=lambda s: (s["wave"], s["display_name"]))

    lines = []
    a = lines.append
    a("# 那莱 出生点标定工作表")
    a("")
    a(f"> 数据源：wows-replay-cache `cache.sqlite`（family=`{FAMILY}`，bracket=`{BRACKET}`）。")
    a(f"> 观测覆盖：缓存 {total_arenas} 局，其中 {sum(c[1] for c in coverage)} 局有 spawn 观测"
      f"（{'；'.join(f'{c[0]} {c[1]} 局' for c in coverage)}）。")
    a("> 口径：首次被点亮 = 第一个 Position(0x0a) 包，无则退化为 EntityCreate(0x05)，与 probe_ship.py 一致。")
    a(f"> 底图：spaces_advance（渲染 build {used_build}；缓存 build {build} 本地无 idx 时自动回退最新可用版本）。")
    a("> 波次：按 spawn_clock 中位数分桶（波0=开局在场/标定口径，波1~6=增援时序；敌方运输舰按标定口径归入波0），"
      "仅用于文件名组织，不替代官方波次编号。")
    a("> 结论由人工判断：散点图中最早/最密集的一撮才接近出生点，脚本不下结论。")
    a("")
    a("## 全部船散点图")
    a("")
    a("| 波次 | 呼号 | 中文船名 | 内码 | n | 出生clock范围(秒) | 中位 | 点亮clock范围(秒) | 最早20均值(x,z) | 50m密集簇(x,z,n) | 格子 |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ships:
        a("| %s | %s | %s | %s | %d | %s | %.1f | %s | (%.1f, %.1f) | (%.1f, %.1f, %d) | %s |"
          % (s["wave"], s["display_name"], s["ship_name"], s["name"], s["n_pos"],
             fmt_range(s["spawn_clock_min"], s["spawn_clock_max"]), s["spawn_clock_median"],
             fmt_range(s["first_seen_clock_min"], s["first_seen_clock_max"]),
             s["early20_mean_x"], s["early20_mean_z"],
             s["cluster_x"], s["cluster_z"], s["cluster_n"], s["cell"]))
    a("")
    if skipped:
        a("## 未出图（无位置观测）")
        a("")
        a("| 内码 | 呼号 | 中文船名 | 观测数 | 有位置 |")
        a("|---|---|---|---|---|")
        for name, disp, ship_cn, n, npos in skipped:
            a(f"| {name} | {disp} | {ship_cn} | {n} | {npos} |")
        a("")
    a("## 说明")
    a("")
    a("- `出生clock` = onNewPlayerSpawnedInBattle 类 spawn 事件时间（replay clock，20:00 开局 = 0）。")
    a("- `点亮clock` = 首次被点亮时刻；船移动后被点亮会沿航线铺开，最早一撮才是出生点附近。")
    a("- `50m密集簇` = 20m 网格最密格中心 ±50m 内的点数，供快速判断离散度。")
    a("- 杰维斯 Apache 在同一局出现多个角色（开局在场+增援），散点会呈现多个簇，需分别确认。")
    a("")
    (WS_MD.parent).mkdir(parents=True, exist_ok=True)
    WS_MD.write_text("\n".join(lines), encoding="utf-8")
    WS_JSON.write_text(
        json.dumps({"family": FAMILY, "bracket": BRACKET, "build": build,
                    "used_build": used_build,
                    "space_size": space_size, "total_arenas": total_arenas,
                    "coverage": [{"scenario": c[0], "arenas": c[1]} for c in coverage],
                    "ships": ships, "skipped": [
                        {"name": s[0], "display_name": s[1], "ship_name": s[2],
                         "n": s[3], "n_pos": s[4]} for s in skipped]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"rendered {len(ships)} ships, skipped {len(skipped)}; worksheet -> {WS_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
