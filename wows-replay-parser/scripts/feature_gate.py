#!/usr/bin/env python3
"""Feature-table gate: locate ships in reports/舰船特色表.xlsx and report status.

Reads the 舰船特色表 sheet, finds rows for the given ships (match by Chinese or
English name), and prints each ship's Excel row number, identity, annotated
features, and the feature columns still waiting to be filled.

Feature cells count as annotated when non-empty (the sheet convention is "1").

Exit code: 0 = every requested ship is annotated; 1 = at least one is not.

Usage:
  python scripts/feature_gate.py 大和 Yamato "North Carolina 2"
  python scripts/feature_gate.py --all-unannotated
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "reports" / "舰船特色表.xlsx"
SHEET = "舰船特色表"


def norm(s: str) -> str:
    s = (s or "").replace("\u00a0", " ").replace("[", "").replace("]", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s'’\-_.,·]+", "", s).lower()


def load():
    import openpyxl
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb[SHEET]
    it = ws.iter_rows(values_only=True)
    header = list(next(it))
    try:
        nation_idx = header.index("国家")
    except ValueError:
        nation_idx = 4
    try:
        note_idx = header.index("备注")
    except ValueError:
        note_idx = len(header) - 1
    feat_names = [h for h in header[nation_idx + 1:note_idx] if h]
    feat_off = nation_idx + 1
    rows = []
    for r, vals in enumerate(it, start=2):
        cells = list(vals) + [None] * (len(header) - len(vals))
        feats = {}
        for i, name in enumerate(feat_names):
            v = cells[feat_off + i]
            feats[name] = "" if v is None else str(v).strip()
        rows.append({
            "row": r,
            "cn": str(cells[0] or "").strip(),
            "en": str(cells[1] or "").strip(),
            "tier": cells[2],
            "cls": str(cells[3] or "").strip(),
            "nation": str(cells[4] or "").strip(),
            "feats": feats,
        })
    wb.close()
    return header, rows


def annotated(feats):
    return [k for k, v in feats.items() if v]


def apply_filter(rows):
    """Set a worksheet-level autoFilter (中文名 column) so the sheet opens with
    only the given rows visible. Uses the classic worksheet autoFilter (not a
    table-internal one) so both Excel and WPS honor it. Any Excel table part is
    removed; the underlying data is unchanged.
    """
    if not rows:
        return
    names = [escape(r["cn"]) for r in rows]
    tmp = XLSX.with_suffix(".filtered.xlsx")

    with zipfile.ZipFile(XLSX, "r") as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        infos = {i.filename: i for i in zin.infolist()}

        # locate the 舰船特色表 sheet file via workbook.xml -> rels
        wb_xml = zin.read("xl/workbook.xml").decode("utf-8")
        m = re.search(r'<(?:x:)?sheet[^>]*name="舰船特色表"[^>]*r:id="([^"]+)"', wb_xml)
        wb_rels = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        sheet_path = "xl/worksheets/sheet1.xml"
        if m:
            rm = re.search(r'<Relationship[^>]*Id="' + re.escape(m.group(1)) + r'"[^>]*Target="([^"]+)"', wb_rels)
            if rm:
                sheet_path = "xl/" + rm.group(1).lstrip("/")

        ref = "A1:AH997"
        for name in ("xl/worksheets/sheet1.xml", sheet_path):
            if name in infos:
                xml = zin.read(name).decode("utf-8")
                dm = re.search(r'<x:dimension[^>]*ref="([^"]+)"', xml)
                if dm:
                    ref = dm.group(1)
                break

        for item in infos.values():
            data = zin.read(item.filename)
            if item.filename == sheet_path:
                xml = data.decode("utf-8")
                new_auto = (
                    f'<x:autoFilter ref="{ref}"><x:filterColumn colId="0"><x:filters>'
                    + "".join(f'<x:filter val="{n}"/>' for n in names)
                    + "</x:filters></x:filterColumn></x:autoFilter>"
                )
                xml = re.sub(r"</(?:x:)?sheetData>", "</x:sheetData>" + new_auto, xml, count=1)
                xml = re.sub(r"<(?:x:)?tableParts[^>]*/>", "", xml)
                xml = re.sub(r"<(?:x:)?tableParts[^>]*>.*?</(?:x:)?tableParts>", "", xml, flags=re.S)
                data = xml.encode("utf-8")
            elif item.filename.startswith("xl/tables/"):
                continue  # drop table parts
            elif item.filename.endswith(".rels") and "/worksheets/" in item.filename:
                rels = data.decode("utf-8")
                rels = re.sub(r"<Relationship[^>]*officeDocument/2006/relationships/table[^>]*/>", "", rels)
                data = rels.encode("utf-8")
            zout.writestr(item, data)
    tmp.replace(XLSX)


def describe(row):
    feats = row["feats"]
    has = annotated(feats)
    missing = [k for k in feats if not feats[k]]
    lines = [
        f"行 {row['row']}: {row['cn']} / {row['en']} (T{row['tier']} {row['cls']} {row['nation']})",
    ]
    if has:
        lines.append(f"  已标注: {', '.join(has)}")
        lines.append(f"  待补: {len(missing)} 列")
    else:
        lines.append(f"  未标注: 28 列全空, 需填 {len(missing)} 个特色列: {', '.join(missing)}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ships", nargs="*", help="ship names to check (Chinese or English)")
    ap.add_argument("--all-unannotated", action="store_true", help="list every unannotated row in the table")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--apply-filter", action="store_true",
                    help="save an Excel autoFilter on the table so only the pending rows are visible when opened")
    args = ap.parse_args(argv)

    header, rows = load()
    if args.all_unannotated:
        hits = [r for r in rows if not annotated(r["feats"])]
    else:
        if not args.ships:
            ap.error("provide ship names or use --all-unannotated")
        wanted = [norm(s) for s in args.ships]
        hits = [r for r in rows if norm(r["cn"]) in wanted or norm(r["en"]) in wanted]
        if not hits:
            print(f"no rows matched ships: {args.ships}", file=sys.stderr)
            return 2

    if args.json:
        payload = [{
            "row": r["row"], "cn": r["cn"], "en": r["en"], "tier": r["tier"],
            "class": r["cls"], "nation": r["nation"],
            "annotated": annotated(r["feats"]),
            "missing": [k for k in r["feats"] if not r["feats"][k]],
        } for r in hits]
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    else:
        for r in hits:
            print(describe(r))
        print()
        ok = all(annotated(r["feats"]) for r in hits)
        print("全部已标注" if ok else "存在未标注船只，拒绝执行分析；请按上方行号补填 '1' 后重试")

    bad = any(not annotated(r["feats"]) for r in hits)
    if args.apply_filter and bad:
        pending = [r for r in hits if not annotated(r["feats"])]
        apply_filter(pending)
        print(f"已筛选特色表: 打开后仅显示 {len(pending)} 行待标注数据")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())