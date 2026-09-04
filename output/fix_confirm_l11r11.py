#!/usr/bin/env python3
"""Byte-level patch: give L11/R11 per-variant positions (CRLF-safe)."""

from __future__ import annotations

import re

P = r"C:/Users/asdfg/.codex/skills/wows-map-spawn-atlas/confirmed_spawns.json"


def new_block(name: str, right: tuple[float, float], left: tuple[float, float]) -> bytes:
    note = (
        "双机制：Kousotsu局=追击得梅因舰队，Romeo出现后约30s独立刷"
        "（左中右/中右中30.3s，右中左/中左中约25s），位置与Romeo同侧："
        "左中右/中右中=右边({:.0f},{:.0f})，右中左/中左中=左边({:.0f},{:.0f})；"
        "Gunkan局=无独立追击波（无Romeo，支线失败提前总攻），"
        "与Falc/Ulrich/Kumo/Chancellor同批作为总攻部队刷出"
        "（033任务=保卫巡洋舰罗密欧，激活于波3清完+约1s）"
    ).format(right[0], right[1], left[0], left[1])
    rx, rz = right
    lx, lz = left
    return (
        '  "Naval_Defense/BASE/{name}": {{\r\n'
        '    "clock": null,\r\n'
        '    "dynamic": true,\r\n'
        '    "note": "{note}",\r\n'
        '    "positions": [\r\n'
        '      {{\r\n'
        '        "x": {rx},\r\n'
        '        "z": {rz}\r\n'
        '      }},\r\n'
        '      {{\r\n'
        '        "x": {lx},\r\n'
        '        "z": {lz}\r\n'
        '      }}\r\n'
        '    ]\r\n'
        '  }},\r\n'
    ).format(name=name, note=note, rx=rx, rz=rz, lx=lx, lz=lz).encode("utf-8")


def main() -> None:
    data = open(P, "rb").read()
    blocks = {
        "Naval_Defense/BASE/IDS_OP_01_04_ATAKER_L11": ((646.0, 242.0), (-202.0, -688.0)),
        "Naval_Defense/BASE/IDS_OP_01_04_ATAKER_R11": ((677.0, 277.0), (-222.0, -688.0)),
    }
    for name, (right, left) in blocks.items():
        pat = re.compile(rb'  "' + name.encode() + rb'": \{.*?\r\n  \},', re.S)
        m = pat.search(data)
        if not m:
            raise SystemExit(f"block not found: {name}")
        data = data[:m.start()] + new_block(name, right, left) + data[m.end():]
    # Repair double-prefixed keys introduced by the template above.
    for short in ("IDS_OP_01_04_ATAKER_L11", "IDS_OP_01_04_ATAKER_R11"):
        data = data.replace(
            ('"Naval_Defense/BASE/Naval_Defense/BASE/' + short + '"').encode(),
            ('"Naval_Defense/BASE/' + short + '"').encode(),
        )
    open(P, "wb").write(data)
    print("patched")


if __name__ == "__main__":
    main()
