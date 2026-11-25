import research_discovery.spherex.yso_population_recon as recon


def test_predeclared_yso_regions_include_independent_control_region():
    assert len(recon.REGIONS) >= 5
    assert any(region["role"] == "control" for region in recon.REGIONS)
    assert all(region["radius_deg"] > 0 for region in recon.REGIONS)


def test_catalogue_query_uses_bounded_row_selection_not_unsupported_count():
    queries = recon.build_region_queries(recon.REGIONS[0])
    catalogue = queries["catalogue_sources"]
    assert "SELECT TOP 50000" in catalogue
    assert "COUNT(" not in catalogue.upper()
    assert "GROUP BY" not in catalogue.upper()
    assert "CONTAINS(POINT(ra, dec), CIRCLE(" in catalogue
    assert "ORDER BY source_id" in catalogue


def test_published_harmonised_and_ml_labels_are_retained_separately():
    queries = recon.build_region_queries(recon.REGIONS[0])
    catalogue = queries["catalogue_sources"]
    candidate = queries["candidate_sources"]
    for label in ("class_1", "yso_pub", "stype_ml"):
        assert label in catalogue
    assert "yso_pub IS NOT NULL" in candidate
    assert "UPPER(class_1) LIKE '%YSO%'" in candidate
    assert "UPPER(stype_ml) LIKE '%YSO%'" in candidate
    assert candidate != catalogue


def test_candidate_query_is_bounded_and_deterministic():
    query = recon.build_region_queries(recon.REGIONS[0])["candidate_sources"]
    assert f"SELECT TOP {recon.CANDIDATE_LIMIT}" in query
    assert "w1var" in query
    assert "w2var" in query
    assert "ORDER BY source_id" in query


def test_dr1_exposure_coverage_uses_centre_point_and_sia2_full_region_intersection():
    queries = recon.build_region_queries(recon.REGIONS[0])
    query = queries["dr1_level2_exposures"]
    assert "spherex.artifact" in query
    assert "spherex.plane" in query
    assert "p.poly" in query
    assert "1 = CONTAINS(POINT('ICRS', 65.70000000, 26.00000000), p.poly)" in query
    assert "AND (LOWER(a.uri) LIKE" in query
    assert "COUNT(" not in query.upper()
    assert "GROUP BY" not in query.upper()

    assert "dr1_level2_exposures_full_region" not in queries
    assert recon.SIA_COLLECTIONS == (
        "spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep"
    )

    # Source-to-product association is local against SIAv2 s_region polygons.
    assert "candidate_source_exposure_matches" not in queries
    assert recon.FOOTPRINT_MATCH_ALGORITHM == "spherical-gnomonic-pip/1.0"


def test_irsa_sia2_region_footprints_use_pos_circle_and_collection(monkeypatch):
    calls = []
    class FakeTable:
        colnames = ["obs_id", "access_url"]
        def __iter__(self):
            return iter([{"obs_id": "OBS-1", "access_url": "https://irsa.example/a.fits"}])

    def fake_query_sia(**kwargs):
        calls.append(kwargs)
        return FakeTable()

    monkeypatch.setattr(recon.Irsa, "query_sia", fake_query_sia)
    region = recon.REGIONS[0]
    result = recon.query_region_footprints_sia(region, "spherex_dr1_deep")
    assert calls == [{
        "pos": (region["ra_deg"], region["dec_deg"], region["radius_deg"]),
        "collection": "spherex_dr1_deep",
        "maxrec": recon.COVERAGE_ROW_LIMIT,
    }]
    assert result["service"] == "IRSA SIAv2"
    assert result["release"] == "dr1"
    assert result["rows"][0]["_chronos_collection"] == "spherex_dr1_deep"
    assert result["rows"][0]["_chronos_dataset_class"] == "real"
    assert result["query_complete_below_row_cap"] is True


