import collections
import json

CLASSES = ["DD", "CL/CA", "BB", "CV", "SS"]


def fmean(v):
    return sum(v) / len(v) if v else float("nan")


def main():
    rows = []
    for path in ("ops_efficiency.jsonl", "ops_efficiency_pve.jsonl"):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r.get("scenario_family") not in {"WW2_OP(new)", "PCVO(legacy_op)"}:
                continue
            if not r.get("raw_exp") or not r.get("team_eff"):
                continue
            if r.get("ship_class") not in CLASSES:
                continue
            rows.append(r)

    # dedupe by (arena, account)
    seen = set()
    uniq = []
    for r in rows:
        k = (r["arena_id"], r["account_id"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    rows = uniq

    by = collections.defaultdict(list)
    for r in rows:
        fam = "new" if r["scenario_family"] == "WW2_OP(new)" else "legacy"
        eff_share = r["efficiency"] / r["team_eff"] if r["team_eff"] else None
        xp_share = r["raw_exp"] / r["team_raw"] if r["team_raw"] else None
        eff_per_dmg = (r["efficiency"] * 100000 / r["damage"]) if r["damage"] else None
        by[(fam, r["ship_class"])].append({
            "eff": r["efficiency"],
            "eff_share": eff_share,
            "xp_share": xp_share,
            "dmg": r["damage"],
            "eff_per_dmg": eff_per_dmg,
        })

    print("class     fam     n      mean_eff  mean_eff_share  mean_dmg  mean_xp_share  eff/100kdmg")
    for fam in ("new", "legacy"):
        for c in CLASSES:
            v = by[(fam, c)]
            if not v:
                continue
            print("%-9s %-6s %4d  %8.2f  %13.3f  %9.0f  %12.3f  %12.2f" % (
                c, fam, len(v), fmean([x["eff"] for x in v]),
                fmean([x["eff_share"] for x in v]), fmean([x["dmg"] for x in v]),
                fmean([x["xp_share"] for x in v]),
                fmean([x["eff_per_dmg"] for x in v if x["eff_per_dmg"] is not None])))

    print("\nSS new vs legacy:")
    for k in ("eff_share", "eff", "dmg", "eff_per_dmg"):
        n = fmean([x[k] for x in by[("new", "SS")] if x[k] is not None])
        l = fmean([x[k] for x in by[("legacy", "SS")] if x[k] is not None])
        print("  %-11s new=%.3f  legacy=%.3f  diff=%+.3f" % (k, n, l, n - l))


if __name__ == "__main__":
    main()
