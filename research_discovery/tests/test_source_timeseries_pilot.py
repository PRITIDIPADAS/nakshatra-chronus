import json
from pathlib import Path
import pytest
from research_discovery.spherex.run_source_timeseries_pilot import (
    SCHEMA,
    validate_native_observation_time,
    validate_pilot_manifest,
)
MANIFEST=Path(__file__).resolve().parents[2]/"data"/"spherex_source_timeseries_pilot.orion_candidate.json"
def test_orion_candidate_pilot_manifest_has_four_distinct_native_dr1_d2_epochs():
 m=json.loads(MANIFEST.read_text(encoding="utf-8")); a=validate_pilot_manifest(m)
 assert m["schema"]==SCHEMA
 assert a["product_count"]==4
 assert a["baseline_days"]==pytest.approx(187.041154)
 assert a["minimum_band_overlap_fraction"]==pytest.approx(0.5)
 assert m["selection_policy"]["minimum_band_overlap_fraction"]==pytest.approx(0.5)
 assert a["observation_ids"]==["2025W36_2B_0638_1","2025W37_2A_0601_1","2026W10_1A_0337_2","2026W11_2A_0253_1"]
 assert all(x["release"]=="DR1" and x["detector"]=="D2" for x in m["products"])
def test_orion_candidate_manifest_does_not_promote_catalogue_labels_to_truth():
 s=json.loads(MANIFEST.read_text(encoding="utf-8"))["source_catalogue"]
 assert s["catalogue_labels_are_independent_confirmation"] is False
 assert s["source_class_claim"]=="catalogue_candidate_only_not_independently_confirmed"
def test_pilot_manifest_rejects_duplicate_or_non_dr1_d2_products():
 m=json.loads(MANIFEST.read_text(encoding="utf-8")); m["products"][1]["observation_id"]=m["products"][0]["observation_id"]
 with pytest.raises(ValueError,match="observation_id values must be unique"): validate_pilot_manifest(m)
 m=json.loads(MANIFEST.read_text(encoding="utf-8")); m["products"][0]["detector"]="D5"
 with pytest.raises(ValueError,match="not a DR1 D2"): validate_pilot_manifest(m)



def test_native_fits_observation_time_must_match_frozen_archive_bounds():
    product = {
        "t_min_mjd": 60000.0,
        "t_max_mjd": 60000.001,
        "mjd_midpoint": 60000.0005,
    }
    science = {"mjd_obs": 60000.0, "exposure_time_s": 86.4}
    result = validate_native_observation_time(science, product)
    assert result["start_offset_seconds"] == pytest.approx(0.0)
    assert result["end_offset_seconds"] == pytest.approx(0.0)
    assert result["midpoint_offset_seconds"] == pytest.approx(0.0)

    science["mjd_obs"] += 0.0002
    with pytest.raises(ValueError, match="disagrees with frozen SIAv2 time bounds"):
        validate_native_observation_time(science, product)



def test_native_field_audit_accepts_explicitly_skipped_calibrated_injection():
    from research_discovery.spherex.run_real_field_audit import validate_calibrated_injection_exit

    validate_calibrated_injection_exit("skipped_by_request", skipped_by_request=True)


def test_native_field_audit_does_not_mask_an_unexpected_injection_failure():
    from research_discovery.spherex.run_real_field_audit import validate_calibrated_injection_exit

    with pytest.raises(SystemExit, match="Calibrated Jy injection/recovery did not complete"):
        validate_calibrated_injection_exit("failed", skipped_by_request=True)
    with pytest.raises(SystemExit, match="Calibrated Jy injection/recovery did not complete"):
        validate_calibrated_injection_exit("not_run", skipped_by_request=False)


def test_native_field_audit_still_requires_completed_injection_when_not_skipped():
    from research_discovery.spherex.run_real_field_audit import validate_calibrated_injection_exit

    validate_calibrated_injection_exit("completed", skipped_by_request=False)



def test_source_series_completion_gate_rejects_incomplete_or_partial_four_epoch_runs():
    from research_discovery.spherex.run_source_timeseries_pilot import source_series_completion_error

    incomplete = {
        "status": "incomplete_no_verified_multi_epoch_source_series",
        "requested_epoch_count": 4,
        "successful_photometry_epoch_count": 0,
        "series_error": None,
        "time_series_summary": {},
        "verified_source_timeseries_manifest_sha256": None,
    }
    assert "did not produce a verified multi-epoch series" in source_series_completion_error(incomplete)

    partial = {
        "status": "verified_multi_epoch_source_series",
        "requested_epoch_count": 4,
        "successful_photometry_epoch_count": 3,
        "time_series_summary": {"usable_multi_epoch_series": True, "epoch_count": 4},
        "verified_source_timeseries_manifest_sha256": "a" * 64,
    }
    assert "only 3/4" in source_series_completion_error(partial)


