import hashlib

import pytest

from research_discovery.spherex.irsa_spectrophotometry import (
    SCHEMA,
    build_source_photometry_manifest,
)


def _sidecar():
    files = {
        "science": {"uri": "https://irsa.ipac.caltech.edu/data/science.fits",
                    "local_path": "/tmp/science.fits", "sha256": "1" * 64},
        "spectral_wcs": {"uri": "https://irsa.ipac.caltech.edu/data/cwave.fits",
                         "local_path": "/tmp/cwave.fits", "sha256": "2" * 64},
        "epsf": {"uri": "https://irsa.ipac.caltech.edu/data/epsf.fits",
                 "local_path": "/tmp/epsf.fits", "sha256": "3" * 64},
        "solid_angle": {"uri": "https://irsa.ipac.caltech.edu/data/omega.fits",
                        "local_path": "/tmp/omega.fits", "sha256": "4" * 64},
    }
    return {
        "schema": SCHEMA,
        "service": {
            "tool_uri": "https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html",
            "job_id": "IRSA-TEST-JOB-1",
            "version": "2026.1",
            "retrieved_utc": "2026-11-26T00:00:00Z",
            "configuration_sha256": "a" * 64,
            "flux_unit": "uJy",
        },
        "source_catalogue": {
            "uri": "https://catalogue.example/sources.csv",
            "local_path": "/tmp/sources.csv",
            "sha256": "5" * 64,
        },
        "sources": [{
            "source_id": "SRC-1",
            "ra_deg": 12.0,
            "dec_deg": -4.0,
            "sample_class": "young_stellar_object",
            "classification_reference": "https://catalogue.example/SRC-1",
            "selection_covariates": {
                "flux_jy": 1e-4, "wavelength_um": 3.1,
                "crowding_index": 0.2, "background_rms": 0.01,
                "epoch_count": 2, "detector_zone": "center",
            },
        }],
        "products": [{
            "lvf_id": "LVF-1",
            "detector": "D2",
            "release": "DR1",
            "archive_product_id": "PROD-1",
            "observation_id": "OBS-1",
            "mjd": 60800.5,
            "calibration_group": "DR1:D2:CAL-1",
            **files,
            "native_mef_audit_sha256": "6" * 64,
            "compatibility_decision": {
                "status": "compatible",
                "sha256": "7" * 64,
                "science_sha256": "1" * 64,
                "spectral_wcs_sha256": "2" * 64,
                "solid_angle_sha256": "4" * 64,
            },
        }],
        "photometry_quality_policy": {
            "policy_id": "IRSA-PSF-QUALITY-v1",
            "flag_policy": "photometry",
            "fit_ql_max": 1.5,
            "max_abs_background_to_flux_ratio": 0.2,
        },
        "image_pixel_origin": 1,
        "source_position_tolerance_arcsec": 0.5,
        "image_wcs_tolerance_pixels": 0.4,
    }


def _row(**overrides):
    result = {
        "wavelength": 3.10,
        "flux": 100.0,
        "flux_err": 5.0,
        "lambda_width": 0.02,
        "flags": 0,
        "fit_ql": 1.1,
        "flux_bkg": 2.0,
        "lvf_id": "LVF-1",
        "det_id": "D2",
        "deep_flg": False,
        "mjd": 60800.5,
        "data_collection": "SPHEREx DR1",
        "x_image": 101.25,
        "y_image": 99.75,
        "ra": 12.0,
        "dec": -4.0,
    }
    result.update(overrides)
    return result


