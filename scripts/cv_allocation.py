#!/usr/bin/env python3
"""Match-level cross-validation (optimized: coarser grid for speed)."""
import collections, json, sys, math
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_class_efficiency as fc

def main():
    paths = ["ops_efficiency_full.jsonl"]
    fams = {"WW2_OP(new)", "PCVO(legacy_op)"}
    rows = fc.load(paths, fams)
    matches = fc.build_matches(rows)
    n = len(matches)
    print(f"Total matches: {n}, rows: {sum(m['n'] for m in matches)}")

    rng = np.random.default_rng(42)
    idx = rng.permutation(n)
    matches_arr = [matches[i] for i in idx]

    k = 10
    fold_size = n // k
    results = []

    for fold in range(k):
        start = fold * fold_size
        end = start + fold_size if fold < k - 1 else n
        test_idx = set(range(start, end))
        train = [m for i, m in enumerate(matches_arr) if i not in test_idx]
        test = [m for i, m in enumerate(matches_arr) if i in test_idx]

        sst_train = fc.sst_of(train)
        best = None
        for a in [round(i * 0.05, 2) for i in range(21)]:
            for lam in [round(i * 0.5, 1) for i in range(5)]:
                K = fc.estimate_K(train, a, lam)
                if K is None:
                    continue
                sse = fc.sse_of(train, a, lam, K)
                if best is None or sse < best[0]:
                    best = (sse, a, lam, K)

        sse_train, a, lam, K = best
        r2_train = 1 - sse_train / sst_train

        sse_test = fc.sse_of(test, a, lam, K)
        sst_test = fc.sst_of(test)
        r2_test = 1 - sse_test / sst_test if sst_test > 0 else float("nan")

        class_errors = collections.defaultdict(list)
        for md in test:
            nd = md["n"]
            denom = sum(K[p["class"]] * fc.contrib(p, lam) for p in md["players"])
            if denom <= 0:
                continue
            for p in md["players"]:
                pred = a / nd + (1 - a) * K[p["class"]] * fc.contrib(p, lam) / denom
                class_errors[p["class"]].append(abs(p["x"] - pred))

        fold_res = {
            "fold": fold + 1, "train_matches": len(train), "test_matches": len(test),
            "a": a, "lam": lam,
            "r2_train": round(r2_train, 4), "r2_test": round(r2_test, 4),
            "test_mae": round(float(np.mean([e for errs in class_errors.values() for e in errs])), 5),
            "per_class_mae": {c: round(float(np.mean(errs)), 5) for c, errs in sorted(class_errors.items())},
        }
        results.append(fold_res)
        print(f"Fold {fold+1}/{k}: train R2={r2_train:.4f} test R2={r2_test:.4f} MAE={fold_res['test_mae']:.5f}")

    r2_trains = [r["r2_train"] for r in results]
    r2_tests = [r["r2_test"] for r in results]
    maes = [r["test_mae"] for r in results]
    print(f"\nSummary: train R2={np.mean(r2_trains):.4f}+/-{np.std(r2_trains):.4f}  test R2={np.mean(r2_tests):.4f}+/-{np.std(r2_tests):.4f}  MAE={np.mean(maes):.5f}")

    all_class_mae = collections.defaultdict(list)
    for r in results:
        for c, v in r["per_class_mae"].items():
            all_class_mae[c].append(v)
    for c in sorted(all_class_mae):
        print(f"  {c}: {np.mean(all_class_mae[c]):.5f}")

    out = {
        "n_matches": n, "n_folds": k, "folds": results,
        "summary": {
            "train_r2_mean": round(float(np.mean(r2_trains)), 4),
            "train_r2_std": round(float(np.std(r2_trains)), 4),
            "test_r2_mean": round(float(np.mean(r2_tests)), 4),
            "test_r2_std": round(float(np.std(r2_tests)), 4),
            "test_mae_mean": round(float(np.mean(maes)), 5),
            "per_class_mae": {c: round(float(np.mean(v)), 5) for c, v in all_class_mae.items()},
        },
    }
    with open("output/cv_allocation.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"Results -> output/cv_allocation.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
