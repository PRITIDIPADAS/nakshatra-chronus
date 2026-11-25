import json
import numpy as np
import pytest


def _row(mjd,wave,index,valid=True,group="SYNTHETIC:TEST"):
    return {"source_id":"S1","observation_id":f"OBS-{index}","source_index":index,
        "mjd":mjd,"wavelength_um":wave,"flux":10+(mjd-60000)*.2+(wave-1),
        "sigma":.1,"flux_unit":"Jy","calibration_group":group,
        "wavelength_unit":"um","wavelength_validated":True,
        "wavelength_source":"synthetic_fixture","synthetic_fixture":True,
        "dataset_class":"synthetic","valid":valid,"invalid_reason":None if valid else "masked"}


def test_session12_reconstruction_has_null_gaps_covariance_and_row_provenance():
    from chronos_spectrotemporal.reconstruction import reconstruct
    rows=[_row(t,w,i) for i,(t,w) in enumerate([(60000,1.0),(60000,1.1),(60001,1.0),(60001,1.1)])]
    rows += [_row(60000.5,1.05,4,False),_row(60000.5,1.05,5,True,"SYNTHETIC:OTHER")]
    cov=np.eye(6)*.01+(np.ones((6,6))-np.eye(6))*.001
    result=reconstruct(rows,[.9,1.,1.1,1.2],[59999,60000,60001,60002],
        wavelength_bandwidth_um=.2,time_bandwidth_days=2,
        calibration_group="SYNTHETIC:TEST",measurement_covariance=cov.tolist(),
        shared_calibration_fractional_sigma=.03,include_grid_covariance=True,min_neighbors=2)
    assert result["data_class"]=="synthetic"
    assert result["flux"][0][0] is None
    assert result["cell_class"][0][0]=="unsupported"
    assert result["cell_class"][1][1]=="measured"
    assert result["measurement_provenance"][0]["observation_id"]=="OBS-0"
    assert {x["status"] for x in result["excluded_rows"]}=={"invalid_or_missing","excluded_calibration_group"}
    assert result["sigma_shared_calibration"][1][1]>0
    assert result["grid_covariance"]["matrix"]
    json.dumps(result,allow_nan=False)


def test_session12_does_not_implicitly_mix_calibration_groups():
    from chronos_spectrotemporal.reconstruction import reconstruct
    rows=[_row(t,w,i) for i,(t,w) in enumerate([(60000,1.0),(60000,1.1),(60001,1.0),(60001,1.1)])]
    rows.append(_row(60000,1.0,4,True,"SYNTHETIC:OTHER"))
    with pytest.raises(ValueError):
        reconstruct(rows,[1.0,1.1],[60000,60001],wavelength_bandwidth_um=.2,time_bandwidth_days=2)


def test_session13_feature_measurement_reports_depth_continuum_and_resolution():
    from chronos_addons.molecular import measure_equivalent_width
    from chronos_addons.spectral import Spectrum
    wave=np.linspace(1.0,1.3,31);flux=np.ones_like(wave)
    flux[(wave>=1.11)&(wave<=1.19)]-=.12
    result=measure_equivalent_width(
        Spectrum(wavelength_um=wave,flux=flux,sigma=np.full_like(wave,.02)),
        [1.1,1.2],[[1.0,1.05],[1.25,1.3]],
        resolution={"lsf_fwhm_um":.02,"source_uri":"https://instrument.example/lsf","sha256":"a"*64},
        potential_blend_intervals_um=[[1.205,1.22]],continuum_model="constant")
    assert result["feature_depth"]>0
    assert result["feature_depth_sigma"] is not None
    assert result["continuum_model"]["type"]=="weighted_constant"
    assert result["resolution_diagnostics"]["lsf_fwhm_um"]==pytest.approx(.02)
    assert result["blend_diagnostics"]
    assert any("no molecule is identified" in x for x in result["limitations"])


def test_session15_planner_needs_structured_external_feasibility_record():
    from chronos_addons.planner import plan_candidate_observations
    pred={"sky":{"mean":1.,"sigma":.1},"detector":{"mean":3.,"sigma":.1}}
    provenance={k:{"fit_id":"FIT-"+k,"input_observation_ids":["OBS-1"]} for k in pred}
    base={"candidate_observation_id":"C1","predictions":pred,"forecast_provenance":provenance}
    unknown=plan_candidate_observations([{**base,"feasibility":{"status":"unknown"}}])
    assert unknown["recommended"] is None
    verified={**base,"time":"2026-11-25T14:00:00Z","feasibility":{"status":"verified","feasible":True,
        "source_uri":"https://visibility.example/query/1","checked_utc":"2026-11-25T12:00:00Z",
        "window_start_utc":"2026-11-25T13:00:00Z","window_end_utc":"2026-11-25T15:00:00Z",
        "calculator":"test","query_id":"Q1","evidence_sha256":"d"*64,
        "query_parameters":{"target":"test","band":"IR"}}}
    result=plan_candidate_observations([verified])
    assert result["recommended"]["candidate_observation_id"]=="C1"


def test_session19_synthetic_fields_fail_real_population_coverage_gate():
    from chronos_population.coverage import assess_population_coverage
    result=assess_population_coverage([{"field_id":"SYNTH-FIELD","dataset_class":"synthetic",
        "independent_field":True,"n_injected":100,"n_recovered":90,
        "null_control_id":"SYNTH-NULL","sources":[]}],
        feature_interval_um=[3.05,3.15],blue_continuum_um=[2.8,2.95],
        red_continuum_um=[3.25,3.4])
    assert result["eligible_for_predeclared_population_protocol"] is False
    assert result["failure_counts"]["field_not_labelled_real"]==1


def test_session12_to_20_api_routes_exist():
    from chronos_causal.api import router
    paths={route.path for route in router.routes}
    for path in ["/api/v5/spectrotemporal/reconstruct","/api/v5/spectrotemporal/feature-evolution",
        "/api/v5/observations/plan-candidate","/api/v5/population/yso/rate",
        "/api/v5/workspace/candidates","/api/v5/workspace/compare",
        "/api/v5/evidence/graph","/api/v5/evidence/package/export"]:
        assert path in paths


def test_session17_site_has_four_workspaces_and_interactive_research_views():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/"site/causal-lab.html").read_text(encoding="utf-8")
    js=(root/"site/causal-lab.js").read_text(encoding="utf-8")
    for panel in ("experiment","spectrum","identity","detector","candidate-library","population"):
        assert f'id="{panel}"' in html
    for name in ("searchCandidates","compareCandidates","shareShortlist","renderEvidenceGraph","inspectSpectralCell"):
        assert name in js
