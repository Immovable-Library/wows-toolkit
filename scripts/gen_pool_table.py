import collections
import json


def fmean(v):
    return sum(v) / len(v) if v else None


def main():
    seen = set()
    matches = collections.defaultdict(list)
    for line in open("ops_efficiency_full.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if not r.get("raw_exp") or r.get("raw_exp") <= 0:
            continue
        k = (r["arena_id"], r["account_id"])
        if k in seen:
            continue
        seen.add(k)
        matches[r["arena_id"]].append(r)

    scen = collections.defaultdict(list)
    for arena, grp in matches.items():
        f = grp[0]
        team_raw = sum(r["raw_exp"] for r in grp)
        scen[f["scenario"]].append({
            "team_raw": team_raw,
            "stars": f["stars_server"],
            "win": f["is_win"],
            "bracket": f["bracket"],
            "difficulty": f["difficulty"],
            "family": f["scenario_family"],
        })

    rows = []
    for s, grp in scen.items():
        full = [r for r in grp if r["win"] is True and r["stars"] == 5]
        base = fmean([r["team_raw"] for r in full]) if full else None
        if base is None:
            continue
        bracket = grp[0]["bracket"] or grp[0]["difficulty"] or "-"
        rows.append({
            "scenario": s,
            "family": grp[0]["family"],
            "level": bracket,
            "n_full": len(full),
            "n_total": len(grp),
            "base_pool": round(base, 0),
        })

    rows.sort(key=lambda r: -r["base_pool"])
    with open("output/pool_table.json", "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)

    print("scenario count:", len(rows))
    print("\nTop 30 base pools (win + 5 stars):")
    for r in rows[:30]:
        print("  %-46s %-6s n=%3d base=%8.0f" % (r["scenario"], r["level"], r["n_full"], r["base_pool"]))
    print("\nBottom 15 base pools:")
    for r in rows[-15:]:
        print("  %-46s %-6s n=%3d base=%8.0f" % (r["scenario"], r["level"], r["n_full"], r["base_pool"]))


if __name__ == "__main__":
    main()
