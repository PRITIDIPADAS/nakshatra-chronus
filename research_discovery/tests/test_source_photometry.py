import csv
import hashlib
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS


def _record(path):
    return {
        "uri": f"https://archive.example/{path.name}",
        "local_path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _photometry_inputs(tmp_path):
    shape = (32, 32)
    image_header = fits.Header()
    image_header["DETECTOR"] = 2
    image_header["OBSID"] = "OBS-1"
    image_header["BUNIT"] = "MJy / sr"
    image_header["CTYPE1"] = "RA---TAN"
    image_header["CTYPE2"] = "DEC--TAN"
    image_header["CRPIX1"] = 16.0
    image_header["CRPIX2"] = 16.0
    image_header["CRVAL1"] = 10.0
    image_header["CRVAL2"] = 20.0
    image_header["CDELT1"] = -0.0001
    image_header["CDELT2"] = 0.0001

    yy, xx = np.mgrid[-5:6, -5:6]
    psf = np.exp(-0.5 * (xx**2 + yy**2) / 2.0)
    psf /= psf.sum()
    omega_sr_value = 38.0 * (np.pi / (180.0 * 3600.0)) ** 2
    response = 1.0e-6 * psf / omega_sr_value
    image = np.zeros(shape, dtype=np.float32)
    patch = np.s_[10:21, 10:21]
    image[patch] = (0.25 * response + 3.0).astype(np.float32)
    variance = np.full(shape, 10000.0, dtype=np.float32)
    flags = np.zeros(shape, dtype=np.uint32)
    science_path = tmp_path / "science.fits"
    fits.HDUList([
        fits.PrimaryHDU(),
        fits.ImageHDU(image, header=image_header, name="IMAGE"),
        fits.ImageHDU(variance, name="VARIANCE"),
        fits.ImageHDU(flags, name="FLAGS"),
    ]).writeto(science_path)

    spectral_header = fits.Header({"DETECTOR": 2, "BUNIT": "um"})
    spectral_path = tmp_path / "spectral.fits"
    fits.HDUList([
        fits.PrimaryHDU(),
        fits.ImageHDU(np.full(shape, 3.1, dtype=np.float32), header=spectral_header, name="CWAVE"),
        fits.ImageHDU(np.full(shape, 0.02, dtype=np.float32), header=spectral_header, name="CBAND"),
    ]).writeto(spectral_path)

    area_header = fits.Header({"DETECTOR": 2, "BUNIT": "arcsec2"})
    area_path = tmp_path / "area.fits"
    fits.HDUList([
        fits.PrimaryHDU(),
        fits.ImageHDU(np.full(shape, 38.0, dtype=np.float32), header=area_header, name="IMAGE"),
    ]).writeto(area_path)

    catalogue_path = tmp_path / "source_catalogue.csv"
    with catalogue_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["source_id", "ra_deg", "dec_deg"])
        writer.writeheader()
        writer.writerow({"source_id": "S1", "ra_deg": 10.0, "dec_deg": 20.0})

    files = {
        "science_file": _record(science_path),
        "spectral_wcs_file": _record(spectral_path),
        "solid_angle_file": _record(area_path),
        "source_catalogue_file": _record(catalogue_path),
    }
    product_id = "ivo://irsa.ipac/spherex_dr1?OBS-1/D2"
    compatibility = {
        "status": "compatible",
        "sha256": "a" * 64,
        "science_sha256": files["science_file"]["sha256"],
        "spectral_wcs_sha256": files["spectral_wcs_file"]["sha256"],
        "solid_angle_sha256": files["solid_angle_file"]["sha256"],
    }
    product = {
        "archive_product_id": product_id,
        "observation_id": "OBS-1",
        "mjd": 60000.0,
        "release": "DR1",
        "detector": "D2",
        "calibration_group": "DR1-D2-CAL-1",
    }
    source = {
        "source_id": "S1",
        "ra_deg": 10.0,
        "dec_deg": 20.0,
        "sample_class": "young_stellar_object",
        "classification_reference": "https://catalogue.example/S1",
    }
    return files, product, source, compatibility


