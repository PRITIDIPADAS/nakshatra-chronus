import pytest


def _fixture():
    prereg = "a" * 64
    event_definition = "b" * 64
    measurements = [
        {"measurement_id": "M-1", "observation_id": "OBS-1", "mjd": 60000.0, "wavelength_um": 3.05},
        {"measurement_id": "M-2", "observation_id": "OBS-2", "mjd": 60002.0, "wavelength_um": 3.05},
        {"measurement_id": "M-3", "observation_id": "OBS-3", "mjd": 60004.0, "wavelength_um": 3.05},
    ]
    fields = [
        {
            "field_id": "FIELD-1", "dataset_class": "real", "independent_field": True,
            "observed_events": 1, "null_events": 0,
            "area_deg2": 1.0, "baseline_days": 4.0,
            "null_control_area_deg2": 1.0, "null_control_baseline_days": 4.0,
            "null_control_to_science_exposure_ratio": 1.0, "null_control_id": "NULL-1",
        },
        {
            "field_id": "FIELD-2", "dataset_class": "real", "independent_field": True,
            "observed_events": 0, "null_events": 0,
            "area_deg2": 1.0, "baseline_days": 4.0,
            "null_control_area_deg2": 1.0, "null_control_baseline_days": 4.0,
            "null_control_to_science_exposure_ratio": 1.0, "null_control_id": "NULL-2",
        },
    ]
    coverage = {
        "thresholds": {"minimum_completeness": 0.5},
        "eligible_sources": [
            {
                "field_id": "FIELD-1", "source_id": "YSO-1",
                "selection_probability": 0.5, "selection_probability_95": [0.3, 0.7],
                "selection_weight": 2.0, "selection_cell_id": "CELL-1",
                "measurement_lineage": measurements,
            },
            {
                "field_id": "FIELD-1", "source_id": "YSO-ZERO",
                "selection_probability": 0.25, "selection_probability_95": [0.15, 0.35],
                "selection_weight": 4.0, "selection_cell_id": "CELL-2",
                "measurement_lineage": [
                    {"measurement_id": "M-Z1", "observation_id": "OBS-1", "mjd": 60000.0, "wavelength_um": 3.05},
                    {"measurement_id": "M-Z2", "observation_id": "OBS-2", "mjd": 60002.0, "wavelength_um": 3.05},
                ],
            },
        ],
        "selection_function": {
            "schema": "chronos-multidimensional-selection-function/1.0",
            "bin_spec_sha256": "c" * 64,
            "injection_trials_sha256": "d" * 64,
            "frozen_provenance": {"preregistration_sha256": prereg},
        },
    }
    trials = [{"event_definition_sha256": event_definition}]
    events = [{
        "event_id": "EV-1", "field_id": "FIELD-1", "source_id": "YSO-1",
        "status": "accepted", "preregistration_sha256": prereg,
        "event_definition_sha256": event_definition,
        "start_mjd": 60000.5, "end_mjd": 60003.5,
        "measurement_ids": ["M-1", "M-2", "M-3"],
    }]
    return fields, coverage, trials, events, prereg, event_definition


def _mock_revalidation(monkeypatch, coverage):
    import chronos_population.source_linked as source_linked
    monkeypatch.setattr(
        source_linked, "_revalidate_coverage",
        lambda *args, **kwargs: coverage,
    )


def test_source_linked_event_yield_applies_source_inverse_probability_weights(monkeypatch):
    from chronos_population.source_linked import estimate_source_linked_event_yield

    fields, coverage, trials, events, prereg, event_definition = _fixture()
    _mock_revalidation(monkeypatch, coverage)
    result = estimate_source_linked_event_yield(
        fields, coverage_audit=coverage,
        selection_trials=trials, selection_bin_spec={"frozen": True},
        source_event_records=events, preregistration_sha256=prereg,
        event_definition_sha256=event_definition, draws=2000, seed=7,
    )
    assert result["scientific_status"] == "source_selection_weighted_candidate_event_yield_not_population_result"
    assert result["accepted_event_count"] == 1
    assert result["total_source_selection_weighted_event_count"] == pytest.approx(2.0)
    assert result["field_reports"][0]["eligible_source_count"] == 2
    assert result["field_reports"][0]["source_count_with_events"] == 1
    assert result["field_reports"][0]["source_selection_weighted_events"] == pytest.approx(2.0)
    assert result["selection_function"]["selection_cell_count"] == 2
    assert "logit-normal approximation" in result["selection_function"]["uncertainty_propagation"]
    assert result["event_yield_per_sqdeg_day"]["median"] > 0
    assert any("Event-detection completeness is not corrected" in item for item in result["limits"])


