from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from research_discovery.spherex.reproject_detector_template import (
    detector_origin_offset, sample_detector_template, validate_template_coordinate_frame,
)
from research_discovery.spherex.extract_epsf_stamp import detector_position_from_cutout, select_epsf_row
from research_discovery.validation.injection_recovery import matched_filter_snr, detect_peaks, run_injection_recovery, wilson_interval
from research_discovery.planet9.ensemble_ephemeris import resolve_columns, propagate_heliocentric_ecliptic
from research_discovery.planet9.compare_horizons import angular_separation_arcsec
import research_discovery.spherex.discover_calibrations as calibration_discovery
from research_discovery.spherex.flag_policy import FLAG_BITS, policy_mask
from research_discovery.citizen_science.build_task_manifest import build_tasks


def test_detector_cutout_origin_documented_convention():
    assert detector_origin_offset({"CRPIX1A": 501.0, "CRPIX2A": 701.0}) == (-500.0, -700.0)
    assert detector_origin_offset({"NAXIS1": 2040, "NAXIS2": 2040}) == (0.0, 0.0)
    # Full native frames stay unshifted even if the headers carry cutout-related WCS keys.
    assert detector_origin_offset({"NAXIS1": 2040, "NAXIS2": 2040, "CRPIX1A": 501, "CRPIX2A": 701}) == (0.0, 0.0)
    with pytest.raises(ValueError):
        detector_origin_offset({"NAXIS1": 128, "NAXIS2": 128})


def test_template_interpolation_and_detector_native_bounds():
    yy, xx = np.mgrid[0:8, 0:8]
    arr = xx + 10 * yy
    x = np.array([[2.0, 3.5, -1.0]])
    y = np.array([[1.0, 2.5, 2.0]])
    out = sample_detector_template(arr, x, y)
    assert out[0, 0] == pytest.approx(12.0)
    assert out[0, 1] == pytest.approx(28.5)
    assert np.isnan(out[0, 2])


def test_wilson_interval_edge_cases():
    lo, hi = wilson_interval(0, 10)
    assert lo == 0 and hi > 0
    lo, hi = wilson_interval(10, 10)
    assert hi == pytest.approx(1.0) and lo < 1
    with pytest.raises(ValueError): wilson_interval(0, 0)


def test_epsf_detector_coordinate_and_zone_selection():
    assert detector_position_from_cutout(2.0, 3.0, {"NAXIS1": 2040, "NAXIS2": 2040, "CRPIX1A": 900, "CRPIX2A": 900}) == (2.0, 3.0)
    assert detector_position_from_cutout(2.0, 3.0, {"NAXIS1": 10, "NAXIS2": 10, "CRPIX1A": 501, "CRPIX2A": 701}) == (-498.0, -697.0)
    class FakeTable:
        colnames = ["XCENTER", "YCENTER", "BINX", "BINY", "EPSF", "CWAVE"]
        data = {"XCENTER": np.array([10., 100., 50.]), "YCENTER": np.array([10., 100., 50.]),
                "BINX": np.array([0, 1, 2]), "BINY": np.array([0, 1, 2]),
                "EPSF": np.zeros((3, 33, 33)), "CWAVE": np.array([1.1, 2.2, 3.3])}
        def __getitem__(self, key): return self.data[key]
    row, meta = select_epsf_row(FakeTable(), 52, 48)
    assert row == 2 and meta["binx"] == 2 and meta["cwave_um"] == pytest.approx(3.3)


def test_matched_filter_detects_injected_stamp():
    rng = np.random.default_rng(4)
    image = rng.normal(0, 1, (64, 64))
    variance = np.ones_like(image)
    y, x = np.mgrid[-2:3, -2:3]
    psf = np.exp(-(x*x+y*y)/2)
    psf /= psf.sum()
    image[30-2:30+3, 25-2:25+3] += 30*psf
    snr = matched_filter_snr(image, variance, psf)
    peaks = detect_peaks(snr, threshold=5)
    assert len(peaks) >= 1
    best = peaks[np.argmax(peaks[:, 2])]
    assert best[0] == pytest.approx(25, abs=1)
    assert best[1] == pytest.approx(30, abs=1)


