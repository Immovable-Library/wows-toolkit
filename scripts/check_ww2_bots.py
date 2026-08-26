import json
import os
import re
import sys

sys.path.insert(0, "scripts")
import extract_ops_replays as ex


def ship(sid, cache):
    info = cache.get(str(sid))
    if info:
        return info.get("name"), info.get("tier")
    return str(sid), None


def first_waves(path, cache):
    meta, packets = ex.read_replay(path)
    res = ex.find_battle_results(packets)
    if not res:
        return None
    ppi = res.get("playersPublicInfo") or {}
    common = ex.resolve_common(res.get("commonList") or [])
    sc = str(common.get("scenario_name") or meta.get("scenario") or "")
    rows = []
    for key, arr in ppi.items():
        if int(arr[0]) >= 0:
            continue
        label = str(arr[1])
        m = re.search(r"ENEMY_WAVE_?(\d+)", label)
        if not m:
            continue
        num = int(m.group(1))
        name, tier = ship(arr[7], cache)
        rows.append((num, name, tier))
    rows.sort()
    return sc, rows


def main():
    cache = json.load(open("ships_cache.json", encoding="utf-8"))
    root = r"D:\World_of_Warships\replays"
    by_scenario = {}
    for dp, _, fn in os.walk(root):
        for f in fn:
            if f.endswith(".wowsreplay") and "WW2_OP" in f:
                path = os.path.join(dp, f)
                try:
                    meta = ex.read_meta_only(path)
                except Exception:
                    continue
                sc = str(meta.get("scenario") or "")
                if "WW2_OPERATION" in sc:
                    by_scenario.setdefault(sc, []).append(path)

    for sc in sorted(by_scenario):
        for path in by_scenario[sc][:3]:
            got = first_waves(path, cache)
            if not got:
                continue
            _, rows = got
            print("====", sc, os.path.basename(path))
            for num, name, tier in rows[:18]:
                print("  wave %2d -> %s tier %s" % (num, name, tier))


if __name__ == "__main__":
    main()
