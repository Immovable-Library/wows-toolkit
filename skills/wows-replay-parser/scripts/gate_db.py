#!/usr/bin/env python3
"""Derive the version-gated replay DB from the all-replays DB.

Two databases are kept side by side:

  replays_all.db  every parseable replay, no gate
                  (collect with extract_ops_replays.py --no-approval-filter)
  replays.db      only arenas the operations approval pool accepts
                  (spawn calibration and other version-sensitive work)

Approved arenas of the source are copied into the destination, replacing any
older copy of the same row. Destination arenas the pool does not approve are
deleted, judged from the destination's own scenario and build, so a source
that is not a superset can never drop an approved row. Idempotent, so it is
also the way to re-apply the gate after approval_pool.json changes, without
re-parsing any replay.

The gate can only be recomputed from what the DB stores (scenario and build).
A rule that needs some other field (operation id, for instance) requires that
field to be ingested first.

Usage:
  python scripts/gate_db.py --src replays_all.db --dst replays.db --dry-run
  python scripts/gate_db.py --src replays_all.db --dst replays.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_ops_replays as ex  # noqa: E402

BUSY_TIMEOUT_MS = 10000


def connect(path, readonly=False):
    if readonly:
        con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    else:
        con = sqlite3.connect(str(path))
    con.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return con


def check_schema(con, path):
    cols = [r[1] for r in con.execute("PRAGMA table_info(rows)")]
    if not cols:
        raise SystemExit(f"{path}: no rows table")
    if cols != ex.DB_COLUMNS:
        raise SystemExit(f"{path}: schema does not match this script's DB_COLUMNS")


def classify_arenas(con, config, approval_lib):
    """Return (approved arena ids, dropped counts) for every arena in ``con``."""
    approved, dropped = [], {}
    for arena_id, scenario, build in con.execute(
            "SELECT arena_id, scenario, build FROM rows GROUP BY arena_id"):
        scenario = scenario or ""
        status, pool, reason = approval_lib.classify(
            scenario, ex.map_family(scenario), build, config)
        if status == "approved":
            approved.append(arena_id)
        else:
            key = (status, pool, reason or "")
            dropped[key] = dropped.get(key, 0) + 1
    return approved, dropped


def report_dropped(dropped, kept, label):
    print(f"{label}: kept={kept} dropped={sum(dropped.values())}")
    for (status, pool, reason), n in sorted(dropped.items(), key=lambda kv: -kv[1])[:8]:
        name = pool or "not in any pool"
        print(f"  {n:6d}  {status:8s} {name}" + (f" [{reason}]" if reason else ""))


def sync(src_path, dst_path, pool_path, dry_run):
    src_p, dst_p = Path(src_path).resolve(), Path(dst_path).resolve()
    if src_p == dst_p:
        raise SystemExit("refusing to run: --src and --dst are the same database")
    if not src_p.exists():
        raise SystemExit(f"{src_p}: not found")

    config, approval_lib = ex.load_approval(pool_path)
    src = connect(src_p, readonly=True)
    check_schema(src, src_p)

    approved, dropped = classify_arenas(src, config, approval_lib)
    src_n = src.execute("SELECT count(*) FROM rows").fetchone()[0]
    src_arenas = src.execute("SELECT count(DISTINCT arena_id) FROM rows").fetchone()[0]
    report_dropped(dropped, len(approved), f"source {src_p} ({src_n} rows / {src_arenas} arenas)")
    if src_n == 0:
        raise SystemExit(f"{src_p}: no rows to derive from; destination left untouched")
    if not approved:
        raise SystemExit(f"{src_p}: no arena passes the pool; destination left untouched. "
                         "Check the pool file before re-running.")

    if dry_run:
        print("dry run: destination untouched")
        return 0

    # Validate the destination before init_db touches it.
    if dst_p.exists():
        existing = connect(dst_p)
        check_schema(existing, dst_p)
        existing.close()

    dst = ex.init_db(dst_path)
    check_schema(dst, dst_p)
    idx = [r for r in dst.execute("PRAGMA index_list(rows)") if r[1] == "idx_arena_acct"]
    if not idx or not idx[0][2]:
        raise SystemExit(f"{dst_p}: idx_arena_acct is missing or not unique; "
                         "refusing to write without the dedup contract")

    dst.execute("ATTACH DATABASE ? AS src", (str(src_p),))
    dst.execute("CREATE TEMP TABLE approved_arena (arena_id INTEGER PRIMARY KEY)")
    dst.executemany("INSERT OR IGNORE INTO approved_arena VALUES (?)",
                    ((a,) for a in approved))

    cols = ", ".join('"%s"' % c for c in ex.DB_COLUMNS)
    before_rows = dst.execute("SELECT count(*) FROM rows").fetchone()[0]
    before_arenas = dst.execute("SELECT count(DISTINCT arena_id) FROM rows").fetchone()[0]

    dst.execute(
        f"INSERT OR REPLACE INTO rows ({cols}) SELECT {cols} FROM src.rows "
        "WHERE arena_id IN (SELECT arena_id FROM approved_arena)")
    copied = dst.execute("SELECT count(*) FROM rows").fetchone()[0] - before_rows

    # Destination arenas the source does not cover are judged by their own
    # scenario and build: approved ones stay, the rest are dropped. Rows with
    # no scenario are kept and reported, because the gate cannot judge them.
    stale = [r for r in dst.execute(
        "SELECT arena_id, scenario, build FROM rows "
        "WHERE arena_id NOT IN (SELECT arena_id FROM approved_arena) "
        "GROUP BY arena_id")]
    doomed, unjudged = [], 0
    for arena_id, scenario, build in stale:
        scenario = scenario or ""
        if not scenario:
            unjudged += 1
            continue
        if approval_lib.classify(scenario, ex.map_family(scenario), build, config)[0] != "approved":
            doomed.append(arena_id)
    removed = 0
    if doomed:
        dst.execute("DELETE FROM rows WHERE arena_id IN (%s)" % ",".join("?" * len(doomed)), doomed)
        removed = len(doomed)
    dst.commit()
    dst.execute("VACUUM")

    after_rows = dst.execute("SELECT count(*) FROM rows").fetchone()[0]
    after_arenas = dst.execute("SELECT count(DISTINCT arena_id) FROM rows").fetchone()[0]
    print(f"{dst_p}: arenas {before_arenas} -> {after_arenas}, "
          f"rows {before_rows} -> {after_rows} ({copied:+d} copied, -{removed} pruned)")
    if unjudged:
        print(f"  warning: {unjudged} destination arenas have no scenario and were left in place")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default="replays_all.db", help="all-replays DB (read-only)")
    ap.add_argument("--dst", default="replays.db", help="gated DB to create/refresh")
    ap.add_argument("--approval-pool", default=str(ex.APPROVAL_POOL),
                    help="operations approval pool (JSON)")
    ap.add_argument("--dry-run", action="store_true", help="classify and report only")
    args = ap.parse_args(argv)
    return sync(args.src, args.dst, args.approval_pool, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
