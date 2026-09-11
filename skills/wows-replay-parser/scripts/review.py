#!/usr/bin/env python3
"""Run the Rust per-volley aiming/ammo review for a replay and print a recap.

Wires the M2 engine (replayshark report) into the skill. With --player/--date it
also prints the Tier-1 spotting profile for the same night from the all-replays
DB (replays_all.db), so a game's review reads as one H1-H6 recap instead of a
bare aiming dump.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _find_replayshark(explicit: str | None) -> str:
    if explicit and Path(explicit).exists():
        return explicit
    if shutil.which("replayshark"):
        return shutil.which("replayshark")  # type: ignore[return-value]
    # Workspace debug binary, for in-repo development.
    for rel in ("target/debug/replayshark.exe", "target/debug/replayshark"):
        p = Path(__file__).resolve().parent.parent.parent / rel
        if p.exists():
            return str(p)
    # Skill-relative candidate.
    for rel in ("bin/replayshark", "replayshark"):
        p = Path(__file__).resolve().parent / rel
        if p.exists():
            return str(p)
    return explicit or "replayshark"


def main() -> int:
    ap = argparse.ArgumentParser(description="WOWS replay aiming/ammo review")
    ap.add_argument("replay", help="Path to a .wowsreplay file")
    ap.add_argument("--game", default="D:/World_of_Warships", help="Game directory")
    ap.add_argument("--deep", action="store_true", help="Use the per-volley deep report (default: normal)")
    ap.add_argument("--replayshark", default=None, help="Path to the replayshark binary")
    ap.add_argument("--player", default=None, help="Player name for the Tier-1 spotting note")
    ap.add_argument("--date", default=None, help="Match date (YYYYMMDD) for the Tier-1 note")
    args = ap.parse_args()

    exe = _find_replayshark(args.replayshark)
    if not Path(exe).exists():
        print(f"replayshark binary not found: {exe}", file=sys.stderr)
        return 1

    cmd = [exe, "-g", args.game, "report"]
    # Use the skill's local Chinese ship-name table when present.
    names = Path(__file__).resolve().parent.parent / "ship_names.json"
    if names.exists():
        cmd += ["--ship-names", str(names)]
    if args.deep:
        cmd.append("--depth")
    cmd.append(args.replay)
    rc = subprocess.run(cmd)
    if rc.returncode != 0:
        return rc.returncode

    # Optional Tier-1 spotting note from the skill DB, matching the same night.
    if args.player and args.date:
        try:
            import spot_credit

            spot_credit.main([f"--player", args.player, "--date", args.date])
        except Exception as exc:  # never fail the review on the optional note
            print(f"(Tier-1 spotting note skipped: {exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
