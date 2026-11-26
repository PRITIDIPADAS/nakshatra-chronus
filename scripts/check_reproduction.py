"""Compare a fresh real-data run with the numbers recorded in this repository.

Usage: python scripts/check_reproduction.py NEW_DIAGNOSTICS.json [--recorded data/injection_diagnostics.json]
Prints a field-by-field table and exits 1 if any recovered count differs by more than the tolerance.
"""
import argparse
import json
import sys


def counts(path):
    d = json.load(open(path))
    rows = d["fields"] if isinstance(d, dict) else d
    out = {}
    for r in rows:
        name = r.get("field") or r["report"].split("/fields/")[1].split("/")[0]
        out[name] = {"primary": [lv["recovered"] for lv in r["levels"]],
                     "sky_aware": (r.get("structured_background_variant") or {}).get("recovered")}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("new")
    ap.add_argument("--recorded", default="data/injection_diagnostics.json")
    ap.add_argument("--tolerance", type=int, default=0)
    a = ap.parse_args(argv)
    old, new = counts(a.recorded), counts(a.new)
    bad = 0
    for f in sorted(old):
        if f not in new:
            print(f"{f:28s} missing from the new run")
            bad += 1
            continue
        diff = max(abs(x - y) for x, y in zip(old[f]["primary"], new[f]["primary"]))
        ok = diff <= a.tolerance
        bad += not ok
        print(f"{f:28s} recorded {old[f]['primary']} new {new[f]['primary']} {'match' if ok else 'DIFFERS'}")
    print("reproduced" if not bad else f"{bad} field(s) differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
