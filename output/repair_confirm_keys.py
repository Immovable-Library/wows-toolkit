#!/usr/bin/env python3
"""Repair double-prefixed keys in confirmed_spawns.json."""

from __future__ import annotations

import json

P = r"C:/Users/asdfg/.codex/skills/wows-map-spawn-atlas/confirmed_spawns.json"


def main() -> None:
    data = open(P, "rb").read()
    for short in ("IDS_OP_01_04_ATAKER_L11", "IDS_OP_01_04_ATAKER_R11"):
        bad = ('"Naval_Defense/BASE/Naval_Defense/BASE/' + short + '"').encode()
        good = ('"Naval_Defense/BASE/' + short + '"').encode()
        n = data.count(bad)
        data = data.replace(bad, good)
        print(f"{short}: replaced {n}")
    open(P, "wb").write(data)
    d = json.load(open(P, encoding="utf-8"))
    print("json ok")
    for k in ("Naval_Defense/BASE/IDS_OP_01_04_ATAKER_L11",
              "Naval_Defense/BASE/IDS_OP_01_04_ATAKER_R11"):
        print(k)
        print(json.dumps(d[k], ensure_ascii=False, indent=1)[:900])


if __name__ == "__main__":
    main()
