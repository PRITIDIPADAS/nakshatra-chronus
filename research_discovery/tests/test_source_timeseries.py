import hashlib
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits


def _write(path: Path, payload: bytes) -> dict:
    path.write_bytes(payload)
    return {
        "uri": f"https://archive.example/{path.name}",
        "local_path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _write_fits(path: Path, hdus) -> dict:
    fits.HDUList(hdus).writeto(path, overwrite=True)
    return {
        "uri": f"https://archive.example/{path.name}",
        "local_path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _manifest(tmp_path):
    source_catalogue = _write(tmp_path / "sources.csv", b"source_id,ra,dec\nS1,10,20\n")
    products = []
    measurements = []
    shape = (32, 32)
    for index, mjd in enumerate((60000.0, 60001.0)):
        product_id = f"PROD-{index}"
        science_header = fits.Header()
        science_header["DETECTOR"] = 2
        science_header["OBSID"] = f"OBS-{index}"
        science_header["BUNIT"] = "MJy / sr"
        science = _write_fits(tmp_path / f"{product_id}-science.fits", [
            fits.PrimaryHDU(),
            fits.ImageHDU(np.full(shape, 0.12 + index * 0.01, dtype=np.float32),
                          header=science_header, name="IMAGE"),
            fits.ImageHDU(np.full(shape, 1e-4, dtype=np.float32), name="VARIANCE"),
        ])
        cwave = np.full(shape, 3.0, dtype=np.float32)
        cwave[11, 11] = 3.1
        cband = np.full(shape, 0.02, dtype=np.float32)
        spectral_header = fits.Header()
        spectral_header["DETECTOR"] = 2
        spectral_header["BUNIT"] = "um"
        spectral = _write_fits(tmp_path / f"{product_id}-cwave.fits", [
            fits.PrimaryHDU(),
            fits.ImageHDU(cwave, header=spectral_header, name="CWAVE"),
            fits.ImageHDU(cband, header=spectral_header, name="CBAND"),
        ])
        epsf = _write(tmp_path / f"{product_id}-epsf.fits", b"epsf bytes")
        area_header = fits.Header()
        area_header["DETECTOR"] = 2
        area_header["BUNIT"] = "arcsec2"
        omega = _write_fits(tmp_path / f"{product_id}-omega.fits", [
            fits.PrimaryHDU(),
            fits.ImageHDU(np.full(shape, 38.0, dtype=np.float32),
                          header=area_header, name="IMAGE"),
        ])
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
        for wave, pixel_index in ((3.0, {"x": 10, "y": 10}), (3.1, {"x": 11, "y": 11})):
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
                "pixel_index": pixel_index,
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


def test_source_timeseries_binds_measurements_to_native_products_and_exact_wavelength_pixels(tmp_path):
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
    assert row["wavelength_provenance"]["pixel_index"] == {
        "x": 10, "y": 10, "convention": "zero-based"
    }
    assert row["wavelength_provenance"]["cwave_pixel_value_um"] == pytest.approx(3.0)
    assert row["wavelength_provenance"]["cband_pixel_value_um"] == pytest.approx(0.02)
    assert row["wavelength_provenance"]["solid_angle_pixel_value"] == pytest.approx(38.0)
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


def test_source_timeseries_rejects_pixel_wavelength_not_matching_native_cwave(tmp_path):
    from research_discovery.spherex.source_timeseries import assemble_source_timeseries

    manifest = _manifest(tmp_path)
    manifest["measurements"][0]["wavelength_um"] = 3.15
    with pytest.raises(ValueError, match="does not match the native CWAVE"):
        assemble_source_timeseries(manifest)


def test_source_timeseries_rejects_pixel_bandwidth_not_matching_native_cband(tmp_path):
    from research_discovery.spherex.source_timeseries import assemble_source_timeseries

    manifest = _manifest(tmp_path)
    manifest["measurements"][0]["bandwidth_um"] = 0.04
    with pytest.raises(ValueError, match="does not match the native CBAND"):
        assemble_source_timeseries(manifest)


def test_source_timeseries_requires_explicit_valid_pixel_index_and_validity(tmp_path):
    from research_discovery.spherex.source_timeseries import assemble_source_timeseries

    manifest = _manifest(tmp_path)
    manifest["measurements"][0].pop("pixel_index")
    with pytest.raises(ValueError, match="pixel_index"):
        assemble_source_timeseries(manifest)

    manifest = _manifest(tmp_path)
    manifest["measurements"][0]["pixel_valid"] = False
    with pytest.raises(ValueError, match="pixel_valid"):
        assemble_source_timeseries(manifest)


def test_source_timeseries_rejects_incompatible_product_and_array_geometry(tmp_path):
    from research_discovery.spherex.source_timeseries import assemble_source_timeseries

    manifest = _manifest(tmp_path)
    path = Path(manifest["products"][0]["solid_angle"]["local_path"])
    fits.HDUList([
        fits.PrimaryHDU(),
        fits.ImageHDU(np.ones((16, 16), dtype=np.float32),
                      header=fits.Header({"DETECTOR": 2, "BUNIT": "arcsec2"}),
                      name="IMAGE"),
    ]).writeto(path, overwrite=True)
    updated_area_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest["products"][0]["solid_angle"]["sha256"] = updated_area_sha
    manifest["products"][0]["compatibility_decision"]["solid_angle_sha256"] = updated_area_sha
    with pytest.raises(ValueError, match="solid-angle dimensions"):
        assemble_source_timeseries(manifest)


def test_source_timeseries_never_silently_accepts_unverified_wavelength_provenance(tmp_path):
    from research_discovery.spherex.source_timeseries import assemble_source_timeseries

    manifest = _manifest(tmp_path)
    manifest["products"][0]["compatibility_decision"]["status"] = "unknown"
    with pytest.raises(ValueError, match="compatible calibration decision"):
        assemble_source_timeseries(manifest)



def test_source_timeseries_requires_common_native_passband_across_epochs(tmp_path):
    from research_discovery.spherex.source_timeseries import assemble_source_timeseries

    manifest = _manifest(tmp_path)
    second_product = manifest["products"][1]
    spectral_path = Path(second_product["spectral_wcs"]["local_path"])
    with fits.open(spectral_path, memmap=False) as hdul:
        hdus = [hdu.copy() for hdu in hdul]
        hdus["CWAVE"].data = np.asarray(hdus["CWAVE"].data, dtype=np.float32) + 0.2
    fits.HDUList(hdus).writeto(spectral_path, overwrite=True)
    new_sha = hashlib.sha256(spectral_path.read_bytes()).hexdigest()
    second_product["spectral_wcs"]["sha256"] = new_sha
    second_product["compatibility_decision"]["spectral_wcs_sha256"] = new_sha
    for row in manifest["measurements"]:
        if row["archive_product_id"] == second_product["archive_product_id"]:
            row["wavelength_um"] += 0.2

    result = assemble_source_timeseries(manifest, minimum_epochs=2)
    summary = result["sources"][0]["time_series_summary"]

    assert summary["epoch_count"] == 2
    assert summary["usable_multi_epoch_series"] is False
    assert summary["temporal_band_comparability"]["usable_temporal_band_cluster_count"] == 0


def test_temporal_band_clusters_accept_overlapping_cwave_cband_samples():
    from research_discovery.spherex.source_timeseries import _summarize_temporal_band_clusters

    rows = [
        {"observation_id": "OBS-A", "mjd": 60000.0, "wavelength_um": 3.10, "bandwidth_um": 0.02, "measurement_id": "M-A"},
        {"observation_id": "OBS-B", "mjd": 60001.0, "wavelength_um": 3.105, "bandwidth_um": 0.02, "measurement_id": "M-B"},
        {"observation_id": "OBS-C", "mjd": 60002.0, "wavelength_um": 3.102, "bandwidth_um": 0.018, "measurement_id": "M-C"},
    ]
    result = _summarize_temporal_band_clusters(rows, minimum_epochs=3)

    assert result["usable_multi_epoch_series"] is True
    assert result["usable_temporal_band_cluster_count"] == 1
    assert result["usable_temporal_band_clusters"][0]["distinct_epoch_count"] == 3


def test_temporal_band_clusters_reject_non_overlapping_wavelength_visits():
    from research_discovery.spherex.source_timeseries import _summarize_temporal_band_clusters

    rows = [
        {"observation_id": "OBS-A", "mjd": 60000.0, "wavelength_um": 3.00, "bandwidth_um": 0.02, "measurement_id": "M-A"},
        {"observation_id": "OBS-B", "mjd": 60001.0, "wavelength_um": 3.10, "bandwidth_um": 0.02, "measurement_id": "M-B"},
        {"observation_id": "OBS-C", "mjd": 60002.0, "wavelength_um": 3.20, "bandwidth_um": 0.02, "measurement_id": "M-C"},
    ]
    result = _summarize_temporal_band_clusters(rows, minimum_epochs=3)

    assert result["usable_multi_epoch_series"] is False
    assert result["usable_temporal_band_cluster_count"] == 0
    assert all(row["distinct_epoch_count"] == 1 for row in result["all_clusters"])
