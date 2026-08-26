import collections
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_ops_replays as ex


def is_operation(sc):
    return (
        sc.startswith("WW2_OPERATION")
        or sc.startswith("PCVO")
        or sc.startswith("OP_")
        or sc.startswith("Attack_On_Base")
        or sc == "Defense"
        or sc.startswith("Dunkirk")
        or sc.startswith("USS_CL")
    )


def main():
    d = sys.argv[1]
    files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".wowsreplay")]
    builds = set()
    ops_by_build = collections.Counter()
    for p in files:
        try:
            m = ex.read_meta_only(p)
            b, v = ex.build_and_version(m)
            sc = str(m.get("scenario") or "")
            if b and b >= 9129736 and is_operation(sc):
                builds.add(b)
                ops_by_build[(b, v)] += 1
        except Exception:
            continue
    print("distinct operation-capable builds (>=13.10):", len(builds))
    for (b, v), c in sorted(ops_by_build.items(), key=lambda kv: -kv[1]):
        print("  build %s %s -> %d ops replays" % (b, v, c))

    cache = Path("constants_cache")
    missing = [b for b in sorted(builds) if not (cache / ("%s.json" % b)).exists()]
    print("\nmissing constants:", missing)
    for b in missing:
        ex.load_build_tables(b, "constants_cache", allow_fetch=True)
    resolved = [b for b in sorted(builds) if (cache / ("%s.json" % b)).exists()]
    print("resolved after fetch:", len(resolved), "/", len(builds))
    still = [b for b in sorted(builds) if not (cache / ("%s.json" % b)).exists()]
    print("still missing:", still)


if __name__ == "__main__":
    main()
