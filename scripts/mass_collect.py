#!/usr/bin/env python3
"""Mass collect: wows-numbers clan leaderboards -> WG member roster -> account/ship oper_solo.

Clan processing order is head/tail interleaved within each region and round-robin
across regions, so an interrupted run stays strength-unbiased. Resumable via cache.
Fetches are concurrent (thread pool) across a rotating pool of WG application ids;
407 rate-limit errors switch app id, back off, and retry.
"""
from __future__ import annotations
import argparse, collections, concurrent.futures as cf, itertools, json, os, sys, threading, time, urllib.parse, urllib.request

APP_IDS = [
    "bc914eb0f45397d5855997f8819056aa",
    "49b96ca5473142048d9b118811c50105",
    "4abd85d2d22608f74b646410ef7e3a16",
]
HOSTS = {"eu": "api.worldofwarships.eu", "asia": "api.worldofwarships.asia", "na": "api.worldofwarships.com"}
SHIP_STATS_FIELDS = ("ship_id,oper_solo.battles,oper_solo.wins,oper_solo.losses,"
                     "oper_solo.survived_wins,oper_solo.survived_battles,oper_solo.wins_by_tasks,oper_solo.xp")

_app_counter = itertools.count()
_app_lock = threading.Lock()
def next_app_id():
    with _app_lock:
        return APP_IDS[next(_app_counter) % len(APP_IDS)]

def log(*a): print(*a, file=sys.stderr, flush=True)