def test_source_series_completion_gate_requires_assembler_confirmation_and_manifest_digest():
    from research_discovery.spherex.run_source_timeseries_pilot import source_series_completion_error

    valid = {
        "status": "verified_multi_epoch_source_series",
        "requested_epoch_count": 4,
        "successful_photometry_epoch_count": 4,
        "time_series_summary": {"usable_multi_epoch_series": True, "epoch_count": 4},
        "verified_source_timeseries_manifest_sha256": "a" * 64,
    }
    assert source_series_completion_error(valid) is None
    assert "canonical SHA-256" in source_series_completion_error({
        **valid, "verified_source_timeseries_manifest_sha256": None
    })
    assert "lacks the assembler" in source_series_completion_error({
        **valid, "time_series_summary": {"usable_multi_epoch_series": False, "epoch_count": 4}
    })


def test_native_audit_retry_recovers_only_transient_irsa_transport_failure(tmp_path, monkeypatch):
    import subprocess
    from research_discovery.spherex import run_source_timeseries_pilot as pilot

    epoch_dir = tmp_path / "epoch"
    audit_dir = epoch_dir / "audit"
    epoch_dir.mkdir()
    audit_dir.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, 1, "Connection refused")
        (audit_dir / "real_field_audit_summary.json").write_text("{}", encoding="utf-8")
        (audit_dir / "native_mef_audit.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "audit passed")

    sleeps = []
    monkeypatch.setattr(pilot.subprocess, "run", fake_run)
    monkeypatch.setattr(pilot.time, "sleep", sleeps.append)
    completed, attempts = pilot.run_native_audit_with_retry(
        ["python", "audit"], cwd=tmp_path, audit_dir=audit_dir, epoch_dir=epoch_dir
    )
    assert completed.returncode == 0
    assert len(calls) == 2
    assert len(attempts) == 2
    assert attempts[0]["transient_irsa_failure"] is True
    assert attempts[1]["native_audit_present"] is True
    assert sleeps == [5]
    assert "ATTEMPT 1 return_code=1" in (epoch_dir / "native_audit_runner.log").read_text(encoding="utf-8")


def test_native_audit_retry_does_not_retry_scientific_or_flag_quality_failures(tmp_path, monkeypatch):
    import subprocess
    from research_discovery.spherex import run_source_timeseries_pilot as pilot

    epoch_dir = tmp_path / "epoch"
    audit_dir = epoch_dir / "audit"
    epoch_dir.mkdir()
    audit_dir.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(1)
        return subprocess.CompletedProcess(
            command, 1, "ValueError: PSF footprint intersects an excluded SPHEREx flag"
        )

    monkeypatch.setattr(pilot.subprocess, "run", fake_run)
    monkeypatch.setattr(pilot.time, "sleep", lambda _: pytest.fail("scientific failures must not be retried"))
    completed, attempts = pilot.run_native_audit_with_retry(
        ["python", "audit"], cwd=tmp_path, audit_dir=audit_dir, epoch_dir=epoch_dir
    )
    assert completed.returncode == 1
    assert len(calls) == 1
    assert len(attempts) == 1
    assert attempts[0]["transient_irsa_failure"] is False


def test_native_audit_retry_stops_after_three_transient_failures(tmp_path, monkeypatch):
    import subprocess
    from research_discovery.spherex import run_source_timeseries_pilot as pilot

    epoch_dir = tmp_path / "epoch"
    audit_dir = epoch_dir / "audit"
    epoch_dir.mkdir()
    audit_dir.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(1)
        return subprocess.CompletedProcess(command, 1, "Connection refused")

    sleeps = []
    monkeypatch.setattr(pilot.subprocess, "run", fake_run)
    monkeypatch.setattr(pilot.time, "sleep", sleeps.append)
    completed, attempts = pilot.run_native_audit_with_retry(
        ["python", "audit"], cwd=tmp_path, audit_dir=audit_dir, epoch_dir=epoch_dir
    )
    assert completed.returncode == 1
    assert len(calls) == 3
    assert len(attempts) == 3
    assert sleeps == [5, 15]
