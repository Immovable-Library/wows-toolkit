#!/usr/bin/env python3
"""Map internal operation scenario codes to standard Chinese names.

The mapping table lives at <skill>/scenario_names.json and mirrors the
verified table in the local wows-toolkit repo
(scripts/gen_ops_name_table.py, output/ops_scenario_mapping_verified.md).
Use this when describing operation games in reports or summaries; raw
internal codes are for data storage only.
"""
from __future__ import annotations

import json
from pathlib import Path


def _load():
    p = Path(__file__).resolve().parent.parent / "scenario_names.json"
    return json.loads(p.read_text(encoding="utf-8"))["entries"]


_ENTRIES = _load()
_BY_CODE = {e["code"]: e for e in _ENTRIES}


def standard_name(scenario: str) -> tuple[str, str | None]:
    """Return (standard Chinese name, matched internal code).

    Unmatched scenarios are returned unchanged with None so nothing is
    silently mislabeled; extend scenario_names.json when a new code shows up.
    """
    for code in _BY_CODE:
        if code in scenario:
            return _BY_CODE[code]["name_cn"], code
    return scenario, None