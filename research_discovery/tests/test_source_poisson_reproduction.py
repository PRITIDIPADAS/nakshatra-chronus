import numpy as np
import pytest

from research_discovery.spherex.source_poisson_reproduction import (
    recompute_source_poisson_bins,
)


def test_source_poisson_reproducer_recomputes_expected_electrons_and_variance():
    psf = np.array([
        [0.05, 0.10, 0.05],
        [0.10, 0.40, 0.10],
        [0.05, 0.10, 0.05],
    ])
    gain = np.full((20, 20), 0.5)
    omega = np.full((20, 20), 8.0e-7)
    injections = [
        {"flux_level": 100e-6, "x": 8.25, "y": 9.75},
        {"flux_level": 100e-6, "x": 13.25, "y": 12.75},
        {"flux_level": 200e-6, "x": 9.25, "y": 14.75},
    ]
    result = recompute_source_poisson_bins(
        injections, psf, gain, omega, exposure_time_s=100.0,
    )
    assert len(result) == 2
    assert result[0]["n_injected"] == 2
    assert result[1]["n_injected"] == 1

    p = psf / psf.sum()
    conversion = 100.0 / 0.5
    source_signal = 100e-6 * 1.0e-6 / 8.0e-7 * p
    expected_per_source = float(np.sum(source_signal * conversion))
    variance_per_source = float(np.sum(source_signal / conversion))
    assert result[0]["expected_electrons_recomputed"] == pytest.approx(2 * expected_per_source)
    assert result[0]["variance_added_image_units2_recomputed"] == pytest.approx(2 * variance_per_source)


def test_source_poisson_reproducer_refuses_invalid_gain_or_area_pixels():
    psf = np.ones((3, 3), dtype=float)
    gain = np.full((10, 10), 0.5)
    omega = np.full((10, 10), 8e-7)
    injection = [{"flux_level": 1e-4, "x": 5.0, "y": 5.0}]

    gain[5, 5] = np.nan
    with pytest.raises(ValueError, match="invalid absolute-gain"):
        recompute_source_poisson_bins(
            injection, psf, gain, omega, exposure_time_s=100.0,
        )

    gain[5, 5] = 0.5
    omega[5, 5] = 0.0
    with pytest.raises(ValueError, match="invalid solid-angle"):
        recompute_source_poisson_bins(
            injection, psf, gain, omega, exposure_time_s=100.0,
        )


def test_source_poisson_reproducer_refuses_edge_clipped_epsf_footprints():
    psf = np.ones((5, 5), dtype=float)
    gain = np.full((10, 10), 0.5)
    omega = np.full((10, 10), 8e-7)
    with pytest.raises(ValueError, match="falls outside"):
        recompute_source_poisson_bins(
            [{"flux_level": 1e-4, "x": 1.0, "y": 1.0}],
            psf, gain, omega, exposure_time_s=100.0,
        )
