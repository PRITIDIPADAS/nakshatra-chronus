import hashlib

import numpy as np
import pytest
from astropy.io import fits

from research_discovery.spherex.electron_conversion import (
    NATIVE_SHAPE,
    derive_electrons_per_image_unit,
)


def _gain_map(path, *, detector="D2", bunit="MJy s / (electron sr)"):
    values = np.full(NATIVE_SHAPE, 0.5, dtype=np.float32)
    values[20, 10] = np.nan
    values[20, 11] = 0.0
    primary = fits.PrimaryHDU()
    image = fits.ImageHDU(values, name="IMAGE")
    image.header["DETECTOR"] = detector
    image.header["BUNIT"] = bunit
    fits.HDUList([primary, image]).writeto(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_absolute_gain_conversion_is_pixelwise_exposure_over_gain(tmp_path):
    path = tmp_path / "gain.fits"
    digest = _gain_map(path)
    result = derive_electrons_per_image_unit(
        calibration_path=path,
        expected_sha256=digest,
        detector="D2",
        calibration_bunit="MJy s / (electron sr)",
        exposure_time_s=100.0,
        origin_xy=(10, 20),
        image_shape=(2, 3),
        science_image_unit="MJy / sr",
    )
    assert result.shape == (2, 3)
    assert result[0, 0] == pytest.approx(200.0)
    assert np.isnan(result[0, 1])
    assert np.isnan(result[0, 2])
    assert np.isfinite(result[1, :]).all()


def test_absolute_gain_conversion_rejects_unverified_file_hash(tmp_path):
    path = tmp_path / "gain.fits"
    digest = _gain_map(path)
    with pytest.raises(ValueError, match="SHA-256"):
        derive_electrons_per_image_unit(
            calibration_path=path,
            expected_sha256="0" * 64 if digest != "0" * 64 else "1" * 64,
            detector="D2",
            calibration_bunit="MJy s / (electron sr)",
            exposure_time_s=100.0,
            origin_xy=(0, 0),
            image_shape=(2, 2),
        )


def test_absolute_gain_conversion_rejects_detector_mismatch(tmp_path):
    path = tmp_path / "gain.fits"
    digest = _gain_map(path, detector="D1")
    with pytest.raises(ValueError, match="detector mismatch"):
        derive_electrons_per_image_unit(
            calibration_path=path,
            expected_sha256=digest,
            detector="D2",
            calibration_bunit="MJy s / (electron sr)",
            exposure_time_s=100.0,
            origin_xy=(0, 0),
            image_shape=(2, 2),
        )


def test_absolute_gain_conversion_rejects_unknown_calibration_units(tmp_path):
    path = tmp_path / "gain.fits"
    digest = _gain_map(path, bunit="MJy/pixel")
    with pytest.raises(ValueError, match="BUNIT"):
        derive_electrons_per_image_unit(
            calibration_path=path,
            expected_sha256=digest,
            detector="D2",
            calibration_bunit="MJy/pixel",
            exposure_time_s=100.0,
            origin_xy=(0, 0),
            image_shape=(2, 2),
        )


def test_absolute_gain_conversion_rejects_out_of_bounds_native_footprint(tmp_path):
    path = tmp_path / "gain.fits"
    digest = _gain_map(path)
    with pytest.raises(ValueError, match="outside the absolute-gain map"):
        derive_electrons_per_image_unit(
            calibration_path=path,
            expected_sha256=digest,
            detector="D2",
            calibration_bunit="MJy s / (electron sr)",
            exposure_time_s=100.0,
            origin_xy=(2039, 2039),
            image_shape=(2, 2),
        )