def test_irsa_adapter_maps_measurements_to_exact_products_and_converts_microjy():
    manifest, audit = build_source_photometry_manifest(
        [_row()],
        _sidecar(),
        export_sha256="8" * 64,
        sidecar_sha256="9" * 64,
    )
    row = manifest["measurements"][0]
    assert manifest["schema"] == "chronos-spherex-source-photometry/1.0"
    assert manifest["extraction_method"]["kind"] == "hosted_service"
    assert manifest["extraction_method"]["job_id"] == "IRSA-TEST-JOB-1"
    assert row["source_id"] == "SRC-1"
    assert row["archive_product_id"] == "PROD-1"
    assert row["mjd"] == pytest.approx(60800.5)
    assert row["wavelength_um"] == pytest.approx(3.10)
    assert row["bandwidth_um"] == pytest.approx(0.02)
    assert row["flux_jy"] == pytest.approx(1e-4)
    assert row["sigma_jy"] == pytest.approx(5e-6)
    assert row["pixel_position"]["x"] == pytest.approx(100.25)
    assert row["pixel_position"]["y"] == pytest.approx(98.75)
    assert row["pixel_position"]["convention"] == "zero-based"
    assert row["photometry_method"] == "IRSA_SPHEREX_SPECTROPHOTOMETRY_TOOL"
    assert row["quality_policy_sha256"] == manifest["photometry_quality_policy"]["sha256"]
    assert audit["measurement_rows_accepted_for_native_verification"] == 1
    assert audit["measurement_rows_excluded"] == 0


def test_irsa_adapter_keeps_quality_rejections_in_audit_not_analysis_rows():
    from research_discovery.spherex.flag_policy import FLAG_BITS

    rows = [
        _row(),
        _row(mjd=60801.5, flags=1 << FLAG_BITS["HOT"]),
        _row(mjd=60802.5, fit_ql=2.0),
        _row(mjd=60803.5, flux_bkg=100.0),
    ]
    manifest, audit = build_source_photometry_manifest(
        rows, _sidecar(), export_sha256="8" * 64, sidecar_sha256="9" * 64
    )
    assert len(manifest["measurements"]) == 1
    assert audit["measurement_rows_excluded"] == 3
    reasons = [reason for row in audit["excluded_rows"] for reason in row["reasons"]]
    assert "excluded_by_predeclared_photometry_flag_policy" in reasons
    assert "fit_ql_missing_or_outside_predeclared_quality_limit" in reasons
    assert "background_fraction_missing_or_outside_predeclared_quality_limit" in reasons


def test_irsa_adapter_requires_exact_lvf_product_and_declared_coordinate_origin():
    with pytest.raises(ValueError, match="no exact LVF/detector/release product mapping"):
        build_source_photometry_manifest(
            [_row(lvf_id="UNKNOWN-LVF")],
            _sidecar(),
            export_sha256="8" * 64,
            sidecar_sha256="9" * 64,
        )
    sidecar = _sidecar()
    sidecar["image_pixel_origin"] = None
    with pytest.raises(ValueError, match="image_pixel_origin"):
        build_source_photometry_manifest(
            [_row()], sidecar,
            export_sha256="8" * 64,
            sidecar_sha256="9" * 64,
        )


def test_irsa_adapter_rejects_qr2_and_ambiguous_product_mapping():
    with pytest.raises(ValueError, match="QR2"):
        build_source_photometry_manifest(
            [_row(data_collection="QR2")], _sidecar(),
            export_sha256="8" * 64,
            sidecar_sha256="9" * 64,
        )
    sidecar = _sidecar()
    sidecar["products"].append(dict(sidecar["products"][0], archive_product_id="PROD-2"))
    with pytest.raises(ValueError, match="ambiguous duplicate LVF-to-product mapping"):
        build_source_photometry_manifest(
            [_row()], sidecar,
            export_sha256="8" * 64,
            sidecar_sha256="9" * 64,
        )



def test_irsa_adapter_enforces_twenty_target_job_limit():
    sidecar = _sidecar()
    sidecar["sources"] = [
        {
            **sidecar["sources"][0],
            "source_id": f"SRC-{index}",
            "ra_deg": 12.0 + index * 0.001,
        }
        for index in range(21)
    ]
    with pytest.raises(ValueError, match="at most 20 targets"):
        build_source_photometry_manifest(
            [_row()],
            sidecar,
            export_sha256="8" * 64,
            sidecar_sha256="9" * 64,
        )
