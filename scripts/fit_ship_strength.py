#!/usr/bin/env python3
"""Fit relative Operations ship strength from WG global oper_solo stats.

Data flow (each stage is independent and resumable):

  clans/info -> member account ids
    -> account/info (batch, extra=statistics.oper_solo)  : account-level ops stats
    -> ships/stats (per account, extra=oper_solo)        : per-ship ops stats
    -> encyclopedia/ships (batch)                        : ship_id -> name/tier/class
    -> build_features -> fit(model) -> export

The fitting model is versioned in MODELS so the algorithm can evolve without
touching the fetch/cache layer.  Add a new model by implementing
`fit_vX(features, cfg)` and registering it in MODELS.

Phase 1 (this script): coarse per-ship strength from aggregate WG data.
Phase 2 (later): replay-derived per-tier pool and class coefficients plug in
as an additional model/stage against replays.db.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

APP_ID = "bc914eb0f45397d5855997f8819056aa"
HOSTS = {
    "eu": "api.worldofwarships.eu",
    "na": "api.worldofwarships.com",
    "asia": "api.worldofwarships.asia",
    "ru": "api.worldofwarships.ru",
}
SHIP_STATS_FIELDS = (
    "ship_id,oper_solo.battles,oper_solo.wins,oper_solo.losses,"
    "oper_solo.survived_wins,oper_solo.survived_battles,oper_solo.wins_by_tasks,oper_solo.xp"
)

# Source clans.  PAD high skill, ZUN mixed, LNRS ordinary.
CLANS = [
    {"tag": "PAD", "id": 500137813, "region": "eu"},
    {"tag": "ZUN", "id": 500193778, "region": "eu"},
    {"tag": "LNRS", "id": 2000021931, "region": "asia"},
]


@dataclass
class Config:
    clans: list
    min_acct_battles: int = 20    # trust account baseline only above this
    min_ship_battles: int = 5     # trust a player x ship above this
    min_ship_players: int = 3     # publish a ship above this many players
    model: str = "v1"
    delay: float = 0.12
    cache: str = "cache/ship_strength_cache.json"
    out_json: str = "output/ship_strength.json"
    out_md: str = "output/ship_strength.md"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def api_get(host, path, params, post=False):
    params = dict(params)
    params["application_id"] = APP_ID
    if post:
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(
            f"https://{host}{path}", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "wows-ship-strength/1.0"})
    else:
        url = f"https://{host}{path}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "wows-ship-strength/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def load_cache(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_cache(path, cache):
    if not path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)
    os.replace(tmp, path)


def fetch_clans(clans, cache):
    by_region = {}
    for c in clans:
        by_region.setdefault(c["region"], []).append(c)
    for region, cs in by_region.items():
        ids = ",".join(str(c["id"]) for c in cs)
        data = api_get(HOSTS[region], "/wows/clans/info/", {"clan_id": ids}).get("data") or {}
        for c in cs:
            d = data.get(str(c["id"])) or {}
            members = [int(x) for x in (d.get("members_ids") or [])]
            cache.setdefault("clans", {})[str(c["id"])] = {
                "tag": c["tag"], "region": region, "name": d.get("name"), "members": members,
            }
            log(f"clan {c['tag']}: {len(members)} members")


def fetch_account_stats(cache, cfg):
    accounts = cache.setdefault("accounts", {})
    # account -> region from clan memberships
    acct_region = {}
    for cid, c in cache.get("clans", {}).items():
        for a in c["members"]:
            acct_region[a] = c["region"]
    need_region = {}
    for a, region in acct_region.items():
        k = str(a)
        if k not in accounts:
            need_region.setdefault(region, []).append(a)
    for region, ids in need_region.items():
        missing = {a: accounts.get(str(a)) is None for a in ids}
        ids_missing = [a for a in ids if missing[a]]
        for i in range(0, len(ids_missing), 100):
            batch = ids_missing[i:i + 100]
            r = api_get(HOSTS[region], "/wows/account/info/",
                        {"account_id": ",".join(map(str, batch)),
                         "extra": "statistics.oper_solo", "fields": "-statistics.pvp"},
                        post=True)
            data = r.get("data") or {}
            for a in batch:
                e = data.get(str(a))
                op = None
                if e and not e.get("hidden_profile"):
                    op = (e.get("statistics") or {}).get("oper_solo")
                accounts[str(a)] = {"region": region, "hidden": e.get("hidden_profile", False) if e else True,
                                    "oper_solo": op, "nickname": e.get("nickname") if e else None}
            log(f"account/info {region}: fetched {len(batch)}")
    save_cache(cfg.cache, cache)


def fetch_ship_stats(cache, cfg):
    ships = cache.setdefault("ships", {})
    accounts = cache.setdefault("accounts", {})
    todo = [a for a, v in accounts.items()
            if str(a) not in ships and not v.get("hidden") and v.get("oper_solo")]
    log(f"ships/stats to fetch: {len(todo)}")
    for i, a in enumerate(todo, 1):
        region = accounts[a]["region"]
        try:
            r = api_get(HOSTS[region], "/wows/ships/stats/",
                        {"account_id": a, "extra": "oper_solo", "fields": SHIP_STATS_FIELDS})
            entries = (r.get("data") or {}).get(str(a)) or []
            ships[str(a)] = {"region": region, "ships": entries}
        except Exception as e:
            log(f"  ships/stats fail {a}: {e}")
            ships[str(a)] = {"region": region, "ships": []}
        if i % 20 == 0 or i == len(todo):
            save_cache(cfg.cache, cache)
            log(f"  ships/stats {i}/{len(todo)}")
        time.sleep(cfg.delay)


def fetch_ship_names(cache, cfg):
    names = cache.setdefault("ship_names", {})
    ships = cache.setdefault("ships", {})
    all_ids = set()
    for v in ships.values():
        for e in v.get("ships", []):
            if (e.get("oper_solo") or {}).get("battles", 0) > 0:
                all_ids.add(e["ship_id"])
    missing = [sid for sid in sorted(all_ids) if str(sid) not in names]
    log(f"encyclopedia ship ids to resolve: {len(missing)}")
    for i in range(0, len(missing), 100):
        batch = missing[i:i + 100]
        r = api_get(HOSTS["eu"], "/wows/encyclopedia/ships/",
                    {"ship_id": ",".join(map(str, batch)), "fields": "name,tier,type,nation"})
        for sid, info in (r.get("data") or {}).items():
            if not info:
                continue
            names[str(sid)] = {"name": info.get("name"), "tier": info.get("tier"),
                               "type": info.get("type"), "nation": info.get("nation")}
        log(f"encyclopedia {i + len(batch)}/{len(missing)}")
    save_cache(cfg.cache, cache)


def _aggr(vals):
    if not vals:
        return None
    return round(statistics.median(vals), 3)


def build_features(cache, cfg):
    accounts = cache.get("accounts", {})
    ships = cache.get("ships", {})
    features = []
    for a, av in accounts.items():
        op = av.get("oper_solo")
        if not op or op.get("battles", 0) < cfg.min_acct_battles:
            continue
        acct_avg = op["xp"] / op["battles"]
        sv = ships.get(a)
        if not sv:
            continue
        for e in sv.get("ships", []):
            so = e.get("oper_solo") or {}
            b = so.get("battles", 0)
            if b < cfg.min_ship_battles:
                continue
            ship_avg = so["xp"] / b
            features.append({
                "account_id": int(a),
                "ship_id": e["ship_id"],
                "ship_battles": b,
                "ship_xp_avg": round(ship_avg, 2),
                "acct_xp_avg": round(acct_avg, 2),
                "rel_xp": round(ship_avg / acct_avg, 4),
                "ship_wr": round(so.get("wins", 0) / b, 4) if b else None,
                "ship_5s": round((so.get("wins_by_tasks") or {}).get("5", 0) / b, 4) if b else None,
            })
    return features


def _pct(x, vals):
    if vals is None or not vals:
        return None
    le = sum(1 for v in vals if v <= x)
    return round(le / len(vals) * 100, 1)


def fit_v1(features, cfg, cache=None):
    by_ship = {}
    for f in features:
        by_ship.setdefault(f["ship_id"], []).append(f)
    rows = []
    for sid, fs in by_ship.items():
        n_players = len(fs)
        if n_players < cfg.min_ship_players:
            continue
        battles = sum(f["ship_battles"] for f in fs)
        # weight each player x ship equally (median), not by battle count
        rows.append({
            "ship_id": sid,
            "rel_xp_median": _aggr([f["rel_xp"] for f in fs]),
            "rel_xp_mean": round(statistics.mean([f["rel_xp"] for f in fs]), 3),
            "abs_xp_avg": round(statistics.mean([f["ship_xp_avg"] for f in fs]), 1),
            "win_rate": round(statistics.mean([f["ship_wr"] for f in fs if f["ship_wr"] is not None]), 3),
            "five_star": round(statistics.mean([f["ship_5s"] for f in fs if f["ship_5s"] is not None]), 3),
            "n_players": n_players,
            "n_battles": battles,
        })
    rows.sort(key=lambda r: r["rel_xp_median"] or 0, reverse=True)
    return rows


def fit_v2(features, cfg, cache=None):
    names = (cache or {}).get("ship_names", {})
    by_ship = {}
    for f in features:
        by_ship.setdefault(f["ship_id"], []).append(f)
    rows = []
    for sid, fs in by_ship.items():
        n_players = len(fs)
        if n_players < cfg.min_ship_players:
            continue
        battles = sum(f["ship_battles"] for f in fs)
        nm = names.get(str(sid)) or {}
        rows.append({
            "ship_id": sid,
            "name": nm.get("name"),
            "tier": nm.get("tier"),
            "class": nm.get("type"),
            "nation": nm.get("nation"),
            "rel_xp_median": _aggr([f["rel_xp"] for f in fs]),
            "abs_xp_avg": round(statistics.mean([f["ship_xp_avg"] for f in fs]), 1),
            "win_rate": round(statistics.mean([f["ship_wr"] for f in fs if f["ship_wr"] is not None]), 3),
            "five_star": round(statistics.mean([f["ship_5s"] for f in fs if f["ship_5s"] is not None]), 3),
            "n_players": n_players,
            "n_battles": battles,
        })
    valid = [r for r in rows if r["rel_xp_median"] is not None]
    all_vals = [r["rel_xp_median"] for r in valid]
    by_tier, by_cls_tier = {}, {}
    for r in valid:
        if r["tier"] is not None:
            by_tier.setdefault(r["tier"], []).append(r["rel_xp_median"])
        if r["tier"] is not None and r["class"] is not None:
            by_cls_tier.setdefault((r["tier"], r["class"]), []).append(r["rel_xp_median"])
    for r in rows:
        x = r["rel_xp_median"]
        r["abs_pct"] = _pct(x, all_vals) if x is not None else None
        tv = by_tier.get(r["tier"])
        r["tier_pct"] = _pct(x, tv) if x is not None and tv and len(tv) >= 3 else None
        cv = by_cls_tier.get((r["tier"], r["class"]))
        r["cls_tier_pct"] = _pct(x, cv) if x is not None and cv and len(cv) >= 3 else None
    rows.sort(key=lambda r: (r["rel_xp_median"] is not None,
                             r["rel_xp_median"] if r["rel_xp_median"] is not None else 0), reverse=True)
    return rows


MODELS = {"v1": fit_v1, "v2": fit_v2}


def export(tbl, cache, cfg):
    names = cache.get("ship_names", {})
    for r in tbl:
        nm = names.get(str(r["ship_id"])) or {}
        r.setdefault("name", nm.get("name"))
        r.setdefault("tier", nm.get("tier"))
        r.setdefault("class", nm.get("type"))
        r.setdefault("nation", nm.get("nation"))
    os.makedirs(os.path.dirname(os.path.abspath(cfg.out_json)), exist_ok=True)
    with open(cfg.out_json, "w", encoding="utf-8") as fh:
        json.dump(tbl, fh, ensure_ascii=False, indent=2)

    import csv
    header = ["#", "船", "等级", "舰种", "绝对强度%", "同级强度%", "同舰种同级强度%",
              "相对经验(中位)", "场均经验", "胜率", "五星率", "玩家数", "场次"]
    lines = ["# 剧情船强度表", "",
             "口径：`rel_xp = 该船场均经验 / 该玩家账号场均经验`，跨玩家取中位数。",
             "绝对强度=全船池百分位；同级强度=同等级百分位；同舰种同级强度=同级同舰种百分位。",
             f"门槛：账号剧情场次>={cfg.min_acct_battles}、单船场次>={cfg.min_ship_battles}、单船玩家数>={cfg.min_ship_players}。", ""]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    csv_rows = []
    for i, r in enumerate(tbl, 1):
        vals = [str(i), str(r.get("name") or r["ship_id"]),
                "" if r.get("tier") is None else str(r.get("tier")),
                "" if r.get("class") is None else str(r.get("class"))]
        for k in ("abs_pct", "tier_pct", "cls_tier_pct"):
            v = r.get(k); vals.append("" if v is None else str(v))
        for k in ("rel_xp_median", "abs_xp_avg", "win_rate", "five_star", "n_players", "n_battles"):
            v = r.get(k); vals.append("" if v is None else str(v))
        lines.append("| " + " | ".join(vals) + " |")
        csv_rows.append(vals)
    with open(cfg.out_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    out_csv = os.path.splitext(cfg.out_json)[0] + ".csv"
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(header); w.writerows(csv_rows)
    log(f"wrote {len(tbl)} ships -> {cfg.out_json} / {cfg.out_md} / {out_csv}")


def main(argv=None):
    cfg = Config(clans=CLANS)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clan", action="append", help="clan tag,id,region (repeatable; overrides defaults)")
    ap.add_argument("--model", default=cfg.model)
    ap.add_argument("--min-acct-battles", type=int, default=cfg.min_acct_battles)
    ap.add_argument("--min-ship-battles", type=int, default=cfg.min_ship_battles)
    ap.add_argument("--min-ship-players", type=int, default=cfg.min_ship_players)
    ap.add_argument("--cache", default=cfg.cache)
    ap.add_argument("--out-json", default=cfg.out_json)
    ap.add_argument("--out-md", default=cfg.out_md)
    ap.add_argument("--no-fetch", action="store_true", help="use cache only (skip network)")
    ap.add_argument("--dry", action="store_true", help="fetch but do not write outputs")
    args = ap.parse_args(argv)

    cfg.model = args.model
    cfg.min_acct_battles = args.min_acct_battles
    cfg.min_ship_battles = args.min_ship_battles
    cfg.min_ship_players = args.min_ship_players
    cfg.cache = args.cache
    cfg.out_json = args.out_json
    cfg.out_md = args.out_md
    if args.clan:
        cfg.clans = []
        for item in args.clan:
            tag, cid, region = item.split(",")
            cfg.clans.append({"tag": tag, "id": int(cid), "region": region})

    cache = load_cache(cfg.cache)
    if not args.no_fetch:
        fetch_clans(cfg.clans, cache)
        save_cache(cfg.cache, cache)
        fetch_account_stats(cache, cfg)
        fetch_ship_stats(cache, cfg)
        fetch_ship_names(cache, cfg)
    features = build_features(cache, cfg)
    log(f"features (player x ship)={len(features)}")
    fit = MODELS[cfg.model]
    tbl = fit(features, cfg, cache)
    if not args.dry:
        export(tbl, cache, cfg)
    for r in tbl[:12]:
        log("  top:", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