def test_source_linked_event_yield_rejects_aggregate_counts_without_source_rows(monkeypatch):
    from chronos_population.source_linked import estimate_source_linked_event_yield

    fields, coverage, trials, events, prereg, event_definition = _fixture()
    _mock_revalidation(monkeypatch, coverage)
    with pytest.raises(ValueError, match="observed_events must equal"):
        estimate_source_linked_event_yield(
            fields, coverage_audit=coverage,
            selection_trials=trials, selection_bin_spec={"frozen": True},
            source_event_records=[], preregistration_sha256=prereg,
            event_definition_sha256=event_definition,
        )


def test_source_linked_event_yield_accepts_an_explicit_zero_event_result(monkeypatch):
    from chronos_population.source_linked import estimate_source_linked_event_yield

    fields, coverage, trials, events, prereg, event_definition = _fixture()
    fields[0]["observed_events"] = 0
    _mock_revalidation(monkeypatch, coverage)
    result = estimate_source_linked_event_yield(
        fields, coverage_audit=coverage,
        selection_trials=trials, selection_bin_spec={"frozen": True},
        source_event_records=[], preregistration_sha256=prereg,
        event_definition_sha256=event_definition, draws=2000, seed=11,
    )
    assert result["accepted_event_count"] == 0
    assert result["event_yield_per_sqdeg_day"]["median"] == 0.0


def test_source_linked_event_yield_rejects_event_rows_outside_source_measurement_lineage(monkeypatch):
    from chronos_population.source_linked import estimate_source_linked_event_yield

    fields, coverage, trials, events, prereg, event_definition = _fixture()
    _mock_revalidation(monkeypatch, coverage)
    events[0]["measurement_ids"] = ["M-1", "NOT-IN-SERIES"]
    with pytest.raises(ValueError, match="measurements absent from the verified source series"):
        estimate_source_linked_event_yield(
            fields, coverage_audit=coverage,
            selection_trials=trials, selection_bin_spec={"frozen": True},
            source_event_records=events, preregistration_sha256=prereg,
            event_definition_sha256=event_definition,
        )


def test_source_linked_event_yield_requires_frozen_preregistration_and_event_rule(monkeypatch):
    from chronos_population.source_linked import estimate_source_linked_event_yield

    fields, coverage, trials, events, prereg, event_definition = _fixture()
    _mock_revalidation(monkeypatch, coverage)
    events[0]["event_definition_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="event-definition digest mismatch"):
        estimate_source_linked_event_yield(
            fields, coverage_audit=coverage,
            selection_trials=trials, selection_bin_spec={"frozen": True},
            source_event_records=events, preregistration_sha256=prereg,
            event_definition_sha256=event_definition,
        )


def test_source_linked_event_yield_requires_distinct_epoch_measurements(monkeypatch):
    from chronos_population.source_linked import estimate_source_linked_event_yield

    fields, coverage, trials, events, prereg, event_definition = _fixture()
    _mock_revalidation(monkeypatch, coverage)
    events[0]["measurement_ids"] = ["M-1", "M-1"]
    with pytest.raises(ValueError, match="repeats a measurement_id"):
        estimate_source_linked_event_yield(
            fields, coverage_audit=coverage,
            selection_trials=trials, selection_bin_spec={"frozen": True},
            source_event_records=events, preregistration_sha256=prereg,
            event_definition_sha256=event_definition,
        )


def test_source_linked_yso_event_yield_api_route_is_registered():
    from chronos_causal.api import router

    paths = {route.path for route in router.routes}
    assert "/api/v5/population/yso/source-linked-event-yield" in paths



def test_source_linked_event_yield_requires_cell_level_selection_uncertainty(monkeypatch):
    from chronos_population.source_linked import estimate_source_linked_event_yield

    fields, coverage, trials, events, prereg, event_definition = _fixture()
    _mock_revalidation(monkeypatch, coverage)
    del coverage["eligible_sources"][0]["selection_probability_95"]
    with pytest.raises(ValueError, match="no 95% selection-probability interval"):
        estimate_source_linked_event_yield(
            fields, coverage_audit=coverage,
            selection_trials=trials, selection_bin_spec={"frozen": True},
            source_event_records=events, preregistration_sha256=prereg,
            event_definition_sha256=event_definition,
        )


def test_source_linked_event_yield_rejects_inconsistent_summaries_within_one_selection_cell(monkeypatch):
    from chronos_population.source_linked import estimate_source_linked_event_yield

    fields, coverage, trials, events, prereg, event_definition = _fixture()
    coverage["eligible_sources"][1]["selection_cell_id"] = "CELL-1"
    _mock_revalidation(monkeypatch, coverage)
    with pytest.raises(ValueError, match="inconsistent probability summaries"):
        estimate_source_linked_event_yield(
            fields, coverage_audit=coverage,
            selection_trials=trials, selection_bin_spec={"frozen": True},
            source_event_records=events, preregistration_sha256=prereg,
            event_definition_sha256=event_definition,
        )
