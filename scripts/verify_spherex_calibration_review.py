#!/usr/bin/env python3
"""Verify an externally signed SPHEREx calibration review against pinned inputs.

This tool verifies bytes, an Ed25519 signature, the out-of-band key fingerprint,
reviewer ID, exact commit, signed report and independent reproduction artifact.
It cannot independently establish the reviewer's real-world identity, expertise,
affiliation, or independence; those require human confirmation outside GitHub.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research_discovery.spherex.independent_calibration_review import (
    verify_review_record,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-record", required=True, type=Path)
    parser.add_argument("--reviewer-public-key", required=True, type=Path)
    parser.add_argument("--expected-reviewer-id", required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument(
        "--expected-input-digests",
        required=True,
        type=Path,
        help="JSON object with every required science/calibration/report/reproduction SHA-256",
    )
    parser.add_argument("--signed-report", required=True, type=Path)
    parser.add_argument("--reproduction-artifact", required=True, type=Path)
    args = parser.parse_args(argv)

    record: Any = json.loads(args.review_record.read_text(encoding="utf-8"))
    expected: Any = json.loads(args.expected_input_digests.read_text(encoding="utf-8"))
    if not isinstance(expected, dict):
        raise ValueError("--expected-input-digests must contain a JSON object")

    result = verify_review_record(
        record,
        args.reviewer_public_key.read_bytes(),
        expected_reviewer_id=args.expected_reviewer_id,
        expected_public_key_sha256=args.expected_public_key_sha256,
        expected_repository_commit=args.expected_commit,
        expected_input_digests=expected,
        signed_report_path=args.signed_report,
        reproduction_artifact_path=args.reproduction_artifact,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
