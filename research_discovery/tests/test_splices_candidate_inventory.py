import csv
import json

import pytest

from research_discovery.spherex.analyze_splices_candidate_inventory import (
    analyze,
    label_flags,
    sha256_json,
    write_candidate_inventory,
)


def _candidate(source_id, region, *, published, class_1, ml):
    return {
        "source_id": source_id,
        "designation": f"J{source_id}",
        "ra": "65.5",
        "dec": "26.1",
        "recon_region": region,
        "region_role": "star_forming_region",
        "yso_pub": "1" if published else "",
        "class_1": "YSO_D" if class_1 else "",
        "stype_ml": "Class II YSO" if ml else "MS Star",
        "w1": "8.0",
        "w1err": "0.03",
        "w2": "7.5",
        "w2err": "0.02",
        "w3": "",
        "w3err": "",
        "w4": "",
        "w4err": "",
        "plx": "",
        "e_plx": "",
        "gaiadist": "",
        "mc_dist": "140",
        "av": "4.5",
        "w1var_class": "N",
        "w2var_class": "I",
    }


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fixture(root):
    regions = [
        {"name": "Taurus_Auriga", "role": "star_forming_region"},
        {"name": "Perseus_NGC1333", "role": "star_forming_region"},
    ]
    rows = [
        _candidate("source-a", "Taurus_Auriga", published=True, class_1=True, ml=True),
        _candidate("source-b", "Taurus_Auriga", published=True, class_1=True, ml=False),
        _candidate("source-c", "Perseus_NGC1333", published=False, class_1=False, ml=True),
        # A repeated archive source ID is retained and reported, never silently
        # collapsed into one row by a position-only merge.
        _candidate("source-a", "Perseus_NGC1333", published=True, class_1=True, ml=True),
    ]
    root.mkdir(parents=True, exist_ok=True)
    _write_csv(root / "candidate_sources_all_regions.csv", rows)

    exposures = {
        "Taurus_Auriga": [
            {"planeid": "plane-1", "uri": "ibe/one.fits", "energy_bandpassname": "SPHEREx-D2",
             "time_bounds_lower": "60000.0", "time_bounds_upper": "60000.1"},
        ],
        "Perseus_NGC1333": [
            {"planeid": "plane-1", "uri": "ibe/one.fits", "energy_bandpassname": "SPHEREx-D2",
             "time_bounds_lower": "60000.0", "time_bounds_upper": "60000.1"},
            {"planeid": "plane-2", "uri": "ibe/two.fits", "energy_bandpassname": "SPHEREx-D1",
             "time_bounds_lower": "60001.0", "time_bounds_upper": "60001.1"},
        ],
    }
    full_region_exposures = {
        "Taurus_Auriga": [
            {"planeid": "plane-1", "uri": "ibe/one.fits", "energy_bandpassname": "SPHEREx-D2",
             "time_bounds_lower": "60000.0", "time_bounds_upper": "60000.1"},
            {"planeid": "plane-2", "uri": "ibe/two.fits", "energy_bandpassname": "SPHEREx-D1",
             "time_bounds_lower": "60001.0", "time_bounds_upper": "60001.1"},
        ],
        "Perseus_NGC1333": [
            {"planeid": "plane-1", "uri": "ibe/one.fits", "energy_bandpassname": "SPHEREx-D2",
             "time_bounds_lower": "60000.0", "time_bounds_upper": "60000.1"},
            {"planeid": "plane-2", "uri": "ibe/two.fits", "energy_bandpassname": "SPHEREx-D1",
             "time_bounds_lower": "60001.0", "time_bounds_upper": "60001.1"},
        ],
    }
    region_results = []
    for region in regions:
        name = region["name"]
        _write_csv(root / name / "dr1_level2_exposures.csv", exposures[name])
        _write_csv(root / name / "dr1_level2_exposures_full_region.csv", full_region_exposures[name])
        region_results.append({
            "region": region,
            "counts": {"catalogue_rows_returned": 10},
            "optional_query_errors": {},
        })

    report = {
        "schema": "chronos-spllices-yso-recon/1.0",
        "region_results": region_results,
        "candidate_record_count": len(rows),
        "errors": [],
        "predeclared_regions": regions,
    }
    report["report_sha256"] = sha256_json(report)
    (root / "yso_population_recon.json").write_text(json.dumps(report), encoding="utf-8")
    return rows


def test_label_flags_keep_published_harmonised_and_ml_labels_separate():
    row = _candidate("x", "Taurus_Auriga", published=True, class_1=True, ml=False)
    assert label_flags(row) == {
        "published_yso_reference_present": True,
        "class_1_contains_yso": True,
        "stype_ml_contains_yso": False,
    }


def test_inventory_report_counts_label_patterns_duplicate_ids_and_region_exposure_repeats(tmp_path):
    _fixture(tmp_path)
    report = analyze(tmp_path)

    assert report["source_identity_audit"]["candidate_rows"] == 4
    assert report["source_identity_audit"]["unique_nonempty_source_ids"] == 3
    assert report["source_identity_audit"]["duplicate_source_id_groups"] == 1
    assert report["source_identity_audit"]["rows_beyond_first_occurrence"] == 1

    patterns = {
        item["pattern"]: item["rows"]
        for item in report["label_overlap_audit"]["three_label_intersection_patterns"]
    }
    assert patterns["published=1;class_1=1;stype_ml=1"] == 2
    assert patterns["published=1;class_1=1;stype_ml=0"] == 1
    assert patterns["published=0;class_1=0;stype_ml=1"] == 1
    assert report["label_overlap_audit"]["published_vs_class_1_membership"]["exact_membership_equivalence_in_candidate_export"] is True

    overlap = report["cross_region_exposure_overlap"]
    assert overlap["exposure_rows_across_regions"] == 3
    assert overlap["unique_plane_ids_across_regions"] == 2
    assert overlap["plane_ids_in_multiple_region_queries"] == 1
    assert overlap["plane_id_region_memberships"]["plane-1"] == ["Perseus_NGC1333", "Taurus_Auriga"]

    full_overlap = report["cross_region_full_region_exposure_overlap"]
    assert full_overlap["exposure_rows_across_regions"] == 4
    assert full_overlap["unique_plane_ids_across_regions"] == 2
    assert full_overlap["plane_ids_in_multiple_region_queries"] == 2
    assert full_overlap["query_semantics"] == "region_circle_intersects_exposure_polygon"
    assert full_overlap["plane_id_region_memberships"]["plane-2"] == ["Perseus_NGC1333", "Taurus_Auriga"]


def test_input_report_hash_and_candidate_row_count_are_fail_closed(tmp_path):
    rows = _fixture(tmp_path)
    report_path = tmp_path / "yso_population_recon.json"
    report = json.loads(report_path.read_text())
    report["candidate_record_count"] = 99
    report["report_sha256"] = sha256_json({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate row count mismatch"):
        analyze(tmp_path)


def test_candidate_inventory_preserves_rows_and_adds_explicit_label_flags(tmp_path):
    rows = [
        _candidate("source-a", "Taurus_Auriga", published=True, class_1=True, ml=False),
    ]
    path = tmp_path / "candidate_label_inventory.csv"
    write_candidate_inventory(rows, path)
    result = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(result) == 1
    assert result[0]["source_id"] == "source-a"
    assert result[0]["published_yso_reference_present"] == "True"
    assert result[0]["class_1_contains_yso"] == "True"
    assert result[0]["stype_ml_contains_yso"] == "False"
