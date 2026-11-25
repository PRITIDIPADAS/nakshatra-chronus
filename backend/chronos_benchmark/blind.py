"""Sealed field-level benchmark truth and configuration freeze.

The encryption key must be held by an independent custodian and must never be
committed with the repository or placed in the analysis runner's environment.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from chronos_addons.validation import split_fields
from .runner import (
    SCHEMA as BENCHMARK_SCHEMA, compare_benchmark_package, canonical_json,
    sha256_json, _validate_signature,
)

BLIND_SCHEMA = "chronos-blind-benchmark/1.0"
FREEZE_SCHEMA = "chronos-frozen-configuration/1.0"


def _fernet(key: bytes):
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError("Install the cryptography package to create or open blind truth stores") from exc
    try:
        return Fernet(key)
    except Exception as exc:
        raise ValueError("CHRONOS blind key is not a valid Fernet key") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_blind_store(fields: Sequence[Mapping[str, Any]], key: bytes, *,
                       test_fraction: float = 0.3, seed: int = 17) -> dict[str, Any]:
    """Create opaque field tokens and encrypt all identities, split labels and truth."""
    if not isinstance(fields, (list, tuple)) or len(fields) < 3:
        raise ValueError("at least three independent fields are required for a blind split")
    ids = [
        str(item.get("field_id") or (item.get("input_signature") or {}).get("field_id") or "")
        for item in fields
    ]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("field_id values must be non-empty and unique")
    group_by_field = {
        str(item.get("field_id") or (item.get("input_signature") or {}).get("field_id")):
        str(item.get("split_group_id") or item.get("field_id") or (item.get("input_signature") or {}).get("field_id"))
        for item in fields
    }
    groups = sorted(set(group_by_field.values()))
    split = split_fields(groups, test_fraction=test_fraction, seed=seed)
    test_groups, development_groups = set(split["test_fields"]), set(split["train_fields"])
    test_ids = {field_id for field_id, group_id in group_by_field.items() if group_id in test_groups}
    development_ids = {field_id for field_id, group_id in group_by_field.items() if group_id in development_groups}
    split["train_split_groups"] = sorted(development_groups)
    split["test_split_groups"] = sorted(test_groups)
    split["field_to_split_group"] = group_by_field
    token_by_id = {field_id: secrets.token_urlsafe(18) for field_id in ids}
    private_fields = []
    public_fields = []
    allowed_controls = {
        "science", "empty_field", "negative_control",
        "shuffled_time_control", "detector_pattern_control",
    }
    for raw in fields:
        field_id = str(raw.get("field_id") or (raw.get("input_signature") or {}).get("field_id"))
        control_type = str(raw.get("control_type", "science"))
        if control_type not in allowed_controls:
            raise ValueError(f"{field_id}: unsupported control_type {control_type!r}")
        signature = dict(raw.get("input_signature") or {})
        truth = raw.get("truth_catalogue")
        if not isinstance(truth, list):
            raise ValueError(f"{field_id}: truth_catalogue must be a list")
        signature = _validate_signature(signature, truth)
        if signature["field_id"] != field_id:
            raise ValueError(f"{field_id}: input_signature.field_id must equal field_id")
        token = token_by_id[field_id]
        role = "blind_test" if field_id in test_ids else "development"
        exposure_tokens = [
            "exposure_" + hashlib.sha256((token + "|" + str(value)).encode()).hexdigest()[:20]
            for value in signature.get("exposure_ids", [])
        ]
        public_signature = dict(signature)
        public_signature["field_id"] = token
        public_signature["exposure_ids"] = exposure_tokens
        public_fields.append({
            "blind_field_token": token,
            "split_role": role,
            "dataset_class": signature.get("dataset_class"),
            "input_signature": public_signature,
            "data_locator_token": token,
        })
        private_field = dict(raw)
        private_field.setdefault("field_id", field_id)
        private_fields.append({
            "blind_field_token": token,
            "split_role": role,
            "split_group_id": group_by_field[field_id],
            "field": private_field,
            "original_field_id": field_id,
            "control_type": control_type,
            "injection_stratum": dict(raw.get("injection_stratum") or {}),
        })
    private_payload = {
        "schema": BLIND_SCHEMA,
        "created_utc": _utc_now(),
        "seed": int(seed),
        "split_policy": "entire independent sky fields; no candidate or pixel random split",
        "split_manifest": split,
        "fields": private_fields,
    }
    encrypted = _fernet(key).encrypt(canonical_json(private_payload))
    ciphertext_sha = hashlib.sha256(encrypted).hexdigest()
    public_manifest = {
        "schema": BLIND_SCHEMA,
        "created_utc": private_payload["created_utc"],
        "field_count": len(fields),
        "blind_test_tokens": sorted(token_by_id[item] for item in test_ids),
        "development_tokens": sorted(token_by_id[item] for item in development_ids),
        "holdout_policy": "whole-field holdout with optional shared split_group_id to keep related periods together",
        "truth_store_sha256": ciphertext_sha,
        "truth_store_is_encrypted": True,
        "key_fingerprint": hashlib.sha256(key).hexdigest()[:16],
        "warning": "Do not place the Fernet key or decrypted truth store in the analysis environment.",
    }
    return {
        "public_manifest": public_manifest,
        "run_manifest": {
            "schema": BLIND_SCHEMA,
            "fields": sorted(public_fields, key=lambda row: row["blind_field_token"]),
        },
        "encrypted_truth_store": encrypted,
        "private_split_manifest": {
            "train_field_count": len(development_ids),
            "blind_test_field_count": len(test_ids),
        },
    }


def freeze_configuration(configuration: Mapping[str, Any], *, source_commit: str,
                         dataset_digest: str) -> dict[str, Any]:
    """Seal all thresholds and processing choices before a blind run is unblinded."""
    commit = str(source_commit).strip()
    if not commit:
        raise ValueError("source_commit is required")
    digest = str(dataset_digest).lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("dataset_digest must be a SHA-256 hex digest")
    body = {
        "schema": FREEZE_SCHEMA,
        "frozen_utc": _utc_now(),
        "source_commit": commit,
        "dataset_digest": digest,
        "configuration": dict(configuration),
    }
    return {**body, "configuration_sha256": hashlib.sha256(canonical_json(body)).hexdigest()}


def verify_frozen_configuration(record: Mapping[str, Any]) -> dict[str, Any]:
    if record.get("schema") != FREEZE_SCHEMA:
        return {"valid": False, "reason": "unsupported freeze schema"}
    digest = record.get("configuration_sha256")
    body = {key: value for key, value in record.items() if key != "configuration_sha256"}
    actual = hashlib.sha256(canonical_json(body)).hexdigest()
    return {
        "valid": isinstance(digest, str) and digest == actual,
        "expected_sha256": digest,
        "actual_sha256": actual,
        "reason": "configuration unchanged" if digest == actual else "configuration was changed after freeze",
    }


def unblind_benchmark(public_manifest: Mapping[str, Any], encrypted_truth_store: bytes,
                      key: bytes, frozen_configuration: Mapping[str, Any],
                      detection_run: Mapping[str, Any], *,
                      bootstrap_draws: int = 2000, seed: int = 20261125) -> dict[str, Any]:
    """Verify a frozen run, reveal held-out truth and evaluate the common-input package."""
    if public_manifest.get("schema") != BLIND_SCHEMA:
        raise ValueError("unsupported blind manifest schema")
    frozen_check = verify_frozen_configuration(frozen_configuration)
    if not frozen_check["valid"]:
        raise ValueError("frozen configuration seal is invalid")
    if hashlib.sha256(encrypted_truth_store).hexdigest() != public_manifest.get("truth_store_sha256"):
        raise ValueError("encrypted truth store checksum does not match public manifest")
    if hashlib.sha256(key).hexdigest()[:16] != public_manifest.get("key_fingerprint"):
        raise ValueError("blind key fingerprint does not match public manifest")
    if detection_run.get("dataset_digest") != frozen_configuration.get("dataset_digest"):
        raise ValueError("detection run dataset digest differs from the frozen dataset")
    if detection_run.get("frozen_configuration_sha256") != frozen_configuration.get("configuration_sha256"):
        raise ValueError("detection run was not executed under the frozen configuration")
    if detection_run.get("source_commit") != frozen_configuration.get("source_commit"):
        raise ValueError("detection run source commit differs from the frozen commit")
    run_configuration = detection_run.get("configuration")
    frozen_config = frozen_configuration.get("configuration")
    if not isinstance(run_configuration, Mapping) or canonical_json(run_configuration) != canonical_json(frozen_config):
        raise ValueError("detection run configuration differs from the frozen thresholds and processing choices")

    try:
        private = json.loads(_fernet(key).decrypt(encrypted_truth_store).decode("utf-8"))
    except Exception as exc:
        raise ValueError("could not decrypt the truth store") from exc
    if private.get("schema") != BLIND_SCHEMA:
        raise ValueError("decrypted truth store has an unsupported schema")
    private_by_token = {
        row["blind_field_token"]: row for row in private.get("fields", [])
        if row.get("split_role") == "blind_test"
    }
    run_rows = detection_run.get("fields")
    if not isinstance(run_rows, list):
        raise ValueError("detection_run.fields must be a list")
    packages = []
    seen = set()
    for run_field in run_rows:
        token = str(run_field.get("blind_field_token", ""))
        if token not in private_by_token:
            raise ValueError(f"unknown or non-held-out blind field token: {token}")
        if token in seen:
            raise ValueError(f"duplicate blind field token: {token}")
        seen.add(token)
        private_row = private_by_token[token]
        original = private_row["field"]
        public_signature = dict(run_field.get("input_signature") or {})
        expected_public = next(
            row for row in (detection_run.get("public_fields") or [])
            if row.get("blind_field_token") == token
        )["input_signature"]
        if public_signature != expected_public:
            raise ValueError(f"{token}: run input signature changed after the blind manifest was issued")
        original_signature = dict(original["input_signature"])
        methods = run_field.get("methods")
        if not isinstance(methods, Mapping):
            raise ValueError(f"{token}: missing method detections")
        restored_methods = {}
        for name, record in methods.items():
            record = dict(record)
            if record.get("input_signature") != public_signature:
                raise ValueError(f"{token}.{name}: method input signature differs from the blind run signature")
            record["input_signature"] = original_signature
            restored_methods[name] = record
        packages.append({
            "input_signature": original_signature,
            "truth_catalogue": original["truth_catalogue"],
            "methods": restored_methods,
            "match_radius": original.get("match_radius"),
            "field_area_deg2": original.get("field_area_deg2"),
            "split": "blind_test",
        })
    expected_tokens = set(public_manifest.get("blind_test_tokens", []))
    if seen != expected_tokens:
        missing = sorted(expected_tokens - seen)
        extra = sorted(seen - expected_tokens)
        raise ValueError(f"blind run must contain every held-out field exactly once; missing={missing}, extra={extra}")
    package = {
        "schema": BENCHMARK_SCHEMA,
        "benchmark_id": str(detection_run.get("benchmark_id", "blind-run")),
        "fields": packages,
        "score_thresholds": detection_run.get("score_thresholds"),
        "matched_target": detection_run.get("matched_target"),
    }
    report = compare_benchmark_package(package, bootstrap_draws=bootstrap_draws, seed=seed)
    report["blind_protocol"] = {
        "unblinded_utc": _utc_now(),
        "truth_access_record": {
            "action": "unblind_and_evaluate",
            "encrypted_truth_store_sha256": public_manifest["truth_store_sha256"],
            "key_fingerprint": public_manifest["key_fingerprint"],
            "heldout_field_tokens_processed": sorted(seen),
        },
        "public_manifest_truth_sha256_verified": True,
        "configuration_freeze_verified": frozen_check,
        "source_commit": frozen_configuration["source_commit"],
        "dataset_digest": frozen_configuration["dataset_digest"],
        "blind_field_count": len(packages),
        "truth_released_after_run_freeze": True,
        "evaluation_scope": "held-out fields only",
    }
    return report
