import math

import numpy as np
import pytest

import core

BARNARD = dict(name="Barnard", ra=269.4485, dec=4.7394, epoch=2016.0, pmra=-801.551, pmdec=10362.394, plx=0.547, sim=dict(sed=[11.8, -0.42]))
STILL = dict(name="Still", ra=76.956, dec=30.401, epoch=2000.0, pmra=0.0, pmdec=0.0, plx=0.0, sim=dict(sed=[11.5, 0.1]))


@pytest.fixture(scope="module")
def sky():
    return core.prepare(core.sim_field(BARNARD, seed=3))


@pytest.fixture(scope="module")
def still():
    return core.prepare(core.sim_field(STILL, seed=4))


def test_zero_motion_is_not_called_motion(still):
    f = core.motion_fit(core.track(still, STILL))
    assert f["verdict"] == "Fixed position preferred"
    assert f["pm"] < 5 * f["err"] + 0.05


def test_catalog_motion_is_recovered(sky):
    f = core.motion_fit(core.track(sky, BARNARD))
    truth = math.hypot(BARNARD["pmra"], BARNARD["pmdec"]) / 1000
    assert f["verdict"] == "Motion model preferred"
    assert abs(f["pm"] - truth) < 4 * f["err"]
    assert abs(f["pm_ra"] - BARNARD["pmra"] / 1000) < 4 * f["e_ra"]


def test_parallax_is_recovered_with_the_right_sign(sky):
    f = core.motion_fit(core.track(sky, BARNARD))
    assert f["model"] == "H2"
    assert abs(f["parallax"] - BARNARD["plx"]) < 4 * f["parallax_err"]


def test_parallax_factor_sign():
    # A star toward the vernal equinox. The Earth sits on the far side of the Sun near the March equinox,
    # and moves toward plus Y three months later. Then the star shifts west, so the east factor is negative.
    fx, _ = core.plx_factors(np.array([60481.0]), 0.0, 0.0)  # near a June solstice: Earth near minus Y in ICRS
    assert fx[0] > 0.8
    fx, _ = core.plx_factors(np.array([60664.0]), 0.0, 0.0)  # near a December solstice: Earth near plus Y
    assert fx[0] < -0.8


def test_different_detector_is_not_a_fair_pair(sky):
    a = sky[0]
    b = next(e for e in sky if e.det != a.det)
    s, fair, why, _ = core.pair_score(a, b)
    assert s == 0 and fair is False


def test_same_channel_next_survey_is_a_fair_pair(sky):
    a = sky[0]
    b = next(e for e in sky if e.id == a.id.replace("_e0_", "_e1_"))
    assert core.pair_score(a, b)[1] is True


def test_half_channel_shift_is_not_a_fair_pair(sky):
    a = sky[0]
    b = next(e for e in sky if e.id == a.id.replace("_e0_", "_e2_"))
    s, fair, why, parts = core.pair_score(a, b)
    assert fair is False and 0.3 < parts["color"] < 0.7 and why


def test_other_channel_is_not_a_fair_pair(sky):
    s, fair, why, parts = core.pair_score(sky[0], sky[1])
    assert fair is False and parts["color"] > 1 and "colors differ" in why[0]


def test_unknown_color_is_never_fair(sky):
    import copy
    a, b = copy.copy(sky[0]), next(e for e in sky if e.id == sky[0].id.replace("_e0_", "_e1_"))
    a.lam_ok = False
    assert core.pair_score(a, b)[1] is False


def test_release_mismatch_is_not_fair(sky):
    import copy
    a, b = copy.copy(sky[0]), next(e for e in sky if e.id == sky[0].id.replace("_e0_", "_e1_"))
    a.rel = "OTHER"
    assert core.pair_score(a, b)[1] is False


def test_noise_check_finds_the_wrong_variance(sky):
    k = {d: np.median([e.noise_k for e in sky if e.det == d]) for d in range(1, 7)}
    assert all(abs(k[d] - 1.0) < 0.08 for d in (1, 2, 3, 4))
    assert all(abs(k[d] - 1.25) < 0.10 for d in (5, 6))


