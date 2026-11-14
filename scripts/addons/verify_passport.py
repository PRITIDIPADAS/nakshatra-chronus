"""Verify a saved CHRONOS evidence passport."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from chronos_addons.passport import verify_passport
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("passport_json");a=ap.parse_args()
    with open(a.passport_json,encoding="utf-8") as f:p=json.load(f)
    result=verify_passport(p);print(json.dumps(result,indent=2));return 0 if result["valid"] else 1
if __name__=="__main__":raise SystemExit(main())
