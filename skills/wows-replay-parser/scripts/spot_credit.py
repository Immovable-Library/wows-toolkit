#!/usr/bin/env python3
"""Per-game spotting-vs-conversion profile (Tier 1, net-credit attribution).

Tier 1 uses only server-settled per-player fields (scouting_damage / damage /
frags) plus team composition. It deliberately does NOT claim per-target
causation, because that requires event-level detection data (see the
attribution-engine spec). Verdicts are conservative and labeled with how much
they are allowed to assert.
"""
from __future__ import annotations

import argparse
import collections
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenario_names
import ship_names


# Spotting credit is a game-mechanics question, so the default source is the
# all-replays DB. Version-sensitive work (spawn calibration and the like) reads
# the gated replays.db instead; pass --db explicitly for that.
DEFAULT_DB = Path(__file__).resolve().parent.parent / "replays_all.db"

# Tier-1 reads a PvE roster: operations and co-op. Other modes store several
# teams (or a single test-room row), which leaves no "share of my team" reference.
PVE_MODES = {"pve", "cooperative"}


# The spotting-credit invariant the whole analysis must honour. scouting_damage
# in the DB is already the server-settled net after this rule, so it can only
# bound "I uniquely lit some damage"; it cannot prove per-target causation and
# it under-reports when own-team ships share a target's detection ring.
SPOT_RULE = (
    "Spotting damage credits only the single own-team unit that uniquely "
    "detects the target. If two or more own-team units sit inside the target's "
    "detection ring at the same moment, that target contributes zero spotting "
    "damage to every one of them. scouting_damage below is the net already "
    "settled by this rule, so it is a lower-bound on 'I lit some damage', not a "
    "count of targets lit and not proof of who ate a given kill."
)


# Ship classes that are plausibly "collector" high-DPM fire sponges in PvE: they
# convert a spotter's reveal into raw damage without producing spotting credit.
COLLECTOR_CLASSES = {"CL/CA", "DD", "CV"}
# Specific ships that are notorious HE/DPM farm boats in ops.
COLLECTOR_SHIPS = {
    "Cleveland", "Mainz", "Helena", "Seattle", "Mogador", "Yoshino", "Kitakaze",
    "Harugumo", "Tiger '59", "Brisbane", "Austin", "Bremen",
}


def _fmt(v):
    if v is None:
        return "-"
    return f"{v:,}"


def _tier(v):
    return f"T{v}" if v is not None else "-"


def _pct(a, b):
    if a is None or not b:
        return "-"
    return f"{a / b * 100:.1f}%"