def test_candidate_source_epoch_rows_identify_dr1_qr3_and_unknown_uris():
    assert recon.release_from_uri("https://irsa.example/spherex/dr1/level2/a.fits") == "dr1"
    assert recon.release_from_uri("https://irsa.example/spherex/qr3/level2/b.fits") == "qr3"
    assert recon.release_from_uri("https://irsa.example/unknown/a.fits") == "unknown"


def test_dr1_all_sky_cube_query_is_separate_from_temporal_exposures(monkeypatch):
    calls = []
    class FakeTable:
        colnames = ["obs_id", "access_url", "dataproduct_type"]
        def __iter__(self):
            return iter([{
                "obs_id": "ALLSKY-DR1",
                "access_url": "https://irsa.example/dr1/allsky-cube.fits",
                "dataproduct_type": "cube",
            }])

    def fake_query_sia(**kwargs):
        calls.append(kwargs)
        return FakeTable()

    monkeypatch.setattr(recon.Irsa, "query_sia", fake_query_sia)
    region = recon.REGIONS[0]
    result = recon.query_dr1_all_sky_cube_sia(region)
    assert calls == [{
        "pos": (region["ra_deg"], region["dec_deg"], region["radius_deg"]),
        "collection": "spherex_dr1_cube",
        "maxrec": recon.CUBE_METADATA_ROW_LIMIT,
    }]
    assert result["region"] == region["name"]
    assert result["query_complete_below_row_cap"] is True
    assert result["product_role"] == "all_sky_spatial_spectral_cube"
    assert result["nominal_spectral_channels"] == 102
    assert result["nominal_wavelength_range_um"] == [0.75, 5.0]
    assert result["native_cube_downloaded"] is False
    assert result["temporal_epoch_series"] is False
    assert result["rows"][0]["_chronos_product_role"] == "all_sky_spatial_spectral_cube"
    assert result["rows"][0]["_chronos_temporal_epoch_series"] is False



def test_source_exposure_cone_filter_handles_ra_wrap_and_deduplicates_source_plane_pairs():
    region = {"name": "Wrap_Test", "ra_deg": 0.0, "dec_deg": 0.0,
              "radius_deg": 1.0, "role": "control"}
    rows = [
        {
            "source_id": "S1", "designation": "J0000", "ra": 359.8, "dec": 0.1,
            "yso_pub": 1, "class_1": "YSO", "stype_ml": "YSO",
            "planeid": "P1", "obsid": "O1", "uri": "p1.fits",
            "energy_bandpassname": "SPHEREx-D1",
            "time_bounds_lower": 60000.0, "time_bounds_upper": 60000.1,
        },
        {
            "source_id": "S1", "designation": "J0000", "ra": 359.8, "dec": 0.1,
            "yso_pub": 1, "class_1": "YSO", "stype_ml": "YSO",
            "planeid": "P1", "obsid": "O1", "uri": "p1-duplicate.fits",
            "energy_bandpassname": "SPHEREx-D1",
            "time_bounds_lower": 60000.0, "time_bounds_upper": 60000.1,
        },
        {
            "source_id": "S1", "designation": "J0000", "ra": 359.8, "dec": 0.1,
            "yso_pub": 1, "class_1": "YSO", "stype_ml": "YSO",
            "planeid": "P2", "obsid": "O2", "uri": "p2.fits",
            "energy_bandpassname": "SPHEREx-D2",
            "time_bounds_lower": 60001.0, "time_bounds_upper": 60001.1,
        },
        {
            "source_id": "S2", "designation": "outside", "ra": 2.0, "dec": 0.0,
            "yso_pub": None, "class_1": "STAR", "stype_ml": "YSO",
            "planeid": "P3", "obsid": "O3", "uri": "p3.fits",
            "energy_bandpassname": "SPHEREx-D3",
            "time_bounds_lower": 60002.0, "time_bounds_upper": 60002.1,
        },
    ]
    candidate_rows = [
        {"source_id": "S1", "ra": 359.8, "dec": 0.1,
         "yso_pub": 1, "class_1": "YSO", "stype_ml": "YSO"},
        {"source_id": "S2", "ra": 2.0, "dec": 0.0,
         "yso_pub": None, "class_1": "STAR", "stype_ml": "YSO"},
    ]
    matched, summaries, report = recon.summarize_candidate_source_epochs(
        region, candidate_rows, rows
    )
    assert recon.great_circle_separation_deg(359.8, 0.1, 0.0, 0.0) < 1.0
    assert len(matched) == 2
    assert {row["planeid"] for row in matched} == {"P1", "P2"}
    assert len(summaries) == 1
    assert summaries[0]["source_id"] == "S1"
    assert summaries[0]["unique_level2_plane_count"] == 2
    assert summaries[0]["unique_observation_count"] == 2
    assert summaries[0]["bands"] == "SPHEREx-D1;SPHEREx-D2"
    assert report["candidate_source_ids_with_level2_footprint_match"] == 1
    assert report["candidate_source_ids_without_level2_footprint_match"] == 1


