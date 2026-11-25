"""Detached Ed25519 attestation for independent blind-benchmark custody.

The custodian key fingerprint must be pinned out-of-band by the analysis team.
The signed statement attests that the external registration receipt was checked
and that the analysis team had no access to holdout data/truth before it.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlparse

ATTESTATION_SCHEMA = "chronos-independent-custodian-attestation/1.0"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _parse_utc(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _ed25519_private_key(pem: bytes):
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = serialization.load_pem_private_key(pem, password=None)
    except Exception as exc:
        raise ValueError("custodian signing key is not a valid unencrypted PEM private key") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("custodian signing key must be Ed25519")
    return key


def _ed25519_public_key(pem: bytes):
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = serialization.load_pem_public_key(pem)
    except Exception as exc:
        raise ValueError("custodian public key is not a valid PEM public key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("custodian public key must be Ed25519")
    return key


def public_key_fingerprint(public_key_pem: bytes) -> str:
    from cryptography.hazmat.primitives import serialization

    key = _ed25519_public_key(public_key_pem)
    raw = key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256_bytes(raw)


def build_attestation_payload(
    *,
    custodian_id: str,
    registration_url: str,
    registration_id: str,
    registered_utc: str,
    registration_receipt: bytes,
    public_manifest: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
    encrypted_truth_store: bytes,
    frozen_configuration: Mapping[str, Any],
    attested_utc: str,
    analysis_team_holdout_access_before_registration: bool,
    custodian_independent_of_analysis_team: bool,
    registration_receipt_verified_by_custodian: bool,
) -> dict[str, Any]:
    from .blind import verify_frozen_configuration

    custodian_id = str(custodian_id).strip()
    if not custodian_id:
        raise ValueError("custodian_id must identify the independent custodian")
    parsed_url = urlparse(str(registration_url))
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("registration_url must be an HTTPS URL")
    if not str(registration_id).strip():
        raise ValueError("registration_id is required")
    if not registration_receipt:
        raise ValueError("an external registration receipt file is required")
    registered = _parse_utc(registered_utc, "registered_utc")
    attested = _parse_utc(attested_utc, "attested_utc")
    created = _parse_utc(public_manifest.get("created_utc"), "public_manifest.created_utc")
    if registered > created:
        raise ValueError("external preregistration timestamp must precede blind dataset creation")
    if attested < created:
        raise ValueError("custodian attestation must be created after the blind dataset was sealed")
    if analysis_team_holdout_access_before_registration:
        raise ValueError("cannot attest a preregistration-first blind protocol after analysis-team holdout access")
    if not custodian_independent_of_analysis_team:
        raise ValueError("custodian must be independent of the analysis team")
    if not registration_receipt_verified_by_custodian:
        raise ValueError("custodian must confirm that the external registration receipt was checked")
    if not verify_frozen_configuration(frozen_configuration)["valid"]:
        raise ValueError("frozen configuration is invalid")
    configuration = frozen_configuration.get("configuration") or {}
    preregistration_sha = str(configuration.get("preregistration_sha256", "")).lower()
    if len(preregistration_sha) != 64 or any(ch not in "0123456789abcdef" for ch in preregistration_sha):
        raise ValueError("frozen configuration needs a valid preregistration_sha256")
    canonical_run = {
        "schema": run_manifest.get("schema"),
        "fields": sorted(
            run_manifest.get("fields") or [],
            key=lambda row: row.get("blind_field_token", ""),
        ),
    }
    dataset_digest = sha256_json({
        "public_manifest": dict(public_manifest),
        "run_manifest": canonical_run,
    })
    if dataset_digest != frozen_configuration.get("dataset_digest"):
        raise ValueError("public manifest/run manifest do not match the frozen dataset digest")
    payload = {
        "schema": ATTESTATION_SCHEMA,
        "custodian_id": custodian_id,
        "custodian_role": "independent_blind_benchmark_custodian",
        "attested_utc": attested.isoformat(),
        "registration_url": str(registration_url),
        "registration_id": str(registration_id),
        "registered_utc": registered.isoformat(),
        "registration_receipt_sha256": sha256_bytes(registration_receipt),
        "registration_receipt_verified_by_custodian": True,
        "analysis_team_holdout_access_before_registration": False,
        "custodian_independent_of_analysis_team": True,
        "public_manifest_sha256": sha256_json(dict(public_manifest)),
        "run_manifest_sha256": sha256_json(canonical_run),
        "encrypted_truth_store_sha256": sha256_bytes(encrypted_truth_store),
        "dataset_digest": dataset_digest,
        "frozen_configuration_sha256": frozen_configuration["configuration_sha256"],
        "source_commit": frozen_configuration["source_commit"],
        "preregistration_sha256": preregistration_sha,
    }
    return payload


def sign_attestation(payload: Mapping[str, Any], private_key_pem: bytes) -> dict[str, Any]:
    if payload.get("schema") != ATTESTATION_SCHEMA:
        raise ValueError("unsupported custodian attestation payload")
    key = _ed25519_private_key(private_key_pem)
    signature = key.sign(canonical_bytes(dict(payload)))
    return {
        "schema": ATTESTATION_SCHEMA,
        "payload": dict(payload),
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }


def verify_custodian_attestation(
    attestation: Mapping[str, Any] | None,
    public_key_pem: bytes | None,
    *,
    expected_public_key_sha256: str | None,
    public_manifest: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
    encrypted_truth_store: bytes,
    frozen_configuration: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify signature, pinned custodian key, data hashes and preregistration ordering."""
    if attestation is None or public_key_pem is None or not expected_public_key_sha256:
        return {
            "valid": False,
            "status": "missing_independent_custodian_attestation",
            "reason": "A detached custodian signature, public key and out-of-band pinned key fingerprint are required.",
        }
    try:
        from .blind import verify_frozen_configuration

        if attestation.get("schema") != ATTESTATION_SCHEMA:
            raise ValueError("unsupported attestation schema")
        payload = attestation.get("payload")
        if not isinstance(payload, Mapping) or payload.get("schema") != ATTESTATION_SCHEMA:
            raise ValueError("attestation payload is missing or invalid")
        fingerprint = public_key_fingerprint(public_key_pem)
        expected = str(expected_public_key_sha256).lower()
        if len(expected) != 64 or fingerprint != expected:
            raise ValueError("custodian public key fingerprint does not match the out-of-band pinned fingerprint")
        key = _ed25519_public_key(public_key_pem)
        signature = base64.b64decode(str(attestation.get("signature_base64", "")), validate=True)
        key.verify(signature, canonical_bytes(dict(payload)))

        if payload.get("custodian_role") != "independent_blind_benchmark_custodian":
            raise ValueError("attestation does not identify an independent custodian role")
        if payload.get("analysis_team_holdout_access_before_registration") is not False:
            raise ValueError("custodian did not attest that the analysis team had no prior holdout access")
        if payload.get("custodian_independent_of_analysis_team") is not True:
            raise ValueError("custodian did not attest independence from the analysis team")
        if payload.get("registration_receipt_verified_by_custodian") is not True:
            raise ValueError("custodian did not attest verification of the external registration receipt")
        if not str(payload.get("registration_url", "")).startswith("https://"):
            raise ValueError("external registration URL is missing")
        if not str(payload.get("registration_id", "")).strip():
            raise ValueError("external registration identifier is missing")
        receipt_sha = str(payload.get("registration_receipt_sha256", "")).lower()
        if len(receipt_sha) != 64 or any(ch not in "0123456789abcdef" for ch in receipt_sha):
            raise ValueError("external registration receipt SHA-256 is missing")

        registered = _parse_utc(payload.get("registered_utc"), "registered_utc")
        attested = _parse_utc(payload.get("attested_utc"), "attested_utc")
        dataset_created = _parse_utc(public_manifest.get("created_utc"), "public_manifest.created_utc")
        if registered > dataset_created or attested < dataset_created:
            raise ValueError("registration/attestation timestamps do not bracket blind dataset creation")

        canonical_run = {
            "schema": run_manifest.get("schema"),
            "fields": sorted(
                run_manifest.get("fields") or [],
                key=lambda row: row.get("blind_field_token", ""),
            ),
        }
        expected_digests = {
            "public_manifest_sha256": sha256_json(dict(public_manifest)),
            "run_manifest_sha256": sha256_json(canonical_run),
            "encrypted_truth_store_sha256": sha256_bytes(encrypted_truth_store),
            "dataset_digest": sha256_json({
                "public_manifest": dict(public_manifest),
                "run_manifest": canonical_run,
            }),
            "frozen_configuration_sha256": frozen_configuration.get("configuration_sha256"),
            "source_commit": frozen_configuration.get("source_commit"),
            "preregistration_sha256": str(
                (frozen_configuration.get("configuration") or {}).get("preregistration_sha256", "")
            ).lower(),
        }
        for field, expected_value in expected_digests.items():
            if payload.get(field) != expected_value:
                raise ValueError(f"custodian attestation mismatch for {field}")
        if not verify_frozen_configuration(frozen_configuration)["valid"]:
            raise ValueError("frozen configuration checksum is invalid")
        return {
            "valid": True,
            "status": "verified_independent_custodian_attestation",
            "custodian_id": payload.get("custodian_id"),
            "custodian_public_key_sha256": fingerprint,
            "registration_url": payload["registration_url"],
            "registration_id": payload["registration_id"],
            "registered_utc": registered.isoformat(),
            "registration_receipt_sha256": receipt_sha,
            "external_timestamp_receipt_checked_by_custodian": True,
            "analysis_team_no_prior_holdout_access_attested": True,
            "signature_sha256": sha256_bytes(signature),
            "verification_note": (
                "The pinned independent-custodian Ed25519 key signed the registration receipt hash, "
                "holdout-access statement and exact blind dataset/configuration digests. The timestamp "
                "authority's receipt is attested by the custodian; this code does not independently query "
                "or validate the external registration service."
            ),
        }
    except Exception as exc:
        return {
            "valid": False,
            "status": "invalid_independent_custodian_attestation",
            "reason": f"{type(exc).__name__}: {exc}",
        }
