"""Assemble a provenance-verified source-level SPHEREx spectral time series.

This module ingests measurements produced by a separately documented source
extractor. It does not extract pixels or manufacture fluxes. It verifies the
local native products, wavelength/calibration provenance and measurement
records, then binds every source measurement to its exact exposure/product.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from chronos_causal.wavelength_gate import validate_science_wavelength

SCHEMA = "chronos-spherex-source-timeseries/1.0"
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
PRODUCT_ROLES = ("science", "spectral_wcs", "epsf", "solid_angle")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha(value: Any, label: str) -> str:
    text = str(value or "")
    if not SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a 64-character SHA-256 hex digest")
    return text.lower()


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be numeric") from None
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _verified_file(record: Mapping[str, Any], label: str, *, verify_files: bool) -> dict[str, Any]:
    uri = str(record.get("uri", "")).strip()
    path = str(record.get("local_path", "")).strip()
    expected = _require_sha(record.get("sha256"), f"{label}.sha256")
    if not uri.startswith("https://"):
        raise ValueError(f"{label}.uri must be the exact HTTPS archive URI")
    if not path:
        raise ValueError(f"{label}.local_path is required to verify native bytes")
    local = Path(path)
    if not local.is_file():
        raise FileNotFoundError(f"{label} bytes are unavailable: {local}")
    actual = sha256_file(local) if verify_files else expected
    if actual.lower() != expected:
        raise ValueError(f"{label} local SHA-256 does not match its manifest")
    return {"uri": uri, "local_path": str(local), "sha256": expected, "bytes": local.stat().st_size}




def _verify_native_pixel(
    product: Mapping[str, Any],
    measurement: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a measurement's zero-based pixel against its native FITS maps."""
    measurement_id = str(measurement.get("measurement_id", "")).strip()
    if measurement.get("pixel_valid") is not True:
        raise ValueError(f"measurement {measurement_id} pixel_valid must be explicitly true")
    pixel_index = measurement.get("pixel_index")
    if not isinstance(pixel_index, Mapping):
        raise ValueError(
            f"measurement {measurement_id} requires a zero-based pixel_index object with x and y"
        )
    x_raw, y_raw = pixel_index.get("x"), pixel_index.get("y")
    try:
        x, y = int(x_raw), int(y_raw)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"measurement {measurement_id} pixel_index x/y must be integers") from None
    if (
        isinstance(x_raw, bool) or isinstance(y_raw, bool)
        or x != x_raw or y != y_raw or x < 0 or y < 0
    ):
        raise ValueError(f"measurement {measurement_id} pixel_index is not a valid zero-based image pixel")

    try:
        from astropy.io import fits
    except ImportError as exc:
        raise RuntimeError("Astropy is required to verify native CWAVE/CBAND and image pixels") from exc

    files = product["files"]
    try:
        with (
            fits.open(files["science"]["local_path"], memmap=True) as science_hdul,
            fits.open(files["spectral_wcs"]["local_path"], memmap=True) as spectral_hdul,
            fits.open(files["solid_angle"]["local_path"], memmap=True) as area_hdul,
        ):
            for name in ("IMAGE", "VARIANCE"):
                if name not in science_hdul:
                    raise ValueError(f"product {product['archive_product_id']} science MEF is missing {name}")
            for name in ("CWAVE", "CBAND"):
                if name not in spectral_hdul:
                    raise ValueError(f"product {product['archive_product_id']} spectral-WCS file is missing {name}")
            area_hdu = area_hdul["IMAGE"] if "IMAGE" in area_hdul else next(
                (hdu for hdu in area_hdul[1:] if getattr(hdu, "data", None) is not None),
                None,
            )
            if area_hdu is None:
                raise ValueError(f"product {product['archive_product_id']} solid-angle file has no image extension")

            image_hdu = science_hdul["IMAGE"]
            variance_hdu = science_hdul["VARIANCE"]
            cwave_hdu = spectral_hdul["CWAVE"]
            cband_hdu = spectral_hdul["CBAND"]
            image = np.asarray(image_hdu.data)
            variance = np.asarray(variance_hdu.data)
            cwave = np.asarray(cwave_hdu.data)
            cband = np.asarray(cband_hdu.data)
            solid_angle = np.asarray(area_hdu.data)

            if image.ndim != 2 or variance.shape != image.shape:
                raise ValueError(f"product {product['archive_product_id']} IMAGE and VARIANCE must be aligned 2D arrays")
            if cwave.shape != image.shape or cband.shape != image.shape:
                raise ValueError(f"product {product['archive_product_id']} CWAVE/CBAND dimensions do not match the native science image")
            if solid_angle.shape != image.shape:
                raise ValueError(f"product {product['archive_product_id']} solid-angle dimensions do not match the native science image")
            if y >= image.shape[0] or x >= image.shape[1]:
                raise ValueError(f"measurement {measurement_id} pixel_index lies outside the native image")

            image_unit = str(image_hdu.header.get("BUNIT", "")).lower().replace(" ", "")
            cwave_unit = str(cwave_hdu.header.get("BUNIT", "")).strip().lower()
            cband_unit = str(cband_hdu.header.get("BUNIT", "")).strip().lower()
            area_unit = str(area_hdu.header.get("BUNIT", "")).strip().lower().replace(" ", "")
            if image_unit not in {"mjy/sr", "mjy*sr-1"}:
                raise ValueError(f"product {product['archive_product_id']} IMAGE must be calibrated in MJy/sr")
            if cwave_unit not in {"um", "micron", "microns"}:
                raise ValueError(f"product {product['archive_product_id']} CWAVE BUNIT must be microns")
            if cband_unit not in {"um", "micron", "microns"}:
                raise ValueError(f"product {product['archive_product_id']} CBAND BUNIT must be microns")
            if area_unit not in {"arcsec2", "arcsec^2", "arcsec**2", "sr"}:
                raise ValueError(f"product {product['archive_product_id']} solid-angle BUNIT must be arcsec2 or sr")

            expected_detector = int(product["detector"][1:])
            for label, hdu in (
                ("science IMAGE", image_hdu),
                ("CWAVE", cwave_hdu),
                ("CBAND", cband_hdu),
                ("solid-angle IMAGE", area_hdu),
            ):
                detector_value = hdu.header.get("DETECTOR")
                try:
                    actual_detector = int(str(detector_value).strip())
                except (TypeError, ValueError):
                    raise ValueError(
                        f"product {product['archive_product_id']} {label} is missing a numeric DETECTOR header"
                    ) from None
                if actual_detector != expected_detector:
                    raise ValueError(
                        f"product {product['archive_product_id']} {label} detector {actual_detector} "
                        f"does not match {product['detector']}"
                    )
            observed_id = str(image_hdu.header.get("OBSID", "")).strip()
            if not observed_id or observed_id != product["observation_id"]:
                raise ValueError(
                    f"product {product['archive_product_id']} science OBSID does not match the archive observation_id"
                )

            actual_wavelength = float(cwave[y, x])
            actual_bandwidth = float(cband[y, x])
            pixel_area = float(solid_angle[y, x])
            pixel_flux = float(image[y, x])
            pixel_variance = float(variance[y, x])
            wavelength = _finite(measurement.get("wavelength_um"), f"measurement {measurement_id} wavelength")
            bandwidth = _finite(measurement.get("bandwidth_um"), f"measurement {measurement_id} bandwidth")
            if not math.isfinite(actual_wavelength) or actual_wavelength <= 0:
                raise ValueError(f"measurement {measurement_id} points to an invalid CWAVE pixel")
            if not math.isfinite(actual_bandwidth) or actual_bandwidth <= 0:
                raise ValueError(f"measurement {measurement_id} points to an invalid CBAND pixel")
            if not math.isclose(wavelength, actual_wavelength, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError(f"measurement {measurement_id} wavelength_um does not match the native CWAVE pixel")
            if not math.isclose(bandwidth, actual_bandwidth, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError(f"measurement {measurement_id} bandwidth_um does not match the native CBAND pixel")
            if not math.isfinite(pixel_area) or pixel_area <= 0:
                raise ValueError(f"measurement {measurement_id} points to an invalid solid-angle pixel")
            if not math.isfinite(pixel_flux):
                raise ValueError(f"measurement {measurement_id} points to a non-finite science IMAGE pixel")
            if not math.isfinite(pixel_variance) or pixel_variance <= 0:
                raise ValueError(f"measurement {measurement_id} points to an invalid VARIANCE pixel")
    except OSError as exc:
        raise ValueError(
            f"measurement {measurement_id} native FITS file could not be read: {exc}"
        ) from exc

    return {
        "pixel_index": {"x": x, "y": y, "convention": "zero-based"},
        "cwave_pixel_value_um": actual_wavelength,
        "cband_pixel_value_um": actual_bandwidth,
        "cwave_abs_error_um": abs(wavelength - actual_wavelength),
        "cband_abs_error_um": abs(bandwidth - actual_bandwidth),
        "solid_angle_pixel_value": pixel_area,
        "solid_angle_unit": area_unit,
        "science_image_pixel_value": pixel_flux,
        "science_variance_pixel_value": pixel_variance,
        "science_image_unit": "MJy/sr",
        "native_image_shape": list(image.shape),
        "native_map_shape": list(cwave.shape),
        "spectral_pixel_value_tolerance_um": 1e-6,
    }

def assemble_source_timeseries(
    manifest: Mapping[str, Any],
    *,
    minimum_epochs: int = 2,
    verify_files: bool = True,
) -> dict[str, Any]:
    """Validate and assemble measured source flux rows into auditable time series.

    Input measurements are not recalculated. A successful result means the
    supplied extraction rows are bound to verified DR1/QR3 native bytes and
    calibration records; it is not an independent validation of the extractor.
    """
    if not isinstance(manifest, Mapping) or manifest.get("schema") != "chronos-spherex-source-photometry/1.0":
        raise ValueError("source photometry manifest schema must be chronos-spherex-source-photometry/1.0")
    if str(manifest.get("dataset_class", "")).lower() != "real":
        raise ValueError("source-level archive measurements must be explicitly labelled real")
    if isinstance(minimum_epochs, bool) or int(minimum_epochs) != minimum_epochs or minimum_epochs < 2:
        raise ValueError("minimum_epochs must be an integer of at least two")

    extractor = manifest.get("extraction_method")
    if not isinstance(extractor, Mapping):
        raise ValueError("a versioned extraction_method record is required")
    for key in ("name", "version", "code_commit"):
        if not str(extractor.get(key, "")).strip():
            raise ValueError(f"extraction_method.{key} is required")
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", str(extractor["code_commit"])):
        raise ValueError("extraction_method.code_commit must be a full Git commit SHA")
    extraction_config_sha = _require_sha(extractor.get("configuration_sha256"), "extraction configuration SHA-256")

    source_catalogue = manifest.get("source_catalogue")
    if not isinstance(source_catalogue, Mapping):
        raise ValueError("a checksum-linked source_catalogue is required")
    verified_catalogue = _verified_file(source_catalogue, "source_catalogue", verify_files=verify_files)

    source_records = manifest.get("sources")
    if not isinstance(source_records, list) or not source_records:
        raise ValueError("sources must be a non-empty catalogue-linked list")
    sources: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(source_records):
        if not isinstance(source, Mapping):
            raise ValueError(f"source {index} must be an object")
        source_id = str(source.get("source_id", "")).strip()
        if not source_id or source_id in sources:
            raise ValueError("source_id values must be non-empty and unique")
        ra = _finite(source.get("ra_deg"), f"source {source_id} RA")
        dec = _finite(source.get("dec_deg"), f"source {source_id} Dec")
        if not 0 <= ra < 360 or not -90 <= dec <= 90:
            raise ValueError(f"source {source_id} has invalid ICRS coordinates")
        sources[source_id] = {
            "source_id": source_id,
            "ra_deg": ra,
            "dec_deg": dec,
            "sample_class": source.get("sample_class"),
            "classification_reference": source.get("classification_reference"),
            "selection_covariates": source.get("selection_covariates"),
        }

    raw_products = manifest.get("products")
    if not isinstance(raw_products, list) or not raw_products:
        raise ValueError("products must contain the exact native science and calibration products")
    products: dict[str, dict[str, Any]] = {}
    observation_keys: set[tuple[str, str, str]] = set()
    for index, product in enumerate(raw_products):
        if not isinstance(product, Mapping):
            raise ValueError(f"product {index} must be an object")
        product_id = str(product.get("archive_product_id", "")).strip()
        observation_id = str(product.get("observation_id", "")).strip()
        detector = str(product.get("detector", "")).upper().strip()
        release = str(product.get("release", "")).upper().strip()
        calibration_group = str(product.get("calibration_group", "")).strip()
        mjd = _finite(product.get("mjd"), f"product {product_id} MJD")
        if not product_id or product_id in products or not observation_id:
            raise ValueError("archive_product_id values must be unique and observation_id non-empty")
        if detector not in {f"D{i}" for i in range(1, 7)}:
            raise ValueError(f"product {product_id} must declare exact detector D1-D6")
        if release not in {"DR1", "QR3"}:
            raise ValueError(f"product {product_id} must use DR1 or QR3")
        if not calibration_group:
            raise ValueError(f"product {product_id} must declare a calibration_group")
        epoch_key = (observation_id, detector, release)
        if epoch_key in observation_keys:
            raise ValueError(f"duplicate observation/detector/release product {epoch_key}")
        observation_keys.add(epoch_key)

        compatibility = product.get("compatibility_decision")
        if not isinstance(compatibility, Mapping) or compatibility.get("status") != "compatible":
            raise ValueError(f"product {product_id} lacks an explicit compatible calibration decision")
        compatibility_sha = _require_sha(compatibility.get("sha256"), f"{product_id} compatibility decision SHA-256")
        files = {}
        for role in PRODUCT_ROLES:
            record = product.get(role)
            if not isinstance(record, Mapping):
                raise ValueError(f"product {product_id} is missing {role} file provenance")
            files[role] = _verified_file(record, f"{product_id}.{role}", verify_files=verify_files)
        spectral_sha = files["spectral_wcs"]["sha256"]
        science_sha = files["science"]["sha256"]
        solid_angle_sha = files["solid_angle"]["sha256"]
        if compatibility.get("science_sha256", "").lower() != science_sha:
            raise ValueError(f"product {product_id} compatibility decision refers to a different science MEF")
        if compatibility.get("spectral_wcs_sha256", "").lower() != spectral_sha:
            raise ValueError(f"product {product_id} compatibility decision refers to a different spectral-WCS file")
        if compatibility.get("solid_angle_sha256", "").lower() != solid_angle_sha:
            raise ValueError(f"product {product_id} compatibility decision refers to a different solid-angle file")
        products[product_id] = {
            "archive_product_id": product_id,
            "observation_id": observation_id,
            "mjd": mjd,
            "release": release,
            "detector": detector,
            "calibration_group": calibration_group,
            "compatibility_decision_sha256": compatibility_sha,
            "files": files,
        }

    raw_measurements = manifest.get("measurements")
    if not isinstance(raw_measurements, list) or not raw_measurements:
        raise ValueError("measurements must contain source-level extracted photometry rows")
    seen_measurements: set[str] = set()
    seen_keys: set[tuple[str, str, float, str]] = set()
    rows_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    product_measurement_counts: dict[str, int] = defaultdict(int)
    for index, measurement in enumerate(raw_measurements):
        if not isinstance(measurement, Mapping):
            raise ValueError(f"measurement {index} must be an object")
        measurement_id = str(measurement.get("measurement_id", "")).strip()
        source_id = str(measurement.get("source_id", "")).strip()
        product_id = str(measurement.get("archive_product_id", "")).strip()
        if not measurement_id or measurement_id in seen_measurements:
            raise ValueError("measurement_id values must be non-empty and globally unique")
        seen_measurements.add(measurement_id)
        if source_id not in sources:
            raise ValueError(f"measurement {measurement_id} references an unknown source_id")
        if product_id not in products:
            raise ValueError(f"measurement {measurement_id} references an unknown archive_product_id")
        product = products[product_id]
        wavelength = _finite(measurement.get("wavelength_um"), f"measurement {measurement_id} wavelength")
        bandwidth = _finite(measurement.get("bandwidth_um"), f"measurement {measurement_id} bandwidth")
        flux = _finite(measurement.get("flux_jy"), f"measurement {measurement_id} flux_jy")
        sigma = _finite(measurement.get("sigma_jy"), f"measurement {measurement_id} sigma_jy")
        if wavelength <= 0 or bandwidth <= 0 or sigma <= 0:
            raise ValueError(f"measurement {measurement_id} wavelength, bandwidth and sigma must be positive")
        native_pixel = _verify_native_pixel(product, measurement)
        if measurement.get("fit_status") != "success":
            raise ValueError(f"measurement {measurement_id} was not produced by a successful extraction fit")
        raw_n_pixels = measurement.get("n_pixels")
        try:
            n_pixels = int(raw_n_pixels)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"measurement {measurement_id} must record a positive integer n_pixels") from None
        if isinstance(raw_n_pixels, bool) or n_pixels < 1 or n_pixels != raw_n_pixels:
            raise ValueError(f"measurement {measurement_id} must record a positive integer n_pixels")
        if str(measurement.get("flux_unit", "")).strip() != "Jy":
            raise ValueError(f"measurement {measurement_id} integrated flux unit must be Jy")
        if measurement.get("valid") is not True:
            raise ValueError(f"measurement {measurement_id} is not marked valid")
        key = (source_id, product_id, round(wavelength, 8), product["calibration_group"])
        if key in seen_keys:
            raise ValueError(f"duplicate source/product/wavelength measurement row: {key}")
        seen_keys.add(key)

        wavelength_provenance = {
            "decision": "compatible",
            "compatibility_group": product["calibration_group"],
            "science_sha256": product["files"]["science"]["sha256"],
            "calibration_sha256": product["files"]["spectral_wcs"]["sha256"],
            "native_mef_audit_sha256": _require_sha(
                product.get("native_mef_audit_sha256"), f"{product_id} native MEF audit SHA-256"
            ),
            "solid_angle_sha256": product["files"]["solid_angle"]["sha256"],
            "science_uri": product["files"]["science"]["uri"],
            "calibration_uri": product["files"]["spectral_wcs"]["uri"],
            "solid_angle_uri": product["files"]["solid_angle"]["uri"],
            **native_pixel,
            "pixel_valid": True,
        }
        row = {
            "source_id": source_id,
            "measurement_id": measurement_id,
            "observation_id": product["observation_id"],
            "archive_product_id": product_id,
            "mjd": product["mjd"],
            "release": product["release"],
            "detector": product["detector"],
            "wavelength_um": wavelength,
            "bandwidth_um": bandwidth,
            "flux": flux,
            "sigma": sigma,
            "flux_unit": "Jy",
            "valid": True,
            "calibration_group": product["calibration_group"],
            "wavelength_source": "CWAVE/CBAND",
            "wavelength_unit": "um",
            "wavelength_validated": True,
            "wavelength_provenance": wavelength_provenance,
            "dataset_class": "real",
            "extraction_method": dict(extractor),
            "quality_flags": list(measurement.get("quality_flags") or []),
            "fit_status": "success",
            "n_pixels": n_pixels,
        }
        validate_science_wavelength(row, index=index)
        rows_by_source[source_id].append(row)
        product_measurement_counts[product_id] += 1

    source_series = []
    for source_id, source in sorted(sources.items()):
        rows = sorted(
            rows_by_source.get(source_id, []),
            key=lambda row: (row["mjd"], row["wavelength_um"], row["archive_product_id"]),
        )
        epoch_keys = {(row["observation_id"], row["mjd"]) for row in rows}
        mjds = sorted({row["mjd"] for row in rows})
        source_series.append({
            **source,
            "dataset_class": "real",
            "observations": rows,
            "time_series_summary": {
                "measurement_count": len(rows),
                "epoch_count": len(epoch_keys),
                "distinct_mjd_count": len(mjds),
                "baseline_days": (max(mjds) - min(mjds)) if len(mjds) > 1 else 0.0,
                "median_cadence_days": (
                    float(np.median(np.diff(mjds))) if len(mjds) > 1 else None
                ),
                "wavelength_count": len({row["wavelength_um"] for row in rows}),
                "calibration_groups": sorted({row["calibration_group"] for row in rows}),
                "usable_multi_epoch_series": len(epoch_keys) >= int(minimum_epochs),
            },
        })

    canonical = {
        "schema": SCHEMA,
        "dataset_class": "real",
        "extraction_method": dict(extractor),
        "extraction_configuration_sha256": extraction_config_sha,
        "source_catalogue": verified_catalogue,
        "products": list(products.values()),
        "sources": source_series,
        "measurement_count": len(seen_measurements),
        "minimum_epochs": int(minimum_epochs),
        "note": "Assembled from supplied extraction measurements; this module verifies provenance but does not re-extract pixels.",
    }
    canonical_bytes = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False, default=str,
    ).encode("utf-8")
    canonical["source_timeseries_manifest_sha256"] = hashlib.sha256(canonical_bytes).hexdigest()
    canonical["product_measurement_counts"] = dict(sorted(product_measurement_counts.items()))
    canonical["usable_source_count"] = sum(
        row["time_series_summary"]["usable_multi_epoch_series"] for row in source_series
    )
    canonical["unusable_source_count"] = len(source_series) - canonical["usable_source_count"]
    return canonical
