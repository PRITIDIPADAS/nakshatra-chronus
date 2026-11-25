import csv
import json

import pytest

from research_discovery.spherex.analyze_splices_candidate_inventory import (
    analyze,
    label_flags,
    sha256_json,
    write_candidate_inventory,
    _check_input_report,
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


def _write_csv(path, rows, *, fieldnames=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Empty query results still need a header row so they are distinguishable
    # from a missing query artifact.
    columns = list(rows[0]) if rows else list(fieldnames or [
        "obs_id", "access_url", "_chronos_collection", "_chronos_release",
        "_chronos_dataset_class", "_chronos_region",
    ])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
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
    source_matches = {
        "Taurus_Auriga": [
            {"source_id": "source-a", "planeid": "plane-1", "obsid": "obs-1",
             "uri": "ibe/one.fits", "energy_bandpassname": "SPHEREx-D2",
             "time_bounds_lower": "60000.0", "time_bounds_upper": "60000.1"},
        ],
        "Perseus_NGC1333": [
            {"source_id": "source-a", "planeid": "plane-1", "obsid": "obs-1",
             "uri": "ibe/one.fits", "energy_bandpassname": "SPHEREx-D2",
             "time_bounds_lower": "60000.0", "time_bounds_upper": "60000.1"},
            {"source_id": "source-c", "planeid": "plane-2", "obsid": "obs-2",
             "uri": "ibe/two.fits", "energy_bandpassname": "SPHEREx-D1",
             "time_bounds_lower": "60001.0", "time_bounds_upper": "60001.1"},
        ],
    }
    source_summaries = {
        "Taurus_Auriga": [
            {"source_id": "source-a", "unique_level2_plane_count": 1,
             "bands": "SPHEREx-D2", "first_mjd": 60000.0, "last_mjd": 60000.1},
        ],
        "Perseus_NGC1333": [
            {"source_id": "source-a", "unique_level2_plane_count": 1,
             "bands": "SPHEREx-D2", "first_mjd": 60000.0, "last_mjd": 60000.1},
            {"source_id": "source-c", "unique_level2_plane_count": 1,
             "bands": "SPHEREx-D1", "first_mjd": 60001.0, "last_mjd": 60001.1},
        ],
    }
    region_results = []
    for region in regions:
        name = region["name"]
        _write_csv(root / name / "dr1_level2_exposures.csv", exposures[name])
        _write_csv(root / name / "dr1_level2_exposures_full_region.csv", full_region_exposures[name])
        _write_csv(root / name / "candidate_source_exposure_matches.csv", source_matches[name])
        _write_csv(root / name / "candidate_source_epoch_summary.csv", source_summaries[name])
        region_results.append({
            "region": region,
            "counts": {
                "catalogue_rows_returned": 10,
                "candidate_source_exposure_query_complete": True,
            },
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


def _fixture_sia_v11(root):
    rows = _fixture(root)
    path = root / "yso_population_recon.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    for result in report["region_results"]:
        region = result["region"]["name"]
        result["optional_sia_errors"] = {}
        result["optional_query_errors"] = {}
        result["counts"]["region_intersecting_spectral_image_rows_by_collection"] = {
            "spherex_dr1": {"product_rows": 2, "query_complete_below_row_cap": True},
            "spherex_dr1_deep": {"product_rows": 0, "query_complete_below_row_cap": True},
            "spherex_qr3": {"product_rows": 1, "query_complete_below_row_cap": True},
            "spherex_qr3_deep": {"product_rows": 0, "query_complete_below_row_cap": True},
        }
        for collection, release, count in (
            ("spherex_dr1", "dr1", 2), ("spherex_dr1_deep", "dr1", 0),
            ("spherex_qr3", "qr3", 1), ("spherex_qr3_deep", "qr3", 0),
        ):
            products = [{
                "obs_id": f"{region}-{collection}-{i}",
                "access_url": f"https://irsa.example/{region}/{collection}/{i}.fits",
                "_chronos_collection": collection,
                "_chronos_release": release,
                "_chronos_dataset_class": "real",
                "_chronos_region": region,
            } for i in range(count)]
            _write_csv(
                root / region / f"region_footprints_sia_{collection}.csv",
                products,
                fieldnames=[
                    "obs_id", "access_url", "_chronos_collection",
                    "_chronos_release", "_chronos_dataset_class", "_chronos_region",
                ],
            )
    _write_csv(root / "dr1_all_sky_cube_sia_metadata.csv", [{
        "obs_id": "DR1-ALLSKY-CUBE",
        "access_url": "https://irsa.example/dr1/allsky-cube.fits",
        "_chronos_collection": "spherex_dr1_cube",
        "_chronos_product_role": "all_sky_spatial_spectral_cube",
    }])
    for region, source_id in (
        ("Taurus_Auriga", "source-a"),
        ("Perseus_NGC1333", "source-c"),
    ):
        _write_csv(root / region / "candidate_source_product_matches.csv", [{
            "source_id": source_id,
            "archive_product_id": f"{region}-product-1",
            "obs_id": f"{region}-obs-1",
            "collection": "spherex_dr1",
            "data_release": "dr1",
            "energy_bandpassname": "SPHEREx-D2",
            "match_method": "spherical-gnomonic-pip/1.0",
            "metadata_only": True,
        }])
    report["schema"] = "chronos-spllices-yso-recon/1.1"
    report["dr1_all_sky_cube"] = {
        "collection": "spherex_dr1_cube", "nominal_channels": 102,
        "wavelength_range_um": [0.75, 5.0], "role": "all_sky_spatial_spectral_cube",
        "queried_in_this_reconnaissance": True, "metadata_row_count": 1,
        "metadata_only": True, "native_cube_downloaded": False,
        "temporal_epoch_series": False,
    }
    report["dr1_all_sky_cube_inventory"] = {
        "row_count": 1, "native_cube_downloaded": False, "temporal_epoch_series": False,
    }
    report["report_sha256"] = sha256_json({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    path.write_text(json.dumps(report), encoding="utf-8")
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

    source_coverage = report["candidate_source_exposure_coverage"]
    assert source_coverage["match_row_count"] == 3
    assert source_coverage["source_summary_row_count"] == 3
    assert source_coverage["regions_with_completed_query"] == 2
    assert source_coverage["regions_with_unavailable_query"] == 0

    source_overlap = report["cross_region_candidate_source_exposure_overlap"]
    assert source_overlap["source_exposure_match_rows"] == 3
    assert source_overlap["unique_source_plane_pairs"] == 2
    assert source_overlap["source_plane_pairs_in_multiple_region_queries"] == 1
    assert "source-a|plane-1" in source_overlap["source_plane_pair_region_memberships"]

    first_region = report["regional_candidate_and_coverage_summaries"][0]
    assert first_region["candidate_source_exposure_query_status"] == "complete_below_declared_row_cap"
    assert first_region["candidate_source_exposure_match_rows"] == 1
    assert first_region["candidate_sources_with_any_level2_footprint_match"] == 1



def test_schema_1_1_siav2_products_and_cube_are_not_epochs(tmp_path):
    _fixture_sia_v11(tmp_path)
    report = analyze(tmp_path)
    first = report["regional_candidate_and_coverage_summaries"][0]
    assert first["dr1_level2_full_region_spectral_image_product_rows"] == 2
    assert first["qr3_level2_full_region_spectral_image_product_rows"] == 1
    assert first["all_release_full_region_spectral_image_product_rows"] == 3
    assert first["dr1_level2_full_region_intersection_exposure_rows"] is None
    assert first["candidate_source_exposure_query_status"] == "complete_below_declared_row_cap"
    assert first["candidate_source_exposure_match_rows"] == 1
    assert first["candidate_source_product_match_rows"] == 1
    assert report["cross_region_candidate_source_exposure_overlap"]["unique_source_archive_product_pairs_observed"] == 2
    cube = report["dr1_all_sky_cube_inventory"]
    assert cube["metadata_rows_verified_against_csv"] == 1
    assert cube["metadata_access_uri_rows"] == 1
    assert cube["native_cube_downloaded"] is False
    assert cube["temporal_epoch_series"] is False
    assert report["cross_region_spectral_image_product_overlap"]["product_rows_across_regions"] == 6


def test_schema_1_1_failed_sia_collection_ignores_stale_csv(tmp_path):
    _fixture_sia_v11(tmp_path)
    path = tmp_path / "yso_population_recon.json"
    report = json.loads(path.read_text())
    report["region_results"][0]["optional_sia_errors"] = {
        "spherex_dr1": "temporary SIAv2 timeout"
    }
    report["report_sha256"] = sha256_json({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    path.write_text(json.dumps(report), encoding="utf-8")
    audited = analyze(tmp_path)
    first = audited["regional_candidate_and_coverage_summaries"][0]
    collections = first["dr1_level2_full_region_spectral_image_products_by_collection"]
    assert collections["spherex_dr1"]["query_status"] == "unavailable"
    assert collections["spherex_dr1"]["product_rows"] is None
    assert first["dr1_level2_full_region_spectral_image_product_rows"] is None
    assert first["all_release_full_region_spectral_image_product_rows"] is None
    assert first["dr1_level2_full_region_intersection_query_status"] == "partial_optional_queries_failed"


def test_failed_optional_full_region_query_ignores_stale_csv_and_never_reports_zero(tmp_path):
    _fixture(tmp_path)
    report_path = tmp_path / "yso_population_recon.json"
    report = json.loads(report_path.read_text())
    report["region_results"][0]["optional_query_errors"] = {
        "dr1_level2_exposures_full_region": "TAP geometry function unavailable"
    }
    report["report_sha256"] = sha256_json({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = analyze(tmp_path)
    first_region = result["regional_candidate_and_coverage_summaries"][0]
    assert first_region["dr1_level2_full_region_intersection_query_status"] == "unavailable"
    assert first_region["dr1_level2_full_region_intersection_exposure_rows"] is None
    assert "TAP geometry function unavailable" in first_region["dr1_level2_full_region_intersection_query_error"]
    # The stale CSV's rows for the failed region are excluded. The other
    # region's successful rows remain available and are not rewritten as zero.
    assert result["cross_region_full_region_exposure_overlap"]["exposure_rows_across_regions"] == 2


def test_failed_optional_source_epoch_query_ignores_stale_match_csv(tmp_path):
    _fixture(tmp_path)
    report_path = tmp_path / "yso_population_recon.json"
    report = json.loads(report_path.read_text())
    report["region_results"][0]["optional_query_errors"] = {
        "candidate_source_exposure_matches": "source-to-polygon query rejected"
    }
    report["report_sha256"] = sha256_json({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = analyze(tmp_path)
    first_region = result["regional_candidate_and_coverage_summaries"][0]
    assert first_region["candidate_source_exposure_query_status"] == "unavailable"
    assert first_region["candidate_source_exposure_match_rows"] is None
    assert first_region["candidate_sources_with_any_level2_footprint_match"] is None
    # Stale Taurus match rows are excluded; the two current Perseus rows remain.
    assert result["candidate_source_exposure_coverage"]["match_row_count"] == 2
    assert result["cross_region_candidate_source_exposure_overlap"]["source_plane_pairs_in_multiple_region_queries"] == 0




def test_failed_optional_full_region_query_does_not_require_missing_csv(tmp_path):
    _fixture(tmp_path)
    report_path = tmp_path / "yso_population_recon.json"
    report = json.loads(report_path.read_text())
    report["region_results"][0]["optional_query_errors"] = {
        "dr1_level2_exposures_full_region": "TAP geometry function unavailable"
    }
    (tmp_path / "Taurus_Auriga" / "dr1_level2_exposures_full_region.csv").unlink()
    report["report_sha256"] = sha256_json({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = analyze(tmp_path)
    first_region = result["regional_candidate_and_coverage_summaries"][0]
    assert first_region["dr1_level2_full_region_intersection_query_status"] == "unavailable"
    assert first_region["dr1_level2_full_region_intersection_exposure_rows"] is None
    assert result["cross_region_full_region_exposure_overlap"]["exposure_rows_across_regions"] == 2


def test_failed_optional_source_epoch_query_does_not_require_missing_csv(tmp_path):
    _fixture(tmp_path)
    report_path = tmp_path / "yso_population_recon.json"
    report = json.loads(report_path.read_text())
    report["region_results"][0]["optional_query_errors"] = {
        "candidate_source_exposure_matches": "source-to-polygon query rejected"
    }
    (tmp_path / "Taurus_Auriga" / "candidate_source_exposure_matches.csv").unlink()
    (tmp_path / "Taurus_Auriga" / "candidate_source_epoch_summary.csv").unlink()
    report["report_sha256"] = sha256_json({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = analyze(tmp_path)
    first_region = result["regional_candidate_and_coverage_summaries"][0]
    assert first_region["candidate_source_exposure_query_status"] == "unavailable"
    assert first_region["candidate_source_exposure_match_rows"] is None
    assert result["candidate_source_exposure_coverage"]["match_row_count"] == 2


def test_schema_1_1_missing_siav2_csv_is_unavailable_not_zero(tmp_path):
    _fixture_sia_v11(tmp_path)
    missing = tmp_path / "Taurus_Auriga" / "region_footprints_sia_spherex_dr1.csv"
    missing.unlink()
    result = analyze(tmp_path)
    first = result["regional_candidate_and_coverage_summaries"][0]
    status = first["dr1_level2_full_region_spectral_image_products_by_collection"]["spherex_dr1"]
    assert status["query_status"] == "unavailable"
    assert status["product_rows"] is None
    assert first["dr1_level2_full_region_spectral_image_product_rows"] is None


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


def test_input_report_accepts_current_v11_schema_with_checksum_and_row_validation(tmp_path):
    rows = _fixture(tmp_path)
    report = json.loads((tmp_path / "yso_population_recon.json").read_text())
    report["schema"] = "chronos-spllices-yso-recon/1.1"
    report["report_sha256"] = sha256_json({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    validated = _check_input_report(report, rows)
    assert validated["report_sha256_verified"] is True
    assert validated["candidate_record_count_verified"] is True
    assert validated["candidate_rows"] == len(rows)


def test_input_report_still_rejects_unknown_future_schema(tmp_path):
    rows = _fixture(tmp_path)
    report = json.loads((tmp_path / "yso_population_recon.json").read_text())
    report["schema"] = "chronos-spllices-yso-recon/9.9"
    report["report_sha256"] = sha256_json({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    with pytest.raises(ValueError, match="unsupported SPLICES reconnaissance report schema"):
        _check_input_report(report, rows)