def fetch_json(host, path, params, post=False, retries=8):
    params = dict(params)
    appid = next_app_id()
    for attempt in range(retries):
        params["application_id"] = appid
        try:
            if post:
                data = urllib.parse.urlencode(params).encode()
                req = urllib.request.Request(f"https://{host}{path}", data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "wows-mass/1.0"})
            else:
                url = f"https://{host}{path}?" + urllib.parse.urlencode(params)
                req = urllib.request.Request(url, headers={"User-Agent": "wows-mass/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode("utf-8"))
            if body.get("status") == "ok":
                return body.get("data") or {}
            if (body.get("error") or {}).get("code") == 407:   # rate limit: switch id and retry
                appid = next_app_id(); time.sleep(0.25 * (attempt + 1)); continue
            return {}
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(0.4 * (attempt + 1))
    return None

def load(by_region):
    for region, f in [("eu","eu_clans.json"),("asia","asia_clans.json"),("na","na_clans.json")]:
        p = os.path.join("input", "clans", f)
        if os.path.exists(p):
            by_region[region] = [int(x) for x in json.load(open(p, encoding="utf-8"))]
    return by_region

def interleave(ids):
    out, i, j = [], 0, len(ids) - 1
    while i <= j:
        out.append(ids[i]); i += 1
        if i <= j: out.append(ids[j]); j -= 1
    return out

def build_order(by_region):
    seq = {r: interleave(by_region[r]) for r in by_region if by_region[r]}
    idx = {r: 0 for r in seq}
    total = sum(len(v) for v in seq.values())
    order, k, regions = [], 0, list(seq.keys())
    while len(order) < total:
        r = regions[k % len(regions)]
        if idx[r] < len(seq[r]):
            order.append((r, seq[r][idx[r]])); idx[r] += 1
        k += 1
    return order

def save(path, cache):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh: json.dump(cache, fh, ensure_ascii=False)
    os.replace(tmp, path)

def load_cache(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}

def stage_rosters(order, cache, cfg):
    clans = cache.setdefault("clans", {})
    by_region = collections.defaultdict(list)
    for r, cid in order:
        if str(cid) not in clans:
            by_region[r].append(cid)
    tasks = []
    for region, ids in by_region.items():
        for i in range(0, len(ids), 100):
            tasks.append((region, ids[i:i+100]))
    def work(t):
        region, batch = t
        return region, batch, fetch_json(HOSTS[region], "/wows/clans/info/", {"clan_id": ",".join(map(str, batch))})
    with cf.ThreadPoolExecutor(max_workers=cfg.workers) as ex:
        futs = [ex.submit(work, t) for t in tasks]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            res = fut.result()
            if not res: continue
            region, batch, data = res
            for cid in batch:
                d = data.get(str(cid)) or {}
                clans[str(cid)] = {"tag": d.get("tag"), "region": region, "name": d.get("name"),
                                   "members": [int(x) for x in (d.get("members_ids") or [])]}
            if i % 20 == 0:
                save(cfg.cache, cache); log(f"rosters {i}/{len(tasks)}")
    save(cfg.cache, cache)

def stage_accounts(cache, cfg):
    accounts = cache.setdefault("accounts", {})
    by_region = collections.defaultdict(set)
    for c in cache.get("clans", {}).values():
        for a in c.get("members", []):
            if str(a) not in accounts:
                by_region[c["region"]].add(a)
    tasks = []
    for region, idset in by_region.items():
        ids = sorted(idset)
        for i in range(0, len(ids), 100):
            tasks.append((region, ids[i:i+100]))
    def work(t):
        region, batch = t
        return region, batch, fetch_json(HOSTS[region], "/wows/account/info/",
                     {"account_id": ",".join(map(str, batch)),
                      "extra": "statistics.oper_solo", "fields": "-statistics.pvp"}, post=True)
    log(f"account batches: {len(tasks)}")
    done = 0
    with cf.ThreadPoolExecutor(max_workers=cfg.workers) as ex:
        futs = [ex.submit(work, t) for t in tasks]
        for fut in cf.as_completed(futs):
            done += 1
            res = fut.result()
            if res:
                region, batch, data = res
                for a in batch:
                    e = data.get(str(a))
                    op = None
                    if e and not e.get("hidden_profile"):
                        op = (e.get("statistics") or {}).get("oper_solo")
                    accounts[str(a)] = {"region": region, "hidden": (e or {}).get("hidden_profile", True),
                                        "oper_solo": op, "nickname": (e or {}).get("nickname")}
            if done % 100 == 0:
                save(cfg.cache, cache); log(f"accounts {done}/{len(futs)}")
    save(cfg.cache, cache)

def stage_ships(order, cache, cfg):
    ships = cache.setdefault("ships", {})
    accounts = cache.get("accounts", {})
    clan_rank = {}
    for rank, (region, cid) in enumerate(order):
        c = cache["clans"].get(str(cid)) or {}
        for a in c.get("members", []):
            clan_rank.setdefault(str(a), rank)
    todo = [a for a in accounts
            if str(a) not in ships and not accounts[a].get("hidden")
            and (accounts[a].get("oper_solo") or {}).get("battles", 0) >= cfg.min_acct_battles]
    todo.sort(key=lambda a: clan_rank.get(str(a), 10**9))
    if cfg.max_accounts and cfg.max_accounts > 0:
        todo = todo[:cfg.max_accounts]
    log(f"ships/stats to fetch: {len(todo)}")
    def work(a):
        region = accounts[a]["region"]
        data = fetch_json(HOSTS[region], "/wows/ships/stats/",
                          {"account_id": a, "extra": "oper_solo", "fields": SHIP_STATS_FIELDS})
        if data:
            data = {str(a): [e for e in (data.get(str(a)) or []) if (e.get("oper_solo") or {}).get("battles", 0) > 0]}
        return a, data
    done = 0
    with cf.ThreadPoolExecutor(max_workers=cfg.workers) as ex:
        futs = [ex.submit(work, a) for a in todo]
        for fut in cf.as_completed(futs):
            done += 1
            a, data = fut.result()
            if data is None:
                ships[str(a)] = {"region": accounts[a]["region"], "ships": []}
            else:
                ships[str(a)] = {"region": accounts[a]["region"], "ships": data.get(str(a)) or []}
            if done % 200 == 0:
                log(f"ships {done}/{len(futs)}")
            if done % 2000 == 0:
                save(cfg.cache, cache)
    save(cfg.cache, cache)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="cache/ship_strength_cache.json")
    ap.add_argument("--max-accounts", type=int, default=0, help="0 = all, else bound ships/stats")
    ap.add_argument("--min-acct-battles", type=int, default=20)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--skip-rosters", action="store_true")
    ap.add_argument("--skip-accounts", action="store_true")
    ap.add_argument("--skip-ships", action="store_true")
    args = ap.parse_args()
    cfg = type("C", (), {"cache": args.cache, "max_accounts": args.max_accounts,
                         "min_acct_battles": args.min_acct_battles, "workers": args.workers})()
    by_region = load({})
    log("clans by region:", {k: len(v) for k, v in by_region.items()})
    order = build_order(by_region)
    log("interleaved order:", len(order))
    cache = load_cache(cfg.cache)
    if not args.skip_rosters:
        stage_rosters(order, cache, cfg)
    if not args.skip_accounts:
        stage_accounts(cache, cfg)
    if not args.skip_ships:
        stage_ships(order, cache, cfg)
    save(cfg.cache, cache)
    log("DONE")

if __name__ == "__main__":
    main()
