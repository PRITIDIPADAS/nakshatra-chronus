import numpy as np
import pytest

from research_discovery.validation.injection_recovery import (
    matched_filter_flux_uncertainty_jy,
    matched_filter_snr_jy,
    run_injection_recovery,
)


def _psf():
    yy, xx = np.mgrid[-2:3, -2:3]
    values = np.exp(-0.5 * (xx * xx + yy * yy) / 1.2)
    return values / values.sum()


def test_jy_flux_uncertainty_uses_per_pixel_solid_angle_and_mjy_sr_variance():
    psf = _psf()
    variance = np.linspace(0.02, 0.05, psf.size).reshape(psf.shape)
    omega = np.linspace(7.0e-7, 9.0e-7, psf.size).reshape(psf.shape)

    expected = 1.0e6 / np.sqrt(np.sum((psf / omega) ** 2 / variance))
    actual = matched_filter_flux_uncertainty_jy(psf, variance, omega)

    assert actual == pytest.approx(expected, rel=1e-12)
    assert np.isfinite(actual) and actual > 0


def test_position_dependent_jy_filter_matches_injected_surface_brightness_model():
    shape = (64, 64)
    yy, xx = np.mgrid[:shape[0], :shape[1]]
    omega = 8.0e-7 * (1.0 + 0.0015 * xx + 0.0005 * yy)
    variance = np.full(shape, 0.04)
    image = np.zeros(shape, dtype=float)
    psf = _psf()
    x, y, flux_jy = 31, 29, 80.0
    px, py = np.array(psf.shape) // 2
    patch = (slice(y - py, y + py + 1), slice(x - px, x + px + 1))
    omega_patch = omega[patch]
    image[patch] = flux_jy * 1.0e-6 * psf / omega_patch

    snr = matched_filter_snr_jy(
        image, variance, psf, omega,
        region_center_xy=(x, y), region_radius_px=8,
    )
    sigma_jy = matched_filter_flux_uncertainty_jy(psf, variance[patch], omega_patch)

    assert snr[y, x] == pytest.approx(flux_jy / sigma_jy, rel=1e-12)
    assert np.isnan(snr[0, 0])
    assert np.isnan(snr[10, 10])


def test_real_image_jy_injection_path_uses_area_aware_filter_and_reports_contract():
    rng = np.random.default_rng(21)
    shape = (96, 96)
    image = rng.normal(0.0, 0.04, shape)
    variance = np.full(shape, 0.04 ** 2)
    flags = np.zeros(shape, dtype=np.uint16)
    omega = np.full(shape, 8.0e-7)
    psf = _psf()

    result = run_injection_recovery(
        image, variance, flags, psf,
        flux_levels=[30.0],
        n_per_level=1,
        snr_threshold=5.0,
        seed=11,
        min_injection_separation=6,
        source_exclusion_radius=0,
        solid_angle_sr_map=omega,
        flux_unit="Jy",
        psf_reference_xy=(48.0, 48.0),
        psf_region_radius=18.0,
    )

    assert result["flux_unit"] == "Jy"
    assert result["detection_template"]["uses_separate_surface_brightness_psf"] is False
    assert len(result["injections"]) == 1
    assert result["flux_summary"][0]["n_injected"] == 1


def test_nonnegative_psf_helper_clips_only_subthreshold_interpolation_overshoot():
    from research_discovery.spherex.psf_physicality import enforce_nonnegative_interpolation_psf

    raw = np.array([
        [0.0, 0.01, 0.0],
        [0.02, 0.95, 0.02],
        [0.0, 0.0, -8.0e-5],
    ])
    corrected, record = enforce_nonnegative_interpolation_psf(raw)

    assert np.all(np.isfinite(corrected))
    assert np.all(corrected >= 0.0)
    assert corrected.sum() == pytest.approx(1.0, abs=1e-14)
    assert record["status"] == "pass"
    assert record["negative_pixel_count"] == 1
    assert record["clipped_pixel_count"] == 1
    assert record["correction_applied"] is True
    assert record["negative_to_positive_integrated_flux_fraction"] < 1.0e-3


def test_nonnegative_psf_helper_rejects_material_negative_lobe():
    from research_discovery.spherex.psf_physicality import enforce_nonnegative_interpolation_psf

    raw = np.array([
        [0.0, 0.1, 0.0],
        [0.1, 0.6, 0.1],
        [0.0, -0.02, 0.12],
    ])
    with pytest.raises(ValueError, match="negative interpolation"):
        enforce_nonnegative_interpolation_psf(raw)


def test_nonnegative_psf_helper_rejects_nonfinite_stamp():
    from research_discovery.spherex.psf_physicality import enforce_nonnegative_interpolation_psf

    raw = _psf()
    raw[0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        enforce_nonnegative_interpolation_psf(raw)
