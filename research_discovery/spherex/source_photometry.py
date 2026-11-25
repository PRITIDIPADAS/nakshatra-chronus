"""Provenance-bound PSF photometry for native SPHEREx Level-2 images.

Fits integrated Jy flux in the delivered MJy/sr IMAGE plane with the
position-specific native ePSF and per-pixel solid angle. Uses delivered
VARIANCE and conservative flags; never reapplies gain to science pixels.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from research_discovery.spherex.extract_epsf_stamp import extract as extract_epsf
from research_discovery.spherex.flag_policy import policy_mask
from research_discovery.spherex.psf_physicality import enforce_nonnegative_interpolation_psf
from research_discovery.spherex.source_timeseries import (
    _bilinear_sample,
    assemble_source_timeseries,
)

ARCSEC2_TO_SR = (math.pi / (180.0 * 3600.0)) ** 2


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha(value: Any, label: str) -> str:
    value = str(value or "").strip().lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be a SHA-256 hex digest")
    return value


def _file_record(record: Mapping[str, Any], label: str) -> dict:
    uri = str(record.get("uri", "")).strip()
    path = Path(str(record.get("local_path", "")))
    expected = _sha(record.get("sha256"), f"{label}.sha256")
    if not uri.startswith("https://"):
        raise ValueError(f"{label}.uri must be the exact archive HTTPS URI")
    if not path.is_file():
        raise FileNotFoundError(f"{label} native file is unavailable: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{label} local SHA-256 does not match its archive manifest")
    return {"uri": uri, "local_path": str(path), "sha256": actual}



def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False, default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verify_native_audit(
    audit_file: Mapping[str, Any],
    *,
    science_sha256: str,
    spectral_wcs_sha256: str,
    solid_angle_sha256: str,
    compatibility_decision: Mapping[str, Any],
) -> dict:
    """Verify the actual native-MEF audit bytes and the exact products it audited."""
    record = _file_record(audit_file, "native_mef_audit")
    try:
        report = json.loads(Path(record["local_path"]).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"native MEF audit report is unreadable: {exc}") from exc
    if not isinstance(report, Mapping):
        raise ValueError("native MEF audit report must be a JSON object")
    if report.get("status") != "STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS":
        raise ValueError("native MEF audit report is not STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS")
    if str(report.get("science_sha256", "")).lower() != science_sha256:
        raise ValueError("native MEF audit report refers to different science MEF bytes")
    if str(report.get("spectral_wcs_sha256", "")).lower() != spectral_wcs_sha256:
        raise ValueError("native MEF audit report refers to different spectral-WCS bytes")
    solid_angle = report.get("solid_angle") or {}
    if str(solid_angle.get("sha256", "")).lower() != solid_angle_sha256:
        raise ValueError("native MEF audit report refers to different solid-angle bytes")
    checks = report.get("checks") or {}
    for name in ("cwave_cband", "wavelength_units", "solid_angle"):
        if (checks.get(name) or {}).get("status") != "pass":
            raise ValueError(f"native MEF audit check {name} did not pass")
    audited_decision = report.get("calibration_compatibility")
    if not isinstance(audited_decision, Mapping):
        raise ValueError("native MEF audit report has no calibration_compatibility decision")
    if audited_decision.get("status") != "compatible":
        raise ValueError("native MEF audit calibration compatibility is not compatible")
    expected_decision = {
        key: value for key, value in compatibility_decision.items() if key != "sha256"
    }
    if _canonical_sha256(audited_decision) != _canonical_sha256(expected_decision):
        raise ValueError("supplied calibration decision does not match the decision embedded in the native audit")
    compatibility_sha256 = _canonical_sha256(expected_decision)
    supplied_decision_sha = compatibility_decision.get("sha256")
    if supplied_decision_sha is not None and _sha(
        supplied_decision_sha, "compatibility_decision.sha256"
    ) != compatibility_sha256:
        raise ValueError("compatibility decision SHA-256 does not match its canonical contents")
    return {
        "file": record,
        "report": report,
        "audit_sha256": record["sha256"],
        "compatibility_sha256": compatibility_sha256,
    }


def fit_psf_flux_jy(
    image: np.ndarray,
    variance: np.ndarray,
    omega_sr: np.ndarray,
    flags: np.ndarray,
    psf: np.ndarray,
    *,
    excluded_flag_bits: int,
) -> dict:
    """Weighted integrated-Jy PSF amplitude plus local planar background."""
    image = np.asarray(image, dtype=float)
    variance = np.asarray(variance, dtype=float)
    omega_sr = np.asarray(omega_sr, dtype=float)
    flags = np.asarray(flags)
    psf = np.asarray(psf, dtype=float)
    if psf.ndim != 2 or any(n % 2 == 0 for n in psf.shape):
        raise ValueError("PSF must be a 2D odd-sized stamp")
    if not (image.shape == variance.shape == omega_sr.shape == flags.shape == psf.shape):
        raise ValueError("IMAGE/VARIANCE/FLAGS/solid-angle/PSF patches must align exactly")
    if not np.isfinite(psf).all() or np.any(psf < 0) or psf.sum() <= 0:
        raise ValueError("PSF must be finite, nonnegative and have positive sum")
    if not np.isfinite(image).all():
        raise ValueError("PSF footprint contains non-finite IMAGE values")
    if not np.isfinite(variance).all() or np.any(variance <= 0):
        raise ValueError("PSF footprint contains invalid VARIANCE values")
    if not np.isfinite(omega_sr).all() or np.any(omega_sr <= 0):
        raise ValueError("PSF footprint contains invalid solid-angle values")
    if excluded_flag_bits and np.any(
        (flags.astype(np.uint64) & np.uint64(excluded_flag_bits)) != 0
    ):
        raise ValueError("PSF footprint intersects an excluded SPHEREx flag")

    psf = psf / float(psf.sum())
    yy, xx = np.mgrid[:psf.shape[0], :psf.shape[1]]
    cx, cy = (psf.shape[1] - 1) / 2.0, (psf.shape[0] - 1) / 2.0
    source_response = 1.0e-6 * psf / omega_sr
    design = np.column_stack((
        source_response.ravel(),
        np.ones(image.size),
        (xx - cx).ravel(),
        (yy - cy).ravel(),
    ))
    standard_deviation = np.sqrt(variance.ravel())
    weighted_design = design / standard_deviation[:, None]
    weighted_image = image.ravel() / standard_deviation
    coefficients, _, rank, _ = np.linalg.lstsq(weighted_design, weighted_image, rcond=None)
    if rank != design.shape[1]:
        raise ValueError("PSF plus local-background design is rank deficient")
    condition = float(np.linalg.cond(weighted_design))
    if not math.isfinite(condition) or condition > 1.0e12:
        raise ValueError(f"PSF photometry design is ill-conditioned ({condition:.6g})")
    covariance = np.linalg.inv(weighted_design.T @ weighted_design)
    residual = weighted_image - weighted_design @ coefficients
    chi2 = float(residual @ residual)
    dof = int(image.size - design.shape[1])
    if dof <= 0:
        raise ValueError("PSF fit has no positive residual degrees of freedom")
    flux, flux_error = float(coefficients[0]), float(math.sqrt(covariance[0, 0]))
    if not math.isfinite(flux) or not math.isfinite(flux_error) or flux_error <= 0:
        raise ValueError("PSF fit returned invalid integrated flux or uncertainty")
    return {
        "flux_jy": flux,
        "sigma_jy": flux_error,
        "snr": flux / flux_error,
        "background_mjy_sr": float(coefficients[1]),
        "background_gradient_x_mjy_sr_per_pixel": float(coefficients[2]),
        "background_gradient_y_mjy_sr_per_pixel": float(coefficients[3]),
        "chi2": chi2,
        "degrees_of_freedom": dof,
        "reduced_chi2": chi2 / dof,
        "design_condition_number": condition,
        "covariance_flux_jy2": float(covariance[0, 0]),
        "n_pixels": int(image.size),
        "variance_treatment": "delivered Level-2 VARIANCE as known diagonal covariance; not rescaled by reduced chi-square",
        "background_treatment": "simultaneously fitted local constant and x/y planar gradient",
    }


def extract_source_photometry(
    *,
    science_file: Mapping[str, Any],
    spectral_wcs_file: Mapping[str, Any],
    solid_angle_file: Mapping[str, Any],
    product_record: Mapping[str, Any],
    source_record: Mapping[str, Any],
    source_catalogue_file: Mapping[str, Any],
    native_mef_audit_file: Mapping[str, Any],
    compatibility_decision: Mapping[str, Any],
    code_commit: str,
    output_dir: str | Path,
    stamp_size: int = 11,
    max_reduced_chi2: float = 10.0,
    epsf_extractor=None,
) -> dict:
    """Extract one source in one native exposure and immediately verify its record.

    The result is a single measurement. It is not a multi-epoch lightcurve.
    """
    for label, record in (
        ("science_file", science_file),
        ("spectral_wcs_file", spectral_wcs_file),
        ("solid_angle_file", solid_angle_file),
        ("source_catalogue_file", source_catalogue_file),
    ):
        if not isinstance(record, Mapping):
            raise ValueError(f"{label} must be a file record")
    if not isinstance(product_record, Mapping) or not isinstance(source_record, Mapping):
        raise ValueError("product_record and source_record must be mappings")
    commit = str(code_commit).strip().lower()
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
        raise ValueError("code_commit must be a 40-character Git commit SHA")
    if stamp_size < 7 or stamp_size % 2 == 0:
        raise ValueError("stamp_size must be odd and at least 7")
    if not math.isfinite(float(max_reduced_chi2)) or max_reduced_chi2 <= 0:
        raise ValueError("max_reduced_chi2 must be finite and positive")

    files = {
        "science": _file_record(science_file, "science"),
        "spectral_wcs": _file_record(spectral_wcs_file, "spectral_wcs"),
        "solid_angle": _file_record(solid_angle_file, "solid_angle"),
        "source_catalogue": _file_record(source_catalogue_file, "source_catalogue"),
    }
    if not isinstance(compatibility_decision, Mapping) or compatibility_decision.get("status") != "compatible":
        raise ValueError("source photometry requires an explicit compatible native MEF audit")
    audit_proof = _verify_native_audit(
        native_mef_audit_file,
        science_sha256=files["science"]["sha256"],
        spectral_wcs_sha256=files["spectral_wcs"]["sha256"],
        solid_angle_sha256=files["solid_angle"]["sha256"],
        compatibility_decision=compatibility_decision,
    )
    audit_sha = audit_proof["audit_sha256"]
    compatibility_sha = audit_proof["compatibility_sha256"]

    source_id = str(source_record.get("source_id", "")).strip()
    product_id = str(product_record.get("archive_product_id", "")).strip()
    observation_id = str(product_record.get("observation_id", "")).strip()
    detector = str(product_record.get("detector", "")).strip().upper()
    release = str(product_record.get("release", "")).strip().upper()
    calibration_group = str(product_record.get("calibration_group", "")).strip()
    if not all((source_id, product_id, observation_id, calibration_group)):
        raise ValueError("source, archive product, observation and calibration IDs are required")
    if detector not in {f"D{i}" for i in range(1, 7)} or release not in {"DR1", "QR3"}:
        raise ValueError("product detector/release must be exact SPHEREx D1-D6 and DR1/QR3")
    ra_deg, dec_deg = float(source_record.get("ra_deg")), float(source_record.get("dec_deg"))
    if not (math.isfinite(ra_deg) and math.isfinite(dec_deg) and 0 <= ra_deg < 360 and -90 <= dec_deg <= 90):
        raise ValueError("source RA/Dec must be finite valid ICRS degrees")
    mjd = float(product_record.get("mjd"))
    if not math.isfinite(mjd):
        raise ValueError("product MJD must be finite")

    try:
        from astropy.coordinates import SkyCoord
        from astropy.io import fits
        from astropy.wcs import WCS
        import astropy.units as u
    except ImportError as exc:
        raise RuntimeError("Astropy is required for native SPHEREx WCS/FITS photometry") from exc

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    science_path = Path(files["science"]["local_path"])
    with (
        fits.open(science_path, memmap=False) as science_hdul,
        fits.open(files["solid_angle"]["local_path"], memmap=False) as area_hdul,
        fits.open(files["spectral_wcs"]["local_path"], memmap=False) as spectral_hdul,
    ):
        for name in ("IMAGE", "VARIANCE", "FLAGS"):
            if name not in science_hdul:
                raise ValueError(f"native science MEF is missing {name}")
        for name in ("CWAVE", "CBAND"):
            if name not in spectral_hdul:
                raise ValueError(f"native spectral-WCS file is missing {name}")
        image_hdu = science_hdul["IMAGE"]
        image = np.asarray(image_hdu.data, dtype=float)
        variance = np.asarray(science_hdul["VARIANCE"].data, dtype=float)
        flags = np.asarray(science_hdul["FLAGS"].data)
        cwave_hdu, cband_hdu = spectral_hdul["CWAVE"], spectral_hdul["CBAND"]
        cwave, cband = np.asarray(cwave_hdu.data, dtype=float), np.asarray(cband_hdu.data, dtype=float)
        area_hdu = area_hdul["IMAGE"] if "IMAGE" in area_hdul else next(
            (h for h in area_hdul[1:] if h.data is not None and np.asarray(h.data).ndim == 2),
            None,
        )
        if area_hdu is None:
            raise ValueError("native solid-angle file has no 2D image extension")
        area = np.asarray(area_hdu.data, dtype=float)
        if image.ndim != 2 or not (image.shape == variance.shape == flags.shape == cwave.shape == cband.shape == area.shape):
            raise ValueError("science IMAGE/VARIANCE/FLAGS, CWAVE/CBAND and solid-angle maps must align exactly")
        if str(image_hdu.header.get("BUNIT", "")).strip().lower().replace(" ", "") not in {"mjy/sr", "mjy*sr-1"}:
            raise ValueError("science IMAGE must use MJy/sr")
        if str(cwave_hdu.header.get("BUNIT", "")).strip().lower() not in {"um", "micron", "microns"}:
            raise ValueError("CWAVE BUNIT must be microns")
        if str(cband_hdu.header.get("BUNIT", "")).strip().lower() not in {"um", "micron", "microns"}:
            raise ValueError("CBAND BUNIT must be microns")
        area_unit = str(area_hdu.header.get("BUNIT", "")).strip().lower().replace(" ", "")
        if area_unit in {"arcsec2", "arcsec^2", "arcsec**2"}:
            omega_sr = area * ARCSEC2_TO_SR
        elif area_unit in {"sr", "steradian", "steradians"}:
            omega_sr = area.copy()
        else:
            raise ValueError("solid-angle BUNIT must be arcsec2 or sr")
        expected_detector = int(detector[1:])
        for label, hdu in (("IMAGE", image_hdu), ("CWAVE", cwave_hdu), ("CBAND", cband_hdu), ("solid angle", area_hdu)):
            raw_detector = str(hdu.header.get("DETECTOR", "")).strip().removeprefix("D")
            try:
                actual_detector = int(raw_detector)
            except ValueError:
                raise ValueError(f"{label} is missing a usable DETECTOR header") from None
            if actual_detector != expected_detector:
                raise ValueError(f"{label} detector does not match {detector}")
        if str(image_hdu.header.get("OBSID", "")).strip() != observation_id:
            raise ValueError("science MEF OBSID does not match archive product observation_id")
        try:
            image_wcs = WCS(image_hdu.header, fobj=science_hdul, relax=True).celestial
            coordinate = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
            x, y = map(float, image_wcs.world_to_pixel(coordinate))
        except Exception as exc:
            raise ValueError(f"could not transform ICRS source position to native IMAGE pixels: {exc}") from exc
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("source WCS transformation returned non-finite pixels")
        pixel_x, pixel_y = int(math.floor(x + 0.5)), int(math.floor(y + 0.5))
        if not (0 <= pixel_x < image.shape[1] and 0 <= pixel_y < image.shape[0]):
            raise ValueError("source lies outside the native science image")
        wavelength_um = _bilinear_sample(cwave, x, y, "CWAVE")
        bandwidth_um = _bilinear_sample(cband, x, y, "CBAND")
        if not (math.isfinite(wavelength_um) and wavelength_um > 0 and math.isfinite(bandwidth_um) and bandwidth_um > 0):
            raise ValueError("source detector pixel has invalid CWAVE/CBAND values")

        flag_bits, flag_names = policy_mask("conservative-photometry")
        stamp_name = f"epsf_{hashlib.sha256((source_id + product_id).encode()).hexdigest()[:20]}.fits"
        stamp_path = out / stamp_name
        epsf_meta = (epsf_extractor or extract_epsf)(
            science_path, x=x, y=y, out=stamp_path, stamp_size=stamp_size
        )
        if not stamp_path.is_file():
            raise ValueError("position-specific EPSF extractor did not create a native-pixel stamp")
        with fits.open(stamp_path, memmap=True) as psf_hdul:
            raw_psf = np.asarray(psf_hdul[0].data, dtype=float)
            psf_header = psf_hdul[0].header.copy()
        psf, psf_physicality = enforce_nonnegative_interpolation_psf(raw_psf)
        psf_detector = str(psf_header.get("DETECTOR", "")).strip().removeprefix("D")
        if psf_detector and psf_detector != detector[1:]:
            raise ValueError("extracted ePSF detector does not match the science detector")
        lower_left = epsf_meta.get("stamp_lower_left_cutout_pixel_0based")
        if not isinstance(lower_left, (list, tuple)) or len(lower_left) != 2:
            raise ValueError("EPSF extractor must record the native stamp lower-left x/y")
        x0, y0 = int(lower_left[0]), int(lower_left[1])
        x1, y1 = x0 + psf.shape[1], y0 + psf.shape[0]
        if x0 < 0 or y0 < 0 or x1 > image.shape[1] or y1 > image.shape[0]:
            raise ValueError("full native ePSF footprint lies outside the science image")
        fit = fit_psf_flux_jy(
            image[y0:y1, x0:x1],
            variance[y0:y1, x0:x1],
            omega_sr[y0:y1, x0:x1],
            flags[y0:y1, x0:x1],
            psf,
            excluded_flag_bits=flag_bits,
        )

    quality_flags = []
    if fit["reduced_chi2"] > float(max_reduced_chi2):
        quality_flags.append("PSF_PLUS_BACKGROUND_REDUCED_CHI2_ABOVE_REVIEW_LIMIT")
    if fit["design_condition_number"] > 1.0e10:
        quality_flags.append("PSF_FIT_DESIGN_CONDITION_NUMBER_HIGH")
    valid = not quality_flags
    configuration = {
        "algorithm": "weighted_position_specific_ePSF_amplitude_plus_local_planar_background",
        "stamp_size": stamp_size,
        "flag_policy": "conservative-photometry",
        "background_model": "constant_plus_x_y_plane",
        "variance_model": "delivered_Level2_VARIANCE_as_known_diagonal_covariance",
        "solid_angle_conversion": "arcsec2_to_sr_before_integrated_Jy_fit",
        "max_reduced_chi2": float(max_reduced_chi2),
        "psf_physicality": psf_physicality,
    }
    config_sha = hashlib.sha256(json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    measurement_seed = "|".join((source_id, product_id, observation_id, detector, str(pixel_x), str(pixel_y)))
    measurement_id = "SPXPHOT-" + hashlib.sha256(measurement_seed.encode()).hexdigest()[:24]
    measurement = {
        "measurement_id": measurement_id,
        "source_id": source_id,
        "archive_product_id": product_id,
        "wavelength_um": wavelength_um,
        "bandwidth_um": bandwidth_um,
        "flux_jy": fit["flux_jy"],
        "sigma_jy": fit["sigma_jy"],
        "flux_unit": "Jy",
        "fit_status": "success" if valid else "review_required",
        "n_pixels": fit["n_pixels"],
        "valid": valid,
        "pixel_valid": True,
        "pixel_index": {"x": pixel_x, "y": pixel_y},
        "pixel_position": {"x": x, "y": y, "convention": "zero-based"},
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "image_wcs_tolerance_pixels": 0.5,
        "quality_flags": quality_flags,
        "fit_diagnostics": fit,
    }
    science_record = dict(files["science"])
    product = {
        "archive_product_id": product_id,
        "observation_id": observation_id,
        "mjd": mjd,
        "release": release,
        "detector": detector,
        "calibration_group": calibration_group,
        "science": science_record,
        "spectral_wcs": dict(files["spectral_wcs"]),
        "epsf": dict(science_record),
        "solid_angle": dict(files["solid_angle"]),
        "native_mef_audit_sha256": audit_sha,
        "compatibility_decision": {
            **{key: value for key, value in compatibility_decision.items() if key != "sha256"},
            "science_sha256": files["science"]["sha256"],
            "spectral_wcs_sha256": files["spectral_wcs"]["sha256"],
            "solid_angle_sha256": files["solid_angle"]["sha256"],
            "sha256": compatibility_sha,
        },
        "epsf_embedding_note": "native EPSF table embedded in science MEF; rendered position-specific stamp is separately retained",
    }
    extractor_record = {
        "name": "chronos-native-spherex-psf-photometry",
        "version": "1.0.1",
        "code_commit": commit,
        "configuration_sha256": config_sha,
    }
    result = {
        "schema": "chronos-spherex-source-photometry/1.0",
        "dataset_class": "real",
        "extraction_method": extractor_record,
        "source_catalogue": files["source_catalogue"],
        "sources": [dict(source_record)],
        "products": [product],
        "measurements": [measurement],
        "extraction_artifacts": {
            "native_mef_audit_file": audit_proof["file"],
            "native_mef_audit_status": audit_proof["report"]["status"],
            "epsf_stamp_path": str(stamp_path),
            "epsf_stamp_sha256": sha256_file(stamp_path),
            "epsf_extraction": epsf_meta,
            "psf_physicality": psf_physicality,
            "native_pixel_position_float": {"x": x, "y": y},
            "native_pixel_index_nearest": {"x": pixel_x, "y": pixel_y},
            "flag_policy": {"name": "conservative-photometry", "excluded_bits": flag_bits, "excluded_names": list(flag_names)},
        },
        "limitations": [
            "One native exposure and one source extraction; not a multi-epoch lightcurve.",
            "Flux uncertainty uses delivered VARIANCE as a diagonal covariance; correlated noise and PSF systematics are not included.",
            "The local planar background does not deblend crowded sources; crowded or blended fits require separate review.",
            "Absolute gain is not applied to already-calibrated IMAGE pixels and source Poisson noise is not re-added during flux fitting.",
            "Source classification and exact visit simultaneity are inherited metadata, not newly validated by this extractor.",
        ],
    }
    result["verified_source_timeseries"] = (
        assemble_source_timeseries(result, minimum_epochs=2, verify_files=True)
        if valid else None
    )
    result["output_manifest_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    output_path = out / f"source_photometry_{hashlib.sha256(measurement_id.encode()).hexdigest()[:20]}.json"
    result["output_path"] = str(output_path)
    output_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result
