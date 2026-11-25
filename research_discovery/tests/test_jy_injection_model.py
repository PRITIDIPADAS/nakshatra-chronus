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

def test_local_psf_region_position_search_enumerates_candidates_without_global_rejection():
    from research_discovery.validation.injection_recovery import _choose_positions

    shape = (4096, 4096)
    valid = np.zeros(shape, dtype=bool)
    center = (2048.25, 2048.75)
    radius = 120.0
    yy, xx = np.mgrid[-120:121, -120:121]
    local_rng = np.random.default_rng(314)
    local_valid = (
        (xx ** 2 + yy ** 2 <= radius ** 2)
        & (local_rng.random(xx.shape) < 0.25)
    )
    valid[2048 - 120:2048 + 121, 2048 - 120:2048 + 121] = local_valid

    points = _choose_positions(
        valid, n=20, margin=12,
        rng=np.random.default_rng(2026),
        min_distance=16,
        phase=(0.25, 0.75),
        reference_xy=center,
        region_radius=radius,
    )

    assert points.shape == (20, 2)
    assert np.all((points[:, 0] - center[0]) ** 2 + (points[:, 1] - center[1]) ** 2 <= radius ** 2)
    assert all(valid[int(y), int(x)] for x, y in points)
    distances = np.sqrt(((points[:, None, :] - points[None, :, :]) ** 2).sum(axis=2))
    distances += np.eye(len(points)) * 1e9
    assert float(distances.min()) >= 16.0


def _pending_electron_record(tmp_path):
    import hashlib

    from datetime import datetime, timezone

    calibration = tmp_path / "abs_gain_D2.fits"
    calibration.write_bytes(b"provenance-bound absolute gain test bytes")
    calibration_sha = hashlib.sha256(calibration.read_bytes()).hexdigest()
    science_sha = "a" * 64
    science_uri = "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/test_science.fits"
    calibration_uri = "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/abs_gain_matrix/test_gain.fits"
    link = {
        "input_table": "spherex.provenance_input",
        "science_planeid": "science-plane",
        "calibration_planeid": "gain-plane",
        "inputid": "gain-plane",
        "outputid": "science-plane",
        "science_native_uri": science_uri,
        "calibration_native_uri": calibration_uri,
        "calibration_sha256": calibration_sha,
        "artifact_planeid": "gain-plane",
        "artifact_md5_status": "pass",
        "query_sha256": "c" * 64,
        "status": "verified_from_live_irsa_foreign_key_query",
    }
    return {
        "verification_status": "derived_pending_independent_review",
        "review_status": "pending",
        "derived_by": "automated test",
        "derived_utc": datetime.now(timezone.utc).isoformat(),
        "science_file_sha256": science_sha,
        "science_native_file_sha256": science_sha,
        "science_observation_id": "TEST_OBS_D2",
        "science_source_uri": science_uri,
        "detector": "D2",
        "image_unit": "MJy/sr",
        "exposure_time_s": 100.0,
        "calibration_product": "abs_gain_matrix",
        "calibration_uri": calibration_uri,
        "calibration_file_path": str(calibration),
        "calibration_sha256": calibration_sha,
        "calibration_bunit": "MJy s / (electron sr)",
        "conversion_method": "e-/image unit = exposure_time_s / absolute_gain",
        "provenance_link": link,
    }


def test_pending_electron_record_requires_explicit_exploratory_opt_in(tmp_path):
    from research_discovery.validation.injection_recovery import (
        validate_electron_calibration_record,
    )

    record = _pending_electron_record(tmp_path)
    with pytest.raises(ValueError, match="pending independent review"):
        validate_electron_calibration_record(record)
    checked = validate_electron_calibration_record(record, allow_unreviewed=True)
    assert checked["verification_status"] == "derived_pending_independent_review"
    assert checked["review_status"] == "pending"


def test_pending_electron_record_rejects_mismatched_provenance_link(tmp_path):
    from research_discovery.validation.injection_recovery import (
        validate_electron_calibration_record,
    )

    record = _pending_electron_record(tmp_path)
    record["provenance_link"]["inputid"] = "different-calibration-plane"
    with pytest.raises(ValueError, match="inputid"):
        validate_electron_calibration_record(record, allow_unreviewed=True)


def test_pending_review_absolute_gain_enables_source_poisson_injection_only_with_opt_in(tmp_path):
    shape = (96, 96)
    rng = np.random.default_rng(71)
    image = rng.normal(0.0, 0.04, shape)
    variance = np.full(shape, 0.04 ** 2)
    flags = np.zeros(shape, dtype=np.uint16)
    omega = np.full(shape, 8.0e-7)
    psf = _psf()
    record = _pending_electron_record(tmp_path)

    with pytest.raises(ValueError, match="pending independent review"):
        run_injection_recovery(
            image.copy(), variance.copy(), flags.copy(), psf,
            flux_levels=[80.0], n_per_level=1, seed=13,
            min_injection_separation=6, source_exclusion_radius=0,
            solid_angle_sr_map=omega, flux_unit="Jy",
            psf_reference_xy=(48.0, 48.0), psf_region_radius=18.0,
            electrons_per_image_unit=np.full(shape, 1000.0),
            electron_calibration_record=record,
        )

    result = run_injection_recovery(
        image.copy(), variance.copy(), flags.copy(), psf,
        flux_levels=[80.0], n_per_level=1, seed=13,
        min_injection_separation=6, source_exclusion_radius=0,
        solid_angle_sr_map=omega, flux_unit="Jy",
        psf_reference_xy=(48.0, 48.0), psf_region_radius=18.0,
        electrons_per_image_unit=np.full(shape, 1000.0),
        electron_calibration_record=record,
        allow_unreviewed_electron_calibration=True,
    )
    assert result["source_photon_noise"]["enabled"] is True
    assert result["source_photon_noise"]["physically_modelled"] is True
    assert result["source_photon_noise"]["calibration_review_status"] == "pending"
    assert result["source_photon_noise"]["independent_human_reviewed"] is False


def test_absolute_gain_bunit_normalization_accepts_space_around_slash():
    from research_discovery.spherex.electron_conversion import _is_surface_brightness_unit

    assert _is_surface_brightness_unit("MJy/sr")
    assert _is_surface_brightness_unit("MJy / sr")
    assert not _is_surface_brightness_unit("Jy/pixel")
