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


def test_dr1_exposure_coverage_uses_centre_point_and_optional_full_region_intersection():
    queries = recon.build_region_queries(recon.REGIONS[0])
    query = queries["dr1_level2_exposures"]
    assert "spherex.artifact" in query
    assert "spherex.plane" in query
    assert "p.poly" in query
    assert "1 = CONTAINS(POINT('ICRS', 65.70000000, 26.00000000), p.poly)" in query
    assert "AND (LOWER(a.uri) LIKE" in query
    assert "COUNT(" not in query.upper()
    assert "GROUP BY" not in query.upper()

    full_region = queries["dr1_level2_exposures_full_region"]
    assert "spherex.artifact" in full_region
    assert "spherex.plane" in full_region
    assert "1 = INTERSECTS(CIRCLE('ICRS', 65.70000000, 26.00000000, 2.00000), p.poly)" in full_region
    assert "AND (LOWER(a.uri) LIKE" in full_region
    for band in recon.DR1_BANDS:
        assert f"'{band}'" in query
        assert f"'{band}'" in full_region

    source_epoch = queries["candidate_source_exposure_matches"]
    assert f"SELECT TOP {recon.SOURCE_EPOCH_ROW_LIMIT}" in source_epoch
    assert "FROM spherex.splices s " in source_epoch
    assert "JOIN spherex.plane p ON CONTAINS(POINT('ICRS', s.ra, s.dec), p.poly) = 1" in source_epoch
    assert "JOIN spherex.artifact a ON a.planeid = p.planeid" in source_epoch
    assert "CONTAINS(POINT('ICRS', s.ra, s.dec), p.poly) = 1" in source_epoch
    assert "s.yso_pub IS NOT NULL" in source_epoch
    assert "LOWER(a.uri) LIKE '%/dr1/level2/%'" in source_epoch
    assert "p.time_bounds_lower" in source_epoch
    assert "CIRCLE(" not in source_epoch  # Exact cone filtering is performed locally.



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
        {"source_id": 1, "class_1": "YSO", "yso_pub": 10, "stype_ml": "YSO"},
        {"source_id": 2, "class_1": "STAR", "yso_pub": None, "stype_ml": "YSO"},
        {"source_id": 3, "class_1": "STAR", "yso_pub": None, "stype_ml": "STAR"},
    ]
    def fake_query(sql):
        if sql.startswith(f"SELECT TOP {recon.SOURCE_EPOCH_ROW_LIMIT} "):
            return {
                "query": sql,
                "row_count": 2,
                "rows": [
                    {
                        "source_id": 1, "designation": "T1", "ra": 65.8, "dec": 26.1,
                        "yso_pub": 10, "class_1": "YSO", "stype_ml": "YSO",
                        "planeid": "plane-a", "obsid": "obs-a", "uri": "a.fits",
                        "energy_bandpassname": "SPHEREx-D2",
                        "time_bounds_lower": 60000.0, "time_bounds_upper": 60000.1,
                    },
                    {
                        "source_id": 2, "designation": "T2", "ra": 65.9, "dec": 26.2,
                        "yso_pub": None, "class_1": "STAR", "stype_ml": "YSO",
                        "planeid": "plane-b", "obsid": "obs-b", "uri": "b.fits",
                        "energy_bandpassname": "SPHEREx-D1",
                        "time_bounds_lower": 60001.0, "time_bounds_upper": 60001.1,
                    },
                ],
            }
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
    result = recon.inspect_region(recon.REGIONS[0])
    assert result["counts"]["catalogue_query_complete"] is False
    assert result["counts"]["total_catalogue_rows"] is None
    assert result["counts"]["class_1_yso_rows"] == 2
    assert result["counts"]["label_counts_are_lower_bounds"] is True


def test_query_failures_are_explicit_not_zero_detections(monkeypatch):
    def fail_query(sql):
        raise RuntimeError("test TAP failure")
    monkeypatch.setattr(recon, "query_rows", fail_query)
    result = recon.inspect_region(recon.REGIONS[0])
    assert set(result["query_errors"]) == {
        "catalogue_sources", "candidate_sources", "dr1_level2_exposures"
    }
    assert set(result["optional_query_errors"]) == {
        "dr1_level2_exposures_full_region", "candidate_source_exposure_matches"
    }
    assert result["counts"]["dr1_level2_exposures_intersecting_full_region_total"] is None
    assert result["counts"]["candidate_source_exposure_match_rows"] is None
    assert result["counts"]["candidate_source_footprint_matches_measured"] is False
    assert result["counts"]["dr1_level2_full_region_optional_query_error"]
    assert result["counts"]["total_catalogue_rows"] is None
    assert result["counts"]["published_yso_label_rows"] is None


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

