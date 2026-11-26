import json
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

    source_x, source_y = 15.25, 15.4
    yy, xx = np.mgrid[10:21, 10:21]
    psf = np.exp(-0.5 * ((xx - source_x) ** 2 + (yy - source_y) ** 2) / 2.0)
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
    grid_y, grid_x = np.mgrid[:shape[0], :shape[1]]
    cwave = 3.0 + 0.001 * grid_x + 0.002 * grid_y
    cband = 0.02 + 0.0001 * grid_x + 0.0002 * grid_y
    fits.HDUList([
        fits.PrimaryHDU(),
        fits.ImageHDU(cwave.astype(np.float32), header=spectral_header, name="CWAVE"),
        fits.ImageHDU(cband.astype(np.float32), header=spectral_header, name="CBAND"),
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
        "compatibility_group": "DR1:D2:7.0.5:2025-001",
        "checks": {
            "release": {"status": "pass"},
            "detector": {"status": "pass"},
            "native_mef_audit": {"status": "pass"},
        },
    }
    audit_report = {
        "status": "STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS",
        "science_sha256": files["science_file"]["sha256"],
        "spectral_wcs_sha256": files["spectral_wcs_file"]["sha256"],
        "solid_angle": {"sha256": files["solid_angle_file"]["sha256"]},
        "checks": {
            "cwave_cband": {"status": "pass"},
            "wavelength_units": {"status": "pass"},
            "solid_angle": {"status": "pass"},
        },
        "calibration_compatibility": compatibility,
    }
    audit_path = tmp_path / "native_mef_audit.json"
    audit_path.write_text(json.dumps(audit_report, sort_keys=True), encoding="utf-8")
    files["native_mef_audit_file"] = _record(audit_path)
    product = {
        "archive_product_id": product_id,
        "observation_id": "OBS-1",
        "mjd": 60000.0,
        "release": "DR1",
        "detector": "D2",
        "calibration_group": "DR1:D2:7.0.5:2025-001",
    }
    source_sky = WCS(image_header).pixel_to_world(source_x, source_y)
    source = {
        "source_id": "S1",
        "ra_deg": float(source_sky.ra.deg),
        "dec_deg": float(source_sky.dec.deg),
        "sample_class": "test_source",
        "display_label": "étoile-test",
        "classification_reference": "https://catalogue.example/S1",
    }
    return files, product, source, compatibility


def _fake_epsf_extractor(science_path, *, x, y, out, stamp_size):
    x_lower = int(np.floor(x - (stamp_size - 1) / 2.0))
    y_lower = int(np.floor(y - (stamp_size - 1) / 2.0))
    yy, xx = np.mgrid[:stamp_size, :stamp_size]
    psf = np.exp(-0.5 * (
        (xx + x_lower - x) ** 2 + (yy + y_lower - y) ** 2
    ) / 2.0)
    psf /= psf.sum()
    fits.PrimaryHDU(
        psf.astype(np.float32),
        header=fits.Header({"DETECTOR": "2", "XLL": x_lower, "YLL": y_lower, "SRCX": x, "SRCY": y}),
    ).writeto(out, overwrite=True)
    return {
        "output_stamp": str(out),
        "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "stamp_lower_left_cutout_pixel_0based": [x_lower, y_lower],
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
    assert row["wavelength_um"] == pytest.approx(3.0 + 0.001 * 15.25 + 0.002 * 15.4, abs=1e-7)
    assert row["bandwidth_um"] == pytest.approx(0.02 + 0.0001 * 15.25 + 0.0002 * 15.4, abs=1e-7)
    assert row["pixel_index"] == {"x": 15, "y": 15}
    assert row["pixel_position"] == {
        "x": pytest.approx(15.25), "y": pytest.approx(15.4), "convention": "zero-based"
    }
    assert row["ra_deg"] == pytest.approx(source["ra_deg"])
    assert row["dec_deg"] == pytest.approx(source["dec_deg"])
    series_summary = result["verified_source_timeseries"]["sources"][0]["time_series_summary"]
    assert series_summary["epoch_count"] == 1
    assert series_summary["usable_multi_epoch_series"] is False
    assert Path(result["output_path"]).is_file()


def test_native_source_photometry_rejects_incompatible_or_unhashed_inputs(tmp_path):
    from research_discovery.spherex.source_photometry import extract_source_photometry

    files, product, source, compatibility = _photometry_inputs(tmp_path)
    compatibility["status"] = "review_required"
    with pytest.raises(ValueError, match="compatible native MEF audit"):
        extract_source_photometry(
            **files, product_record=product, source_record=source,
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



def test_native_source_photometry_rejects_failed_cwave_audit_and_mismatched_decision(tmp_path):
    from research_discovery.spherex.source_photometry import extract_source_photometry

    files, product, source, compatibility = _photometry_inputs(tmp_path)
    audit_path = Path(files["native_mef_audit_file"]["local_path"])
    report = json.loads(audit_path.read_text(encoding="utf-8"))
    report["checks"]["cwave_cband"]["status"] = "review_required"
    audit_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    files["native_mef_audit_file"] = _record(audit_path)
    with pytest.raises(ValueError, match="native MEF audit check cwave_cband did not pass"):
        extract_source_photometry(
            **files, product_record=product, source_record=source,
            compatibility_decision=compatibility,
            code_commit="1" * 40, output_dir=tmp_path / "failed-cwave",
            epsf_extractor=_fake_epsf_extractor,
        )

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    files, product, source, compatibility = _photometry_inputs(forged_dir)
    forged = {**compatibility, "compatibility_group": "DIFFERENT-GROUP"}
    with pytest.raises(ValueError, match="does not match the decision embedded in the native audit"):
        extract_source_photometry(
            **files, product_record=product, source_record=source,
            compatibility_decision=forged,
            code_commit="1" * 40, output_dir=tmp_path / "forged-decision",
            epsf_extractor=_fake_epsf_extractor,
        )


def test_native_source_photometry_rejects_tampered_audit_file_bytes(tmp_path):
    from research_discovery.spherex.source_photometry import extract_source_photometry

    files, product, source, compatibility = _photometry_inputs(tmp_path)
    audit_path = Path(files["native_mef_audit_file"]["local_path"])
    audit_path.write_text(audit_path.read_text(encoding="utf-8") + "\n ", encoding="utf-8")
    with pytest.raises(ValueError, match="local SHA-256 does not match its archive manifest"):
        extract_source_photometry(
            **files, product_record=product, source_record=source,
            compatibility_decision=compatibility,
            code_commit="1" * 40, output_dir=tmp_path / "tampered-audit",
            epsf_extractor=_fake_epsf_extractor,
        )



def test_native_source_photometry_batch_assembles_two_real_product_epochs(tmp_path):
    from research_discovery.spherex.source_photometry import (
        assemble_source_photometry_series,
        extract_source_photometry,
    )

    files, product, source, compatibility = _photometry_inputs(tmp_path)
    first = extract_source_photometry(
        **files, product_record=product, source_record=source,
        compatibility_decision=compatibility,
        code_commit="1" * 40, output_dir=tmp_path / "out-1",
        epsf_extractor=_fake_epsf_extractor,
    )

    science_2_path = tmp_path / "science-epoch-2.fits"
    with fits.open(files["science_file"]["local_path"], memmap=False) as hdul:
        hdul["IMAGE"].header["OBSID"] = "OBS-2"
        hdul.writeto(science_2_path)
    files_2 = dict(files)
    files_2["science_file"] = _record(science_2_path)
    audit_2_path = tmp_path / "native_mef_audit-epoch-2.json"
    audit_2 = {
        "status": "STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS",
        "science_sha256": files_2["science_file"]["sha256"],
        "spectral_wcs_sha256": files_2["spectral_wcs_file"]["sha256"],
        "solid_angle": {"sha256": files_2["solid_angle_file"]["sha256"]},
        "checks": {
            "cwave_cband": {"status": "pass"},
            "wavelength_units": {"status": "pass"},
            "solid_angle": {"status": "pass"},
        },
        "calibration_compatibility": compatibility,
    }
    audit_2_path.write_text(json.dumps(audit_2, sort_keys=True), encoding="utf-8")
    files_2["native_mef_audit_file"] = _record(audit_2_path)
    product_2 = {
        **product,
        "archive_product_id": product["archive_product_id"] + "-epoch-2",
        "observation_id": "OBS-2",
        "mjd": 60001.0,
    }
    compatibility_2 = dict(compatibility)
    second = extract_source_photometry(
        **files_2, product_record=product_2, source_record=source,
        compatibility_decision=compatibility_2,
        code_commit="1" * 40, output_dir=tmp_path / "out-2",
        epsf_extractor=_fake_epsf_extractor,
    )

    combined = assemble_source_photometry_series(
        [first, second],
        minimum_epochs=2,
        verify_files=True,
        output_path=tmp_path / "verified-series.json",
    )
    assert combined["series_status"] == "verified_multi_epoch_series"
    assert combined["accepted_measurement_count"] == 2
    assert combined["excluded_measurement_count"] == 0
    series = combined["verified_source_timeseries"]["sources"][0]
    summary = series["time_series_summary"]
    assert summary["epoch_count"] == 2
    assert summary["distinct_mjd_count"] == 2
    assert summary["baseline_days"] == pytest.approx(1.0)
    assert summary["usable_multi_epoch_series"] is True
    assert len(combined["input_extraction_results"]) == 2
    assert Path(combined["output_path"]).is_file()


def test_native_source_photometry_batch_rejects_mixed_source_identity(tmp_path):
    from research_discovery.spherex.source_photometry import (
        assemble_source_photometry_series,
        extract_source_photometry,
    )

    files, product, source, compatibility = _photometry_inputs(tmp_path)
    result = extract_source_photometry(
        **files, product_record=product, source_record=source,

        compatibility_decision=compatibility,
        code_commit="1" * 40, output_dir=tmp_path / "out",
        epsf_extractor=_fake_epsf_extractor,
    )
    other = json.loads(json.dumps(result))
    other["sources"][0]["source_id"] = "OTHER-SOURCE"
    with pytest.raises(ValueError, match="different source identities"):
        assemble_source_photometry_series([result, other])



def test_native_source_photometry_rejects_audit_json_with_different_native_file_hashes(tmp_path):
    from research_discovery.spherex.source_photometry import extract_source_photometry

    files, product, source, compatibility = _photometry_inputs(tmp_path)
    audit_path = Path(files["native_mef_audit_file"]["local_path"])
    report = json.loads(audit_path.read_text(encoding="utf-8"))
    report["science_sha256"] = "0" * 64
    audit_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    files["native_mef_audit_file"] = _record(audit_path)
    with pytest.raises(ValueError, match="refers to different science MEF bytes"):
        extract_source_photometry(
            **files, product_record=product, source_record=source,
            compatibility_decision=compatibility,
            code_commit="1" * 40, output_dir=tmp_path / "mismatched-native-audit",
            epsf_extractor=_fake_epsf_extractor,
        )



def test_source_photometry_batch_reverifies_native_audit_and_epsf_bytes(tmp_path):
    from research_discovery.spherex.source_photometry import (
        assemble_source_photometry_series,
        extract_source_photometry,
    )

    files, product, source, compatibility = _photometry_inputs(tmp_path)
    result = extract_source_photometry(
        **files, product_record=product, source_record=source,
        compatibility_decision=compatibility,
        code_commit="1" * 40, output_dir=tmp_path / "out",
        epsf_extractor=_fake_epsf_extractor,
    )
    audit_path = Path(result["extraction_artifacts"]["native_mef_audit_file"]["local_path"])
    audit_bytes = audit_path.read_bytes()
    audit_path.write_bytes(audit_bytes + b" ")
    with pytest.raises(ValueError, match="local SHA-256 does not match its archive manifest"):
        assemble_source_photometry_series([result], verify_files=True)
    audit_path.write_bytes(audit_bytes)

    stamp_path = Path(result["extraction_artifacts"]["epsf_stamp_path"])
    stamp_bytes = stamp_path.read_bytes()
    stamp_path.write_bytes(stamp_bytes + b" ")
    with pytest.raises(ValueError, match="rendered ePSF stamp SHA-256 mismatch"):
        assemble_source_photometry_series([result], verify_files=True)


def test_source_photometry_batch_rejects_output_stamp_for_another_subpixel_position(tmp_path):
    from research_discovery.spherex.source_photometry import (
        assemble_source_photometry_series,
        extract_source_photometry,
    )

    files, product, source, compatibility = _photometry_inputs(tmp_path)
    result = extract_source_photometry(
        **files, product_record=product, source_record=source,
        compatibility_decision=compatibility,
        code_commit="1" * 40, output_dir=tmp_path / "out",
        epsf_extractor=_fake_epsf_extractor,
    )
    stamp_path = Path(result["extraction_artifacts"]["epsf_stamp_path"])
    with fits.open(stamp_path, memmap=False) as hdul:
        hdul[0].header["SRCX"] = float(hdul[0].header["SRCX"]) + 0.25
        hdul.writeto(stamp_path, overwrite=True)
    with pytest.raises(ValueError, match="rendered ePSF stamp SHA-256 mismatch"):
        assemble_source_photometry_series([result], verify_files=True)
