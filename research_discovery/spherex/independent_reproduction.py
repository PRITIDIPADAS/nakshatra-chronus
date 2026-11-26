"""Signed independent astronomical reproduction records and fail-closed readiness."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

SCHEMA = "chronos-independent-astronomical-reproduction/1.0"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
CLAIMS = {
    "source_timeseries", "instrument_calibration", "source_selection",
    "candidate_event_yield", "blind_benchmark", "population_inference",
}
CHECKS = (
    "native_source_data", "wcs_cwave_cband", "calibration_and_noise",
    "source_identity_and_classification", "source_selection_function",
    "event_detection_and_contamination", "blind_benchmark",
    "statistical_reproduction", "negative_controls_and_exclusions", "claim_scope",
)
REQUIRED_CHECKS = CHECKS
SCOPE_CHECKS = {
    "source_timeseries": {
        "native_source_data", "wcs_cwave_cband", "calibration_and_noise",
        "statistical_reproduction", "negative_controls_and_exclusions", "claim_scope",
    },
    "instrument_calibration": {
        "native_source_data", "wcs_cwave_cband", "calibration_and_noise",
        "statistical_reproduction", "claim_scope",
    },
    "source_selection": {
        "native_source_data", "calibration_and_noise", "source_selection_function",
        "statistical_reproduction", "negative_controls_and_exclusions", "claim_scope",
    },
    "candidate_event_yield": {
        "native_source_data", "wcs_cwave_cband", "calibration_and_noise",
        "source_identity_and_classification", "source_selection_function",
        "event_detection_and_contamination", "statistical_reproduction",
        "negative_controls_and_exclusions", "claim_scope",
    },
    "blind_benchmark": {
        "native_source_data", "wcs_cwave_cband", "calibration_and_noise",
        "source_selection_function", "blind_benchmark",
        "statistical_reproduction", "negative_controls_and_exclusions", "claim_scope",
    },
    "population_inference": {
        "native_source_data", "wcs_cwave_cband", "calibration_and_noise",
        "source_identity_and_classification", "source_selection_function",
        "event_detection_and_contamination", "blind_benchmark",
        "statistical_reproduction", "negative_controls_and_exclusions", "claim_scope",
    },
}
REQUIRED_DIGESTS = {
    "input_manifest_sha256", "native_source_data_sha256",
    "source_timeseries_sha256", "calibration_audit_sha256",
    "selection_trials_sha256", "analysis_output_sha256",
    "software_environment_sha256", "signed_report_sha256",
    "reproduction_artifact_sha256",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _sha(value: Any, label: str) -> str:
    result = str(value or "").lower()
    if not SHA_RE.fullmatch(result):
        raise ValueError(f"{label} must be a 64-character lowercase SHA-256 digest")
    return result


def _utc(value: Any, label: str) -> None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")


def _public_key(pem: bytes):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        key = serialization.load_pem_public_key(pem)
    except Exception as exc:
        raise ValueError("reviewer public key must be a valid PEM Ed25519 key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("reviewer public key must use Ed25519")
    return key


def _private_key(pem: bytes):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    try:
        key = serialization.load_pem_private_key(pem, password=None)
    except Exception as exc:
        raise ValueError("reviewer private key must be an unencrypted PEM Ed25519 key") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("reviewer private key must use Ed25519")
    return key


def public_key_fingerprint(pem: bytes) -> str:
    from cryptography.hazmat.primitives import serialization
    key = _public_key(pem)
    raw = key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256_bytes(raw)


def validate_reproduction_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("schema") != SCHEMA:
        raise ValueError(f"payload schema must be {SCHEMA}")
    for name in ("reviewer_id", "reviewer_role", "affiliation", "review_conclusion"):
        if not str(payload.get(name, "")).strip():
            raise ValueError(f"{name} is required")
    if payload.get("independent_of_analysis_authors") is not True:
        raise ValueError("reviewer must explicitly attest independence from the analysis authors")
    if payload.get("authored_or_tuned_claim") is not False:
        raise ValueError("reviewer must explicitly attest they did not author or tune the reviewed claim")
    conflicts = payload.get("conflicts_of_interest")
    if not isinstance(conflicts, list) or any(not str(item).strip() for item in conflicts):
        raise ValueError("conflicts_of_interest must be a list; use [] when none are declared")
    _utc(payload.get("reviewed_utc"), "reviewed_utc")

    commit = str(payload.get("repository_commit", "")).lower()
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError("repository_commit must be a full 40- or 64-character commit SHA")
    claims = payload.get("scope_claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("scope_claims must be a non-empty list")
    normalized_claims = sorted({str(item).strip() for item in claims})
    unknown = sorted(set(normalized_claims) - CLAIMS)
    if unknown:
        raise ValueError(f"unsupported scope_claims: {unknown}")
    in_scope = set().union(*(SCOPE_CHECKS[item] for item in normalized_claims))

    digests = payload.get("input_digests")
    if not isinstance(digests, Mapping):
        raise ValueError("input_digests must be an object")
    missing = sorted(REQUIRED_DIGESTS - set(digests))
    if missing:
        raise ValueError(f"input_digests is missing: {missing}")
    normalized_digests = {
        str(name): _sha(value, f"input_digests.{name}")
        for name, value in digests.items()
    }

    for name in ("signed_report_uri", "reproduction_artifact_uri"):
        parsed = urlparse(str(payload.get(name, "")).strip())
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"{name} must be an HTTPS URI")

    checks = payload.get("checks")
    if not isinstance(checks, Mapping) or set(checks) != set(CHECKS):
        raise ValueError("checks must contain every required domain exactly once")
    normalized_checks = {}
    for name in CHECKS:
        status = str(checks[name]).strip().lower()
        if status not in {"accepted", "rejected", "not_assessed", "not_in_scope"}:
            raise ValueError(f"checks.{name} has an unsupported status")
        if name in in_scope and status == "not_in_scope":
            raise ValueError(f"checks.{name} is required by the declared review scope")
        if name not in in_scope and status != "not_in_scope":
            raise ValueError(f"checks.{name} must be not_in_scope for the declared review scope")
        normalized_checks[name] = status

    disposition = str(payload.get("disposition", "")).strip().lower()
    if disposition not in {"accepted", "accepted_with_conditions", "not_accepted"}:
        raise ValueError("disposition must be accepted, accepted_with_conditions, or not_accepted")
    conditions = payload.get("conditions")
    if not isinstance(conditions, list) or any(not str(item).strip() for item in conditions):
        raise ValueError("conditions must be a list of non-empty strings")
    if disposition == "accepted":
        if any(normalized_checks[name] != "accepted" for name in in_scope):
            raise ValueError("unconditional acceptance requires every in-scope check to be accepted")
        if conditions:
            raise ValueError("unconditional acceptance cannot contain unresolved conditions")
    elif disposition == "accepted_with_conditions" and not conditions:
        raise ValueError("conditional acceptance requires explicit conditions")

    if set(normalized_claims) & {"blind_benchmark", "population_inference"}:
        registration = payload.get("external_registration")
        if not isinstance(registration, Mapping):
            raise ValueError("blind/population reproduction requires external_registration evidence")
        parsed = urlparse(str(registration.get("receipt_uri", "")).strip())
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("external_registration.receipt_uri must be HTTPS")
        _sha(registration.get("receipt_sha256"), "external_registration.receipt_sha256")
        _utc(registration.get("registered_utc"), "external_registration.registered_utc")

    normalized = dict(payload)
    normalized["repository_commit"] = commit
    normalized["scope_claims"] = normalized_claims
    normalized["input_digests"] = normalized_digests
    normalized["checks"] = normalized_checks
    normalized["disposition"] = disposition
    return normalized


def sign_reproduction_payload(payload: Mapping[str, Any], reviewer_private_key_pem: bytes) -> dict[str, Any]:
    """Create a detached signature; the private key belongs to the external astronomer."""
    normalized = validate_reproduction_payload(payload)
    signature = _private_key(reviewer_private_key_pem).sign(canonical_bytes(normalized))
    return {
        "schema": SCHEMA,
        "payload": normalized,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
        "signed_payload_sha256": sha256_json(normalized),
    }


def verify_reproduction_record(
    record: Mapping[str, Any] | None,
    reviewer_public_key_pem: bytes | None,
    *,
    expected_reviewer_id: str,
    expected_public_key_sha256: str,
    expected_repository_commit: str,
    expected_input_digests: Mapping[str, str],
    signed_report_path: str | Path,
    reproduction_artifact_path: str | Path,
) -> dict[str, Any]:
    """Verify signature, out-of-band reviewer/key pins, commit, inputs and report bytes."""
    try:
        if not isinstance(record, Mapping) or reviewer_public_key_pem is None:
            raise ValueError("signed reproduction record and reviewer public key are required")
        if record.get("schema") != SCHEMA:
            raise ValueError("unsupported reproduction record schema")
        payload = validate_reproduction_payload(record.get("payload") or {})
        fingerprint = public_key_fingerprint(reviewer_public_key_pem)
        if fingerprint != _sha(expected_public_key_sha256, "expected_public_key_sha256"):
            raise ValueError("reviewer public key does not match the out-of-band pinned fingerprint")
        if payload["reviewer_id"] != str(expected_reviewer_id).strip():
            raise ValueError("reviewer_id does not match the independently verified reviewer identity")
        if payload["repository_commit"] != str(expected_repository_commit).lower():
            raise ValueError("reproduction record targets a different repository commit")
        if set(expected_input_digests) != set(payload["input_digests"]):
            raise ValueError("expected_input_digests must pin the complete signed input-digest set")
        for name, expected in expected_input_digests.items():
            if payload["input_digests"][name] != _sha(expected, f"expected_input_digests.{name}"):
                raise ValueError(f"reproduction input digest mismatch for {name}")

        report = Path(signed_report_path)
        artifact = Path(reproduction_artifact_path)
        if not report.is_file() or not artifact.is_file():
            raise FileNotFoundError("signed report and reproduction artifact files are both required")
        if sha256_bytes(report.read_bytes()) != payload["input_digests"]["signed_report_sha256"]:
            raise ValueError("signed astronomer report SHA-256 does not match its signed record")
        if sha256_bytes(artifact.read_bytes()) != payload["input_digests"]["reproduction_artifact_sha256"]:
            raise ValueError("reproduction artifact SHA-256 does not match its signed record")

        from cryptography.exceptions import InvalidSignature
        signature = base64.b64decode(str(record.get("signature_base64", "")), validate=True)
        if record.get("signed_payload_sha256") != sha256_json(payload):
            raise ValueError("signed payload SHA-256 does not match the normalized payload")
        try:
            _public_key(reviewer_public_key_pem).verify(signature, canonical_bytes(payload))
        except InvalidSignature as exc:
            raise ValueError("reviewer Ed25519 signature is invalid") from exc

        required = set().union(*(SCOPE_CHECKS[item] for item in payload["scope_claims"]))
        return {
            "valid": True,
            "status": "verified_independent_astronomical_reproduction",
            "reviewer_id": payload["reviewer_id"],
            "reviewer_public_key_sha256": fingerprint,
            "repository_commit": payload["repository_commit"],
            "scope_claims": payload["scope_claims"],
            "disposition": payload["disposition"],
            "accepted_check_count": sum(payload["checks"][name] == "accepted" for name in required),
            "required_check_count": len(required),
            "rejected_check_count": sum(payload["checks"][name] == "rejected" for name in required),
            "not_assessed_check_count": sum(payload["checks"][name] == "not_assessed" for name in required),
            "review_payload_sha256": sha256_json(payload),
            "signature_sha256": sha256_bytes(signature),
            "signed_report_path": str(report.resolve()),
            "reproduction_artifact_path": str(artifact.resolve()),
            "verification_boundary": (
                "The pinned key and digests verify the signed record and exact artifacts. Reviewer identity, "
                "qualifications, affiliation, independence, original-data access and scientific correctness "
                "still require external human verification."
            ),
        }
    except Exception as exc:
        return {
            "valid": False,
            "status": "invalid_or_missing_independent_astronomical_reproduction",
            "reason": f"{type(exc).__name__}: {exc}",
        }


def evaluate_scientific_release_readiness(
    *,
    calibration_review: Mapping[str, Any] | None,
    astronomical_reproduction: Mapping[str, Any] | None,
    custodian_attestation: Mapping[str, Any] | None,
    blind_benchmark: Mapping[str, Any] | None,
    source_timeseries: Mapping[str, Any] | None,
    source_selection: Mapping[str, Any] | None,
    event_detection: Mapping[str, Any] | None,
    contamination_review: Mapping[str, Any] | None,
    independent_classifications: Mapping[str, Any] | None,
    external_preregistration: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compute readiness only; this function never publishes or authorizes a release."""
    def accepted_review(value: Mapping[str, Any] | None) -> bool:
        if not isinstance(value, Mapping):
            return False
        try:
            required = int(value.get("required_check_count", -1))
            accepted = int(value.get("accepted_check_count", -2))
            rejected = int(value.get("rejected_check_count", 1))
            not_assessed = int(value.get("not_assessed_check_count", 1))
        except (TypeError, ValueError, OverflowError):
            return False
        return (
            value.get("valid") is True
            and value.get("disposition") == "accepted"
            and required > 0 and accepted == required
            and rejected == 0 and not_assessed == 0
            and value.get("external_identity_and_independence_confirmed") is True
        )

    def accepted_blind_benchmark(value: Mapping[str, Any] | None) -> bool:
        """A completed run is not a superiority result; require the actual blind gate."""
        if not isinstance(value, Mapping):
            return False
        required_methods = {
            "snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin"
        }
        methods = value.get("methods")
        if not isinstance(methods, (list, tuple)) or any(not isinstance(x, str) for x in methods):
            return False
        if set(methods) != required_methods:
            return False
        if value.get("scientific_claim_eligible") is not True:
            return False
        reproducibility = value.get("reproducibility") or {}
        if not isinstance(reproducibility, Mapping):
            return False
        if reproducibility.get("same_input_enforced_for_all_methods") is not True:
            return False
        blind = value.get("blind_evaluation") or {}
        if not isinstance(blind, Mapping):
            return False
        if (
            blind.get("custodian_attestation_verified") is not True
            or blind.get("configuration_freeze_verified") is not True
            or blind.get("truth_released_after_run_freeze") is not True
            or blind.get("multiple_comparison_correction") != "bonferroni_95_familywise"
        ):
            return False
        preregistration = str(blind.get("preregistration_sha256", "")).lower()
        if not SHA_RE.fullmatch(preregistration):
            return False
        unblind = blind.get("unblinding_record") or {}
        if not isinstance(unblind, Mapping):
            return False
        encrypted_truth_sha = str(unblind.get("encrypted_truth_store_sha256", "")).lower()
        processed_tokens = unblind.get("heldout_field_tokens_processed")
        if not SHA_RE.fullmatch(encrypted_truth_sha):
            return False
        if not isinstance(processed_tokens, (list, tuple)) or not processed_tokens:
            return False
        paired = value.get("paired_superiority") or {}
        if not isinstance(paired, Mapping):
            return False
        margin = paired.get("predeclared_false_candidate_noninferiority_margin")
        try:
            independent_groups = int(paired.get("independent_group_count", 0))
        except (TypeError, ValueError, OverflowError):
            return False
        correction = paired.get("multiple_comparator_correction") or {}
        if not isinstance(correction, Mapping):
            return False
        if (
            paired.get("status") != "paired_field_group_bootstrap_completed"
            or paired.get("verdict_status") != "superiority_gate_passed"
            or paired.get("superiority_supported") is not True
            or independent_groups < 5
            or isinstance(margin, bool)
            or not isinstance(margin, (int, float))
            or not math.isfinite(float(margin))
            or float(margin) < 0
            or correction.get("method") != "bonferroni_95_familywise"
            or correction.get("verified_predeclared") is not True
        ):
            return False
        comparisons = paired.get("comparisons") or {}
        if not isinstance(comparisons, Mapping) or set(comparisons) != {"snr_only", "chronos_pda", "instrument_forensics"}:
            return False
        for comparison in comparisons.values():
            if not isinstance(comparison, Mapping):
                return False
            completeness = comparison.get("delta_completeness_twin_minus_comparator") or {}
            false_candidates = comparison.get("delta_false_candidates_per_field_twin_minus_comparator") or {}
            if not isinstance(completeness, Mapping) or not isinstance(false_candidates, Mapping):
                return False
            completeness_ci = completeness.get("familywise_95_interval_bonferroni")
            false_candidate_ci = false_candidates.get("familywise_95_interval_bonferroni")
            if (
                not isinstance(completeness_ci, (list, tuple)) or len(completeness_ci) != 2
                or not isinstance(false_candidate_ci, (list, tuple)) or len(false_candidate_ci) != 2
            ):
                return False
            try:
                if not (float(completeness_ci[0]) > 0 and float(false_candidate_ci[1]) <= float(margin)):
                    return False
            except (TypeError, ValueError, OverflowError):
                return False
        return True

    def _minimum_independent_groups(value: Mapping[str, Any], minimum: int) -> bool:
        try:
            return int(value.get("independent_field_count", 0)) >= minimum
        except (TypeError, ValueError, OverflowError):
            return False

    summary = source_timeseries.get("time_series_summary", {}) if isinstance(source_timeseries, Mapping) else {}
    digest = str(source_timeseries.get("verified_source_timeseries_manifest_sha256", "")).lower() if isinstance(source_timeseries, Mapping) else ""
    try:
        requested_epochs = int(source_timeseries.get("requested_epoch_count", 0)) if isinstance(source_timeseries, Mapping) else 0
        successful_epochs = int(source_timeseries.get("successful_photometry_epoch_count", 0)) if isinstance(source_timeseries, Mapping) else 0
        distinct_epochs = int(summary.get("epoch_count", 0)) if isinstance(summary, Mapping) else 0
        distinct_mjds = int(summary.get("distinct_mjd_count", 0)) if isinstance(summary, Mapping) else 0
        epochs_ok = (
            isinstance(source_timeseries, Mapping)
            and requested_epochs >= 4
            and successful_epochs >= requested_epochs
            and successful_epochs >= 4
            and distinct_epochs >= 4
            and distinct_mjds >= 4
        )
    except (TypeError, ValueError, OverflowError):
        epochs_ok = False

    def accepted_full_scope_astronomical_reproduction(value: Mapping[str, Any] | None) -> bool:
        if not accepted_review(value):
            return False
        scopes = value.get("scope_claims")
        if not isinstance(scopes, (list, tuple)):
            return False
        # A narrow claim-scoped reproduction is valid for its declared scope,
        # but cannot be promoted to a project-wide scientific release gate.
        return set(scopes) == set(CLAIMS)
    try:
        selection_ok = (
            isinstance(source_selection, Mapping)
            and source_selection.get("supported") is True
            and int(source_selection.get("independent_field_count", 0)) >= 5
            and bool(source_selection.get("cells"))
            and all(cell.get("supported") is True for cell in source_selection.get("cells", []))
        )
    except (TypeError, ValueError, OverflowError, AttributeError):
        selection_ok = False
    try:
        classes_ok = isinstance(independent_classifications, Mapping) and independent_classifications.get("status") == "independently_verified" and int(independent_classifications.get("source_count", 0)) > 0
    except (TypeError, ValueError, OverflowError):
        classes_ok = False

    gates = {
        "independent_calibration_review": accepted_review(calibration_review),
        "independent_astronomical_reproduction": accepted_full_scope_astronomical_reproduction(astronomical_reproduction),
        "independent_blind_custodian": (
            isinstance(custodian_attestation, Mapping)
            and custodian_attestation.get("valid") is True
            and custodian_attestation.get("custodian_identity_verified_out_of_band") is True
            and custodian_attestation.get("custodian_independence_verified_out_of_band") is True
        ),
        "blind_four_baseline_benchmark": accepted_blind_benchmark(blind_benchmark),
        "verified_multi_epoch_source_timeseries": isinstance(source_timeseries, Mapping) and source_timeseries.get("status") == "verified_multi_epoch_source_series" and epochs_ok and bool(SHA_RE.fullmatch(digest)) and isinstance(summary, Mapping) and summary.get("usable_multi_epoch_series") is True,
        "real_supported_source_selection_function": selection_ok,
        "event_detection_efficiency": (
            isinstance(event_detection, Mapping)
            and event_detection.get("supported") is True
            and event_detection.get("real_source_timeseries_injections") is True
            and event_detection.get("negative_controls_passed") is True
            and event_detection.get("outside_support_abstention_verified") is True
            and _minimum_independent_groups(event_detection, 5)
        ),
        "source_level_contamination_review": (
            isinstance(contamination_review, Mapping)
            and contamination_review.get("status") == "independently_reviewed"
            and contamination_review.get("source_level_controls") is True
            and contamination_review.get("independent_reviewer_identity_verified_out_of_band") is True
        ),
        "independent_source_classifications": classes_ok,
        "external_preregistration": (
            isinstance(external_preregistration, Mapping)
            and external_preregistration.get("verified") is True
            and bool(SHA_RE.fullmatch(str(external_preregistration.get("receipt_sha256", "")).lower()))
            and external_preregistration.get("registered_before_data_access") is True
            and external_preregistration.get("independent_timestamp_verified") is True
            and external_preregistration.get("receipt_bytes_verified") is True
            and external_preregistration.get("custodian_no_prior_holdout_access_attested") is True
        ),
    }
    blockers = sorted(name for name, passed in gates.items() if not passed)
    return {
        "schema": "chronos-scientific-release-readiness/1.0",
        "decision": "closed" if blockers else "all_evidence_gates_passed_pending_human_release_authorization",
        "release_allowed": not blockers,
        "gates": gates,
        "blockers": blockers,
        "boundary": "Readiness reporting does not publish, tag, or authorize a scientific release; human release authorization remains required.",
    }
