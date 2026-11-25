from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chronos_benchmark.blind import (
    create_blind_store,
    freeze_configuration,
    unblind_benchmark,
)
from chronos_benchmark.custodian_attestation import (
    build_attestation_payload,
    public_key_fingerprint,
    sign_attestation,
    verify_custodian_attestation,
)
from chronos_benchmark.runner import sha256_json


def _field(field_id):
    from chronos_benchmark.runner import truth_catalogue_digest

    truth = [{"truth_id": f"{field_id}-T", "x": 10.0, "y": 12.0}]
    signature = {
        "field_id": field_id,
        "dataset_class": "synthetic",
        "exposure_ids": [field_id + "-E1", field_id + "-E2"],
        "mask_sha256": "a" * 64,
        "truth_catalogue_sha256": truth_catalogue_digest(truth),
        "coordinate_frame": "sky",
        "coordinate_unit": "pixel",
        "pixel_wcs_sha256": "b" * 64,
    }
    methods = {
        name: {"input_signature": dict(signature), "detections": []}
        for name in ("snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin")
    }
    return {
        "field_id": field_id,
        "input_signature": signature,
        "truth_catalogue": truth,
        "methods": methods,
        "match_radius": 1.0,
        "split": "not_split",
    }


def _signing_keypair():
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
    return private_pem, public_pem, public_key_fingerprint(public_pem)


def _sealed_fixture():
    fields = [_field(f"CUSTODIAN-FIELD-{i}") for i in range(4)]
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    blind = create_blind_store(fields, key, test_fraction=0.25, seed=55)
    public = blind["public_manifest"]
    run_manifest = blind["run_manifest"]
    dataset_digest = sha256_json({
        "public_manifest": public,
        "run_manifest": run_manifest,
    })
    methods = ("snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin")
    configuration = {
        "preregistration_sha256": "c" * 64,
        "score_thresholds": {name: [1.0] for name in methods},
        "matched_target": {"false_candidates_per_field": 0.0},
        "matching_radii_by_field": {
            row["blind_field_token"]: float(row["match_radius"])
            for row in run_manifest["fields"]
        },
        "false_candidate_noninferiority_margin": 0.0,
        "multiple_comparison_correction": "bonferroni_95_familywise",
    }
    frozen = freeze_configuration(
        configuration, source_commit="d" * 40, dataset_digest=dataset_digest
    )
    test_tokens = set(public["blind_test_tokens"])
    detection_fields = []
    for row in run_manifest["fields"]:
        if row["blind_field_token"] not in test_tokens:
            continue
        signature = row["input_signature"]
        detection_fields.append({
            "blind_field_token": row["blind_field_token"],
            "input_signature": signature,
            "methods": {
                name: {"input_signature": signature, "detections": []}
                for name in methods
            },
        })
    detection_run = {
        "benchmark_id": "custodian-attestation-test",
        "dataset_digest": dataset_digest,
        "frozen_configuration_sha256": frozen["configuration_sha256"],
        "source_commit": "d" * 40,
        "configuration": configuration,
        "public_fields": run_manifest["fields"],
        "matching_radii_by_field": configuration["matching_radii_by_field"],
        "fields": detection_fields,
        "score_thresholds": configuration["score_thresholds"],
        "matched_target": configuration["matched_target"],
    }
    return key, blind, public, run_manifest, frozen, detection_run


def _attestation(private_pem, public, run_manifest, encrypted, frozen):
    return build_attestation_payload(
        custodian_id="Independent Reviewer A",
        registration_url="https://registration.example.org/records/CHRONOS-001",
        registration_id="CHRONOS-001",
        registered_utc="2026-11-20T12:00:00+00:00",
        registration_receipt=b"immutable externally timestamped protocol receipt",
        public_manifest=public,
        run_manifest=run_manifest,
        encrypted_truth_store=encrypted,
        frozen_configuration=frozen,
        attested_utc=datetime.now(timezone.utc).isoformat(),
        analysis_team_holdout_access_before_registration=False,
        custodian_independent_of_analysis_team=True,
        registration_receipt_verified_by_custodian=True,
    )


def test_independent_custodian_signature_binds_receipt_and_exact_holdout_data():
    key, blind, public, run_manifest, frozen, detection_run = _sealed_fixture()
    private_pem, public_pem, fingerprint = _signing_keypair()
    payload = _attestation(
        private_pem, public, run_manifest, blind["encrypted_truth_store"], frozen
    )
    signed = sign_attestation(payload, private_pem)

    verified = verify_custodian_attestation(
        signed, public_pem,
        expected_public_key_sha256=fingerprint,
        public_manifest=public,
        run_manifest=run_manifest,
        encrypted_truth_store=blind["encrypted_truth_store"],
        frozen_configuration=frozen,
    )
    assert verified["valid"] is True
    assert verified["status"] == "verified_independent_custodian_attestation"
    assert verified["registration_receipt_sha256"] == payload["registration_receipt_sha256"]

    report = unblind_benchmark(
        public, blind["encrypted_truth_store"], key, frozen, detection_run,
        custodian_attestation=signed,
        custodian_public_key=public_pem,
        expected_custodian_public_key_sha256=fingerprint,
        bootstrap_draws=100,
    )
    assert report["blind_protocol"]["custodian_attestation"]["valid"] is True
    assert report["scientific_claim_eligible"] is False  # This fixture is synthetic, not real held-out SPHEREx.


def test_custodian_attestation_fails_on_unpinned_key_or_changed_manifest():
    key, blind, public, run_manifest, frozen, detection_run = _sealed_fixture()
    private_pem, public_pem, fingerprint = _signing_keypair()
    signed = sign_attestation(
        _attestation(private_pem, public, run_manifest, blind["encrypted_truth_store"], frozen),
        private_pem,
    )
    wrong_key = "0" * 64
    rejected = verify_custodian_attestation(
        signed, public_pem,
        expected_public_key_sha256=wrong_key,
        public_manifest=public,
        run_manifest=run_manifest,
        encrypted_truth_store=blind["encrypted_truth_store"],
        frozen_configuration=frozen,
    )
    assert rejected["valid"] is False
    assert "pinned fingerprint" in rejected["reason"]

    altered = dict(public)
    altered["field_count"] += 1
    rejected = verify_custodian_attestation(
        signed, public_pem,
        expected_public_key_sha256=fingerprint,
        public_manifest=altered,
        run_manifest=run_manifest,
        encrypted_truth_store=blind["encrypted_truth_store"],
        frozen_configuration=frozen,
    )
    assert rejected["valid"] is False
    assert "public_manifest_sha256" in rejected["reason"]


def test_missing_custodian_signature_keeps_blind_scoring_exploratory():
    key, blind, public, run_manifest, frozen, detection_run = _sealed_fixture()
    report = unblind_benchmark(
        public, blind["encrypted_truth_store"], key, frozen, detection_run,
        bootstrap_draws=100,
    )
    assert report["blind_protocol"]["custodian_attestation"]["valid"] is False
    assert report["scientific_claim_eligible"] is False
    assert "independent_custodian_attestation_missing_or_invalid" in report["scientific_eligibility_reasons"]
