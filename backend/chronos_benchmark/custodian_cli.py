"""Independent-custodian CLI for blind field splits, freezing and unblinding.

Run preparation and unblinding on the custodian-controlled machine. The
analysis runner receives only public field tokens, never the Fernet key or
decrypted truth catalogue.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def create_key_file(path: str | Path) -> Path:
    """Create a Fernet key file with owner-only permissions."""
    from cryptography.fernet import Fernet

    target = Path(path).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing key file: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(Fernet.generate_key() + b"\n")
    try:
        target.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    if os.name != "nt":
        mode = stat.S_IMODE(target.stat().st_mode)
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            target.unlink(missing_ok=True)
            raise PermissionError("key file permissions must be owner-only (0600)")
    return target


def _read_key(path: str | Path) -> bytes:
    target = Path(path).expanduser()
    if not target.is_file():
        raise FileNotFoundError(f"custodian key file does not exist: {target}")
    if os.name != "nt":
        mode = stat.S_IMODE(target.stat().st_mode)
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise PermissionError("custodian key file must have owner-only permissions (0600)")
    key = target.read_bytes().strip()
    if not key:
        raise ValueError("custodian key file is empty")
    return key


def prepare_blind_files(fields_path: str | Path, key_path: str | Path,
                        output_dir: str | Path, *, test_fraction: float = 0.3,
                        seed: int = 17) -> dict[str, Any]:
    """Create public run metadata and a separately held encrypted truth store."""
    from .blind import create_blind_store

    fields = _read_json(fields_path)
    key = _read_key(key_path)
    result = create_blind_store(fields, key, test_fraction=test_fraction, seed=seed)
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "encrypted_truth_store.bin").write_bytes(result["encrypted_truth_store"])
    _write_json(target / "public_manifest.json", result["public_manifest"])
    _write_json(target / "run_manifest.json", result["run_manifest"])
    _write_json(target / "custodian_summary.json", result["private_split_manifest"])
    return {
        "output_dir": str(target),
        "public_manifest": str(target / "public_manifest.json"),
        "run_manifest": str(target / "run_manifest.json"),
        "encrypted_truth_store": str(target / "encrypted_truth_store.bin"),
        "field_count": result["public_manifest"]["field_count"],
        "blind_test_field_count": result["private_split_manifest"]["blind_test_field_count"],
        "truth_store_sha256": result["public_manifest"]["truth_store_sha256"],
        "key_fingerprint": result["public_manifest"]["key_fingerprint"],
        "warning": "Transfer run_manifest.json to the analysis team. Keep the key and encrypted truth store with the independent custodian.",
    }


def freeze_run(configuration_path: str | Path, source_commit: str,
               dataset_digest: str, output_path: str | Path) -> dict[str, Any]:
    from .blind import freeze_configuration

    configuration = _read_json(configuration_path)
    protocol = str(configuration.get("preregistration_sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", protocol):
        raise ValueError("configuration must include preregistration_sha256 (64 hex characters)")
    commit = str(source_commit).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        raise ValueError("source_commit must be a full 40- or 64-character Git commit SHA")
    frozen = freeze_configuration(
        configuration, source_commit=commit, dataset_digest=dataset_digest,
    )
    _write_json(output_path, frozen)
    return {
        "output": str(Path(output_path).resolve()),
        "configuration_sha256": frozen["configuration_sha256"],
        "source_commit": frozen["source_commit"],
        "dataset_digest": frozen["dataset_digest"],
        "frozen_utc": frozen["frozen_utc"],
        "warning": "Freeze thresholds and pipeline settings before the blind detection run. Do not edit the frozen file.",
    }


def unblind_files(key_path: str | Path, public_manifest_path: str | Path,
                  encrypted_store_path: str | Path, frozen_path: str | Path,
                  detection_run_path: str | Path, output_path: str | Path,
                  *, bootstrap_draws: int = 2000, seed: int = 20261125) -> dict[str, Any]:
    """Unblind only after a run was frozen and the detector output is complete."""
    from .blind import unblind_benchmark

    key = _read_key(key_path)
    public_manifest = _read_json(public_manifest_path)
    encrypted = Path(encrypted_store_path).read_bytes()
    frozen = _read_json(frozen_path)
    detection_run = _read_json(detection_run_path)
    report = unblind_benchmark(
        public_manifest, encrypted, key, frozen, detection_run,
        bootstrap_draws=bootstrap_draws, seed=seed,
    )
    _write_json(output_path, report)
    return {
        "output": str(Path(output_path).resolve()),
        "scientific_claim_eligible": report["scientific_claim_eligible"],
        "eligibility_reasons": report.get("scientific_eligibility_reasons", []),
        "blind_field_count": report["blind_protocol"]["blind_field_count"],
        "unblinded_utc": report["blind_protocol"]["unblinded_utc"],
        "warning": "Keep the custodian key private. Do not interpret a benchmark as a scientific discovery.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="chronos-custodian",
        description="Create and verify custodian-controlled blind benchmark records.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    key_parser = sub.add_parser("generate-key", help="create an owner-only Fernet key outside the repository")
    key_parser.add_argument("--key-file", required=True)

    prepare = sub.add_parser("prepare", help="split fields and encrypt the private truth store")
    prepare.add_argument("--fields", required=True)
    prepare.add_argument("--key-file", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--test-fraction", type=float, default=0.3)
    prepare.add_argument("--seed", type=int, default=17)

    freeze = sub.add_parser("freeze", help="seal the preregistration, data digest and code commit")
    freeze.add_argument("--configuration", required=True)
    freeze.add_argument("--source-commit", required=True)
    freeze.add_argument("--dataset-digest", required=True)
    freeze.add_argument("--output", required=True)

    unblind = sub.add_parser("unblind", help="open held-out truth and score a frozen detection run")
    unblind.add_argument("--key-file", required=True)
    unblind.add_argument("--public-manifest", required=True)
    unblind.add_argument("--encrypted-store", required=True)
    unblind.add_argument("--frozen-configuration", required=True)
    unblind.add_argument("--detection-run", required=True)
    unblind.add_argument("--output", required=True)
    unblind.add_argument("--bootstrap-draws", type=int, default=2000)
    unblind.add_argument("--seed", type=int, default=20261125)

    args = parser.parse_args(argv)
    try:
        if args.command == "generate-key":
            path = create_key_file(args.key_file)
            result = {"key_file": str(path), "permissions": "0600",
                      "warning": "Store this file offline with the independent custodian. Never commit it."}
        elif args.command == "prepare":
            result = prepare_blind_files(args.fields, args.key_file, args.output_dir,
                                         test_fraction=args.test_fraction, seed=args.seed)
        elif args.command == "freeze":
            result = freeze_run(args.configuration, args.source_commit,
                                args.dataset_digest, args.output)
        else:
            result = unblind_files(args.key_file, args.public_manifest,
                                   args.encrypted_store, args.frozen_configuration,
                                   args.detection_run, args.output,
                                   bootstrap_draws=args.bootstrap_draws, seed=args.seed)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"chronos-custodian: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
