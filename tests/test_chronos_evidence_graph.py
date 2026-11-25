from __future__ import annotations

import pytest

from chronos_causal.evidence_graph import build_evidence_graph


def test_evidence_graph_keeps_multiple_spectral_samples_from_one_exposure_distinct():
    observations = [
        {
            "observation_id": "SPHEREX-OBS-1",
            "mjd": 60000.0,
            "wavelength_um": 2.8,
            "flux": 1.2,
            "sigma": 0.1,
            "calibration_group": "DR1-D2-CAL-A",
            "calibration_product_id": "GAIN-A",
        },
        {
            "observation_id": "SPHEREX-OBS-1",
            "mjd": 60000.0,
            "wavelength_um": 3.0,
            "flux": 1.1,
            "sigma": 0.1,
            "calibration_group": "DR1-D2-CAL-A",
            "calibration_product_id": "GAIN-A",
        },
    ]
    manifest = {
        "files": [{
            "archive_id": "GAIN-A",
            "product_type": "absolute_gain_calibration",
            "native_uri": "https://archive.example/gain.fits",
            "sha256": "a" * 64,
        }]
    }
    graph = build_evidence_graph(
        candidate_id="YSO-CANDIDATE-1",
        observations=observations,
        analysis={"verdict": "unknown", "abstention_reasons": ["insufficient evidence"]},
        manifest=manifest,
    )

    measurements = [node for node in graph["nodes"] if node["type"] == "measurement"]
    assert len(measurements) == 2
    assert len({node["id"] for node in measurements}) == 2
    assert {node["observation_id"] for node in measurements} == {"SPHEREX-OBS-1"}
    assert {node["record_sha256"] for node in measurements}.__len__() == 2
    assert graph["claim"]["status"] == "unresolved"

    known = {node["id"] for node in graph["nodes"]}
    assert all(edge["source"] in known and edge["target"] in known for edge in graph["edges"])
    calibration_edges = [edge for edge in graph["edges"] if edge["relation"] == "calibration_for_measurement"]
    assert len(calibration_edges) == 2


def test_evidence_graph_rejects_duplicate_explicit_measurement_ids():
    row = {
        "observation_id": "OBS-1",
        "measurement_id": "MEAS-1",
        "wavelength_um": 2.8,
        "flux": 1.2,
        "sigma": 0.1,
    }
    with pytest.raises(ValueError, match="duplicate measurement identity"):
        build_evidence_graph(
            candidate_id="C1",
            observations=[row, dict(row, wavelength_um=3.0)],
            analysis={"verdict": "unknown"},
        )


def test_evidence_graph_rejects_exact_duplicate_implicit_measurement_rows():
    row = {
        "observation_id": "OBS-1",
        "wavelength_um": 2.8,
        "flux": 1.2,
        "sigma": 0.1,
    }
    with pytest.raises(ValueError, match="duplicate measurement identity"):
        build_evidence_graph(
            candidate_id="C1",
            observations=[row, dict(row)],
            analysis={"verdict": "unknown"},
        )


def test_evidence_graph_rejects_duplicate_archive_product_ids():
    manifest = {
        "files": [
            {"archive_id": "PRODUCT-1", "product_type": "science"},
            {"archive_id": "PRODUCT-1", "product_type": "calibration"},
        ]
    }
    with pytest.raises(ValueError, match="duplicate evidence graph node ID"):
        build_evidence_graph(
            candidate_id="C1",
            observations=[{"observation_id": "OBS-1"}],
            analysis={"verdict": "unknown"},
            manifest=manifest,
        )


def test_evidence_graph_rejects_duplicate_model_run_ids():
    runs = [{"run_id": "RUN-1", "model": "A"}, {"run_id": "RUN-1", "model": "B"}]
    with pytest.raises(ValueError, match="duplicate evidence graph node ID"):
        build_evidence_graph(
            candidate_id="C1",
            observations=[{"observation_id": "OBS-1"}],
            analysis={"verdict": "unknown"},
            model_runs=runs,
        )