def _fake_epsf_extractor(science_path, *, x, y, out, stamp_size):
    yy, xx = np.mgrid[-stamp_size // 2 + 1:stamp_size // 2 + 1,
                      -stamp_size // 2 + 1:stamp_size // 2 + 1]
    psf = np.exp(-0.5 * (xx**2 + yy**2) / 2.0)
    psf /= psf.sum()
    fits.PrimaryHDU(
        psf.astype(np.float32),
        header=fits.Header({"DETECTOR": "2", "XLL": 10, "YLL": 10, "SRCX": x, "SRCY": y}),
    ).writeto(out, overwrite=True)
    return {
        "output_stamp": str(out),
        "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "stamp_lower_left_cutout_pixel_0based": [10, 10],
        "source_position_cutout_pixel_0based": [x, y],
        "method": "synthetic unit-test ePSF fixture",
    }


def test_native_source_photometry_fits_integrated_jy_and_reverifies_native_wavelength(tmp_path):
    from research_discovery.spherex.source_photometry import extract_source_photometry

    files, product, source, compatibility = _photometry_inputs(tmp_path)
    result = extract_source_photometry(
        **files,
        product_record=product,
        source_record=source,
        native_mef_audit_sha256="b" * 64,
        compatibility_decision=compatibility,
        code_commit="1" * 40,
        output_dir=tmp_path / "out",
        epsf_extractor=_fake_epsf_extractor,
    )
    row = result["measurements"][0]
    assert row["valid"] is True
    assert row["fit_status"] == "success"
    assert row["flux_jy"] == pytest.approx(0.25, rel=1e-4)
    assert row["sigma_jy"] > 0
    assert row["wavelength_um"] == pytest.approx(3.1)
    assert row["bandwidth_um"] == pytest.approx(0.02)
    assert row["pixel_index"] == {"x": 15, "y": 15}
    assert result["verified_source_timeseries"]["sources"][0]["time_series_summary"]["epoch_count"] == 1
    assert Path(result["output_path"]).is_file()


def test_native_source_photometry_rejects_incompatible_or_unhashed_inputs(tmp_path):
    from research_discovery.spherex.source_photometry import extract_source_photometry

    files, product, source, compatibility = _photometry_inputs(tmp_path)
    compatibility["status"] = "review_required"
    with pytest.raises(ValueError, match="compatible native MEF audit"):
        extract_source_photometry(
            **files, product_record=product, source_record=source,
            native_mef_audit_sha256="b" * 64,
            compatibility_decision=compatibility,
            code_commit="1" * 40, output_dir=tmp_path / "out",
            epsf_extractor=_fake_epsf_extractor,
        )


def test_psf_flux_fit_uses_delivered_variance_and_rejects_bad_flags():
    from research_discovery.spherex.source_photometry import fit_psf_flux_jy

    yy, xx = np.mgrid[-2:3, -2:3]
    psf = np.exp(-0.5 * (xx**2 + yy**2) / 1.0)
    psf /= psf.sum()
    omega = np.full(psf.shape, 1.0e-8)
    response = 1.0e-6 * psf / omega
    image = 0.4 * response + 2.0
    variance = np.full(psf.shape, 25.0)
    flags = np.zeros(psf.shape, dtype=np.uint32)
    fit = fit_psf_flux_jy(image, variance, omega, flags, psf, excluded_flag_bits=1 << 7)
    assert fit["flux_jy"] == pytest.approx(0.4, rel=1e-8)
    assert fit["sigma_jy"] > 0
    flags[0, 0] = 1 << 7
    with pytest.raises(ValueError, match="excluded SPHEREx flag"):
        fit_psf_flux_jy(image, variance, omega, flags, psf, excluded_flag_bits=1 << 7)
