from research_discovery.spherex.yso_population_recon import (
    CANDIDATE_LIMIT,
    DR1_BANDS,
    REGIONS,
    build_region_queries,
    digest_json,
    region_predicate,
)


def test_predeclared_yso_regions_include_independent_control_region():
    assert len(REGIONS) >= 5
    assert any(region["role"] == "control" for region in REGIONS)
    assert all(region["radius_deg"] > 0 for region in REGIONS)


def test_published_yso_reference_and_ml_class_are_separate_queries():
    queries = build_region_queries(REGIONS[0])
    assert "yso_pub IS NOT NULL" in queries["published_yso_label"]
    assert "UPPER(class_1) LIKE '%YSO%'" in queries["class_1_yso"]
    assert "UPPER(stype_ml) LIKE '%YSO%'" in queries["ml_yso"]
    assert queries["published_yso_label"] != queries["ml_yso"]
    assert "GROUP BY class_1, yso_pub, stype_ml" in queries["class_distribution"]


def test_candidate_query_is_bounded_and_retains_both_human_and_ml_labels():
    query = build_region_queries(REGIONS[0])["candidate_sources"]
    assert f"TOP {CANDIDATE_LIMIT}" in query
    assert "class_1" in query
    assert "yso_pub" in query
    assert "stype_ml" in query
    assert "ORDER BY source_id" in query


def test_dr1_coverage_query_is_spatially_joined_and_detector_band_specific():
    query = build_region_queries(REGIONS[0])["dr1_level2_coverage_by_band"]
    assert "spherex.artifact" in query
    assert "spherex.plane" in query
    assert "p.poly" in query
    assert "CONTAINS" in query
    assert "POINT(65.70000000, 26.00000000)" in query
    assert query.index("CONTAINS(") < query.index(" = 1")
    assert "/dr1/level2/" in query
    for band in DR1_BANDS:
        assert f"'{band}'" in query


def test_region_predicate_uses_explicit_icrs_center_and_radius():
    region = {"ra_deg": 65.7, "dec_deg": 26.0, "radius_deg": 2.0}
    predicate = region_predicate(region)
    assert predicate == "CONTAINS(POINT(ra, dec), CIRCLE(65.70000000, 26.00000000, 2.00000)) = 1"


def test_query_hash_is_deterministic_for_equivalent_mappings():
    assert digest_json({"a": "query A", "b": "query B"}) == digest_json(
        {"b": "query B", "a": "query A"}
    )
