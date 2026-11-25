import numpy as np
import pytest


def _sample(index, mjd, wavelength, flux):
    return {
        "observation_id": f"SYNTH-{index}",
        "mjd": float(mjd),
        "wavelength_um": float(wavelength),
        "flux": float(flux),
        "sigma": 1.0,
        "calibration_group": "SYNTHETIC-SESSION-12",
        "wavelength_source": "synthetic_fixture",
        "wavelength_unit": "um",
        "wavelength_validated": True,
        "synthetic_fixture": True,
        "valid": True,
        "source_index": index,
    }


def _samples():
    return [
        _sample(0, 60000.0, 2.0, 10.0),
        _sample(1, 60000.0, 2.2, 12.0),
        _sample(2, 60001.0, 2.0, 11.0),
        _sample(3, 60001.0, 2.2, 13.0),
    ]


def test_spectrotemporal_gls_reconstruction_propagates_shared_calibration_covariance():
    from chronos_spectrotemporal.reconstruction import reconstruct

    samples = _samples()
    covariance = np.eye(4)
    covariance[0, 1] = covariance[1, 0] = 0.2
    covariance[2, 3] = covariance[3, 2] = 0.15

    result = reconstruct(
        samples,
        [2.1],
        [60000.5],
        wavelength_bandwidth_um=0.2,
        time_bandwidth_days=1.0,
        min_neighbors=2,
        measurement_covariance=covariance,
        shared_calibration_fractional_sigma=0.05,
    )

    assert result["valid"] == [[True]]
    assert result["sigma_shared_calibration"][0][0] > 0
    assert result["sigma_total"][0][0] > result["sigma_measurement"][0][0]
    assert result["n_samples"][0][0] == 4
    assert {row["source_index"] for row in result["linear_weights"][0][0]} == {0, 1, 2, 3}
    assert result["covariance_model"]["measurement_covariance_supplied"] is True
    assert result["covariance_model"]["shared_calibration_fractional_sigma"] == 0.05


def test_spectrotemporal_covariance_must_match_original_rows_and_sigma_diagonal():
    from chronos_spectrotemporal.reconstruction import reconstruct

    samples = _samples()
    with pytest.raises(ValueError, match="original input-row order"):
        reconstruct(
            samples, [2.1], [60000.5],
            wavelength_bandwidth_um=0.2, time_bandwidth_days=1.0,
            measurement_covariance=np.eye(3),
        )

    wrong_diagonal = np.eye(4) * 2.0
    with pytest.raises(ValueError, match="diagonal"):
        reconstruct(
            samples, [2.1], [60000.5],
            wavelength_bandwidth_um=0.2, time_bandwidth_days=1.0,
            measurement_covariance=wrong_diagonal,
        )


def test_spectrotemporal_covariance_is_subset_after_invalid_rows_are_masked():
    from chronos_spectrotemporal.reconstruction import reconstruct

    samples = _samples()
    samples.insert(1, _sample(99, 60000.4, 2.1, 1000.0) | {"valid": False})
    covariance = np.eye(5)
    covariance[0, 2] = covariance[2, 0] = 0.1
    result = reconstruct(
        samples, [2.1], [60000.5],
        wavelength_bandwidth_um=0.2, time_bandwidth_days=1.0,
        measurement_covariance=covariance,
    )
    assert result["valid"] == [[True]]
    assert 99 not in result["source_indices"][0][0]
    assert result["covariance_model"]["covariance_row_source_indices"] == [0, 1, 2, 3]


def test_spectrotemporal_reconstruction_keeps_unsupported_cells_missing():
    from chronos_spectrotemporal.reconstruction import reconstruct

    result = reconstruct(
        _samples(),
        [1.8, 2.1, 2.4],
        [60000.5],
        wavelength_bandwidth_um=0.2,
        time_bandwidth_days=1.0,
        min_neighbors=2,
    )
    assert result["valid"] == [[False, True, False]]
    assert np.isnan(result["flux"][0][0])
    assert np.isnan(result["flux"][0][2])


def test_equivalent_width_reports_lsf_sampling_and_possible_blending():
    from chronos_addons.molecular import measure_equivalent_width
    from chronos_addons.spectral import Spectrum

    wave = np.linspace(1.0, 2.0, 101)
    flux = 1.0 - 0.2 * np.exp(-0.5 * ((wave - 1.5) / 0.04) ** 2)
    spectrum = Spectrum(wave, flux, sigma=np.full(wave.size, 0.01))
    result = measure_equivalent_width(
        spectrum,
        [1.4, 1.6],
        [[1.2, 1.3], [1.7, 1.8]],
        resolution={
            "resolving_power": 50.0,
            "source_uri": "https://irsa.ipac.caltech.edu/spherex/dr1/cal/lsf/D2.fits",
            "sha256": "a" * 64,
        },
        potential_blend_intervals_um=[[1.59, 1.64]],
    )
    resolution = result["resolution_diagnostics"]
    assert resolution["status"] == "provided"
    assert resolution["lsf_fwhm_um"] == pytest.approx(0.03)
    assert resolution["samples_per_fwhm"] == pytest.approx(3.0)
    assert resolution["sampling_status"] == "sampled_at_two_or_more_pixels_per_fwhm"
    assert resolution["source_reference_recorded"] is True
    assert result["resolution_diagnostics"]["blend_diagnostics"]["status"] == "possible_blend"


def test_equivalent_width_does_not_call_unverified_resolution_calibrated():
    from chronos_addons.molecular import measure_equivalent_width
    from chronos_addons.spectral import Spectrum

    wave = np.linspace(1.0, 2.0, 101)
    spectrum = Spectrum(wave, np.ones(wave.size), sigma=np.full(wave.size, 0.01))
    with pytest.raises(ValueError, match="disagree"):
        measure_equivalent_width(
            spectrum, [1.4, 1.6], [[1.2, 1.3], [1.7, 1.8]],
            resolution={"resolving_power": 100.0, "lsf_fwhm_um": 0.1},
        )


def test_feature_evolution_preserves_resolution_and_blend_reports():
    from chronos_spectrotemporal.feature_evolution import measure_feature_evolution

    wave = np.linspace(1.0, 2.0, 101)
    flux = (1.0 - 0.2 * np.exp(-0.5 * ((wave - 1.5) / 0.04) ** 2)).tolist()
    epoch = {
        "epoch_id": "E1",
        "mjd": 60000.0,
        "wavelength_um": wave.tolist(),
        "flux": flux,
        "sigma": [0.01] * wave.size,
        "valid": [True] * wave.size,
        "calibration_group": "SYNTHETIC-FEATURE",
        "wavelength_source": "synthetic_fixture",
        "wavelength_unit": "um",
        "wavelength_validated": True,
        "synthetic_fixture": True,
        "resolution": {"lsf_fwhm_um": 0.03},
    }
    result = measure_feature_evolution(
        [epoch], [1.4, 1.6], [[1.2, 1.3], [1.7, 1.8]],
        potential_blend_intervals_um=[[1.59, 1.64]],
    )
    assert result["epochs"][0]["resolution_diagnostics"]["status"] == "provided"
    assert result["epochs"][0]["blend_diagnostics"]["status"] == "possible_blend"
