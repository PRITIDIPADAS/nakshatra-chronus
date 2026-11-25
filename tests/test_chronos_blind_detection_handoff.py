from copy import deepcopy

import pytest

from chronos_benchmark.blind import (
    BLIND_SCHEMA,
    build_blind_detection_run,
    create_blind_store,
    freeze_configuration,
)
from chronos_benchmark.runner import REQUIRED_METHODS, sha256_json, truth_catalogue_digest


def _field(field_id):
    truth = [{"truth_id": f"{field_id}-T", "x": 10.0, "y": 12.0}]
    signature = {
        "field_id": field_id,
        "dataset_class": "real",
        "exposure_ids": [field_id + "-E1", field_id + "-E2"],
        "mask_sha256": "a" * 64,
        "truth_catalogue_sha256": truth_catalogue_digest(truth),
        "coordinate_frame": "sky",
        "coordinate_unit": "pixel",
        "pixel_wcs_sha256": "b" * 64,
    }
    return {
        "field_id": field_id,
        "input_signature": signature,
        "truth_catalogue": truth,
        "match_radius": 1.0,
        "split_group_id": field_id,
    }


def _fixture():
    fields = []
    for index in range(4):
        field = _field(f"PRIVATE-FIELD-{index}")
        public_ids = [
            f"exposure_opaque_{index}_a",
            f"exposure_opaque_{index}_b",
        ]
        public_signature = dict(field["input_signature"])
        public_signature["exposure_ids"] = public_ids
        # The custodian computes this mask digest after substituting public_ids
        # into the same prepared exposure/mask state.
        public_signature["mask_sha256"] = f"{index + 10:064x}"
        field["public_exposure_ids"] = public_ids
        field["public_input_signature"] = public_signature
        fields.append(field)

    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    blind = create_blind_store(fields, key, test_fraction=0.25, seed=55)
    public = blind["public_manifest"]
    run_manifest = blind["run_manifest"]
    canonical_run = {
        "schema": BLIND_SCHEMA,
        "fields": sorted(run_manifest["fields"], key=lambda row: row["blind_field_token"]),
    }
    digest = sha256_json({"public_manifest": public, "run_manifest": canonical_run})
    configuration = {
        "preregistration_sha256": "c" * 64,
        "score_thresholds": {name: [3.0, 5.0] for name in REQUIRED_METHODS},
        "matched_target": {"false_candidates_per_field": 0.1},
        "matching_radii_by_field": {
            row["blind_field_token"]: row["match_radius"]
            for row in run_manifest["fields"]
        },
        "false_candidate_noninferiority_margin": 0.05,
        "multiple_comparison_correction": "bonferroni_95_familywise",
    }
    frozen = freeze_configuration(
        configuration, source_commit="d" * 40, dataset_digest=digest
    )
    records = []
    for public_field in run_manifest["fields"]:
        if public_field["split_role"] != "blind_test":
            continue
        signature = public_field["input_signature"]
        methods = {
            name: {
                "input_signature": signature,
                "detections": [{
                    "detection_id": f"{name}-0",
                    "x": 10.2,
                    "y": 12.1,
                    "score": 5.1,
                    "provenance": {"method": name, "model_version": "test-1"},
                }],
            }
            for name in REQUIRED_METHODS
        }
        records.append({
            "blind_field_token": public_field["blind_field_token"],
            "input_signature": signature,
            "match_radius": public_field["match_radius"],
            "methods": methods,
            "baseline_contract": {
                "same_pipeline_state": True,
                "verified_exposure_ids": sorted(signature["exposure_ids"]),
                "verified_mask_sha256": signature["mask_sha256"],
                "verified_pixel_wcs_sha256": signature["pixel_wcs_sha256"],
            },
        })
    return key, blind, frozen, records


