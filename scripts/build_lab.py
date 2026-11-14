"""Build site/data/lab/<field>.json, the ten CHRONOS 4D laboratories for every prepared field. Run after build_static.py (seconds)."""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import lab  # noqa: E402


def load(n):
    p = os.path.join(ROOT, "data", n)
    return json.load(open(p)) if os.path.exists(p) else None


out = os.path.join(ROOT, "site", "data", "lab")
os.makedirs(out, exist_ok=True)
index = []
for p in sorted(glob.glob(os.path.join(ROOT, "site", "data", "fields", "*.json"))):
    k = os.path.basename(p)[:-5]
    if k == "index":
        continue
    L = lab.laboratory(json.load(open(p)), load("validation.json"), load("real_injection.json"))
    json.dump(L, open(os.path.join(out, k + ".json"), "w"), separators=(",", ":"), default=float)
    for c in L["candidates"]:  # one canonical passport body per candidate: anyone can check it with sha256sum
        open(os.path.join(out, f"passport_{k}_{c['id']}.json"), "wb").write(lab.canonical(c["passport"]["body"]))
        index.append(dict(field=k, id=c["id"], seal=c["passport"]["seal"]))
    print(k, len(L["candidates"]), "candidates")
json.dump(index, open(os.path.join(out, "passports.json"), "w"), indent=1)
