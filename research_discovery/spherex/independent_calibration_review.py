"""Signed independent SPHEREx calibration-review records.

The review is a human scientific judgment, not an automated status promotion.
Verification requires an out-of-band pinned Ed25519 public-key fingerprint and
exact expected input digests supplied by the project maintainer. The code checks
integrity and declared scope; it cannot independently establish a reviewer's
identity, expertise, affiliation, or independence.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

REVIEW_SCHEMA = "chronos-independent-spherex-calibration-review/1.0"
REQUIRED_CHECKS = (
    "product_units_and_gain_bunit",
    "exposure_time_conversion",
    "level2_variance_noise_accounting",
    "source_poisson_increment",
    "solid_angle_conversion",
    "invalid_pixel_and_flag_masks",
    "epsf_and_photometry",
    "native_cwave_cband_and_wcs",
    "cross_field_calibration_applicability",
    "independent_reproduction",
)
ALLOWED_CHECK_STATUS = {"accepted", "rejected", "not_assessed"}
ALLOWED_DISPOSITION = {"accepted", "accepted_with_conditions", "not_accepted"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _utc(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _sha(value: Any, label: str) -> str:
    text = str(value or "").lower()
    if not SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a 64-character lowercase SHA-256 digest")
    return text


def _public_key(pem: bytes):
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = serialization.load_pem_public_key(pem)
    except Exception as exc:
        raise ValueError("reviewer public key must be a valid PEM Ed25519 key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("reviewer public key must use Ed25519")
    return key


def _private_key(pem: bytes):
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = serialization.load_pem_private_key(pem, password=None)
    except Exception as exc:
        raise ValueError("reviewer private key must be a valid unencrypted PEM Ed25519 key") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("reviewer private key must use Ed25519")
    return key


def public_key_fingerprint(public_key_pem: bytes) -> str:
    from cryptography.hazmat.primitives import serialization
    key = _public_key(public_key_pem)
    raw = key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256_bytes(raw)


def validate_review_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("schema") != REVIEW_SCHEMA:
        raise ValueError(f"review payload schema must be {REVIEW_SCHEMA}")
    for name in ("reviewer_id", "reviewer_role", "affiliation"):
        if not str(payload.get(name, "")).strip():
            raise ValueError(f"{name} is required")
    if payload.get("independent_of_project_authors") is not True:
        raise ValueError("reviewer must explicitly attest independence from project authors")
    conflicts = payload.get("conflicts_of_interest")
    if not isinstance(conflicts, list):
        raise ValueError("conflicts_of_interest must be a list; use [] when none are declared")
    _utc(payload.get("reviewed_utc"), "reviewed_utc")

    commit = str(payload.get("repository_commit", "")).lower()
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError("repository_commit must be a full 40- or 64-character commit SHA")
    digests = payload.get("input_digests")
    if not isinstance(digests, Mapping):
        raise ValueError("input_digests must be an object")
    required_digests = (
        "science_sha256", "absolute_gain_sha256", "spectral_wcs_sha256",
        "solid_angle_sha256", "native_audit_sha256", "review_packet_sha256",
        "input_manifest_sha256", "signed_report_sha256", "reproduction_artifact_sha256",
    )
    normalized_digests = {
        name: _sha(digests.get(name), f"input_digests.{name}")
        for name in required_digests
    }
    reproduction_uri = str(payload.get("reproduction_artifact_uri", "")).strip()
    if not reproduction_uri.startswith("https://"):
        raise ValueError("reproduction_artifact_uri must be an HTTPS URI")

    checks = payload.get("checks")
    if not isinstance(checks, Mapping):
        raise ValueError("checks must be an object")
    missing = [name for name in REQUIRED_CHECKS if name not in checks]
    if missing:
        raise ValueError("review is missing required checks: " + ", ".join(missing))
    normalized_checks = {}
    for name in REQUIRED_CHECKS:
        status = str(checks[name]).strip().lower()
        if status not in ALLOWED_CHECK_STATUS:
            raise ValueError(f"checks.{name} must be accepted, rejected, or not_assessed")
        normalized_checks[name] = status

    disposition = str(payload.get("disposition", "")).strip().lower()
    if disposition not in ALLOWED_DISPOSITION:
        raise ValueError("disposition must be accepted, accepted_with_conditions, or not_accepted")
    conditions = payload.get("conditions")
    if not isinstance(conditions, list) or any(not str(x).strip() for x in conditions):
        raise ValueError("conditions must be a list of non-empty strings")
    if disposition == "accepted":
        if any(value != "accepted" for value in normalized_checks.values()):
            raise ValueError("unconditional acceptance requires every required check to be accepted")
        if conditions:
            raise ValueError("unconditional acceptance cannot contain unresolved conditions")
    if disposition == "accepted_with_conditions" and not conditions:
        raise ValueError("conditional acceptance requires explicit conditions")
    if any(value == "rejected" for value in normalized_checks.values()) and disposition == "accepted":
        raise ValueError("a rejected check cannot be reported as unconditionally accepted")

    report_uri = str(payload.get("signed_report_uri", "")).strip()
    if not report_uri.startswith("https://"):
        raise ValueError("signed_report_uri must be an HTTPS URI")
    normalized = dict(payload)
    normalized["repository_commit"] = commit
    normalized["input_digests"] = normalized_digests
    normalized["checks"] = normalized_checks
    normalized["disposition"] = disposition
    return normalized


def sign_review_payload(payload: Mapping[str, Any], reviewer_private_key_pem: bytes) -> dict[str, Any]:
    """Create a detached signature. The private key belongs to the external reviewer."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    normalized = validate_review_payload(payload)
    key = _private_key(reviewer_private_key_pem)
    signature = key.sign(canonical_bytes(normalized))
    return {
        "schema": REVIEW_SCHEMA,
        "payload": normalized,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
        "signed_payload_sha256": sha256_json(normalized),
    }


