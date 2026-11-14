import numpy as np
import pytest

from chronos_addons.spectral import Spectrum,AllSkyCube,compare_spectra,extract_cube_spectrum
from chronos_addons.forensics import diagnose_candidate,template_overlap_score,calibration_ablation
from chronos_addons.planner import expected_information_gain,plan_observations
from chronos_addons.passport import create_passport,verify_passport
from chronos_addons.validation import score_recovery,split_fields,probability_metrics


def test_spectrum_sorts_all_arrays_together():
    s=Spectrum([2.,1.],[20.,10.],sigma=[2.,1.],valid=[True,False]).normalized()
    assert s.wavelength_um.tolist()==[1.,2.]
    assert s.flux.tolist()==[10.,20.]
    assert s.sigma.tolist()==[1.,2.]
    assert s.valid.tolist()==[False,True]


def test_spectral_compare_reports_significance_only_with_sigmas():
    a=Spectrum([1,2,3],[1,2,3],[.1,.1,.1]);b=Spectrum([1,2,3],[1,2.2,3],[.1,.1,.1])
    result=compare_spectra(a,b,min_overlap=3)
    assert result["significance_available"] and result["n_valid"]==3
    no=compare_spectra(Spectrum([1,2,3],[1,2,3]),Spectrum([1,2,3],[1,2.2,3]),min_overlap=3)
    assert not no["significance_available"] and no["mean_squared_significance"] is None


def test_spectral_compare_does_not_invent_overlapping_samples():
    with pytest.raises(ValueError): compare_spectra(Spectrum([1,2,3],[1,2,3]),Spectrum([1,2,3],[2,3,4]),min_overlap=5)


def test_cube_extraction_does_not_treat_nhits_as_variance():
    im=np.arange(3*3*3,dtype=float).reshape(3,3,3); hits=np.ones_like(im,int)*4;flags=np.zeros_like(im,int)
    cube=AllSkyCube(im,hits,flags,np.array([1.,2.,3.]),np.array([True,False,True]),[1],{},"fixture.fits")
    s=extract_cube_spectrum(cube,1,1,radius=1)
    assert s.sigma is None and s.valid.tolist()==[True,False,True] and s.hits.tolist()==[36.,0.,36.]


def test_forensic_triage_is_not_probability():
    r=diagnose_candidate({"candidate_id":"C1","candidate_snr":7,"flagged_fraction":.6,"release_mismatch":True})
    assert r["status"]=="instrumental-review-priority" and "probability" not in r


def test_template_overlap():
    assert template_overlap_score(np.array([[1,1],[0,0.]]),np.array([[True,False],[False,False]]))==pytest.approx(.5)


def test_calibration_ablation_matches_positions_one_to_one():
    r=calibration_ablation([[1,1],[5,5]],{"without_x":[[1.2,1.1]]},1.)
    assert r["variants"][0]["matched_to_baseline"]==1


def test_planner_prefers_discriminating_forecast():
    low={"moving":{"mean":0,"sigma":.2},"variable":{"mean":.1,"sigma":.2}}
    high={"moving":{"mean":-2,"sigma":.2},"variable":{"mean":2,"sigma":.2}}
    assert expected_information_gain(high,measurement_sigma=.1)["expected_information_gain_bits"]>expected_information_gain(low,measurement_sigma=.1)["expected_information_gain_bits"]
    p=plan_observations([{"time":"t1","predictions":low},{"time":"t2","predictions":high}],measurement_sigma=.1)
    assert p["recommended"]["time"]=="t2"


def test_passport_detects_modified_content():
    p=create_passport(project="CHRONOS",candidate_id="C1",creator="Analyst",inputs={},measurements={},methods={},software={})
    assert verify_passport(p)["valid"]
    p["measurements"]["flux"]=123
    assert not verify_passport(p)["valid"]


def test_recovery_metrics():
    r=score_recovery([[0,0],[10,10]],[[.5,.4],[50,50]],match_radius=2)
    assert (r["true_positive"],r["false_positive"],r["false_negative"])==(1,1,1)
    assert r["precision"]==.5 and r["recall_completeness"]==.5


def test_field_split_has_no_overlap():
    r=split_fields(["a","a","b","c","d","e"],seed=4)
    assert set(r["train_fields"]).isdisjoint(r["test_fields"])
    assert set(r["train_fields"]+r["test_fields"])==set("abcde")


def test_probability_metrics_reports_abstention_coverage():
    r=probability_metrics(["moving","variable"],[{"moving":.8,"variable":.2},None],["moving","variable"])
    assert r["n_covered"]==1 and r["coverage"]==.5 and r["brier_score"] is not None


