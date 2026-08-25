#!/usr/bin/env python3
"""Generate a per-player markdown report from a replays SQLite database."""
from __future__ import annotations

import argparse
import collections
import datetime
import os
import re
import sqlite3
import sys


def fmt_dt(source, ts):
    m = re.match(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", source or "")
    if m:
        return f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}"
    if ts:
        return datetime.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    return "?"


def pct(a, b):
    return f"{a / b * 100:.1f}%" if b else "-"


def build(rows):
    player = rows[0]["name"]
    account = rows[0]["account_id"]
    realm = rows[0]["home_realm"]
    versions = sorted({r["client_version"] for r in rows if r["client_version"]})
    dates = [fmt_dt(r["source"], r["ts"]) for r in rows]
    date_min, date_max = min(dates), max(dates)

    n = len(rows)
    wins = sum(1 for r in rows if r["is_win"])
    losses = sum(1 for r in rows if r["is_loss"])
    draws = sum(1 for r in rows if r["is_draw"])
    resolved = sum(1 for r in rows if r["fields_resolved"])
    tot_dmg = sum((r["damage"] or 0) for r in rows)
    tot_frag = sum((r["frags"] or 0) for r in rows)
    alive = sum(1 for r in rows if r["is_alive"])

    L = [f"# {player} 解析报告\n"]
    L.append(f"- 账号 dbid：`{account}`  区服：`{realm}`\n")
    L.append(f"- 场次：{n}（其中 **{resolved} 场含完整 damage/exp**）  时间：{date_min} ~ {date_max}\n")
    L.append(f"- 版本：{', '.join(versions) or '未知'}\n")

    L.append("\n## 总览\n")
    L.append("| 指标 | 值 |")
    L.append("|---|---|")
    L.append(f"| 场次 | {n} |")
    L.append(f"| 胜 / 负 / 平 | {wins} / {losses} / {draws} |")
    L.append(f"| 胜率 | {pct(wins, wins + losses)} |")
    L.append(f"| 总伤害 / 场均 | {tot_dmg:,} / {(tot_dmg // n) if n else 0:,} |")
    L.append(f"| 总击杀 / 场均 | {tot_frag} / {tot_frag / n:.2f} |")
    L.append(f"| 存活率 | {alive}/{n} = {pct(alive, n)} |")

    # mode split
    L.append("\n## 分模式\n")
    L.append("| 模式 | 场次 | 胜 | 负 | 胜率 | 场均伤害 | 场均基础经验 |")
    L.append("|---|---|---|---|---|---|---|")
    for mg in sorted({r["match_group"] for r in rows if r["match_group"]}, key=lambda x: str(x)):
        g = [r for r in rows if r["match_group"] == mg]
        w = sum(1 for r in g if r["is_win"])
        lo = sum(1 for r in g if r["is_loss"])
        ad = sum((r["damage"] or 0) for r in g) // len(g)
        ae = sum((r["exp"] or 0) for r in g) // len(g)
        L.append(f"| {mg} | {len(g)} | {w} | {lo} | {pct(w, w + lo)} | {ad:,} | {ae:,} |")

    # ship breakdown
    L.append("\n## 舰船明细\n")
    L.append("| 舰船 | 等级 | 舰种 | 场次 | 胜 | 胜率 | 场均伤害 | 场均击杀 | 场均基础经验 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    ships = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
    for r in rows:
        k = (r["ship_name"] or f"id{r['ship_id']}", r["tier"], r["ship_class"])
        ships[k][0] += 1
        ships[k][1] += 1 if r["is_win"] else 0
        ships[k][2] += r["damage"] or 0
        ships[k][3] += r["frags"] or 0
        ships[k][4] += r["exp"] or 0
    for (nm, tier, cl), v in sorted(ships.items(), key=lambda kv: -kv[1][0]):
        L.append(f"| {nm} | T{tier} | {cl} | {v[0]} | {v[1]} | {pct(v[1], v[0])} | {v[2] // v[0]:,} | {v[3] / v[0]:.2f} | {v[4] // v[0]:,} |")

    # per-game, adaptive for stars/bracket
    has_stars = any(r["stars_server"] is not None for r in rows)
    has_bracket = any(r["bracket"] for r in rows)
    L.append("\n## 逐场明细\n")
    head = "| 时间 | 模式 | 舰船 | 等级 | 结果 | 伤害 | 击杀 | 基础经验 | 存活 |"
    if has_stars:
        head += " 星级 |"
    if has_bracket:
        head += " 档位 |"
    L.append(head)
    L.append("|---".join([""] * head.count("|")) + "|")
    for r in rows:
        wl = "胜" if r["is_win"] else ("负" if r["is_loss"] else "平")
        line = (f"| {fmt_dt(r['source'], r['ts'])} | {r['match_group']} | {r['ship_name']} "
                f"| T{r['tier']} | {wl} | {r['damage']:,} | {r['frags']} | {r['exp']} "
                f"| {'存活' if r['is_alive'] else '阵亡'} |")
        if has_stars:
            line += f" {r['stars_server']} |"
        if has_bracket:
            line += f" {r['bracket']} |"
        L.append(line)

    return "\n".join(L) + "\n"


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="replays.db", help="SQLite database (table: rows)")
    ap.add_argument("--player", required=True, help="exact in-game player name")
    ap.add_argument("--family", help="optional substring match on scenario_family (pvp/ops/coop/...)")
    ap.add_argument("--match-group", help="optional exact match on match_group")
    ap.add_argument("--out", help="output .md path (default reports/<player>_report.md)")
    args = ap.parse_args(argv)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    q = "SELECT * FROM rows WHERE name = ?"
    params = [args.player]
    if args.family:
        q += " AND scenario_family LIKE ?"
        params.append(f"%{args.family}%")
    if args.match_group:
        q += " AND match_group = ?"
        params.append(args.match_group)
    q += " ORDER BY ts"
    rows = [dict(r) for r in con.execute(q, params)]
    con.close()

    if not rows:
        print(f"no rows for player {args.player!r} with given filters", file=sys.stderr)
        return 1

    out = args.out or os.path.join("reports", f"{args.player}_report.md")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    md = build(rows)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"wrote {len(rows)} games -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
