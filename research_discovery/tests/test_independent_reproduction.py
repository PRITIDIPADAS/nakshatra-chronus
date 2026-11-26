import hashlib
import pytest

from research_discovery.spherex.independent_reproduction import (
    REQUIRED_CHECKS, SCHEMA, SCOPE_CHECKS,
    evaluate_scientific_release_readiness, sign_reproduction_payload,
    verify_reproduction_record,
)
from research_discovery.spherex.independent_reproduction import public_key_fingerprint


def _keys():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private = Ed25519PrivateKey.generate()
    return (
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    )


def _payload(report_bytes, artifact_bytes, scope=("source_timeseries",)):
    in_scope = set().union(*(SCOPE_CHECKS[item] for item in scope))
    return {
        "schema": SCHEMA,
        "reviewer_id": "independent-astronomer-01",
        "reviewer_role": "external astronomy reproducer",
        "affiliation": "independently declared institution",
        "independent_of_analysis_authors": True,
        "authored_or_tuned_claim": False,
        "conflicts_of_interest": [],
        "reviewed_utc": "2026-11-26T04:00:00Z",
        "repository_commit": "a" * 40,
        "scope_claims": list(scope),
        "input_digests": {
            "input_manifest_sha256": hashlib.sha256(b"manifest").hexdigest(),
            "native_source_data_sha256": hashlib.sha256(b"native").hexdigest(),
            "source_timeseries_sha256": hashlib.sha256(b"series").hexdigest(),
            "calibration_audit_sha256": hashlib.sha256(b"calibration").hexdigest(),
            "selection_trials_sha256": hashlib.sha256(b"selection").hexdigest(),
            "analysis_output_sha256": hashlib.sha256(b"analysis").hexdigest(),
            "software_environment_sha256": hashlib.sha256(b"environment").hexdigest(),
            "signed_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "reproduction_artifact_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        },
        "signed_report_uri": "https://example.org/reproduction-report.pdf",
        "reproduction_artifact_uri": "https://example.org/reproduction-artifact.zip",
        "checks": {name: ("accepted" if name in in_scope else "not_in_scope") for name in REQUIRED_CHECKS},
        "disposition": "accepted",
        "conditions": [],
        "review_conclusion": "Reproduced only the declared scope using supplied original data and commands.",
    }


def test_reproduction_record_verifies_signature_commit_and_exact_report_artifact_bytes(tmp_path):
    private, public = _keys()
    report, artifact = tmp_path / "report.pdf", tmp_path / "reproduction.zip"
    report.write_bytes(b"external report")
    artifact.write_bytes(b"reproduction output")
    payload = _payload(report.read_bytes(), artifact.read_bytes())
    record = sign_reproduction_payload(payload, private)
    result = verify_reproduction_record(
        record, public,
        expected_reviewer_id="independent-astronomer-01",
        expected_public_key_sha256=public_key_fingerprint(public),
        expected_repository_commit="a" * 40,
        expected_input_digests=payload["input_digests"],
        signed_report_path=report,
        reproduction_artifact_path=artifact,
    )
    assert result["valid"] is True
    assert result["required_check_count"] == len(SCOPE_CHECKS["source_timeseries"])
    assert result["accepted_check_count"] == result["required_check_count"]


def test_reproduction_record_rejects_wrong_key_or_changed_commit(tmp_path):
    private, public = _keys()
    _, wrong_public = _keys()
    report, artifact = tmp_path / "report.pdf", tmp_path / "reproduction.zip"
    report.write_bytes(b"report")
    artifact.write_bytes(b"artifact")
    payload = _payload(report.read_bytes(), artifact.read_bytes())
    record = sign_reproduction_payload(payload, private)
    common = dict(
        expected_reviewer_id="independent-astronomer-01",
        expected_public_key_sha256=public_key_fingerprint(public),
        expected_repository_commit="a" * 40,
        expected_input_digests=payload["input_digests"],
        signed_report_path=report,
        reproduction_artifact_path=artifact,
    )
    assert not verify_reproduction_record(record, wrong_public, **common)["valid"]
    changed = verify_reproduction_record(record, public, **{**common, "expected_repository_commit": "b" * 40})
    assert not changed["valid"]


def test_reproduction_record_rejects_tampered_report_or_artifact(tmp_path):
    private, public = _keys()
    report, artifact = tmp_path / "report.pdf", tmp_path / "reproduction.zip"
    report.write_bytes(b"report")
    artifact.write_bytes(b"artifact")
    payload = _payload(report.read_bytes(), artifact.read_bytes())
    record = sign_reproduction_payload(payload, private)
    report.write_bytes(b"changed report")
    result = verify_reproduction_record(
        record, public,
        expected_reviewer_id="independent-astronomer-01",
        expected_public_key_sha256=public_key_fingerprint(public),
        expected_repository_commit="a" * 40,
        expected_input_digests=payload["input_digests"],
        signed_report_path=report,
        reproduction_artifact_path=artifact,
    )
    assert not result["valid"]
    assert "report SHA-256" in result["reason"]


def test_reproduction_record_rejects_unassessed_or_hidden_scoped_checks():
    private, _ = _keys()
    payload = _payload(b"report", b"artifact")
    payload["checks"]["native_source_data"] = "not_assessed"
    with pytest.raises(ValueError, match="unconditional acceptance"):
        sign_reproduction_payload(payload, private)
    payload = _payload(b"report", b"artifact")
    payload["checks"]["native_source_data"] = "not_in_scope"
    with pytest.raises(ValueError, match="required by the declared review scope"):
        sign_reproduction_payload(payload, private)


def test_release_readiness_is_fail_closed_until_all_evidence_gates_pass():
    missing = evaluate_scientific_release_readiness(
        calibration_review=None, astronomical_reproduction=None,
        custodian_attestation=None, blind_benchmark=None,
        source_timeseries=None, source_selection=None,
        event_detection=None, contamination_review=None,
        independent_classifications=None, external_preregistration=None,
    )
    assert not missing["release_allowed"]
    assert "independent_astronomical_reproduction" in missing["blockers"]
    assert "verified_multi_epoch_source_timeseries" in missing["blockers"]

    accepted = {
        "valid": True, "disposition": "accepted",
        "accepted_check_count": 10, "required_check_count": 10,
        "rejected_check_count": 0, "not_assessed_check_count": 0,
    }
    ready = evaluate_scientific_release_readiness(
        calibration_review=accepted, astronomical_reproduction=accepted,
        custodian_attestation={"valid": True},
        blind_benchmark={"status": "completed", "all_methods_same_inputs": True, "custodian_unblinded": True},
        source_timeseries={
            "status": "verified_multi_epoch_source_series",
            "successful_photometry_epoch_count": 4, "requested_epoch_count": 4,
            "verified_source_timeseries_manifest_sha256": "1" * 64,
            "time_series_summary": {"usable_multi_epoch_series": True},
        },
        source_selection={"supported": True, "independent_field_count": 5, "cells": [{"supported": True}]},
        event_detection={"supported": True, "real_source_timeseries_injections": True},
        contamination_review={"status": "independently_reviewed", "source_level_controls": True},
        independent_classifications={"status": "independently_verified", "source_count": 10},
        external_preregistration={"verified": True, "receipt_sha256": "2" * 64, "registered_before_data_access": True},
    )
    assert ready["release_allowed"]
    assert ready["decision"] == "all_evidence_gates_passed_pending_human_release_authorization"
