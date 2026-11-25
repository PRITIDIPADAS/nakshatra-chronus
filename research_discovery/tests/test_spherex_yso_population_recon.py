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


def test_dr1_exposure_coverage_uses_irsa_spherex_polygon_pattern():
    query = recon.build_region_queries(recon.REGIONS[0])["dr1_level2_exposures"]
    assert "spherex.artifact" in query
    assert "spherex.plane" in query
    assert "p.poly" in query
    assert "1 = CONTAINS(POINT('ICRS', 65.70000000, 26.00000000), p.poly)" in query
    assert "AND (LOWER(a.uri) LIKE" in query
    assert "COUNT(" not in query.upper()
    assert "GROUP BY" not in query.upper()
    for band in recon.DR1_BANDS:
        assert f"'{band}'" in query


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
        if "spherex.splices" in sql and "stype_ml" in sql:
            if "SELECT TOP 5000" in sql:
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
    assert result["counts"]["total_catalogue_rows"] is None
    assert result["counts"]["published_yso_label_rows"] is None


def test_query_hash_is_deterministic_for_equivalent_mappings():
    assert recon.digest_json({"a": "query A", "b": "query B"}) == recon.digest_json(
        {"b": "query B", "a": "query A"}
    )