def test_region_predicate_uses_irsa_adql_catalogue_cone_syntax():
    region = {"ra_deg": 65.7, "dec_deg": 26.0, "radius_deg": 2.0}
    predicate = recon.region_predicate(region)
    assert predicate == "CONTAINS(POINT(ra, dec), CIRCLE(65.70000000, 26.00000000, 2.00000)) = 1"


def test_yso_like_detection_preserves_literature_and_both_class_sources():
    assert recon._is_yso_like({"yso_pub": 17, "class_1": None, "stype_ml": None})
    assert recon._is_yso_like({"yso_pub": None, "class_1": "YSO", "stype_ml": None})
    assert recon._is_yso_like({"yso_pub": None, "class_1": "STAR", "stype_ml": "YSO"})
    assert not recon._is_yso_like({"yso_pub": None, "class_1": "STAR", "stype_ml": "STAR"})


def test_local_catalogue_summary_reports_exact_counts_when_below_cap(monkeypatch):
    rows = [
        {"source_id": 1, "designation": "T1", "ra": 65.8, "dec": 26.1,
         "class_1": "YSO", "yso_pub": 10, "stype_ml": "YSO"},
        {"source_id": 2, "designation": "T2", "ra": 65.9, "dec": 26.2,
         "class_1": "STAR", "yso_pub": None, "stype_ml": "YSO"},
        {"source_id": 3, "designation": "T3", "ra": 66.0, "dec": 26.3,
         "class_1": "STAR", "yso_pub": None, "stype_ml": "STAR"},
    ]
    def fake_query(sql):
        if "spherex.splices" in sql and "stype_ml" in sql:
            if sql.startswith("SELECT TOP 5000 "):
                return {"query": sql, "row_count": 2, "rows": rows[:2]}
            return {"query": sql, "row_count": len(rows), "rows": rows}
        return {
            "query": sql,
            "row_count": 2,
            "rows": [
                {"planeid": "a", "uri": "a.fits", "energy_bandpassname": "SPHEREx-D2",
                 "time_bounds_lower": 1, "time_bounds_upper": 2},
                {"planeid": "b", "uri": "b.fits", "energy_bandpassname": "SPHEREx-D2",
                 "time_bounds_lower": 3, "time_bounds_upper": 4},
            ],
        }
    monkeypatch.setattr(recon, "query_rows", fake_query)
    product = {
        "obs_id": "obs-a", "obs_publisher_did": "ivo:product-a",
        "access_url": "https://irsa.example/dr1/level2/a.fits",
        "s_region": "POLYGON ICRS 64.0 25.0 67.0 25.0 67.0 28.0 64.0 28.0 64.0 25.0",
        "energy_bandpassname": "SPHEREx-D2", "t_min": 60000.0, "t_max": 60000.1,
        "calib_level": "2", "dataproduct_type": "image",
        "dataproduct_subtype": "science", "algorithm_name": "exposure",
        "_chronos_collection": "spherex_dr1", "_chronos_release": "dr1",
    }
    def fake_sia(region, collection):
        products = [product] if collection == "spherex_dr1" else []
        return {
            "service": "IRSA SIAv2", "collection": collection,
            "release": recon.SIA_COLLECTION_RELEASE[collection],
            "maxrec": recon.COVERAGE_ROW_LIMIT, "row_count": len(products),
            "columns": list(product) if products else [],
            "rows": products, "query_complete_below_row_cap": True,
        }
    monkeypatch.setattr(recon, "query_region_footprints_sia", fake_sia)
    result = recon.inspect_region(recon.REGIONS[0])
    assert result["query_errors"] == {}
    assert result["counts"]["total_catalogue_rows"] == 3
    assert result["counts"]["published_yso_label_rows"] == 1
    assert result["counts"]["class_1_yso_rows"] == 1
    assert result["counts"]["ml_yso_rows"] == 2
    assert result["counts"]["catalogue_query_complete"] is True
    assert result["counts"]["dr1_level2_exposure_rows_by_band"]["SPHEREx-D2"]["exposure_rows"] == 2
    assert result["counts"]["candidate_source_exposure_query_complete"] is True
    assert result["counts"]["candidate_source_exposure_match_rows"] == 2
    assert result["counts"]["candidate_source_archive_product_pair_match_count"] == 2
    assert result["queries"]["candidate_source_product_matches"]["row_count"] == 2
    assert result["counts"]["candidate_unique_source_ids_with_level2_footprint_match"] == 2
    assert len(result["queries"]["candidate_source_epoch_summary"]["rows"]) == 2
    assert len(result["queries"]["class_distribution"]["rows"]) == 3


