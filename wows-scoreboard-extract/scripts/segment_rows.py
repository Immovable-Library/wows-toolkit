#!/usr/bin/env python3
"""Segment a World of Warships '我的团队' scoreboard screenshot into row crops.

The detector is tuned for the standard WoWS post-battle team table:
a narrow header band ("我的团队") followed by 7 data rows.  It finds text
bands using bright-pixel projection on the left side of the image (player
name / ship name area), drops the first band (the header), and writes one
upscaled PNG per data row.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image
import numpy as np


def find_text_bands(
    gray: Image.Image,
    x1: int,
    x2: int,
    threshold: int = 95,
    min_count: int = 4,
    gap: int = 3,
) -> list[tuple[int, int]]:
    """Return (y_start, y_end) bands containing bright text pixels."""
    arr = np.asarray(gray, dtype=np.uint8)
    counts = (arr[:, x1:x2] > threshold).sum(axis=1)
    ys = np.where(counts > min_count)[0]
    if len(ys) == 0:
        return []

    bands: list[tuple[int, int]] = []
    start = int(ys[0])
    prev = int(ys[0])
    for y in ys[1:]:
        y = int(y)
        if y - prev > gap:
            bands.append((start, prev))
            start = y
        prev = y
    bands.append((start, prev))
    return bands


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate one crop PNG per data row from a WoWS team scoreboard screenshot."
    )
    parser.add_argument("image", help="Path to the scoreboard screenshot")
    parser.add_argument(
        "-o",
        "--outdir",
        default=".",
        help="Output directory for row crops (default: current directory)",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=3,
        help="Upscale factor for each row crop (default: 3)",
    )
    parser.add_argument(
        "--left",
        type=int,
        default=35,
        help="Left x used for text-band detection (default: 35)",
    )
    parser.add_argument(
        "--right",
        type=int,
        default=450,
        help="Right x used for text-band detection (default: 450)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=95,
        help="Brightness threshold for text pixels (default: 95)",
    )
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Image not found: {image_path}", file=sys.stderr)
        return 1

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as im:
        width, height = im.size
        gray = im.convert("L")
        left = max(0, min(args.left, width - 1))
        right = max(left + 1, min(args.right, width))
        bands = find_text_bands(gray, left, right, threshold=args.threshold)

    # Expected: 1 header band + 7 data rows for this table layout.
    if len(bands) < 2:
        print(
            f"Warning: only {len(bands)} text bands found; "
            "cannot reliably separate the table.",
            file=sys.stderr,
        )

    # The first band is the table header when the screenshot starts with
    # '我的团队'.  For this skill we specifically drop it.
    row_bands = bands[1:8]

    if len(row_bands) == 0:
        print("No data rows found.", file=sys.stderr)
        return 1

    with Image.open(image_path) as im:
        # Keep the full row width so the crop contains tier, ship name, and
        # the kill / XP columns.
        x1 = 0
        x2 = width
        crop_paths: list[Path] = []
        for i, (y1, y2) in enumerate(row_bands, start=1):
            # Add a small vertical margin around the detected text band.
            cy1 = max(0, y1 - 3)
            cy2 = min(height, y2 + 4)
            crop = im.crop((x1, cy1, x2, cy2))
            if args.scale > 1:
                crop = crop.resize(
                    (crop.width * args.scale, crop.height * args.scale),
                    Image.LANCZOS,
                )
            out_path = outdir / f"row_{i:02d}.png"
            crop.save(out_path)
            crop_paths.append(out_path)
            print(out_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
