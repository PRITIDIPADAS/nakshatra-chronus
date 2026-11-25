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