def test_catalogue_at_query_cap_is_reported_as_lower_bound(monkeypatch):
    monkeypatch.setattr(recon, "CATALOGUE_ROW_LIMIT", 2)
    def fake_query(sql):
        if "spherex.splices" in sql:
            rows = [{"source_id": 1, "class_1": "YSO", "yso_pub": None, "stype_ml": None}] * 2
            return {"query": sql, "row_count": len(rows), "rows": rows}
        return {"query": sql, "row_count": 0, "rows": []}
    monkeypatch.setattr(recon, "query_rows", fake_query)
    monkeypatch.setattr(recon, "query_region_footprints_sia", lambda region, collection: {
        "service": "IRSA SIAv2", "collection": collection,
        "release": recon.SIA_COLLECTION_RELEASE[collection],
        "maxrec": recon.COVERAGE_ROW_LIMIT, "row_count": 0,
        "columns": [], "rows": [], "query_complete_below_row_cap": True,
    })
    result = recon.inspect_region(recon.REGIONS[0])
    assert result["counts"]["catalogue_query_complete"] is False
    assert result["counts"]["total_catalogue_rows"] is None
    assert result["counts"]["class_1_yso_rows"] == 2
    assert result["counts"]["label_counts_are_lower_bounds"] is True


def test_query_failures_are_explicit_not_zero_detections(monkeypatch):
    def fail_query(sql):
        raise RuntimeError("test TAP failure")
    monkeypatch.setattr(recon, "query_rows", fail_query)
    monkeypatch.setattr(recon, "query_region_footprints_sia", lambda region, collection: (_ for _ in ()).throw(RuntimeError("test SIA failure")))
    result = recon.inspect_region(recon.REGIONS[0])
    assert set(result["query_errors"]) == {
        "catalogue_sources", "candidate_sources", "dr1_level2_exposures"
    }
    assert result["optional_query_errors"] == {}
    assert set(result["optional_sia_errors"]) == set(recon.SIA_COLLECTIONS)
    assert result["counts"]["dr1_level2_exposures_intersecting_full_region_total"] is None
    assert result["counts"]["candidate_source_exposure_match_rows"] is None
    assert result["counts"]["candidate_source_exposure_query_status"] == "unavailable"
    assert result["counts"]["candidate_source_footprint_matches_measured"] is False
    assert result["counts"]["dr1_level2_full_region_optional_query_error"] is not None
    assert result["counts"]["region_footprint_sia_collection_count_failed"] == len(recon.SIA_COLLECTIONS)
    assert result["counts"]["total_catalogue_rows"] is None
    assert result["counts"]["published_yso_label_rows"] is None




