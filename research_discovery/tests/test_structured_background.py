import numpy as np

from research_discovery.validation.injection_recovery import run_injection_recovery, structured_background_model


def _scene(structure, seed=3):
    rng = np.random.default_rng(seed)
    n = 256
    yy, xx = np.mgrid[:n, :n]
    var = np.full((n, n), 1.0)
    sky = structure * (np.sin(xx / 7.0) * np.cos(yy / 5.0) + 0.5 * np.sin((xx + yy) / 3.0))
    img = sky + rng.normal(0, 1.0, (n, n)) + 4.0
    return img, var, np.zeros((n, n), int)


def _psf():
    y, x = np.mgrid[-5:6, -5:6]
    p = np.exp(-(x * x + y * y) / (2 * 1.3 ** 2))
    return p / p.sum()


def test_flat_sky_needs_no_correction():
    img, var, flags = _scene(0.0)
    bg, scale = structured_background_model(img, var, np.ones_like(var, bool))
    assert abs(np.median(bg) - 4.0) < 0.1
    assert np.median(scale) < 1.1


def test_structured_sky_raises_the_noise_scale():
    img, var, flags = _scene(4.0)
    _, scale = structured_background_model(img, var, np.ones_like(var, bool))
    assert np.median(scale) > 2.0


def test_structured_background_reduces_false_baseline_peaks():
    img, var, flags = _scene(4.0)
    kw = dict(flux_levels=[60.0], n_per_level=5, snr_threshold=5.0, min_injection_separation=16, source_exclusion_radius=0)
    plain = run_injection_recovery(img, var, flags, _psf(), **kw)
    honest = run_injection_recovery(img, var, flags, _psf(), structured_background=True, **kw)
    assert honest["n_baseline_detections"] < plain["n_baseline_detections"]
    assert honest["structured_background"]["noise_scale_median"] > 2.0


def test_reported_rule_follows_the_preregistered_threshold():
    from research_discovery.validation.injection_recovery import reported_rule
    assert reported_rule(1.18) == "primary"
    assert reported_rule(2.0) == "sky_aware"
    assert reported_rule(7.9) == "sky_aware"
    assert reported_rule(float("nan")) == "primary"


def test_region_noise_excess_sees_structured_sky():
    from research_discovery.validation.injection_recovery import region_noise_excess
    flat = region_noise_excess(*_scene(0.0)[:2], (128, 128), 100)
    lumpy = region_noise_excess(*_scene(4.0)[:2], (128, 128), 100)
    assert 0.9 < flat < 1.1
    assert lumpy > 2.0
