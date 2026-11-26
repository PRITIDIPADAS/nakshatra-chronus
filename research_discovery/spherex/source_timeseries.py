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




def _bilinear_sample(array: np.ndarray, x: float, y: float, label: str) -> float:
    """Sample a native detector map at a sub-pixel position without extrapolation."""
    values = np.asarray(array, dtype=float)
    if values.ndim != 2:
        raise ValueError(f"{label} must be a two-dimensional native map")
    x0, y0 = math.floor(x), math.floor(y)
    dx, dy = x - x0, y - y0
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        if x0 < 0 or y0 < 0 or y0 >= values.shape[0] or x0 >= values.shape[1]:
            raise ValueError(f"{label} sample lies outside the native map")
        samples = np.asarray([values[y0, x0]], dtype=float)
        weights = np.asarray([1.0])
    else:
        x1, y1 = x0 + 1, y0 + 1
        if x0 < 0 or y0 < 0 or x1 >= values.shape[1] or y1 >= values.shape[0]:
            raise ValueError(f"{label} interpolation footprint lies outside the native map")
        samples = np.asarray([
            values[y0, x0], values[y0, x1],
            values[y1, x0], values[y1, x1],
        ], dtype=float)
        weights = np.asarray([
            (1 - dx) * (1 - dy),
            dx * (1 - dy),
            (1 - dx) * dy,
            dx * dy,
        ])
    if np.any(~np.isfinite(samples)):
        raise ValueError(f"{label} interpolation footprint contains non-finite pixels")
    if label in {"CWAVE", "CBAND", "solid angle", "VARIANCE"} and np.any(samples <= 0):
        raise ValueError(f"{label} interpolation footprint contains non-positive pixels")
    return float(np.dot(samples, weights))


