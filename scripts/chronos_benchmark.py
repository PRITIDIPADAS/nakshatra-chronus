#!/usr/bin/env python3
"""Run CHRONOS four-baseline comparisons and sealed blind-field evaluations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from chronos_benchmark.runner import compare_benchmark_package, canonical_json, sha256_json
from chronos_benchmark.blind import (
    create_blind_store,
    freeze_configuration,
    unblind_benchmark,
)


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, value):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(destination)


def read_key(path):
    value = Path(path).read_bytes().strip()
    if not value:
        raise ValueError("blind key file is empty")
    return value


def command_compare(args):
    package = read_json(args.package)
    report = compare_benchmark_package(
        package, bootstrap_draws=args.draws, seed=args.seed
    )
    write_json(args.output, report)
    print(json.dumps({
        "output": str(args.output),
        "scientific_claim_eligible": report["scientific_claim_eligible"],
        "field_count": len(report["fields"]),
        "methods": report["methods"],
    }, indent=2))


def command_seal(args):
    from cryptography.fernet import Fernet

    key_path = Path(args.key_file).expanduser().resolve()
    try:
        key_path.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("blind key must be stored outside the repository")
    if key_path.exists():
        raise FileExistsError("refusing to overwrite an existing blind key file")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_path.write_bytes(key + b"\n")
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    fields = read_json(args.fields)
    result = create_blind_store(
        fields, key, test_fraction=args.test_fraction, seed=args.seed
    )
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "public_manifest.json", result["public_manifest"])
    write_json(output / "run_manifest.json", result["run_manifest"])
    (output / "truth_store.enc").write_bytes(result["encrypted_truth_store"])
    write_json(output / "split_counts.json", result["private_split_manifest"])
    print(json.dumps({
        "output_dir": str(output),
        "key_file": str(key_path),
        "blind_test_count": result["private_split_manifest"]["blind_test_field_count"],
        "development_count": result["private_split_manifest"]["train_field_count"],
        "warning": "Keep the key file outside the repository and analysis environment.",
    }, indent=2))


def command_freeze(args):
    public = read_json(args.public_manifest)
    run = read_json(args.run_manifest)
    dataset_digest = sha256_json({"public_manifest": public, "run_manifest": run})
    configuration = read_json(args.configuration)
    frozen = freeze_configuration(
        configuration, source_commit=args.commit, dataset_digest=dataset_digest
    )
    write_json(args.output, frozen)
    print(json.dumps({
        "output": str(args.output),
        "configuration_sha256": frozen["configuration_sha256"],
        "dataset_digest": dataset_digest,
        "source_commit": args.commit,
    }, indent=2))


def command_unblind(args):
    public = read_json(args.public_manifest)
    run_manifest = read_json(args.run_manifest)
    frozen = read_json(args.frozen_configuration)
    detection_run = read_json(args.detection_run)
    detection_run["public_fields"] = run_manifest["fields"]
    dataset_digest = sha256_json({
        "public_manifest": public,
        "run_manifest": run_manifest,
    })
    if frozen.get("dataset_digest") != dataset_digest:
        raise ValueError("frozen configuration refers to a different blind dataset")
    report = unblind_benchmark(
        public,
        Path(args.truth_store).read_bytes(),
        read_key(args.key_file),
        frozen,
        detection_run,
        bootstrap_draws=args.draws,
        seed=args.seed,
    )
    write_json(args.output, report)
    print(json.dumps({
        "output": str(args.output),
        "blind_field_count": report["blind_protocol"]["blind_field_count"],
        "scientific_claim_eligible": report["scientific_claim_eligible"],
        "methods": report["methods"],
    }, indent=2))


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    compare = commands.add_parser("compare", help="evaluate a common-input four-baseline package")
    compare.add_argument("--package", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--draws", type=int, default=2000)
    compare.add_argument("--seed", type=int, default=20261125)
    compare.set_defaults(function=command_compare)

    seal = commands.add_parser("seal", help="create opaque field tokens and an encrypted truth store")
    seal.add_argument("--fields", type=Path, required=True)
    seal.add_argument("--output-dir", type=Path, required=True)
    seal.add_argument("--key-file", type=Path, required=True)
    seal.add_argument("--test-fraction", type=float, default=0.3)
    seal.add_argument("--seed", type=int, default=17)
    seal.set_defaults(function=command_seal)

    freeze = commands.add_parser("freeze", help="seal thresholds and configuration before unblinding")
    freeze.add_argument("--public-manifest", type=Path, required=True)
    freeze.add_argument("--run-manifest", type=Path, required=True)
    freeze.add_argument("--configuration", type=Path, required=True)
    freeze.add_argument("--commit", required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.set_defaults(function=command_freeze)

    unblind = commands.add_parser("unblind", help="evaluate held-out detections after configuration freeze")
    unblind.add_argument("--public-manifest", type=Path, required=True)
    unblind.add_argument("--run-manifest", type=Path, required=True)
    unblind.add_argument("--truth-store", type=Path, required=True)
    unblind.add_argument("--key-file", type=Path, required=True)
    unblind.add_argument("--frozen-configuration", type=Path, required=True)
    unblind.add_argument("--detection-run", type=Path, required=True)
    unblind.add_argument("--output", type=Path, required=True)
    unblind.add_argument("--draws", type=int, default=2000)
    unblind.add_argument("--seed", type=int, default=20261125)
    unblind.set_defaults(function=command_unblind)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    try:
        arguments.function(arguments)
    except Exception as exc:
        parser().error(str(exc))