def test_injection_recovery_real_array_contract_and_metrics():
    rng = np.random.default_rng(11)
    image = rng.normal(0, 1, (128, 128))
    variance = np.ones_like(image)
    flags = np.zeros_like(image, dtype=np.uint16)
    y, x = np.mgrid[-2:3, -2:3]
    psf = np.exp(-(x*x+y*y)/2); psf /= psf.sum()
    result = run_injection_recovery(image, variance, flags, psf,
        flux_levels=[25.0], n_per_level=4, snr_threshold=5.0, seed=8)
    assert result["flux_summary"][0]["n_injected"] == 4
    assert 0 <= result["flux_summary"][0]["completeness"] <= 1
    assert "all-sky performance" in result["interpretation"]
    assert result["flux_summary"][0]["completeness_wilson95_low"] <= result["flux_summary"][0]["completeness"]
    assert result["flux_summary"][0]["completeness_wilson95_high"] >= result["flux_summary"][0]["completeness"]



def test_injection_recovery_subtracts_aligned_background_model():
    rng = np.random.default_rng(91)
    background = np.full((80, 80), 12.0)
    image = background + rng.normal(0, 1, background.shape)
    variance = np.ones_like(image)
    flags = np.zeros_like(image, dtype=np.uint16)
    psf = np.ones((3, 3), dtype=float)
    result = run_injection_recovery(image, variance, flags, psf, flux_levels=[10.0],
        n_per_level=1, snr_threshold=5.0, seed=3, background=background)
    assert result["background_model_subtracted"] is True


def test_injection_recovery_fails_closed_on_too_small_image():
    image = np.zeros((12, 12), dtype=float)
    variance = np.ones_like(image)
    flags = np.zeros_like(image, dtype=np.uint16)
    with pytest.raises(ValueError, match="too small"):
        run_injection_recovery(image, variance, flags, np.ones((3, 3)),
            flux_levels=[1.0], n_per_level=1)

def test_injection_locations_avoid_preexisting_sources():
    rng = np.random.default_rng(31)
    image = rng.normal(0, 1, (160, 160))
    variance = np.ones_like(image)
    flags = np.zeros_like(image, dtype=np.uint16)
    yy, xx = np.mgrid[-3:4, -3:4]
    psf = np.exp(-(xx*xx + yy*yy)/2); psf /= psf.sum()
    image[80-3:80+4, 80-3:80+4] += 100*psf
    result = run_injection_recovery(image, variance, flags, psf, flux_levels=[8.0],
        n_per_level=6, snr_threshold=5.0, seed=12, source_exclusion_radius=10)
    coords = np.array([[r["x"], r["y"]] for r in result["injections"]])
    assert np.all(np.sqrt(((coords - [80, 80])**2).sum(axis=1)) > 10)
    assert result["baseline_source_exclusion_applied"] is True


def test_calibration_discovery_uses_official_numeric_detector_folder(monkeypatch):
    base = calibration_discovery.ROOT + "dr1/epsf/"
    version_dir = base + "cal-epsf-v1-2026-191/"
    calls = []
    def fake_list(url):
        calls.append(url)
        if url == base:
            return [version_dir]
        if url == version_dir + "4/":
            return [version_dir + "4/epsf_D4_spx_cal-epsf-v1-2026-191.fits"]
        return []
    monkeypatch.setattr(calibration_discovery, "_list", fake_list)
    results = calibration_discovery.find_products("epsf", detector=4, release="dr1")
    assert results == [version_dir + "4/epsf_D4_spx_cal-epsf-v1-2026-191.fits"]
    assert version_dir + "4/" in calls
    assert all("/D4/" not in call for call in calls)