def _verify_native_pixel(
    product: Mapping[str, Any],
    measurement: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify exact measurement position and wavelength against native FITS products."""
    measurement_id = str(measurement.get("measurement_id", "")).strip()
    if measurement.get("pixel_valid") is not True:
        raise ValueError(f"measurement {measurement_id} pixel_valid must be explicitly true")

    pixel_position = measurement.get("pixel_position")
    pixel_index = measurement.get("pixel_index")
    if isinstance(pixel_position, Mapping):
        if pixel_position.get("convention") != "zero-based":
            raise ValueError(f"measurement {measurement_id} pixel_position must declare zero-based coordinates")
        x = _finite(pixel_position.get("x"), f"measurement {measurement_id} pixel_position.x")
        y = _finite(pixel_position.get("y"), f"measurement {measurement_id} pixel_position.y")
    elif isinstance(pixel_index, Mapping):
        x_raw, y_raw = pixel_index.get("x"), pixel_index.get("y")
        try:
            x, y = int(x_raw), int(y_raw)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"measurement {measurement_id} pixel_index x/y must be integers") from None
        if (
            isinstance(x_raw, bool) or isinstance(y_raw, bool)
            or x != x_raw or y != y_raw
        ):
            raise ValueError(f"measurement {measurement_id} pixel_index is not a valid zero-based image pixel")
    else:
        raise ValueError(
            f"measurement {measurement_id} requires zero-based pixel_index or pixel_position coordinates"
        )
    if x < 0 or y < 0:
        raise ValueError(f"measurement {measurement_id} native pixel position must be non-negative")

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
            if math.floor(y) >= image.shape[0] or math.floor(x) >= image.shape[1]:
                raise ValueError(f"measurement {measurement_id} pixel position lies outside the native image")

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

            source_ra = measurement.get("ra_deg")
            source_dec = measurement.get("dec_deg")
            wcs_residual = None
            if source_ra is not None or source_dec is not None:
                if source_ra is None or source_dec is None:
                    raise ValueError(f"measurement {measurement_id} must provide both ra_deg and dec_deg")
                try:
                    import astropy.units as u
                    from astropy.coordinates import SkyCoord
                    from astropy.wcs import WCS
                    sky = SkyCoord(
                        ra=_finite(source_ra, f"measurement {measurement_id} RA") * u.deg,
                        dec=_finite(source_dec, f"measurement {measurement_id} Dec") * u.deg,
                        frame="icrs",
                    )
                    image_wcs = WCS(image_hdu.header).celestial
                    if not image_wcs.has_celestial:
                        raise ValueError("science IMAGE has no celestial WCS for the supplied sky position")
                    expected_x, expected_y = image_wcs.world_to_pixel(sky)
                    expected_x, expected_y = float(expected_x), float(expected_y)
                    wcs_residual = math.hypot(expected_x - x, expected_y - y)
                    tolerance = _finite(
                        measurement.get("image_wcs_tolerance_pixels", 0.5),
                        f"measurement {measurement_id} image_wcs_tolerance_pixels",
                    )
                    if not math.isfinite(wcs_residual) or tolerance <= 0 or wcs_residual > tolerance:
                        raise ValueError(
                            f"measurement {measurement_id} source sky position disagrees with image WCS "
                            f"by {wcs_residual:.6g} pixels (limit {tolerance})"
                        )
                except (ImportError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"measurement {measurement_id} image-WCS position verification failed: {exc}"
                    ) from exc

            actual_wavelength = _bilinear_sample(cwave, x, y, "CWAVE")
            actual_bandwidth = _bilinear_sample(cband, x, y, "CBAND")
            pixel_area = _bilinear_sample(solid_angle, x, y, "solid angle")
            pixel_flux = _bilinear_sample(image, x, y, "IMAGE")
            pixel_variance = _bilinear_sample(variance, x, y, "VARIANCE")
            wavelength = _finite(measurement.get("wavelength_um"), f"measurement {measurement_id} wavelength")
            bandwidth = _finite(measurement.get("bandwidth_um"), f"measurement {measurement_id} bandwidth")
            if not math.isclose(wavelength, actual_wavelength, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError(f"measurement {measurement_id} wavelength_um does not match the native CWAVE position")
            if not math.isclose(bandwidth, actual_bandwidth, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError(f"measurement {measurement_id} bandwidth_um does not match the native CBAND position")

    except OSError as exc:
        raise ValueError(
            f"measurement {measurement_id} native FITS file could not be read: {exc}"
        ) from exc

    output = {
        "pixel_position": {"x": x, "y": y, "convention": "zero-based"},
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
    if abs(x - round(x)) < 1e-12 and abs(y - round(y)) < 1e-12:
        output["pixel_index"] = {
            "x": int(round(x)), "y": int(round(y)), "convention": "zero-based"
        }
    if wcs_residual is not None:
        output["image_wcs_position_residual_pixels"] = wcs_residual
    return output


def _summarize_temporal_band_clusters(
    rows: Sequence[Mapping[str, Any]],
    *,
    minimum_epochs: int,
    minimum_overlap_fraction: float = 0.5,
) -> dict[str, Any]:
    """Find repeated temporal measurements with a common native passband.

    Each measurement contributes its native CWAVE centre and CBAND width.
    A cluster is temporally comparable only when the intersection of all
    passbands retains at least the declared fraction of the narrowest band
    and the cluster spans the requested number of distinct observation/MJD
    epochs. This prevents a wavelength shift between visits from masquerading
    as temporal variability.
    """
    if not math.isfinite(float(minimum_overlap_fraction)) or not 0 < minimum_overlap_fraction <= 1:
        raise ValueError("minimum_overlap_fraction must be in (0, 1]")
    prepared = []
    for row in rows:
        wavelength = _finite(row.get("wavelength_um"), "temporal wavelength_um")
        bandwidth = _finite(row.get("bandwidth_um"), "temporal bandwidth_um")
        if wavelength <= 0 or bandwidth <= 0:
            raise ValueError("temporal wavelength and bandwidth must be positive")
        observation_id = str(row.get("observation_id", "")).strip()
        mjd = _finite(row.get("mjd"), "temporal MJD")
        if not observation_id:
            raise ValueError("temporal measurement requires observation_id")
        prepared.append({
            "observation_id": observation_id,
            "mjd": mjd,
            "lower_um": wavelength - bandwidth / 2.0,
            "upper_um": wavelength + bandwidth / 2.0,
            "bandwidth_um": bandwidth,
            "measurement_id": str(row.get("measurement_id", "")),
        })
    prepared.sort(key=lambda row: (
        (row["lower_um"] + row["upper_um"]) / 2.0,
        row["mjd"], row["observation_id"], row["measurement_id"],
    ))

    raw_clusters: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    common_lower = common_upper = minimum_bandwidth = None
    for item in prepared:
        if not current:
            current = [item]
            common_lower, common_upper = item["lower_um"], item["upper_um"]
            minimum_bandwidth = item["bandwidth_um"]
            continue
        next_lower = max(float(common_lower), item["lower_um"])
        next_upper = min(float(common_upper), item["upper_um"])
        next_minimum_bandwidth = min(float(minimum_bandwidth), item["bandwidth_um"])
        overlap_fraction = max(0.0, next_upper - next_lower) / next_minimum_bandwidth
        if next_upper > next_lower and overlap_fraction >= minimum_overlap_fraction:
            current.append(item)
            common_lower, common_upper = next_lower, next_upper
            minimum_bandwidth = next_minimum_bandwidth
        else:
            raw_clusters.append(current)
            current = [item]
            common_lower, common_upper = item["lower_um"], item["upper_um"]
            minimum_bandwidth = item["bandwidth_um"]
    if current:
        raw_clusters.append(current)

    clusters = []
    for index, cluster in enumerate(raw_clusters, start=1):
        lower = max(row["lower_um"] for row in cluster)
        upper = min(row["upper_um"] for row in cluster)
        narrowest = min(row["bandwidth_um"] for row in cluster)
        overlap_width = max(0.0, upper - lower)
        overlap_fraction = overlap_width / narrowest
        epochs = sorted({(row["observation_id"], row["mjd"]) for row in cluster})
        usable = len(epochs) >= int(minimum_epochs) and overlap_fraction >= minimum_overlap_fraction
        clusters.append({
            "cluster_index": index,
            "measurement_count": len(cluster),
            "distinct_epoch_count": len(epochs),
            "observation_ids": sorted({row["observation_id"] for row in cluster}),
            "mjd_min": min((row["mjd"] for row in cluster), default=None),
            "mjd_max": max((row["mjd"] for row in cluster), default=None),
            "common_passband_lower_um": lower if overlap_width > 0 else None,
            "common_passband_upper_um": upper if overlap_width > 0 else None,
            "common_passband_width_um": overlap_width,
            "narrowest_native_bandwidth_um": narrowest,
            "common_overlap_fraction_of_narrowest_band": overlap_fraction,
            "minimum_overlap_fraction_required": float(minimum_overlap_fraction),
            "usable_temporal_band": usable,
            "measurement_ids": sorted(
                row["measurement_id"] for row in cluster if row["measurement_id"]
            ),
        })
    usable = [row for row in clusters if row["usable_temporal_band"]]
    return {
        "rule": "native_CWAVE_CBand_common_interval_overlap",
        "minimum_overlap_fraction": float(minimum_overlap_fraction),
        "cluster_count": len(clusters),
        "usable_temporal_band_cluster_count": len(usable),
        "usable_temporal_band_clusters": usable,
        "all_clusters": clusters,
        "usable_multi_epoch_series": bool(usable),
    }


def assemble_source_timeseries(
    manifest: Mapping[str, Any],
    *,
    minimum_epochs: int = 2,
    verify_files: bool = True,
    minimum_band_overlap_fraction: float = 0.5,
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
    extractor_kind = str(extractor.get("kind", "version_controlled")).strip()
    for key in ("name", "version"):
        if not str(extractor.get(key, "")).strip():
            raise ValueError(f"extraction_method.{key} is required")
    if extractor_kind == "hosted_service":
        service_uri = str(extractor.get("service_uri", "")).strip()
        job_id = str(extractor.get("job_id", "")).strip()
        retrieved_utc = str(extractor.get("retrieved_utc", "")).strip()
        if not service_uri.startswith("https://") or not job_id or not retrieved_utc:
            raise ValueError("hosted-service extraction requires exact HTTPS service_uri, job_id and retrieved_utc")
    elif extractor_kind == "version_controlled":
        if not str(extractor.get("code_commit", "")).strip():
            raise ValueError("extraction_method.code_commit is required")
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", str(extractor["code_commit"])):
            raise ValueError("extraction_method.code_commit must be a full Git commit SHA")
    else:
        raise ValueError("extraction_method.kind must be version_controlled or hosted_service")
    extraction_config_sha = _require_sha(extractor.get("configuration_sha256"), "extraction configuration SHA-256")
    quality_policy = manifest.get("photometry_quality_policy")
    quality_policy_sha256 = None
    quality_policy_mask = 0
    if extractor_kind == "hosted_service":
        if not isinstance(quality_policy, Mapping):
            raise ValueError("hosted-service photometry requires a predeclared photometry_quality_policy")
        policy_payload = {
            "policy_id": str(quality_policy.get("policy_id", "")).strip(),
            "flag_policy": str(quality_policy.get("flag_policy", "")).strip(),
            "fit_ql_max": _finite(quality_policy.get("fit_ql_max"), "photometry_quality_policy.fit_ql_max"),
            "max_abs_background_to_flux_ratio": _finite(
                quality_policy.get("max_abs_background_to_flux_ratio"),
                "photometry_quality_policy.max_abs_background_to_flux_ratio",
            ),
            "background_fraction_definition": "abs(flux_bkg) / max(abs(flux), flux_err)",
        }
        if (
            not policy_payload["policy_id"] or policy_payload["fit_ql_max"] <= 0
            or policy_payload["max_abs_background_to_flux_ratio"] <= 0
        ):
            raise ValueError("photometry quality thresholds must be named and positive")
        quality_policy_sha256 = _require_sha(
            quality_policy.get("sha256"), "photometry quality-policy SHA-256"
        )
        expected_policy_sha = hashlib.sha256(json.dumps(
            policy_payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False, default=str,
        ).encode("utf-8")).hexdigest()
        if quality_policy_sha256 != expected_policy_sha:
            raise ValueError("photometry quality-policy SHA-256 does not match its frozen contents")
        try:
            from research_discovery.spherex.flag_policy import policy_mask
            quality_policy_mask, _ = policy_mask(policy_payload["flag_policy"])
        except (ImportError, ValueError) as exc:
            raise ValueError(f"photometry quality policy has an invalid flag policy: {exc}") from exc

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
        native_mef_audit_sha256 = _require_sha(
            product.get("native_mef_audit_sha256"),
            f"{product_id} native MEF audit SHA-256",
        )
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
            "native_mef_audit_sha256": native_mef_audit_sha256,
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
        n_pixels = None
        if raw_n_pixels is not None:
            try:
                n_pixels = int(raw_n_pixels)
            except (TypeError, ValueError, OverflowError):
                raise ValueError(f"measurement {measurement_id} must record a positive integer n_pixels") from None
            if isinstance(raw_n_pixels, bool) or n_pixels < 1 or n_pixels != raw_n_pixels:
                raise ValueError(f"measurement {measurement_id} must record a positive integer n_pixels")
        elif not (
            extractor_kind == "hosted_service"
            and str(measurement.get("photometry_method", "")) == "IRSA_SPHEREX_SPECTROPHOTOMETRY_TOOL"
        ):
            raise ValueError(
                f"measurement {measurement_id} must record n_pixels or identify the IRSA hosted photometry method"
            )
        if str(measurement.get("flux_unit", "")).strip() != "Jy":
            raise ValueError(f"measurement {measurement_id} integrated flux unit must be Jy")
        if extractor_kind == "hosted_service":
            if str(measurement.get("photometry_method", "")) != "IRSA_SPHEREX_SPECTROPHOTOMETRY_TOOL":
                raise ValueError(f"measurement {measurement_id} hosted-service photometry method is not identified")
            if _require_sha(
                measurement.get("quality_policy_sha256"),
                f"measurement {measurement_id} quality-policy SHA-256",
            ) != quality_policy_sha256:
                raise ValueError(f"measurement {measurement_id} uses a different quality policy")
            fit_ql = _finite(measurement.get("fit_ql"), f"measurement {measurement_id} fit_ql")
            flux_background = _finite(
                measurement.get("flux_background"),
                f"measurement {measurement_id} flux_background",
            )
            flags = measurement.get("photometry_flags")
            if isinstance(flags, bool):
                raise ValueError(f"measurement {measurement_id} photometry_flags must be an integer")
            try:
                flags_int = int(flags)
            except (TypeError, ValueError, OverflowError):
                raise ValueError(f"measurement {measurement_id} photometry_flags must be an integer") from None
            if flags_int < 0 or flags_int != flags:
                raise ValueError(f"measurement {measurement_id} photometry_flags must be a non-negative integer")
            background_fraction = abs(flux_background) / max(abs(flux), sigma)
            if flags_int & quality_policy_mask:
                raise ValueError(f"measurement {measurement_id} fails the predeclared photometry flag policy")
            if fit_ql < 0 or fit_ql > float(quality_policy["fit_ql_max"]):
                raise ValueError(f"measurement {measurement_id} fails the predeclared fit_ql quality cut")
            if background_fraction > float(quality_policy["max_abs_background_to_flux_ratio"]):
                raise ValueError(f"measurement {measurement_id} fails the predeclared background quality cut")
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
        measurement_mjd = _finite(measurement.get("mjd", product["mjd"]), f"measurement {measurement_id} MJD")
        row = {
            "source_id": source_id,
            "measurement_id": measurement_id,
            "observation_id": product["observation_id"],
            "archive_product_id": product_id,
            "mjd": measurement_mjd,
            "product_mjd": product["mjd"],
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
            "photometry_method": measurement.get("photometry_method"),
            "fit_ql": measurement.get("fit_ql"),
            "flux_background": measurement.get("flux_background"),
            "photometry_flags": measurement.get("photometry_flags"),
            "photometry_quality_policy_sha256": quality_policy_sha256,
        }
        if n_pixels is not None:
            row["n_pixels"] = n_pixels
        if measurement.get("extraction_configuration_sha256") is not None:
            measurement_config_sha = _require_sha(
                measurement.get("extraction_configuration_sha256"),
                f"measurement {measurement_id} extraction configuration SHA-256",
            )
            if measurement_config_sha != extraction_config_sha:
                raise ValueError(f"measurement {measurement_id} uses a different extraction configuration")
            row["extraction_configuration_sha256"] = measurement_config_sha
        if "quality_policy_sha256" in measurement:
            row["quality_policy_sha256"] = measurement["quality_policy_sha256"]
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
        temporal_bands = _summarize_temporal_band_clusters(
            rows,
            minimum_epochs=int(minimum_epochs),
            minimum_overlap_fraction=minimum_band_overlap_fraction,
        )
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
                "temporal_band_comparability": temporal_bands,
                "usable_multi_epoch_series": (
                    len(epoch_keys) >= int(minimum_epochs)
                    and temporal_bands["usable_multi_epoch_series"]
                ),
            },
        })

    canonical = {
        "schema": SCHEMA,
        "dataset_class": "real",
        "extraction_method": dict(extractor),
        "extraction_configuration_sha256": extraction_config_sha,
        "photometry_quality_policy": dict(quality_policy) if isinstance(quality_policy, Mapping) else None,
        "photometry_quality_policy_sha256": quality_policy_sha256,
        "source_catalogue": verified_catalogue,
        "products": list(products.values()),
        "sources": source_series,
        "measurement_count": len(seen_measurements),
        "minimum_epochs": int(minimum_epochs),
        "minimum_band_overlap_fraction": float(minimum_band_overlap_fraction),
        "note": "Assembled from supplied extraction measurements; this module verifies provenance but does not re-extract pixels. Temporal comparability also requires overlapping native CWAVE/CBAND intervals across epochs.",
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
