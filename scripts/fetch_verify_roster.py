#!/usr/bin/env python3
"""Fetch WG oper_solo stats for replay rosters not already in the main cache."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

APP_ID = "bc914eb0f45397d5855997f8819056aa"
HOSTS = {
    "eu": "api.worldofwarships.eu",
    "na": "api.worldofwarships.com",
    "asia": "api.worldofwarships.asia",
}
SHIP_STATS_FIELDS = (
    "ship_id,oper_solo.battles,oper_solo.wins,oper_solo.losses,"
    "oper_solo.survived_wins,oper_solo.survived_battles,"
    "oper_solo.wins_by_tasks,oper_solo.xp"
)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def api_get(host, path, params, post=False):
    params = dict(params)
    params["application_id"] = APP_ID
    if post:
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(
            f"https://{host}{path}", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "User-Agent": "wows-verify-roster/1.0"})
    else:
        url = f"https://{host}{path}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "wows-verify-roster/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def load_cache(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {"accounts": {}, "ships": {}}


def save_cache(path, cache):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replays", default="tmp_aug.jsonl")
    ap.add_argument("--main-cache", default="cache/ship_strength_cache.json")
    ap.add_argument("--extra-cache", action="append", default=[],
                    help="additional existing cache to reuse (repeatable)")
    ap.add_argument("--out", default="cache/verify_aug_cache.json")
    ap.add_argument("--region", default="eu")
    ap.add_argument("--delay", type=float, default=0.12)
    args = ap.parse_args(argv)

    rows = [json.loads(x) for x in open(args.replays, encoding="utf-8")]
    roster = {}
    for r in rows:
        roster.setdefault(r["account_id"], set()).add(r.get("home_realm") or args.region)

    main = load_cache(args.main_cache)
    extras = [load_cache(p) for p in args.extra_cache]
    out = load_cache(args.out)

    accounts = dict(main.get("accounts", {}))
    ships = dict(main.get("ships", {}))
    for e in extras:
        accounts.update(e.get("accounts", {}))
        ships.update(e.get("ships", {}))
    accounts.update(out.get("accounts", {}))
    ships.update(out.get("ships", {}))

    todo = [a for a in roster if str(a) not in accounts]
    log(f"accounts to fetch: {len(todo)}")

    host = HOSTS[args.region]
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        r = api_get(host, "/wows/account/info/",
                    {"account_id": ",".join(map(str, batch)),
                     "extra": "statistics.oper_solo",
                     "fields": "-statistics.pvp"}, post=True)
        data = r.get("data") or {}
        for a in batch:
            e = data.get(str(a))
            if e and not e.get("hidden_profile"):
                op = (e.get("statistics") or {}).get("oper_solo")
            else:
                op = None
            out.setdefault("accounts", {})[str(a)] = {
                "region": args.region,
                "hidden": e.get("hidden_profile", False) if e else True,
                "oper_solo": op,
                "nickname": e.get("nickname") if e else None,
            }
        log(f"account/info batch {len(batch)} done")
        time.sleep(args.delay)
    save_cache(args.out, out)

    accounts = dict(main.get("accounts", {}))
    for e in extras:
        accounts.update(e.get("accounts", {}))
    accounts.update(out.get("accounts", {}))
    todo_ships = [a for a in roster
                  if str(a) in accounts and str(a) not in ships
                  and not accounts[str(a)].get("hidden") and accounts[str(a)].get("oper_solo")]
    log(f"ships/stats to fetch: {len(todo_ships)}")
    for idx, a in enumerate(todo_ships, 1):
        try:
            r = api_get(host, "/wows/ships/stats/",
                        {"account_id": a, "extra": "oper_solo",
                         "fields": SHIP_STATS_FIELDS})
            entries = (r.get("data") or {}).get(str(a)) or []
            out.setdefault("ships", {})[str(a)] = {"region": args.region, "ships": entries}
        except Exception as e:
            log(f"  ships/stats fail {a}: {e}")
            out.setdefault("ships", {})[str(a)] = {"region": args.region, "ships": []}
        if idx % 10 == 0 or idx == len(todo_ships):
            save_cache(args.out, out)
            log(f"  ships/stats {idx}/{len(todo_ships)}")
        time.sleep(args.delay)
    save_cache(args.out, out)
    log(f"done -> {args.out} (accounts={len(out.get('accounts', {}))}, ships={len(out.get('ships', {}))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
