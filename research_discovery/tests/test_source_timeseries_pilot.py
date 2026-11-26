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