def verify_review_record(
    record: Mapping[str, Any] | None,
    reviewer_public_key_pem: bytes | None,
    *,
    expected_reviewer_id: str,
    expected_public_key_sha256: str,
    expected_repository_commit: str,
    expected_input_digests: Mapping[str, str],
    signed_report_path: str | Path | None = None,
    reproduction_artifact_path: str | Path | None = None,
) -> dict[str, Any]:
    """Verify the signed review against out-of-band identity, commit and file-hash pins."""
    try:
        if not isinstance(record, Mapping) or reviewer_public_key_pem is None:
            raise ValueError("signed reviewer record and PEM public key are required")
        if record.get("schema") != REVIEW_SCHEMA:
            raise ValueError("unsupported reviewer record schema")
        payload = validate_review_payload(record.get("payload") or {})
        fingerprint = public_key_fingerprint(reviewer_public_key_pem)
        expected_fingerprint = _sha(expected_public_key_sha256, "expected_public_key_sha256")
        if fingerprint != expected_fingerprint:
            raise ValueError("reviewer public key does not match the out-of-band pinned fingerprint")
        if payload["reviewer_id"] != str(expected_reviewer_id).strip():
            raise ValueError("reviewer_id does not match the independently confirmed reviewer identity")
        if payload["repository_commit"] != str(expected_repository_commit).lower():
            raise ValueError("review record targets a different repository commit")
        required_expected_digests = {
            "science_sha256", "absolute_gain_sha256", "spectral_wcs_sha256",
            "solid_angle_sha256", "native_audit_sha256", "review_packet_sha256",
            "input_manifest_sha256", "signed_report_sha256", "reproduction_artifact_sha256",
        }
        if set(expected_input_digests) != required_expected_digests:
            raise ValueError("expected_input_digests must pin every required science, calibration, report, and reproduction artifact digest")
        for name, expected in expected_input_digests.items():
            actual = payload["input_digests"].get(name)
            if actual != _sha(expected, f"expected_input_digests.{name}"):
                raise ValueError(f"review input digest mismatch for {name}")

        if signed_report_path is None or reproduction_artifact_path is None:
            raise ValueError("both signed_report_path and reproduction_artifact_path are required to verify the review bytes")
        signed_report = Path(signed_report_path)
        if not signed_report.is_file():
            raise FileNotFoundError(f"signed reviewer report is unavailable: {signed_report}")
        if sha256_bytes(signed_report.read_bytes()) != payload["input_digests"]["signed_report_sha256"]:
            raise ValueError("signed reviewer report SHA-256 does not match the signed review")
        from cryptography.exceptions import InvalidSignature
        key = _public_key(reviewer_public_key_pem)
        signature = base64.b64decode(str(record.get("signature_base64", "")), validate=True)
        if record.get("signed_payload_sha256") != sha256_json(payload):
            raise ValueError("signed payload digest does not match the review payload")
        try:
            key.verify(signature, canonical_bytes(payload))
        except InvalidSignature as exc:
            raise ValueError("Ed25519 reviewer signature is invalid") from exc

        path = Path(reproduction_artifact_path)
        if not path.is_file():
            raise FileNotFoundError(f"reproduction artifact is unavailable: {path}")
        actual = sha256_bytes(path.read_bytes())
        if actual != payload["input_digests"]["reproduction_artifact_sha256"]:
            raise ValueError("local reproduction artifact SHA-256 does not match the signed review")
        reproduction_path = str(path.resolve())
        signed_report_verified_path = str(signed_report.resolve())

        return {
            "valid": True,
            "status": "verified_independent_calibration_review_signature",
            "reviewer_id": payload["reviewer_id"],
            "reviewer_public_key_sha256": fingerprint,
            "repository_commit": payload["repository_commit"],
            "disposition": payload["disposition"],
            "accepted_check_count": sum(x == "accepted" for x in payload["checks"].values()),
            "rejected_check_count": sum(x == "rejected" for x in payload["checks"].values()),
            "not_assessed_check_count": sum(x == "not_assessed" for x in payload["checks"].values()),
            "review_payload_sha256": sha256_json(payload),
            "signature_sha256": sha256_bytes(signature),
            "signed_report_path": signed_report_verified_path,
            "reproduction_artifact_path": reproduction_path,
            "verification_boundary": (
                "The signature and pinned key bind the review to its declared reviewer, commit and inputs. "
                "Reviewer qualifications, affiliation, independence and the scientific correctness of the "
                "judgment still require external human verification."
            ),
        }
    except Exception as exc:
        return {
            "valid": False,
            "status": "invalid_or_missing_independent_calibration_review",
            "reason": f"{type(exc).__name__}: {exc}",
        }