def open_db(path):
    """Read-only connection; a missing DB is an error, not a new empty file."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"database not found: {p} (pass --db, or ingest replays first)")
    con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _team_member(row):
    name = row["name"]
    cn = ship_names.cn_name(row["ship_id"], row["ship_name"])
    return {
        "name": name,
        "cn": cn,
        "ship_class": row["ship_class"],
        "damage": row["damage"] or 0,
        "frags": row["frags"] or 0,
        "scout": row["scouting_damage"] or 0,
    }


def _skip_match(mine, scenario_cn, verdict, reason):
    """A game the Tier-1 analysis cannot judge; rendered without a verdict."""
    return {
        "key": mine.get("source"),
        "scenario_cn": scenario_cn,
        "ship_cn": ship_names.cn_name(mine["ship_id"], mine["ship_name"]),
        "tier": mine["tier"],
        "win": bool(mine["is_win"]),
        "damage": None, "frags": None, "exp": None, "scout": None,
        "team_dmg": 0, "team_scout": 0,
        "mates": [],
        "reasons": [reason],
        "verdict": verdict,
    }


def analyze(game_rows, player_name, scenario_cn):
    """Classify one match for player_name; returns a dict of diagnostics."""
    rows = [dict(r) for r in game_rows]
    mine = next((r for r in rows if r["name"] == player_name), None)
    if mine is None:
        return None
    if not mine["fields_resolved"] or mine["scouting_damage"] is None:
        return _skip_match(mine, scenario_cn, "unresolved",
                           "旧版本无 damage/exp/点亮结算（fields_resolved=0），跳过归因。")

    if mine["match_group"] not in PVE_MODES:
        return _skip_match(mine, scenario_cn, "非 PvE 对局",
                           "本局 match_group=%s，不是 PvE 对局，净额占比没有参照意义，跳过判定。"
                           % mine["match_group"])

    # The net-credit reading assumes a single-team roster: every stored row is a
    # team mate of the player. Mixed-team games (pvp) and games recorded with a
    # single row have no meaningful "share of my team" reference.
    team = [r for r in rows if r["team_id"] == mine["team_id"]]
    if len(team) != len(rows) or len(team) < 2:
        return _skip_match(mine, scenario_cn, "样本不适用",
                           "本局入库样本不是单队 PvE 构成（队友数 %d / 总行数 %d），"
                           "净额占比没有参照意义，跳过判定。" % (len(team) - 1, len(rows)))

    n = len(rows)
    total_dmg = sum(r["damage"] or 0 for r in rows)
    total_scout = sum(r["scouting_damage"] or 0 for r in rows)
    mean_share = 1.0 / n if n else 0.0

    mine_dmg = mine["damage"] or 0
    mine_scout = mine["scouting_damage"] or 0
    mine_frags = mine["frags"] or 0
    mine_dmg_share = (mine_dmg / total_dmg) if total_dmg else 0.0
    mine_scout_share = (mine_scout / total_scout) if total_scout else 0.0

    def rank_of(field):
        order = sorted(rows, key=lambda r: (r[field] or 0), reverse=True)
        for i, r in enumerate(order):
            if r["account_id"] == mine["account_id"]:
                return i + 1
        return n + 1

    mine_dmg_rank = rank_of("damage")
    mine_scout_rank = rank_of("scouting_damage")
    mine_frag_rank = rank_of("frags")

    mates = []
    for r in rows:
        if r["name"] == player_name:
            continue
        m = _team_member(r)
        m["dmg_share"] = (m["damage"] / total_dmg) if total_dmg else 0.0
        m["scout_share"] = (m["scout"] / total_scout) if total_scout else 0.0
        mates.append(m)
    mates.sort(key=lambda m: m["damage"], reverse=True)

    # A scout_share well above the even split means the server credited us a lot
    # of unique-spotting damage relative to the rest of the team.
    top_scout = mine_scout_rank == 1 and mine_scout_share >= 1.5 * mean_share
    top_dmg = mine_dmg_rank <= 2
    # A collector is a teammate that out-farms us on damage while producing less
    # than an even share of spotting credit (they convert our reveal into damage).
    high_dpm_mates = [
        m for m in mates
        if m["ship_class"] in COLLECTOR_CLASSES or m["cn"] in COLLECTOR_SHIPS
    ]
    overtaken_by_collector = any(
        m["damage"] > mine_dmg and m["dmg_share"] > mine_dmg_share and m["scout_share"] < mean_share
        for m in mates
    )
    crowd_signals = high_dpm_mates and mine_scout_rank <= 2 and not top_scout

    # Decide verdict (ordered from most assertive to most cautious).
    reasons = []
    if top_scout and top_dmg and not overtaken_by_collector:
        verdict = "自亮自吃"
        reasons.append("净点亮最高且自身伤害/击杀也在队内前列，无低亮高伤队友反超。")
    elif top_scout and overtaken_by_collector:
        verdict = "净额支持：独亮被收割"
        reasons.append("净点亮全场最高，但存在低亮高伤队友在伤害/击杀上反超你，净额支持'你开灯、队友收钱'。")
    elif crowd_signals:
        verdict = "疑似人群并存（需事件级验证）"
        reasons.append(
            "你的净点亮未显著高于均值，且队内存在多个高DPM收割船。"
            "按唯一侦察者规则，若你与它们同处目标隐蔽圈会被互相清零，"
            "净数据无法区分'你被清零'还是'你没亮到'，故不做进一步归因。"
        )
    elif top_scout and not top_dmg:
        verdict = "净额参照：高点亮、低转化"
        reasons.append("净点亮偏高但自身伤害未同步领先，净额提示'开灯多于收钱'；若队内无低亮高伤者，则更可能是你自身转化问题，需事件级确认。")
    else:
        verdict = "净额参照：无明显被收割信号"
        reasons.append("净点亮/伤害均在常规区间，表层数据无异常归因。")

    return {
        "key": mine.get("source"),
        "scenario_cn": scenario_cn,
        "ship_cn": ship_names.cn_name(mine["ship_id"], mine["ship_name"]),
        "tier": mine["tier"],
        "win": bool(mine["is_win"]),
        "damage": mine_dmg,
        "frags": mine_frags,
        "exp": mine["exp"],
        "scout": mine_scout,
        "dmg_share": mine_dmg_share,
        "scout_share": mine_scout_share,
        "dmg_rank": mine_dmg_rank,
        "scout_rank": mine_scout_rank,
        "frag_rank": mine_frag_rank,
        "team_dmg": total_dmg,
        "team_scout": total_scout,
        "n": n,
        "verdict": verdict,
        "reasons": reasons,
        "mates": mates,
    }


def render(matches):
    L = ["# \u70b9\u4eae-\u53d8\u73b0\u753b\u50cf\uff08Tier 1\uff09\n", SPOT_RULE + "\n"]
    L.append("\n## \u9010\u573a\u5224\u5b9a\n")
    L.append("| 时间 | 剧情 | 舰船 | 等级 | 结果 | 伤害 | 击杀 | 经验 | 净点亮 | 点亮/全队 | 伤害/全队 | 判定 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m in matches:
        L.append(
            f"| {(m['key'] or '?')[:20]} | {m['scenario_cn']} | {m['ship_cn']} | {_tier(m['tier'])} | "
            f"{'胜' if m['win'] else '负'} | {_fmt(m['damage'])} | {_fmt(m['frags'])} | {_fmt(m['exp'])} | "
            f"{_fmt(m['scout'])} | {_pct(m['scout'], m['team_scout'])} | {_pct(m['damage'], m['team_dmg'])} | "
            f"{m['verdict']} |"
        )

    L.append("\n## 分队细节（按伤害排序）\n")
    for m in matches:
        L.append(f"\n### {m['ship_cn']} {_tier(m['tier'])} @ {m['scenario_cn']} - {m['verdict']}\n")
        L.append("| 玩家 | 舰船 | 伤害 | 击杀 | 净点亮 | 点亮占比 | 伤害占比 |")
        L.append("|---|---|---|---|---|---|---|")
        L.append(
            f"| **{m['ship_cn']}(你)** | {m['ship_cn']} | {_fmt(m['damage'])} | {_fmt(m['frags'])} | "
            f"{_fmt(m['scout'])} | {_pct(m['scout'], m['team_scout'])} | {_pct(m['damage'], m['team_dmg'])} |"
        )
        for mm in m["mates"]:
            L.append(
                f"| {mm['name']} | {mm['cn']} | {_fmt(mm['damage'])} | {_fmt(mm['frags'])} | "
                f"{_fmt(mm['scout'])} | {_pct(mm['scout'], m['team_scout'])} | {_pct(mm['damage'], m['team_dmg'])} |"
            )
        for reason in m["reasons"]:
            L.append(f"\n- {reason}")
    return "\n".join(L) + "\n"


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(DEFAULT_DB),
                    help="SQLite database (table rows); defaults to the all-replays DB")
    ap.add_argument("--player", required=True, help="exact in-game player name")
    ap.add_argument("--date", default=None, help="source date prefix, e.g. 20260904")
    ap.add_argument("--out", default=None, help="output .md path (default reports/<player>_spot.md)")
    args = ap.parse_args(argv)

    con = open_db(args.db)

    # First find the games (by source filename) the player took part in.
    q = "SELECT source FROM rows WHERE name = ?"
    params = [args.player]
    if args.date:
        q += " AND source LIKE ?"
        params.append(f"{args.date}%")
    player_sources = {r["source"] for r in con.execute(q, params)}
    if not player_sources:
        print(f"no rows for player {args.player!r}", file=sys.stderr)
        con.close()
        return 1

    # Then pull every player's row for those games so team attribution is real.
    placeholders = ",".join("?" * len(player_sources))
    q = f"SELECT * FROM rows WHERE source IN ({placeholders}) ORDER BY ts"
    rows = [dict(r) for r in con.execute(q, list(player_sources))]
    con.close()

    by_game = collections.OrderedDict()
    for r in rows:
        by_game.setdefault(r["source"], []).append(r)

    matches = []
    for src, g in by_game.items():
        scenario_cn, _ = scenario_names.standard_name(g[0]["scenario"] or "")
        matches.append(analyze(g, args.player, scenario_cn))
    matches = [m for m in matches if m]

    out = args.out or os.path.join("reports", f"{args.player}_spot.md")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    md = render(matches)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"wrote {len(matches)} games -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
