"""Verify a downloaded CHRONOS investigation package."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .investigation_package import verify_investigation_package

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(prog="chronos-package")
    sub=parser.add_subparsers(dest="command",required=True)
    verify=sub.add_parser("verify",help="verify ZIP sidecar and member hashes")
    verify.add_argument("archive")
    args=parser.parse_args(argv)
    try:
        result=verify_investigation_package(Path(args.archive))
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0 if result.get("valid") is True else 1
    except Exception as exc:
        print(f"chronos-package: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
