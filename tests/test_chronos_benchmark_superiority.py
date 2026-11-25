import numpy as np

from chronos_benchmark.runner import compare_benchmark_package, truth_catalogue_digest


def _field(field_id, found, method_names):
    truth = [{"truth_id": f"{field_id}-T", "x": 20.0, "y": 30.0}]
    signature = {
        "field_id": field_id,
        "dataset_class": "synthetic",
        "exposure_ids": [f"{field_id}-E1", f"{field_id}-E2"],
        "mask_sha256": "a" * 64,
        "truth_catalogue_sha256": truth_catalogue_digest(truth),
        "coordinate_frame": "sky",
        "coordinate_unit": "pixel",
        "pixel_wcs_sha256": "b" * 64,
    }
    methods = {}
    for name in method_names:
        detections = []
        if name == "sky_detector_twin" or found.get(name, False):
            detections = [{
                "detection_id": f"{field_id}-{name}",
                "x": 20.0, "y": 30.0, "score": 9.0,
                "provenance": {"pipeline": name},
            }]
        methods[name] = {"input_signature": dict(signature), "detections": detections}
    return {
        "field_id": field_id,
        "independence_group_id": field_id,
        "split": "not_split",
        "input_signature": signature,
        "truth_catalogue": truth,
        "methods": methods,
        "match_radius": 1.0,
        "control_type": "science",
    }


def test_paired_superiority_report_uses_independent_field_groups_and_stays_closed_for_synthetic_data():
    method_names = (
        "snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin"
    )
    fields = []
    for index in range(12):
        field_id = f"FIELD-{index:02d}"
        found = {
            "snr_only": index % 3 == 0,
            "chronos_pda": index % 2 == 0,
            "instrument_forensics": index % 3 == 0,
        }
        fields.append(_field(field_id, found, method_names))

    package = {
        "schema": "chronos-four-baseline-package/1.0",
        "benchmark_id": "paired-superiority-test",
        "fields": fields,
        "score_thresholds": {name: [5.0, 1.0] for name in method_names},
        "matched_target": {"false_candidates_per_field": 0.0},
    }
    result = compare_benchmark_package(package, bootstrap_draws=300, seed=27)

    paired = result["paired_superiority"]
    assert paired["status"] == "paired_field_group_bootstrap_completed"
    assert paired["independent_group_count"] == 12
    assert set(paired["comparisons"]) == set(method_names) - {"sky_detector_twin"}
    assert paired["superiority_supported"] is False
    assert paired["verdict_status"] == "not_scientifically_eligible"
    for comparison in paired["comparisons"].values():
        interval = comparison["delta_completeness_twin_minus_comparator"][
            "familywise_95_interval_bonferroni"
        ]
        assert interval is not None and len(interval) == 2
        assert np.isfinite(interval).all()
