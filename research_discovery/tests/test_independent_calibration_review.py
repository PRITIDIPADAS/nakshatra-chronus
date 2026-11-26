from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from research_discovery.spherex.independent_calibration_review import (
    REQUIRED_CHECKS,
    REVIEW_SCHEMA,
    public_key_fingerprint,
    sign_review_payload,
    verify_review_record,
)


def _keys():
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _payload():
    return {
        "schema": REVIEW_SCHEMA,
        "reviewer_id": "independent-reviewer-01",
        "reviewer_role": "instrument calibration scientist",
        "affiliation": "Independent institution",
        "independent_of_project_authors": True,
        "conflicts_of_interest": [],
        "reviewed_utc": "2026-11-26T10:00:00+00:00",
        "repository_commit": "a" * 40,
        "input_digests": {
            "science_sha256": "1" * 64,
            "absolute_gain_sha256": "2" * 64,
            "spectral_wcs_sha256": "3" * 64,
            "solid_angle_sha256": "4" * 64,
            "native_audit_sha256": "5" * 64,
            "review_packet_sha256": "6" * 64,
            "input_manifest_sha256": "7" * 64,
            "reproduction_artifact_sha256": "8" * 64,
        },
        "reproduction_artifact_uri": "https://example.org/reproduction.zip",
        "checks": {name: "accepted" for name in REQUIRED_CHECKS},
        "findings": [
            {"check": "level2_variance_noise_accounting", "finding": "Independently reproduced."}
        ],
        "disposition": "accepted",
        "conditions": [],
        "signed_report_uri": "https://example.org/reviewer-report.pdf",
    }


def test_independent_review_signature_is_bound_to_reviewer_commit_and_exact_inputs(tmp_path):
    private_pem, public_pem = _keys()
    payload = _payload()
    signed = sign_review_payload(payload, private_pem)
    pinned = public_key_fingerprint(public_pem)

    artifact = tmp_path / "reproduction.zip"
    artifact.write_bytes(b"independent reproduction output")
    import hashlib
    payload["input_digests"]["reproduction_artifact_sha256"] = hashlib.sha256(
        artifact.read_bytes()
    ).hexdigest()
    signed = sign_review_payload(payload, private_pem)

    result = verify_review_record(
        signed, public_pem,
        expected_reviewer_id="independent-reviewer-01",
        expected_public_key_sha256=pinned,
        expected_repository_commit="a" * 40,
        expected_input_digests=payload["input_digests"],
        reproduction_artifact_path=artifact,
    )
    assert result["valid"] is True
    assert result["disposition"] == "accepted"
    assert result["accepted_check_count"] == len(REQUIRED_CHECKS)
    assert result["reproduction_artifact_path"] == str(artifact.resolve())


def test_independent_review_rejects_unpinned_key_or_changed_commit():
    private_pem, public_pem = _keys()
    signed = sign_review_payload(_payload(), private_pem)
    wrong_pin = "f" * 64
    result = verify_review_record(
        signed, public_pem,
        expected_reviewer_id="independent-reviewer-01",
        expected_public_key_sha256=wrong_pin,
        expected_repository_commit="a" * 40,
        expected_input_digests=_payload()["input_digests"],
    )
    assert result["valid"] is False
    assert "out-of-band pinned fingerprint" in result["reason"]

    result = verify_review_record(
        signed, public_pem,
        expected_reviewer_id="independent-reviewer-01",
        expected_public_key_sha256=public_key_fingerprint(public_pem),
        expected_repository_commit="b" * 40,
        expected_input_digests=_payload()["input_digests"],
    )
    assert result["valid"] is False
    assert "different repository commit" in result["reason"]


def test_independent_review_cannot_claim_unconditional_acceptance_with_open_checks():
    payload = _payload()
    payload["checks"]["source_poisson_increment"] = "not_assessed"
    with pytest.raises(ValueError, match="every required check to be accepted"):
        sign_review_payload(payload, _keys()[0])


def test_independent_review_requires_explicit_independence_and_conflict_statement():
    payload = _payload()
    payload["independent_of_project_authors"] = False
    with pytest.raises(ValueError, match="independence"):
        sign_review_payload(payload, _keys()[0])

    payload = _payload()
    payload.pop("conflicts_of_interest")
    with pytest.raises(ValueError, match="conflicts_of_interest"):
        sign_review_payload(payload, _keys()[0])


def test_tampered_signed_review_payload_is_rejected():
    private_pem, public_pem = _keys()
    signed = sign_review_payload(_payload(), private_pem)
    signed["payload"]["disposition"] = "not_accepted"
    result = verify_review_record(
        signed, public_pem,
        expected_reviewer_id="independent-reviewer-01",
        expected_public_key_sha256=public_key_fingerprint(public_pem),
        expected_repository_commit="a" * 40,
        expected_input_digests=_payload()["input_digests"],
    )
    assert result["valid"] is False