def test_blind_store_accepts_custodian_issued_opaque_exposure_ids():
    _, blind, _, _ = _fixture()
    for row in blind["run_manifest"]["fields"]:
        exposure_ids = row["input_signature"]["exposure_ids"]
        assert len(exposure_ids) == 2
        assert all(value.startswith("exposure_opaque_") for value in exposure_ids)
        assert all("PRIVATE-FIELD" not in value for value in exposure_ids)


def test_detection_run_is_truth_free_and_contains_all_holdouts_once():
    _, blind, frozen, records = _fixture()
    result = build_blind_detection_run(
        blind["public_manifest"], blind["run_manifest"], frozen, records,
        benchmark_id="spx-dr1-blind-001",
    )
    assert result["schema"] == BLIND_SCHEMA
    assert result["blind_run_contract"]["truth_catalogues_accessed"] is False
    assert result["blind_run_contract"]["private_field_ids_accessed"] is False
    assert result["blind_run_contract"]["all_holdout_tokens_present_once"] is True
    assert {row["blind_field_token"] for row in result["fields"]} == set(
        blind["public_manifest"]["blind_test_tokens"]
    )
    assert all(set(row["methods"]) == set(REQUIRED_METHODS) for row in result["fields"])
    assert all("truth_catalogue" not in row for row in result["fields"])
    assert all("PRIVATE-FIELD" not in str(row) for row in result["fields"])


def test_detection_run_rejects_missing_duplicate_or_development_fields():
    _, blind, frozen, records = _fixture()
    with pytest.raises(ValueError, match="every holdout field exactly once"):
        build_blind_detection_run(
            blind["public_manifest"], blind["run_manifest"], frozen, records[:-1],
            benchmark_id="missing",
        )
    duplicate = records + [deepcopy(records[0])]
    with pytest.raises(ValueError, match="duplicate blind field record"):
        build_blind_detection_run(
            blind["public_manifest"], blind["run_manifest"], frozen, duplicate,
            benchmark_id="duplicate",
        )
    development = next(
        row for row in blind["run_manifest"]["fields"]
        if row["split_role"] == "development"
    )
    bad = deepcopy(records)
    bad.append({
        "blind_field_token": development["blind_field_token"],
        "input_signature": development["input_signature"],
        "match_radius": development["match_radius"],
        "methods": {},
    })
    with pytest.raises(ValueError, match="unknown or non-holdout"):
        build_blind_detection_run(
            blind["public_manifest"], blind["run_manifest"], frozen, bad,
            benchmark_id="development",
        )


def test_detection_run_rejects_signature_method_and_truth_leaks():
    _, blind, frozen, records = _fixture()
    changed = deepcopy(records)
    changed[0]["input_signature"]["mask_sha256"] = "e" * 64
    with pytest.raises(ValueError, match="signature differs"):
        build_blind_detection_run(
            blind["public_manifest"], blind["run_manifest"], frozen, changed,
            benchmark_id="changed",
        )
    leaked = deepcopy(records)
    leaked[0]["truth_catalogue"] = [{"truth_id": "unsealed"}]
    with pytest.raises(ValueError, match="forbidden private fields"):
        build_blind_detection_run(
            blind["public_manifest"], blind["run_manifest"], frozen, leaked,
            benchmark_id="leaked",
        )
    missing_method = deepcopy(records)
    missing_method[0]["methods"].pop(REQUIRED_METHODS[0])
    with pytest.raises(ValueError, match="exactly the four required"):
        build_blind_detection_run(
            blind["public_manifest"], blind["run_manifest"], frozen, missing_method,
            benchmark_id="missing-method",
        )


def test_detection_run_rejects_mutated_frozen_manifest():
    _, blind, frozen, records = _fixture()
    altered = deepcopy(blind["public_manifest"])
    altered["field_count"] += 1
    with pytest.raises(ValueError, match="dataset digest"):
        build_blind_detection_run(
            altered, blind["run_manifest"], frozen, records,
            benchmark_id="mutated-manifest",
        )
