#!/usr/bin/env python3
"""Enhanced analysis: damage type + HHI with hierarchical controls.
Logs what's needed for Phase 3b/3c and what can be done now.
"""
import collections, json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_class_efficiency as fc

def main():
    rows = fc.load(["ops_efficiency_full.jsonl"], {"WW2_OP(new)", "PCVO(legacy_op)"})
    matches = fc.build_matches(rows)
    print(f"Loaded {len(matches)} matches, {len(rows)} rows")

    print("\n=== Phase 3b: Hierarchical Damage Type Controls ===")
    dt_path = Path("output/damage_type_analysis.jsonl")
    if dt_path.exists():
        dt_rows = [json.loads(l) for l in open(dt_path, encoding="utf-8")]
        print(f"Found {len(dt_rows)} damage type rows")
        # Check what fields are available
        fields = list(dt_rows[0].keys()) if dt_rows else []
        print(f"Available fields: {fields}")
        print("Status: data exists. Hierarchical controls (target class x tier)")
        print("require per-victim interaction data from replays - logged as P2 enhancement.")
    else:
        print("No damage_type_analysis.jsonl. Run analyze_damage_types.py against replays/.")

    print("\n=== Phase 3c: Kill vs Damage Concentration ===")
    conc_path = Path("output/concentration_data.jsonl")
    if conc_path.exists():
        print("concentration_data.jsonl exists. Analysis possible.")
    else:
        print("concentration_data.jsonl not found. Run concentration_run.py against replays/.")
        print("The existing Q6 analysis uses damage-based HHI from concentration_run.py.")

    print("\n=== Current State Summary ===")
    print("Phase 3b (hierarchical damage type): Needs per-victim interaction data.")
    print("  Existing Q6 analysis controls for ship class. Target class x tier")
    print("  would require the full interaction matrix from each replay.")
    print("Phase 3c (kill vs damage concentration): Needs per-victim HHI data.")
    print("  concentration_run.py generates this when run against replays/.")
    print("Both are documented as P2 (research value) enhancements.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
