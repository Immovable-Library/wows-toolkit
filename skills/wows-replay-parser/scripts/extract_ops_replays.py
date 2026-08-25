#!/usr/bin/env python3
"""Recursively extract per-player battle results from WoWS .wowsreplay files.

No Rust build required. Recovers three layers per replay:
  1. plaintext metadata header (version, build, mode, scenario, player);
  2. encrypted packet stream (constant Blowfish key + XOR chain + zlib);
  3. the BattleResults packet (type 0x22): a UTF-8 JSON battle report with
     per-player damage / frags / base XP and the objective/task (star) data.

The battle report's positional arrays are resolved with per-build lookup
tables (wows-constants: CLIENT_PUBLIC_RESULTS_INDICES / COMMON_RESULTS /
PLAYER_PRIVATE_RESULTS_INDICES). These shift between game versions, so the
script reads each replay's build number from ``clientVersionFromExe`` and
selects the matching table. Covered builds (13.10+) are loaded from a cache
dir and auto-fetched from the padtrack/wows-constants GitHub repo on demand.
Older builds have no published index table; for those the script still emits
every version-stable field (identity, ship, team, frags, alive, win/loss,
stars, bracket) and leaves damage/exp/raw_exp/scouting as null with
``fields_resolved=false``.

Only non-stdlib dependency: ``pip install cryptography``.

Usage:
  python extract_ops_replays.py "D:/replays" --out result.jsonl
  python extract_ops_replays.py "D:/replays" --out result.jsonl --workers 8
  python extract_ops_replays.py "D:/replays" --no-resolve-ships --limit 100
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import struct
import sys
import urllib.parse
import urllib.request
import zlib
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPLAY_BLOWFISH_KEY = bytes([
    0x29, 0xB7, 0xC9, 0x09, 0x38, 0x3F, 0x84, 0x88,
    0xFA, 0x98, 0xEC, 0x4E, 0x13, 0x19, 0x79, 0xFB,
])
WG_APP_ID = "4abd85d2d22608f74b646410ef7e3a16"
CONSTANTS_REPO_TMPL = "https://raw.githubusercontent.com/padtrack/wows-constants/main/data/versions/{build}.json"

# Version-stable lookup tables (valid across every known build; these are the
# leading identity/result fields that never get reordered).
COMMON_RESULTS = [
    "arena_id", "cluster_id", "start_dt", "winner_team_id", "win_type_id",
    "team_build_type_id", "clan_season_type", "clan_season_id", "duration_sec",
    "map_type_id", "scenario_name", "survey_id", "game_mode", "sse_info",
    "battle_logic_info", "weather_preset_id", "pve_operation_id",
    "event_operation_id",
]

STABLE_PUBLIC = {
    "account_db_id": 0, "name": 1, "clan_id": 2, "clan_tag": 3, "team_id": 6,
    "vehicle_type_id": 7, "home_realm": 9, "achievements": 10, "max_health": 15,
    "is_alive": 21, "life_time_sec": 22, "ships_killed": 32, "team_ships_killed": 33,
}

# Version-shifted public fields (index depends on build).
SHIFTING_PUBLIC = ["raw_exp", "exp", "scouting_damage", "damage", "resources"]

PRIVATE_FIELDS = {
    "init_economics": 7, "common_economics": 8, "subtotal_economics": 9,
    "tasks": 11, "pve_details": 44,
}

INIT_ECONOMICS_INDICES = {"credits": 0, "credits_penalty": 1, "exp_penalty": 2, "exp": 3, "credits_compensation": 4}

FINISH_REASONS = {
    "0": "MAIN_TASK_COMPLETE", "1": "SCORE_EXCESS", "2": "TECHNICAL",
    "3": "UNKNOWN", "4": "MAIN_TASK_FAILED", "5": "TARGET_PULLED_TO_DESTINATION",
    "8": "EXTERMINATION", "9": "FAILURE", "10": "PROTECTED_TARGETS_DESTROYED",
    "11": "BASE", "12": "PROTECTED_TARGETS_SURVIVED", "13": "TIMEOUT",
    "15": "TARGET_REACHED_DESTINATION", "16": "SCORE_ZERO", "17": "SCORE",
    "18": "SCORE_ON_TIMEOUT",
}

DB_COLUMNS = [
    "source", "build", "client_version", "fields_resolved", "match_group",
    "game_mode_meta", "scenario_family", "ts", "arena_id", "cluster_id",
    "game_mode", "scenario", "map_kind", "bracket", "difficulty", "duration_sec",
    "is_win", "is_loss", "is_draw", "win_type_id", "finish_type",
    "stars_server", "secondary_completed", "secondary_total", "team_damage",
    "team_exp", "team_max_tier", "team_classes", "team_has_cv", "team_has_ss",
    "team_has_tier11", "account_id", "name", "clan_tag", "home_realm",
    "team_id", "ship_id", "ship_name", "tier", "ship_type", "ship_class",
    "damage", "frags", "exp", "raw_exp", "scouting_damage", "is_alive",
    "max_health",
]


def _db_value(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


def init_db(db_path, overwrite=False):
    if overwrite and Path(db_path).exists():
        Path(db_path).unlink()
    con = sqlite3.connect(str(db_path))
    cols = ", ".join('"%s"' % c for c in DB_COLUMNS)
    con.execute("CREATE TABLE IF NOT EXISTS rows (%s)" % cols)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_acct ON rows(arena_id, account_id)")
    con.commit()
    return con


def upsert_db(con, rows):
    cols = ", ".join('"%s"' % c for c in DB_COLUMNS)
    ph = ", ".join("?" for _ in DB_COLUMNS)
    con.executemany(
        "INSERT OR IGNORE INTO rows (%s) VALUES (%s)" % (cols, ph),
        ([_db_value(r.get(c)) for c in DB_COLUMNS] for r in rows),
    )
    con.commit()


def load_seen(jsonl_path, db_path):
    seen = set()
    if jsonl_path and Path(jsonl_path).exists():
        try:
            with open(jsonl_path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        a = json.loads(line).get("arena_id")
                        if a is not None:
                            seen.add(a)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
    if db_path and Path(db_path).exists():
        try:
            con = sqlite3.connect(str(db_path))
            for (a,) in con.execute("SELECT DISTINCT arena_id FROM rows WHERE arena_id IS NOT NULL"):
                seen.add(a)
            con.close()
        except sqlite3.Error:
            pass
    return seen



_REG = None


def _blowfish_ecb_decrypt(key, data):
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:
        raise SystemExit("This script needs 'cryptography' (pip install cryptography)") from exc
    d = Cipher(algorithms.Blowfish(key), modes.ECB()).decryptor()
    return d.update(data) + d.finalize()


def decrypt_packet_stream(ciphertext):
    n = len(ciphertext) - len(ciphertext) % 8
    raw = bytearray(_blowfish_ecb_decrypt(REPLAY_BLOWFISH_KEY, ciphertext[:n]))
    prev = b"\x00" * 8
    for i in range(0, len(raw), 8):
        block = bytes(a ^ b for a, b in zip(raw[i:i + 8], prev))
        raw[i:i + 8] = block
        prev = block
    d = zlib.decompressobj()
    return d.decompress(bytes(raw)) + d.flush()


def read_meta_only(path):
    with open(path, "rb") as fh:
        hdr = fh.read(12)
        if len(hdr) < 12:
            raise ValueError("short header")
        magic, block_count, meta_len = struct.unpack("<III", hdr)
        return json.loads(fh.read(meta_len).decode("utf-8", "replace"))


def read_replay(path):
    with open(path, "rb") as fh:
        hdr = fh.read(12)
        if len(hdr) < 12:
            raise ValueError("short header")
        magic, block_count, meta_len = struct.unpack("<III", hdr)
        meta = json.loads(fh.read(meta_len).decode("utf-8", "replace"))
        for _ in range(block_count - 1):
            (bs,) = struct.unpack("<I", fh.read(4))
            fh.seek(bs, 1)
        _, _ = struct.unpack("<II", fh.read(8))
        ciphertext = fh.read()
    return meta, decrypt_packet_stream(ciphertext)


def find_battle_results(packet_bytes):
    i, last = 0, None
    n = len(packet_bytes)
    while i + 12 <= n:
        size, ptype = struct.unpack_from("<II", packet_bytes, i)
        i += 12
        if size < 0 or i + size > n:
            break
        payload = packet_bytes[i:i + size]
        i += size
        if ptype == 0x22 and len(payload) >= 4:
            (jlen,) = struct.unpack_from("<I", payload, 0)
            try:
                last = json.loads(payload[4:4 + jlen].decode("utf-8", "replace"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return last


def build_and_version(meta):
    cv = str(meta.get("clientVersionFromExe") or "")
    if "," not in cv:
        parts = cv.replace(".", ",").split(",")
    else:
        parts = cv.split(",")
    parts = [p.strip() for p in parts]
    if len(parts) >= 4 and parts[3].isdigit():
        build = int(parts[3]) if parts[3] != "0" else None
    else:
        build = None
    ver = ".".join(parts[:3]) if len(parts) >= 3 else cv
    return build, ver


def map_kind(scenario):
    if scenario.startswith("WW2_OPERATION"):
        return "new"
    if scenario.startswith("PCVO"):
        return "legacy_op"
    return "other"


def bracket_of(scenario):
    m = re.search(r"(\d+LVL)", scenario)
    return m.group(1) if m else None


def difficulty_of(scenario):
    m = re.search(r"(LOW|MEDIUM|HIGH)_LVL", scenario)
    return m.group(1) if m else None


def scenario_family(scenario, match_group):
    if scenario.startswith("WW2_OPERATION"):
        return "WW2_OP(new)"
    if scenario.startswith("PCVO"):
        return "PCVO(legacy_op)"
    if match_group == "pvp":
        return "pvp"
    if match_group == "cooperative":
        return "coop"
    if "asymm" in scenario:
        return "asymmetric"
    if "boss_fight" in scenario:
        return "boss_fight"
    return "other:" + scenario[:24]


def normalize_class(t):
    if not t:
        return None
    s = str(t).lower()
    if "carrier" in s:
        return "CV"
    if "submarine" in s:
        return "SS"
    if "battleship" in s:
        return "BB"
    if "cruiser" in s:
        return "CL/CA"
    if "destroyer" in s:
        return "DD"
    return s


def load_build_tables(build, cache_dir, allow_fetch):
    """Return full PUBLIC name->index for this build (shifted + stable), or None."""
    cache = Path(cache_dir)
    if build is None:
        return None
    f = cache / f"{build}.json"
    if f.exists():
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
            return c.get("CLIENT_PUBLIC_RESULTS_INDICES") or None
        except (OSError, json.JSONDecodeError):
            pass
    marker = cache / f"{build}.unresolved"
    if allow_fetch and not marker.exists():
        url = CONSTANTS_REPO_TMPL.format(build=build)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "extract_ops_replays"})
            data = urllib.request.urlopen(req, timeout=30).read()
            c = json.loads(data)
            f.write_bytes(data)
            return c.get("CLIENT_PUBLIC_RESULTS_INDICES") or None
        except Exception:
            (cache / f"{build}.unresolved").write_text("", encoding="utf-8")
    elif not (cache / f"{build}.unresolved").exists():
        pass
    return None


def resolve_common(arr):
    if not isinstance(arr, list):
        return {}
    return {COMMON_RESULTS[i]: v for i, v in enumerate(arr) if i < len(COMMON_RESULTS)}


def resolve_player(arr, table):
    if not isinstance(arr, list):
        return {}
    return {k: arr[idx] for k, idx in table.items() if idx < len(arr)}


def resolve_private(arr):
    if not isinstance(arr, list):
        return {}
    return {k: arr[idx] for k, idx in PRIVATE_FIELDS.items() if idx < len(arr)}


def _set_reg(reg):
    global _REG
    _REG = reg


def _parse_game(path):
    meta, packets = read_replay(path)
    build, ver = build_and_version(meta)
    shifted = _REG["resolved"].get(str(build)) if build is not None else None
    table = dict(STABLE_PUBLIC)
    resolved = False
    if shifted is not None:
        table.update({k: v for k, v in shifted.items() if v is not None})
        resolved = True

    results = find_battle_results(packets)
    if results is None:
        return None

    common = resolve_common(results.get("commonList"))
    players = []
    for dbid, arr in (results.get("playersPublicInfo") or {}).items():
        p = resolve_player(arr, table)
        acct = p.get("account_db_id")
        if isinstance(acct, (int, float)) and int(acct) > 0:
            players.append(p)

    private = resolve_private(results.get("privateDataList"))
    pve = private.get("pve_details") or {}
    stars_server = pve.get("cur_tasks_completed") if isinstance(pve, dict) else None

    battle_logic = common.get("battle_logic_info")
    tasks = battle_logic.get("tasks", []) if isinstance(battle_logic, dict) else []
    sec_total, sec_done = 0, 0
    if isinstance(tasks, list):
        for t in tasks:
            if isinstance(t, dict) and t.get("category") == 2:
                sec_total += 1
                if t.get("targetValueAchieved") == 2:
                    sec_done += 1

    winner = common.get("winner_team_id")
    human_teams = {p.get("team_id") for p in players if p.get("team_id") is not None}
    self_team = next(iter(human_teams), None)
    is_win = is_loss = is_draw = None
    if winner is not None and self_team is not None:
        is_draw = int(winner) < 0
        is_win = int(winner) == int(self_team)
        is_loss = not is_win and not is_draw

    scenario = str(common.get("scenario_name") or meta.get("scenario") or "")
    init_econ = private.get("init_economics")
    base_exp_self = None
    if isinstance(init_econ, list) and len(init_econ) > INIT_ECONOMICS_INDICES["exp"]:
        base_exp_self = init_econ[INIT_ECONOMICS_INDICES["exp"]]

    return {
        "source": os.path.basename(path),
        "build": build,
        "client_version": ver,
        "fields_resolved": resolved,
        "match_group": meta.get("matchGroup"),
        "game_mode_meta": meta.get("gameMode"),
        "arena_id": common.get("arena_id") or results.get("arenaUniqueID"),
        "ts": common.get("start_dt"),
        "cluster_id": common.get("cluster_id"),
        "game_mode": common.get("game_mode"),
        "scenario": scenario,
        "map_kind": map_kind(scenario),
        "scenario_family": scenario_family(scenario, meta.get("matchGroup")),
        "bracket": bracket_of(scenario),
        "difficulty": difficulty_of(scenario),
        "duration_sec": common.get("duration_sec"),
        "winner_team_id": winner,
        "win_type_id": common.get("win_type_id"),
        "finish_type": FINISH_REASONS.get(str(common.get("win_type_id"))),
        "is_win": is_win, "is_loss": is_loss, "is_draw": is_draw,
        "stars_server": stars_server,
        "secondary_completed": sec_done,
        "secondary_total": sec_total,
        "base_exp_self": base_exp_self,
        "players": players,
    }


def resolve_ship_info(ship_ids, cache_path, enabled, region, app_id, chunk=100):
    info = {}
    if cache_path and Path(cache_path).exists():
        try:
            info.update({str(k): v for k, v in json.loads(Path(cache_path).read_text(encoding="utf-8")).items()})
        except (OSError, json.JSONDecodeError):
            info = {}
    missing = [s for s in sorted(ship_ids) if str(s) not in info]
    if missing and enabled:
        host = f"api.worldofwarships.{region}"
        for i in range(0, len(missing), chunk):
            batch = missing[i:i + chunk]
            data = urllib.parse.urlencode({"application_id": app_id,
                                           "ship_id": ",".join(str(x) for x in batch),
                                           "fields": "name,tier,type,nation"}).encode()
            url = f"https://{host}/wows/encyclopedia/ships/"
            try:
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                if payload.get("status") == "ok" and isinstance(payload.get("data"), dict):
                    info.update(payload["data"])
            except (OSError, ValueError) as exc:
                print(f"warning: ship lookup failed ({exc}); continuing without ship names", file=sys.stderr)
                break
        if cache_path:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            Path(cache_path).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return info


def emit_rows(games, ship_info, resolve):
    for g in games:
        players = g["players"]
        resolved = g["fields_resolved"]
        team_damage = sum(int(p.get("damage") or 0) for p in players) if resolved else None
        team_exp = sum(int(p.get("exp") or 0) for p in players) if resolved else None
        tiers, classes = [], set()
        if ship_info:
            for p in players:
                e = ship_info.get(str(p.get("vehicle_type_id")))
                if e and e.get("tier") is not None:
                    tiers.append(int(e["tier"]))
                if e and e.get("type"):
                    classes.add(normalize_class(e.get("type")))
        base = {
            "source": g["source"], "build": g["build"], "client_version": g["client_version"],
            "fields_resolved": resolved, "match_group": g["match_group"],
            "game_mode_meta": g["game_mode_meta"], "scenario_family": g["scenario_family"],
            "ts": g["ts"], "arena_id": g["arena_id"], "cluster_id": g["cluster_id"],
            "game_mode": g["game_mode"], "scenario": g["scenario"], "map_kind": g["map_kind"],
            "bracket": g["bracket"], "difficulty": g["difficulty"], "duration_sec": g["duration_sec"],
            "is_win": g["is_win"], "is_loss": g["is_loss"], "is_draw": g["is_draw"],
            "win_type_id": g["win_type_id"], "finish_type": g["finish_type"],
            "stars_server": g["stars_server"], "secondary_completed": g["secondary_completed"],
            "secondary_total": g["secondary_total"],
            "team_damage": team_damage, "team_exp": team_exp,
            "team_max_tier": max(tiers) if tiers else None,
            "team_classes": sorted(classes) or None,
            "team_has_cv": ("CV" in classes) or None,
            "team_has_ss": ("SS" in classes) or None,
            "team_has_tier11": (11 in tiers) or None,
        }
        for p in players:
            e = ship_info.get(str(p.get("vehicle_type_id"))) if resolve else None
            st = e.get("type") if e else None
            row = dict(base)
            row.update({
                "account_id": int(p["account_db_id"]) if p.get("account_db_id") is not None else None,
                "name": p.get("name"), "clan_tag": p.get("clan_tag"),
                "home_realm": p.get("home_realm"), "team_id": p.get("team_id"),
                "ship_id": p.get("vehicle_type_id"),
                "ship_name": e.get("name") if e else None,
                "tier": e.get("tier") if e else None,
                "ship_type": st, "ship_class": normalize_class(st),
                "damage": (int(p.get("damage") or 0) if resolved else None),
                "frags": int(p.get("ships_killed") or 0),
                "exp": (int(p.get("exp") or 0) if resolved else None),
                "raw_exp": (int(p.get("raw_exp") or 0) if resolved else None),
                "scouting_damage": (int(p.get("scouting_damage") or 0) if resolved else None),
                "is_alive": p.get("is_alive"), "max_health": p.get("max_health"),
            })
            yield row


def discover(items):
    out = []
    for item in items:
        if os.path.isdir(item):
            out.extend(sorted(glob.glob(os.path.join(item, "**", "*.wowsreplay"), recursive=True)))
        elif os.path.isfile(item):
            out.append(item)
        else:
            hit = sorted(glob.glob(item, recursive=True))
            if hit:
                out.extend(hit)
            else:
                print(f"warning: no matches for {item!r}", file=sys.stderr)
    seen, dedup = set(), []
    for p in out:
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            dedup.append(p)
    return dedup


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("replays", nargs="+", help="dirs / files / glob patterns (recurses into dirs)")
    ap.add_argument("--out", default="replays_parsed.jsonl", help="output JSONL (one row per player)")
    ap.add_argument("--constants-dir", default="constants_cache", help="per-build constants cache dir")
    ap.add_argument("--no-fetch", action="store_true", help="do not fetch missing constants from GitHub")
    ap.add_argument("--no-resolve-ships", action="store_true", help="skip WG ship name/tier/class lookup")
    ap.add_argument("--ship-cache", default="ships_cache.json", help="ship id -> name/tier/class cache")
    ap.add_argument("--region", default="eu", help="WG API region")
    ap.add_argument("--app-id", default=WG_APP_ID, help="WG application id")
    ap.add_argument("--workers", type=int, default=0, help="parallel workers (0 = cpu count)")
    ap.add_argument("--limit", type=int, default=0, help="only full-parse the first N files (for testing)")
    ap.add_argument("--db", default="replays.db", help="SQLite output (upsert, dedup by arena_id+account_id)")
    ap.add_argument("--overwrite", action="store_true", help="start fresh (clear JSONL and DB) instead of appending")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    paths = discover(args.replays)
    if not paths:
        print("no replay files matched", file=sys.stderr)
        return 2

    # ---- fast metadata pre-scan: modes, versions, distinct builds ----
    metas = {}
    builds = set()
    pre_ok = 0
    for p in paths:
        try:
            m = read_meta_only(p)
            metas[p] = m
            b, _ = build_and_version(m)
            if b is not None:
                builds.add(b)
            pre_ok += 1
        except Exception as exc:
            print(f"SKIP {p}: bad header ({exc})", file=sys.stderr)

    # ---- resolve per-build constants (cache + optional fetch) ----
    resolved = {}
    unresolved_builds = []
    for b in sorted(builds):
        tbl = load_build_tables(b, args.constants_dir, allow_fetch=not args.no_fetch)
        if tbl:
            resolved[str(b)] = {k: tbl.get(k) for k in SHIFTING_PUBLIC}
        else:
            unresolved_builds.append(b)

    reg = {"resolved": resolved}
    if args.workers == 0:
        workers = os.cpu_count() or 1
    else:
        workers = args.workers
    workers = max(1, min(workers, len(paths)))

    target = paths[: args.limit] if args.limit else paths
    games = []
    if workers == 1:
        _set_reg(reg)
        for i, p in enumerate(target, 1):
            try:
                g = _parse_game(p) if p in metas else None
                if g:
                    games.append(g)
            except Exception as exc:
                print(f"SKIP {p}: {exc}", file=sys.stderr)
            if args.verbose and i % 200 == 0:
                print(f"  parsed {i}/{len(target)}", file=sys.stderr)
    else:
        from concurrent.futures import as_completed
        _set_reg(reg)
        with ProcessPoolExecutor(max_workers=workers, initializer=_set_reg, initargs=(reg,)) as ex:
            futs = {ex.submit(_parse_game, p): p for p in target if p in metas}
            done = 0
            for fut in as_completed(futs):
                p = futs[fut]
                done += 1
                try:
                    g = fut.result()
                    if g:
                        games.append(g)
                except Exception as exc:
                    print(f"SKIP {p}: {exc}", file=sys.stderr)
                if args.verbose and done % 200 == 0:
                    print(f"  parsed {done}/{len(futs)}", file=sys.stderr)
        games.sort(key=lambda g: g["source"])

    # ---- ship resolution ----
    ship_ids = set()
    for g in games:
        for p in g["players"]:
            if p.get("vehicle_type_id") is not None:
                ship_ids.add(int(p["vehicle_type_id"]))
    do_ships = not args.no_resolve_ships
    ship_info = resolve_ship_info(ship_ids, args.ship_cache, do_ships, args.region, args.app_id)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = list(emit_rows(games, ship_info, do_ships))

    con = None
    if args.db:
        con = init_db(args.db, overwrite=args.overwrite)
    seen = set() if args.overwrite else load_seen(out, args.db if args.db else None)
    new_rows = [r for r in rows if r.get("arena_id") not in seen]

    mode = "w" if args.overwrite else "a"
    with open(out, mode, encoding="utf-8") as fh:
        for row in new_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    written = len(new_rows)
    if con is not None:
        upsert_db(con, new_rows)
        con.close()

    # ---- report ----
    fam = {}
    for g in games:
        fam[g["scenario_family"]] = fam.get(g["scenario_family"], 0) + 1
    print(f"files matched={pre_ok} full-parsed={len(games)} player-rows={written} -> {out}")
    print(f"distinct builds={len(builds)} resolved={len(resolved)} unresolved={len(unresolved_builds)}")
    if unresolved_builds:
        print("unresolved builds (damage/exp nulled):", ", ".join(map(str, unresolved_builds)))
    print("scenario family:")
    for k, v in sorted(fam.items(), key=lambda x: -x[1]):
        print(f"  {k:22s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
