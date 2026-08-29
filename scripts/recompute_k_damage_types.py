#!/usr/bin/env python3
"""Recompute class multipliers K with damage-type-weighted efficiency.

Each player's raw ship-eff is repriced in main-battery-equivalent units:
    eff_xp = sum_c (b_c / b_main) * eff_c
where b_c are the fitted XP-share coefficients per damage type (2025+ corpus,
class-controlled share regression). The same within-match equal-floor model
used by fit_class_efficiency.py is then re-estimated on eff_xp. The ratio of
the new K to the raw-eff K shows how much of the class multiplier was actually
damage-type composition.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_class_efficiency as fc
import fit_damage_types as fdt


ROOT = Path(__file__).resolve().parent.parent


def load_weights():
    res = json.loads((ROOT / "output" / "damage_type_results.json").read_text(encoding="utf-8"))
    m = res["damage_split"]
    coefs = dict(zip(m["fields"], m["coef"]))
    weights = {}
    for f, c in coefs.items():
        if f.startswith("eff_"):
            weights[f] = c
    base = weights["eff_main"]
    return {f: c / base for f, c in weights.items()}, base


def main(argv=None):
    rows = fdt.load_rows()
    weights, base = load_weights()

    # Main-battery-equivalent efficiency: every damage type is priced at its
    # fitted XP coefficient relative to main battery.
    rows_xp = []
    rows_raw = []
    for r in rows:
        if not (r.get("raw_exp") or 0) > 0 or not (r.get("eff_total") or 0) > 0:
            continue
        eff_xp = sum((r.get(f) or 0.0) * w for f, w in weights.items())
        rr = dict(r)
        rr["efficiency"] = eff_xp
        rows_xp.append(rr)
        rr2 = dict(r)
        rr2["efficiency"] = r.get("eff_total") or 0.0
        rows_raw.append(rr2)

    print("rows=%d (matches after build_matches filter shown below)" % len(rows_xp))
    res_raw = fc.fit(rows_raw, "raw eff (2025+)")
    res_xp = fc.fit(rows_xp, "xp-weighted eff (2025+)")

    def fit_meta(rows, best):
        matches = fc.build_matches(rows)
        sst = fc.sst_of(matches)
        return {k: best[k] for k in ("a", "lam", "sse")} | {"r2": 1.0 - best["sse"] / sst}

    out = {
        "weights": weights,
        "base_type": "eff_main",
        "base_coef": base,
        "raw_eff": res_raw["K_rebased"],
        "xp_weighted": res_xp["K_rebased"],
        "raw_eff_fit": fit_meta(rows_raw, res_raw),
        "xp_weighted_fit": fit_meta(rows_xp, res_xp),
    }

    # Composition-only expectation: class-level share-weighted mean weight.
    comp = json.loads((ROOT / "output" / "damage_type_results.json").read_text(encoding="utf-8"))[
        "class_composition"
    ]
    out["composition_mean_weight"] = {}
    for cls, rec in comp.items():
        mean_w = sum(
            rec.get("share_%s" % f, 0.0) * w for f, w in weights.items()
        )
        out["composition_mean_weight"][cls] = round(mean_w, 4)
    ca_w = out["composition_mean_weight"]["CL/CA"]
    out["composition_relative_to_CA"] = {
        cls: round(w / ca_w, 4) for cls, w in out["composition_mean_weight"].items()
    }

    (ROOT / "output" / "k_recompute_damage_types.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nweights (relative to main):")
    for f, w in sorted(weights.items()):
        print("  %-14s %8.4f" % (f, w))
    print("\nK (CL/CA = 1.00):")
    print("  %-7s %10s %10s %10s" % ("class", "raw eff", "xp-weighted", "composition rel CA"))
    for cls in fc.CLASSES:
        rel = out["composition_relative_to_CA"].get(cls)
        print("  %-7s %10.4f %10.4f %10.4f" % (
            cls, out["raw_eff"][cls], out["xp_weighted"][cls], rel or 0.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
