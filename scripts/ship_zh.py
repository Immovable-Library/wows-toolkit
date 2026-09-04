#!/usr/bin/env python3
"""Map ship ids to standard Chinese names for operation reports.

Sources:
  ships_zh.json        ship id -> Chinese name (built from the 996-ship
                       roster in the local play-style table)
  SPECIAL_ZH           剧情-only entities that WG's encyclopedia does not
                       resolve (transports, facilities, and Z-38)
"""

from __future__ import annotations

import json
from pathlib import Path


_ZH = json.loads(
    (Path(__file__).resolve().parent.parent / "ships_zh.json").read_text(encoding="utf-8")
)

SPECIAL_ZH = {
    "3522049840": "Z-38（德国 T7 驱逐，显示名 Fritz 1~3）",
    "4293146608": "运输船（剧情专用）",
    "4248057104": "运输船（剧情专用）",
    "4247008528": "运输船（剧情专用）",
    "4266931472": "运输船（剧情专用）",
    "4288952304": "运输船（剧情专用）",
    "3448747280": "航母（剧情专用）",
    "3767448848": "环境设施（剧情专用，超高血量）",
}


def zh_name(ship_id, fallback_en=None):
    """Return the standard Chinese name for ship_id, else fallback_en."""
    if ship_id is None:
        return fallback_en
    sid = str(ship_id)
    if sid in SPECIAL_ZH:
        return SPECIAL_ZH[sid]
    return _ZH.get(sid) or fallback_en