def test_spherical_s_region_point_in_polygon_handles_ra_wrap():
    polygon = recon.parse_sia_s_region_polygon(
        "POLYGON ICRS 359.5 -0.5 0.5 -0.5 0.5 0.5 359.5 0.5 359.5 -0.5"
    )
    assert polygon is not None
    assert recon.spherical_point_in_polygon(359.8, 0.1, polygon)
    assert recon.spherical_point_in_polygon(0.5, 0.0, polygon)
    assert not recon.spherical_point_in_polygon(2.0, 0.0, polygon)


def test_sia_source_match_fails_closed_when_product_polygon_is_missing():
    region = {"name": "Test_Field", "ra_deg": 65.7, "dec_deg": 26.0,
              "radius_deg": 2.0, "role": "control"}
    candidates = [{"source_id": "S1", "ra": 65.8, "dec": 26.1}]
    product = {"obs_id": "OBS-1", "obs_publisher_did": "ivo:product-1",
               "access_url": "https://irsa.example/dr1/level2/a.fits", "s_region": None}
    collections = {
        name: {"error": None, "query_complete_below_row_cap": True}
        for name in recon.SIA_COLLECTIONS
    }
    matched, summaries, product_matches, report = recon.match_candidates_to_sia_footprints(
        region, candidates, [product], candidate_query_complete=True,
        collection_results=collections,
    )
    assert matched == []
    assert product_matches == []
    assert len(summaries) == 1
    assert report["products_with_invalid_or_unsupported_s_region"] == 1
    assert report["source_footprint_matching_complete"] is False
    assert report["candidate_sources_without_archive_footprint_match"] is None
    assert report["status"] == "observed_lower_bound"


def test_query_hash_is_deterministic_for_equivalent_mappings():
    assert recon.digest_json({"a": "query A", "b": "query B"}) == recon.digest_json(
        {"b": "query B", "a": "query A"}
    )

def test_label_concordance_keeps_ml_only_candidates_separate_from_published_labels():
    rows = [
        {"source_id": 1, "designation": "A", "yso_pub": 12, "class_1": "YSO", "stype_ml": "YSO"},
        {"source_id": 2, "designation": "B", "yso_pub": None, "class_1": "STAR", "stype_ml": "YSO",
         "stype_ml_prob1": 0.91},
        {"source_id": 3, "designation": "C", "yso_pub": 8, "class_1": "YSO", "stype_ml": "STAR"},
    ]
    profiles = [recon.label_profile(row) for row in rows]
    assert profiles[0]["label_profile"] == "published_harmonised_ml_agree"
    assert profiles[0]["independent_label_source_count"] == 3
    assert profiles[1]["label_profile"] == "ml_only"
    assert profiles[1]["machine_only_candidate"] is True
    assert profiles[1]["interpretation"] == "ML-only candidate for independent review"
    assert profiles[2]["label_profile"] == "non_ml_label_without_ml_yso"
    summary = recon.summarise_label_concordance(rows)
    assert summary["all_three_label_sources_agree_count"] == 1
    assert summary["ml_only_label_count"] == 1
    assert summary["published_yso_pub_count"] == 2
    assert summary["machine_stype_ml_yso_count"] == 2
    assert summary["non_ml_label_without_ml_yso_count"] == 1
    assert "not independent validation" in summary["interpretation"]

