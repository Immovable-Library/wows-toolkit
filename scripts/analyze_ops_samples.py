#!/usr/bin/env python3
"""Analyse the Operations pre-battle snapshot and post-battle result logs.

Joins `ops_samples.jsonl` (pre-battle `oper_solo` server stats) to
`ops_results.jsonl` (each human's per-match outcome) on `(arena_id,
account_id)`, then reports how well the historical stats predict the current
match's individual output (XP, damage, frags).

Usage:
    python scripts/analyze_ops_samples.py [SAMPLES_JSONL] [RESULTS_JSONL]

When no paths are given, defaults to the Windows app data directory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np


FEATURES = [
    "account_avg_xp",
    "account_win_rate",
    "account_five_star",
    "account_battles",
    "ship_avg_xp",
    "ship_win_rate",
    "ship_five_star",
    "ship_battles",
]

LABELS = ["damage", "frags", "raw_xp"]


def default_samples_path() -> str:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return "ops_samples.jsonl"
    return os.path.join(appdata, "WoWs Toolkit", "data", "ops_samples.jsonl")


def default_results_path() -> str:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return "ops_results.jsonl"
    return os.path.join(appdata, "WoWs Toolkit", "data", "ops_results.jsonl")


def load(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def battles_of(block) -> int | None:
    if not block:
        return None
    n = block.get("battles")
    return n if isinstance(n, int) and n > 0 else None


def avg_xp(block) -> float | None:
    n = battles_of(block)
    if n is None:
        return None
    return float(block.get("xp") or 0) / n


def win_rate(block) -> float | None:
    n = battles_of(block)
    if n is None:
        return None
    return float(block.get("wins") or 0) / n


def five_star_rate(block) -> float | None:
    n = battles_of(block)
    if n is None:
        return None
    return float((block.get("wins_by_tasks") or {}).get("5", 0)) / n


def build_dataset(samples: list[dict], results: list[dict]) -> list[dict]:
    snapshots = {(s["arena_id"], s["account_id"]): s for s in samples}
    rows = []
    for result in results:
        snapshot = snapshots.get((result["arena_id"], result["account_id"]))
        if snapshot is None:
            continue
        account = snapshot.get("account") or {}
        ship = snapshot.get("ship")
        rows.append(
            {
                "arena_id": result["arena_id"],
                "account_id": result["account_id"],
                "account_avg_xp": avg_xp(account),
                "account_win_rate": win_rate(account),
                "account_five_star": five_star_rate(account),
                "account_battles": account.get("battles"),
                "ship_avg_xp": avg_xp(ship),
                "ship_win_rate": win_rate(ship),
                "ship_five_star": five_star_rate(ship),
                "ship_battles": (ship or {}).get("battles"),
                "damage": result.get("damage"),
                "frags": result.get("frags"),
                "raw_xp": result.get("raw_xp"),
            }
        )
    return rows


def add_within_match_z(dataset: list[dict]) -> None:
    by_arena = defaultdict(list)
    for row in dataset:
        by_arena[row["arena_id"]].append(row)
    for rows in by_arena.values():
        for label in LABELS:
            values = [row[label] for row in rows if row[label] is not None]
            if len(values) < 3:
                continue
            mean = float(np.mean(values))
            std = float(np.std(values))
            for row in rows:
                value = row[label]
                row[f"{label}_z"] = (value - mean) / std if (std > 0 and value is not None) else None


def pearson(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    if len(a) < 3:
        return None, len(a)
    return float(np.corrcoef(a, b)[0, 1]), len(a)


def linear_fit(cols, ycol, dataset):
    data = [
        [row[c] for c in cols] + [row[ycol]]
        for row in dataset
        if all(row[c] is not None for c in cols) and row[ycol] is not None
    ]
    if len(data) < 4:
        return None
    data = np.asarray(data, dtype=float)
    x = np.column_stack([data[:, :-1], np.ones(len(data))])
    y = data[:, -1]
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    y_hat = x @ coef
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return coef, r2, len(y)


def rank_stats(dataset, label, key="ship_avg_xp"):
    by_arena = defaultdict(list)
    for row in dataset:
        by_arena[row["arena_id"]].append(row)
    top1 = 0
    total = 0
    spearman = []
    for rows in by_arena.values():
        ranked = [row for row in rows if row[key] is not None and row[label] is not None]
        if len(ranked) < 3:
            continue
        predicted_best = max(ranked, key=lambda row: row[key])
        actual_best = max(ranked, key=lambda row: row[label])
        total += 1
        if predicted_best["account_id"] == actual_best["account_id"]:
            top1 += 1
        if len(ranked) > 1:
            rx = np.argsort(np.argsort([row[key] for row in ranked]))
            ry = np.argsort(np.argsort([row[label] for row in ranked]))
            spearman.append(float(np.corrcoef(rx, ry)[0, 1]))
    mean_spearman = float(np.mean(spearman)) if spearman else float("nan")
    return total, top1, mean_spearman


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples", nargs="?", default=default_samples_path())
    parser.add_argument("results", nargs="?", default=default_results_path())
    args = parser.parse_args()

    samples = load(args.samples)
    results = load(args.results)
    dataset = build_dataset(samples, results)
    add_within_match_z(dataset)

    print(f"samples: {len(samples)} rows  results: {len(results)} rows  joined: {len(dataset)} rows")
    print(f"unique matches: {len(set(row['arena_id'] for row in dataset))}")

    print("\n== Pearson correlation (feature -> label) ==")
    for feature in FEATURES:
        for label in LABELS:
            r, n = pearson([row[feature] for row in dataset], [row[label] for row in dataset])
            if r is not None:
                print(f"  {feature:20s} -> {label:8s}  r={r:+.3f}  n={n}")

    print("\n== Pearson correlation (feature -> within-match z-scored label) ==")
    for feature in FEATURES:
        for label in LABELS:
            r, n = pearson([row[feature] for row in dataset], [row[f"{label}_z"] for row in dataset])
            if r is not None:
                print(f"  {feature:20s} -> {label}_z  r={r:+.3f}  n={n}")

    print("\n== Linear regression R2 ==")
    for ycol in ["raw_xp", "raw_xp_z", "damage", "damage_z"]:
        for cols in [
            ["ship_avg_xp"],
            ["ship_avg_xp", "account_avg_xp"],
            ["ship_avg_xp", "account_avg_xp", "ship_win_rate"],
        ]:
            fit = linear_fit(cols, ycol, dataset)
            if fit is None:
                continue
            _, r2, n = fit
            print(f"  {ycol:10s} ~ {cols}  R2={r2:+.3f}  n={n}")

    print("\n== Ranking sanity (ship_avg_xp, per match, >=3 ranked players) ==")
    for label in ["raw_xp", "damage"]:
        total, top1, spearman = rank_stats(dataset, label)
        print(f"  {label}: matches={total} top1-accuracy={top1}/{total} mean-within-Spearman={spearman:+.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
