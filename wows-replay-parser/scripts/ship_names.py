#!/usr/bin/env python3
"""Map ship ids to standard Chinese ship names.

Source: <skill>/ship_names.json, generated from the local wows-toolkit
output/ship_strength_full.json (ship_id -> Chinese name). Unknown ships
fall back to the English name instead of inventing a translation.
"""
from __future__ import annotations

import json
from pathlib import Path

_CN = json.loads(
    (Path(__file__).resolve().parent.parent / "ship_names.json").read_text(encoding="utf-8")
)


def cn_name(ship_id, fallback_en=None):
    """Return the standard Chinese ship name for ship_id, or fallback_en."""
    if ship_id is None:
        return fallback_en
    name = _CN.get(str(ship_id))
    return name or fallback_en