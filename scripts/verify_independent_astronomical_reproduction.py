#!/usr/bin/env python3
"""Verify a signed independent astronomical reproduction bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_discovery.spherex.independent_reproduction import verify_reproduction_record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--reviewer-public-key", type=Path, required=True)
    parser.add_argument("--expected-reviewer-id", required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-input-digests", type=Path, required=True)
    parser.add_argument("--signed-report", type=Path, required=True)
    parser.add_argument("--reproduction-artifact", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    record = json.loads(args.record.read_text(encoding="utf-8"))
    expected = json.loads(args.expected_input_digests.read_text(encoding="utf-8"))
    result = verify_reproduction_record(
        record, args.reviewer_public_key.read_bytes(),
        expected_reviewer_id=args.expected_reviewer_id,
        expected_public_key_sha256=args.expected_public_key_sha256,
        expected_repository_commit=args.expected_commit,
        expected_input_digests=expected,
        signed_report_path=args.signed_report,
        reproduction_artifact_path=args.reproduction_artifact,
    )
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    print(rendered)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    if result.get("valid") is not True:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