def test_spectral_bridge_requires_cwave_cband_and_preserves_missing_channels():
    from chronos_addons.bridge import sample_cwave,measure_candidate_exposures,assemble_channel_epochs
    class E: id="OBS_D2";frame="f1";mjd=60000.;det=2;rel="DR1"
    e=E()
    sampled=sample_cwave(np.ones((5,5))*2,np.ones((5,5))*.1,1,1)
    assert sampled["source"]=="CWAVE/CBAND"
    with pytest.raises(ValueError):measure_candidate_exposures([e],{e.id:{"wavelength_um":2,"bandwidth_um":.1,"source":"WCS-WAVE","calibration_group":"g"}},photometry_fn=lambda _: (1,.1,0))
    rows=measure_candidate_exposures([e],{e.id:{"wavelength_um":2,"bandwidth_um":.1,"source":"CWAVE/CBAND","calibration_group":"DR1-v1"}},photometry_fn=lambda _:(4,.2,0))
    s=assemble_channel_epochs(rows,[1.9,2.,2.1])
    assert s[0]["valid"]==[False,True,False] and s[0]["flux"][1]==pytest.approx(4.)


def test_equivalent_width_measures_absorption_but_not_species():
    from chronos_addons.molecular import measure_equivalent_width
    wave=np.linspace(1.,2.,101);flux=np.ones_like(wave)*5;flux-=np.exp(-.5*((wave-1.5)/.05)**2)
    r=measure_equivalent_width(Spectrum(wave,flux,np.ones_like(wave)*.05),[1.38,1.62],[[1.05,1.25],[1.75,1.95]])
    assert r["equivalent_width_um"]>0 and r["equivalent_width_sigma_um"] is not None
    assert any("no molecule is identified" in x for x in r["limitations"])


def test_catalogue_crossmatch_handles_ra_wraparound():
    from chronos_addons.catalogs import crossmatch_catalog
    r=crossmatch_catalog([{"candidate_id":"C1","ra":359.9999,"dec":0}], [{"id":"S1","ra":.0001,"dec":0}],radius_arcsec=2)
    assert r["match_count"]==1 and r["matches"][0]["separation_arcsec"]<1


def test_orbit_sandbox_returns_approximate_track():
    from chronos_addons.orbits import apparent_track
    el={"a_au":50.,"eccentricity":.1,"inclination_deg":10.,"ascending_node_deg":80.,"argument_perihelion_deg":30.,"mean_anomaly_deg":20.,"epoch_mjd":60000.}
    r=apparent_track([60000,60100],el)
    assert len(r)==2 and 0<=r[0]["ra_deg"]<360 and -90<=r[0]["dec_deg"]<=90
    assert "not a validated ephemeris" in r[0]["model"]


def test_selection_correction_skips_low_completeness():
    from chronos_addons.selection import selection_corrected_counts
    r=selection_corrected_counts([{"tile_id":"A","raw_sky_candidates":10,"raw_null_candidates":2,"completeness":.5,"n_injected":100,"area_deg2":2},{"tile_id":"B","raw_sky_candidates":4,"raw_null_candidates":1,"completeness":.01,"n_injected":100,"area_deg2":2}])
    assert r["corrected_excess_total"]==pytest.approx(16) and r["skipped_tiles"][0]["tile_id"]=="B"


def test_citizen_aggregation_computes_fleiss_kappa():
    from chronos_addons.citizen import analyze_reviews
    rows=[];labels={"p1":["moving","variable"],"p2":["moving","variable"],"p3":["artifact","variable"]}
    for person,answers in labels.items():
        for case,answer in zip(["C1","C2"],answers):rows.append({"participant_id":person,"case_id":case,"label":answer,"confidence":.8})
    r=analyze_reviews(rows,{"C1":"moving","C2":"variable"})
    assert r["fleiss_kappa"] is not None and r["crowd_majority_accuracy_on_answer_key"]==1.


def test_api_router_imports_and_has_expected_routes():
    from chronos_addons.api import router
    assert len(router.routes)==14


def test_recovery_matching_maximizes_cardinality_before_distance():
    # Greedy nearest-first can consume the only match available to the second truth.
    r=score_recovery([[0,0],[1.5,0]],[[.7,0],[-.8,0]],match_radius=1.0)
    assert r["true_positive"]==2


def test_stratified_recovery_pools_fields_within_each_stratum():
    from chronos_addons.validation import stratified_recovery
    rows=[{"field_id":"F1","stratum":{"mag":"bright"},"truth_positions":[[0,0]],"detection_positions":[[.1,0]]},
          {"field_id":"F2","stratum":{"mag":"bright"},"truth_positions":[[0,0]],"detection_positions":[]},
          {"field_id":"F3","stratum":{"mag":"faint"},"truth_positions":[[0,0]],"detection_positions":[]}]
    r=stratified_recovery(rows)
    assert r["strata"]["mag=bright"]["fields"]==2
    assert r["strata"]["mag=bright"]["completeness"]==.5
