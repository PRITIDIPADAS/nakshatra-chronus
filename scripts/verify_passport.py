"""Verify a CHRONOS evidence passport without trusting CHRONOS: python scripts/verify_passport.py passport.json
Accepts a full passport (body, seal) or a canonical body file plus --seal HEX."""
import hashlib
import json
import sys

d = open(sys.argv[1], "rb").read()
obj = json.loads(d)
if "body" in obj:
    body = json.dumps(obj["body"], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    seal = obj["seal"]
else:
    body, seal = d, sys.argv[sys.argv.index("--seal") + 1]
h = hashlib.sha256(body).hexdigest()
print("computed", h, "\nsealed  ", seal, "\nVALID" if h == seal else "\nCHANGED AFTER SEALING")
sys.exit(0 if h == seal else 1)
