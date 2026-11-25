import hashlib
from pathlib import Path

import pytest


def _write(path: Path, payload: bytes) -> dict:
    path.write_bytes(payload)
    return {
        "uri": f"https://archive.example/{path.name}",
        "local_path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _manifest(tmp_path):
    source_catalogue = _write(tmp_path / "sources.csv", b"source_id,ra,dec\nS1,10,20\n")
    products = []
    measurements = []
    for index, mjd in enumerate((60000.0, 60001.0)):
        product_id = f"PROD-{index}"
        science = _write(tmp_path / f"{product_id}-science.fits", b"SIMPLE  science" + bytes([index]))
        spectral = _write(tmp_path / f"{product_id}-cwave.fits", b"SIMPLE  cwave" + bytes([index]))
        epsf = _write(tmp_path / f"{product_id}-epsf.fits", b"SIMPLE  epsf" + bytes([index]))
        omega = _write(tmp_path / f"{product_id}-omega.fits", b"SIMPLE  omega" + bytes([index]))
        audit_sha = hashlib.sha256(f"audit-{index}".encode()).hexdigest()
        group = f"CAL-{index}"
        products.append({
            "archive_product_id": product_id,
            "observation_id": f"OBS-{index}",
            "mjd": mjd,
            "release": "DR1",
            "detector": "D2",
            "calibration_group": group,
            "science": science,
            "spectral_wcs": spectral,
            "epsf": epsf,
            "solid_angle": omega,
            "native_mef_audit_sha256": audit_sha,
            "compatibility_decision": {
                "status": "compatible",
                "sha256": hashlib.sha256(f"compat-{index}".encode()).hexdigest(),
                "science_sha256": science["sha256"],
                "spectral_wcs_sha256": spectral["sha256"],
                "solid_angle_sha256": omega["sha256"],
            },
        })
        for wave in (3.0, 3.1):
            measurements.append({
                "measurement_id": f"M-{index}-{wave}",
                "source_id": "S1",
                "archive_product_id": product_id,
                "wavelength_um": wave,
                "bandwidth_um": 0.02,
                "flux_jy": 0.12 + index * 0.01,
                "sigma_jy": 0.01,
                "flux_unit": "Jy",
                "fit_status": "success",
                "n_pixels": 11,
                "valid": True,
                "pixel_valid": True,
            })
    return {
        "schema": "chronos-spherex-source-photometry/1.0",
        "dataset_class": "real",
        "extraction_method": {
            "name": "test-PSF-extractor", "version": "1.0",
            "code_commit": "1" * 40,
            "configuration_sha256": "2" * 64,
        },
        "source_catalogue": source_catalogue,
        "sources": [{
            "source_id": "S1", "ra_deg": 10.0, "dec_deg": 20.0,
            "sample_class": "young_stellar_object",
            "classification_reference": "https://catalogue.example/source/S1",
        }],
        "products": products,
        "measurements": measurements,
    }


def test_source_timeseries_binds_measurements_to_verified_native_products(tmp_path):
    from research_discovery.spherex.source_timeseries import assemble_source_timeseries

    result = assemble_source_timeseries(_manifest(tmp_path), minimum_epochs=2)
    source = result["sources"][0]
    assert result["dataset_class"] == "real"
    assert source["time_series_summary"]["epoch_count"] == 2
    assert source["time_series_summary"]["usable_multi_epoch_series"] is True
    assert len(source["observations"]) == 4
    row = source["observations"][0]
    assert row["wavelength_source"] == "CWAVE/CBAND"
    assert row["wavelength_provenance"]["decision"] == "compatible"
    assert row["dataset_class"] == "real"


def test_source_timeseries_rejects_modified_native_bytes_and_duplicate_rows(tmp_path):
    from research_discovery.spherex.source_timeseries import assemble_source_timeseries

    manifest = _manifest(tmp_path)
    Path(manifest["products"][0]["science"]["local_path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        assemble_source_timeseries(manifest)

    clean = _manifest(tmp_path)
    clean["measurements"].append(dict(clean["measurements"][0]))
    with pytest.raises(ValueError, match="measurement_id"):
        assemble_source_timeseries(clean)


def test_source_timeseries_never_silently_accepts_unverified_wavelength_provenance(tmp_path):
    from research_discovery.spherex.source_timeseries import assemble_source_timeseries

    manifest = _manifest(tmp_path)
    manifest["products"][0]["compatibility_decision"]["status"] = "unknown"
    with pytest.raises(ValueError, match="compatible calibration decision"):
        assemble_source_timeseries(manifest)