def test_spherex_flag_policies_encode_documented_bit_positions():
    mask, names = policy_mask("photometry")
    assert names == ("SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD", "NONLINEAR", "PERSIST")
    assert mask == sum(1 << FLAG_BITS[name] for name in names)
    conservative, conservative_names = policy_mask("conservative-photometry")
    assert "DICHROIC" in conservative_names and conservative == (mask | (1 << 7))
    background, background_names = policy_mask("background")
    assert "SOURCE" in background_names and "TRANSIENT" in background_names
    assert background & (1 << 21) and background & (1 << 0)

def test_orbit_propagation_circular_orbit_period():
    # One AU, circular, zero inclination; one Julian year later returns to start.
    p0 = propagate_heliocentric_ecliptic([1.0],[0.0],[0.0],[0.0],[0.0],[0.0],51544.5,51544.5)
    p1 = propagate_heliocentric_ecliptic([1.0],[0.0],[0.0],[0.0],[0.0],[0.0],51544.5,51544.5+365.256363004)
    assert np.linalg.norm(p0[0]-p1[0]) < 1e-8


def test_orbit_requires_explicit_column_mapping_when_ambiguous():
    cols=["a","semimajor_axis_au","eccentricity","inclination_deg","Omega","argument_perihelion_deg","M"]
    with pytest.raises(ValueError,match="Ambiguous"):
        resolve_columns(cols)
    mapping={"a_au":"a","eccentricity":"eccentricity","inclination_deg":"inclination_deg",
      "ascending_node_deg":"Omega","argument_perihelion_deg":"argument_perihelion_deg","mean_anomaly_deg":"M"}
    got=resolve_columns(cols,mapping)
    assert got["a_au"]=="a"


def test_horizons_angular_separation_handles_ra_wrap():
    sep=angular_separation_arcsec([359.999],[0.0],[0.001],[0.0])[0]
    assert sep == pytest.approx(7.2, rel=0.01)


def test_citizen_task_manifest_separates_answer_key(tmp_path):
    cases=tmp_path/"cases.csv"
    cases.write_text("case_id,epoch_a,epoch_b,answer_key,field_id\nA,images/a.png,images/b.png,moving_source,field-1\nB,images/c.png,images/d.png,artifact,field-2\n")
    result=build_tasks(cases,tmp_path/"out",seed=7)
    pub=json.loads((tmp_path/"out/tasks_public.json").read_text())
    priv=json.loads((tmp_path/"out/answer_key_private.json").read_text())
    assert result["n_tasks"]==2 and result["n_keyed"]==2
    assert all("answer_key" not in t and "field_id" not in t for t in pub["tasks"])
    assert len(priv["answer_key"])==2


def test_template_frame_must_be_explicitly_native():
    with pytest.raises(ValueError, match="not proven"):
        validate_template_coordinate_frame("unknown", {})


def test_template_frame_rejects_sky_oriented_epsf_header():
    with pytest.raises(ValueError, match="DETCOORD='sky'"):
        validate_template_coordinate_frame("detector-native", {"DETCOORD": "sky"})


def test_template_frame_accepts_explicit_native_map():
    validate_template_coordinate_frame("detector-native", {"DETCOORD": "native"})


def test_published_planet_nine_pair_separation_matches_paper():
    from research_discovery.planet9.published_candidate_diagnostic import compute
    result = compute()
    assert result["separation_arcmin"] == pytest.approx(47.4586, abs=0.0001)
    assert result["position_angle_deg_from_north_eastward"] == pytest.approx(207.386, abs=0.002)
    assert "NOT_CONFIRMED_PLANET_NINE" in result["status"]
    assert result["heuristic_distance_range_au_NOT_A_FIT"][0] < result["heuristic_distance_range_au_NOT_A_FIT"][1]


def test_native_mef_query_field_parser_and_filename_guard():
    from research_discovery.spherex.fetch_native_mefs import parse_field, _safe_basename
    field = parse_field("M101,210.80227,54.34895")
    assert field.name == "M101" and field.ra_deg == pytest.approx(210.80227)
    assert _safe_basename("https://irsa.ipac.caltech.edu/ibe/data/level2_x.fits") == "level2_x.fits"
    with pytest.raises(ValueError):
        _safe_basename("https://example.com/README.txt")
