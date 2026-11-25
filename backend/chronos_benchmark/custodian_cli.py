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
from datetime import datetime, timezone
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


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


def create_signing_keypair(private_path: str | Path, public_path: str | Path) -> dict[str, str]:
    """Create an Ed25519 custodian signing key; keep the private key outside the repository."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from .custodian_attestation import public_key_fingerprint

    private_target = Path(private_path).expanduser().resolve()
    public_target = Path(public_path).expanduser().resolve()
    try:
        private_target.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("custodian signing private key must be stored outside the repository")
    if private_target.exists() or public_target.exists():
        raise FileExistsError("refusing to overwrite an existing custodian signing key")
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_target.parent.mkdir(parents=True, exist_ok=True)
    public_target.parent.mkdir(parents=True, exist_ok=True)
    private_target.write_bytes(private_pem)
    public_target.write_bytes(public_pem)
    try:
        private_target.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    if os.name != "nt":
        mode = stat.S_IMODE(private_target.stat().st_mode)
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            private_target.unlink(missing_ok=True)
            public_target.unlink(missing_ok=True)
            raise PermissionError("custodian signing private key must have owner-only permissions (0600)")
    return {
        "private_key_file": str(private_target),
        "public_key_file": str(public_target),
        "public_key_sha256": public_key_fingerprint(public_pem),
        "private_key_permissions": "0600",
        "warning": "Pin the public-key SHA-256 out-of-band with the analysis team. Never commit or disclose the private key.",
    }


def _read_signing_private_key(path: str | Path) -> bytes:
    target = Path(path).expanduser().resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("custodian signing private key must be stored outside the repository")
    if not target.is_file():
        raise FileNotFoundError(f"custodian signing private key does not exist: {target}")
    if os.name != "nt":
        mode = stat.S_IMODE(target.stat().st_mode)
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise PermissionError("custodian signing private key must have owner-only permissions (0600)")
    return target.read_bytes()


def create_custodian_attestation_file(
    *,
    custodian_id: str,
    registration_url: str,
    registration_id: str,
    registered_utc: str,
    registration_receipt_path: str | Path,
    public_manifest_path: str | Path,
    run_manifest_path: str | Path,
    encrypted_truth_store_path: str | Path,
    frozen_configuration_path: str | Path,
    private_signing_key_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    from cryptography.hazmat.primitives import serialization
    from .custodian_attestation import build_attestation_payload, sign_attestation, public_key_fingerprint

    public = _read_json(public_manifest_path)
    run = _read_json(run_manifest_path)
    frozen = _read_json(frozen_configuration_path)
    encrypted = Path(encrypted_truth_store_path).read_bytes()
    receipt = Path(registration_receipt_path).read_bytes()
    private_pem = _read_signing_private_key(private_signing_key_path)
    payload = build_attestation_payload(
        custodian_id=custodian_id,
        registration_url=registration_url,
        registration_id=registration_id,
        registered_utc=registered_utc,
        registration_receipt=receipt,
        public_manifest=public,
        run_manifest=run,
        encrypted_truth_store=encrypted,
        frozen_configuration=frozen,
        attested_utc=datetime.now(timezone.utc).isoformat(),
        analysis_team_holdout_access_before_registration=False,
        custodian_independent_of_analysis_team=True,
        registration_receipt_verified_by_custodian=True,
    )
    attestation = sign_attestation(payload, private_pem)
    _write_json(output_path, attestation)
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "output": str(Path(output_path).resolve()),
        "custodian_id": custodian_id,
        "custodian_public_key_sha256": public_key_fingerprint(public_pem),
        "registered_utc": registered_utc,
        "public_manifest_sha256": payload["public_manifest_sha256"],
        "encrypted_truth_store_sha256": payload["encrypted_truth_store_sha256"],
        "frozen_configuration_sha256": payload["frozen_configuration_sha256"],
        "warning": "The analysis team must verify this Ed25519 signature using the separately pinned custodian public-key fingerprint.",
    }


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
                  *, custodian_attestation_path: str | Path | None = None,
                  custodian_public_key_path: str | Path | None = None,
                  expected_custodian_public_key_sha256: str | None = None,
                  bootstrap_draws: int = 2000, seed: int = 20261125) -> dict[str, Any]:
    """Unblind only after a run was frozen and the detector output is complete."""
    from .blind import unblind_benchmark

    key = _read_key(key_path)
    public_manifest = _read_json(public_manifest_path)
    encrypted = Path(encrypted_store_path).read_bytes()
    frozen = _read_json(frozen_path)
    detection_run = _read_json(detection_run_path)
    attestation = (
        _read_json(custodian_attestation_path)
        if custodian_attestation_path is not None else None
    )
    public_key = (
        Path(custodian_public_key_path).read_bytes()
        if custodian_public_key_path is not None else None
    )
    report = unblind_benchmark(
        public_manifest, encrypted, key, frozen, detection_run,
        custodian_attestation=attestation,
        custodian_public_key=public_key,
        expected_custodian_public_key_sha256=expected_custodian_public_key_sha256,
        bootstrap_draws=bootstrap_draws, seed=seed,
    )
    _write_json(output_path, report)
    return {
        "output": str(Path(output_path).resolve()),
        "scientific_claim_eligible": report["scientific_claim_eligible"],
        "eligibility_reasons": report.get("scientific_eligibility_reasons", []),
        "custodian_attestation": report["blind_protocol"].get("custodian_attestation"),
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

    signing_keys = sub.add_parser("generate-signing-key", help="create the independent custodian Ed25519 signing key")
    signing_keys.add_argument("--private-key-file", required=True)
    signing_keys.add_argument("--public-key-file", required=True)

    attest = sub.add_parser("attest", help="sign preregistration, holdout custody and exact blind dataset digests")
    attest.add_argument("--custodian-id", required=True)
    attest.add_argument("--registration-url", required=True)
    attest.add_argument("--registration-id", required=True)
    attest.add_argument("--registered-utc", required=True)
    attest.add_argument("--registration-receipt", required=True)
    attest.add_argument("--public-manifest", required=True)
    attest.add_argument("--run-manifest", required=True)
    attest.add_argument("--encrypted-store", required=True)
    attest.add_argument("--frozen-configuration", required=True)
    attest.add_argument("--private-signing-key", required=True)
    attest.add_argument("--output", required=True)
    attest.add_argument("--confirm-no-prior-holdout-access", action="store_true", required=True)
    attest.add_argument("--confirm-independent-custodian", action="store_true", required=True)
    attest.add_argument("--confirm-registration-receipt-checked", action="store_true", required=True)

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
    unblind.add_argument("--custodian-attestation", required=True)
    unblind.add_argument("--custodian-public-key", required=True)
    unblind.add_argument("--expected-custodian-key-sha256", required=True)
    unblind.add_argument("--bootstrap-draws", type=int, default=2000)
    unblind.add_argument("--seed", type=int, default=20261125)

    args = parser.parse_args(argv)
    try:
        if args.command == "generate-key":
            path = create_key_file(args.key_file)
            result = {"key_file": str(path), "permissions": "0600",
                      "warning": "Store this file offline with the independent custodian. Never commit it."}
        elif args.command == "generate-signing-key":
            result = create_signing_keypair(args.private_key_file, args.public_key_file)
        elif args.command == "attest":
            if not (args.confirm_no_prior_holdout_access
                    and args.confirm_independent_custodian
                    and args.confirm_registration_receipt_checked):
                raise ValueError("all three independent-custodian confirmations are required")
            result = create_custodian_attestation_file(
                custodian_id=args.custodian_id,
                registration_url=args.registration_url,
                registration_id=args.registration_id,
                registered_utc=args.registered_utc,
                registration_receipt_path=args.registration_receipt,
                public_manifest_path=args.public_manifest,
                run_manifest_path=args.run_manifest,
                encrypted_truth_store_path=args.encrypted_store,
                frozen_configuration_path=args.frozen_configuration,
                private_signing_key_path=args.private_signing_key,
                output_path=args.output,
            )
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
                                   custodian_attestation_path=args.custodian_attestation,
                                   custodian_public_key_path=args.custodian_public_key,
                                   expected_custodian_public_key_sha256=args.expected_custodian_key_sha256,
                                   bootstrap_draws=args.bootstrap_draws, seed=args.seed)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"chronos-custodian: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