def test_photometry_matches_the_injected_flux(sky):
    rows = core.spectrum(sky)
    r = np.array([row["f"] / core.sim_flux(BARNARD["sim"], e.lam, e.mjd) for row, e in zip(rows, sky) if not row["flagged"]])
    assert abs(np.median(r) - 1) < 0.02
    pull = np.array([(row["f"] - core.sim_flux(BARNARD["sim"], e.lam, e.mjd)) / row["e"] for row, e in zip(rows, sky) if not row["flagged"]])
    assert np.isfinite(pull).all()


def test_false_change_meter_predicts_the_color_effect(sky):
    rows = core.spectrum(sky)
    fc = core.false_change(rows, 0, 1)  # two channels of detector 1, same visit
    true = core.sim_flux(BARNARD["sim"], sky[1].lam, sky[1].mjd) / core.sim_flux(BARNARD["sim"], sky[0].lam, sky[0].mjd) - 1
    assert abs(fc["predicted"] - true) < 0.01
    assert abs(fc["excess_sigma"]) < 4
    fair = core.false_change(rows, 0, next(i for i, e in enumerate(sky) if e.id == sky[0].id.replace("_e0_", "_e1_")))
    assert abs(fair["predicted"]) < 0.003


def test_false_change_meter_keeps_a_real_change():
    T = dict(STILL, sim=dict(sed=[11.5, 0.1], var=0.55, chroma=1.0))
    E = core.prepare(core.sim_field(T, seed=5))
    rows = core.spectrum(E)
    a = 0
    b = next(i for i, e in enumerate(E) if e.id == E[0].id.replace("_e0_", "_e1_"))
    fc = core.false_change(rows, a, b)
    assert fc["measured"] < -0.3 and fc["excess_sigma"] < -5


def test_difference_map_is_quiet_for_stars_that_did_not_change(still):
    a = still[0]
    b = next(e for e in still if e.id == a.id.replace("_e0_", "_e1_"))
    z, k, fsys = core.zmap(a, b)
    assert abs(k - 1) < 0.2 and np.nanmax(np.abs(z)) < 9


def test_witness_separates_a_glitch_from_a_star(sky):
    gi = next(i for i, e in enumerate(sky) if e.notes)
    gx, gy = (float(v) for v in sky[gi].notes[0].split()[-1].split(","))
    assert core.witness(sky, gi, gx, gy)["kind"] == "single"
    sx, sy = sky[gi].ref[0]
    assert core.witness(sky, gi, sx + sky[gi].shift[0], sy + sky[gi].shift[1])["kind"] == "sky"


def test_recovery_curve_rises_and_controls_stay_quiet(sky):
    r = core.recovery(sky)
    c = {p["snr"]: p["completeness"] for p in r["curve"]}
    assert c[2] < 0.5 and c[12] > 0.9
    assert core.false_alarm_rate(sky, r["threshold"])["rate"] < 0.05


def test_forecast_says_faint_target_is_not_visible_at_short_colors():
    T = dict(BARNARD, sim=dict(sed=[17.2, 2.4]))
    E = core.prepare(core.sim_field(T, seed=6))
    tags = {e.det: core.forecast(e, T["sim"]["sed"])[1] for e in E}
    assert tags[1] == "not visible" and tags[6] in ("visible", "marginal")


def test_epsf_fit_agrees_with_gaussian_fit(sky):
    e = sky[10]
    a = core.centroid(e.img, e.var, *e.xy)
    b = core.centroid(e.img, e.var, *e.xy, psf=core.gauss_psf())
    assert abs(a[0] - b[0]) < 0.05 and abs(a[1] - b[1]) < 0.05 and abs(a[4] / b[4] - 1) < 0.03


def test_wcs_round_trip():
    w = core.make_wcs(133.76, -7.24, 20.3, 19.6, 37.0)
    ra, dec = core.to_sky(w, [3.0, 40.2], [7.5, 11.1])
    x, y = core.to_pix(w, ra, dec)
    assert np.allclose(x, [3.0, 40.2], atol=1e-6) and np.allclose(y, [7.5, 11.1], atol=1e-6)


def test_flag_table_from_file_replaces_the_default(sky):
    import copy
    e = copy.copy(sky[0])
    e.flags = e.flags.copy()
    x, y = (int(round(v)) for v in e.xy)
    e.flags[y, x] |= 1 << 3
    assert core.flag_names(e, core.box(e)) == []
    e.bits = dict(e.bits, BLOOM=3)
    assert core.flag_names(e, core.box(e)) == ["BLOOM"]
