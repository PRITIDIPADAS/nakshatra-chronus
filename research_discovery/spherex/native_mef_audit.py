"""Inspect native SPHEREx Level-2 MEFs and detector-matched CWAVE/CBAND calibration."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
import numpy as np
from research_discovery.spherex.coordinate_transform import detector_origin_offset
from research_discovery.spherex.calibration_compatibility import compatibility_decision


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _header_summary(header):
    keep = {"DETECTOR", "OBSID", "DATE-OBS", "MJD-OBS", "VERSION", "PROCDATE",
            "RELEASE", "BUNIT", "WCSNAME", "WCSNAMEA", "CRPIX1A", "CRPIX2A",
            "CTYPE1", "CTYPE2", "CTYPE1A", "CTYPE2A", "CUNIT1", "CUNIT2", "WCSAXESA"}
    return {str(key): header[key] for key in header
            if key in keep or str(key).startswith("MP_")}


def science_wavelength_cutout(cwave, cband, image_header, image_shape):
    """Slice native detector calibration maps, without interpolation or extrapolation."""
    wave = np.asarray(cwave, dtype=float)
    band = np.asarray(cband, dtype=float)
    if wave.ndim != 2 or band.shape != wave.shape:
        raise ValueError("CWAVE and CBAND must be equal-shaped 2D maps")
    if wave.shape != (2040, 2040):
        raise ValueError(f"CWAVE/CBAND must be on the native 2040x2040 detector grid; got {wave.shape}")
    origin_x, origin_y = detector_origin_offset(image_header)
    height, width = map(int, image_shape)
    if origin_x < 0 or origin_y < 0 or origin_x + width > wave.shape[1] or origin_y + height > wave.shape[0]:
        raise ValueError("science image footprint exceeds the native calibration grid; refusing extrapolation")
    cut_wave = wave[origin_y:origin_y + height, origin_x:origin_x + width].copy()
    cut_band = band[origin_y:origin_y + height, origin_x:origin_x + width].copy()
    valid = np.isfinite(cut_wave) & (cut_wave > 0) & np.isfinite(cut_band) & (cut_band > 0)
    cut_wave[~valid] = np.nan
    cut_band[~valid] = np.nan
    return {"cwave_um": cut_wave, "cband_um": cut_band, "valid_mask": valid,
            "native_origin_xy": [origin_x, origin_y], "invalid_pixels": int((~valid).sum()),
            "valid_fraction": float(valid.mean())}


def audit(science_path, spectral_wcs_path, *, solid_angle_path=None,
          compatibility_evidence=None, science_uri=None, spectral_wcs_uri=None):
    try:
        from astropy.io import fits
        from astropy.wcs import WCS
    except ImportError as exc:
        raise RuntimeError("Install astropy to audit native SPHEREx FITS files") from exc

    science_path = Path(science_path)
    spectral_wcs_path = Path(spectral_wcs_path)
    report = {
        "science_file": str(science_path), "science_native_uri": science_uri,
        "science_sha256": sha256(science_path),
        "spectral_wcs_file": str(spectral_wcs_path), "spectral_wcs_native_uri": spectral_wcs_uri,
        "spectral_wcs_sha256": sha256(spectral_wcs_path),
        "checks": {}, "status": "review_required",
        "wavelength_authority": "CWAVE and CBAND in the separate spectral-WCS calibration",
        "not_used_for_science_wavelengths": "WCS-WAVE",
    }

    with fits.open(science_path, memmap=True, checksum=True) as science:
        names = [str(hdu.name).upper() for hdu in science]
        report["science_hdus"] = [
            {"index": index, "name": hdu.name,
             "shape": list(hdu.data.shape) if hdu.data is not None else None,
             "bunit": hdu.header.get("BUNIT"), "extver": hdu.header.get("EXTVER"),
             "header": _header_summary(hdu.header)}
            for index, hdu in enumerate(science)
        ]
        required = ("IMAGE", "FLAGS", "VARIANCE", "ZODI", "WCS-WAVE")
        missing = [name for name in required if name not in names]
        report["checks"]["required_hdus"] = {"status": "pass" if not missing else "fail",
                                              "required": list(required), "missing": missing}
        if "IMAGE" not in names or science[names.index("IMAGE")].data is None:
            report["status"] = "FAILED"
            report["error"] = "Native Level-2 MEF has no populated IMAGE HDU"
            return report

        image_hdu = science[names.index("IMAGE")]
        image = np.asarray(image_hdu.data)
        image_header = dict(image_hdu.header)
        science_detector = str(image_hdu.header.get("DETECTOR", "")).strip()
        report["image_shape"] = list(image.shape)
        report["image_bunit"] = image_hdu.header.get("BUNIT")
        report["science_detector"] = science_detector
        report["checks"]["image_2d"] = {"status": "pass" if image.ndim == 2 else "fail"}
        report["checks"]["native_full_frame"] = {
            "status": "pass" if image.shape == (2040, 2040) else "fail",
            "expected_shape": [2040, 2040]}
        unit = str(image_hdu.header.get("BUNIT", "")).lower().replace(" ", "")
        report["checks"]["image_unit"] = {
            "status": "pass" if unit == "mjy/sr" else "review_required",
            "bunit": image_hdu.header.get("BUNIT"), "expected": "MJy/sr"}

        primary = science[0].header
        release = str(primary.get("RELEASE", "")).lower()
        if not release:
            path_lower = str(science_path).lower()
            release = "dr1" if "/dr1/" in path_lower else "qr3" if "/qr3/" in path_lower else "unknown"
        expected_psf = "EPSF" if release in {"dr1", "qr3"} else "PSF" if release == "qr2" else None
        report["release"] = release
        report["checks"]["release_psf_family"] = {
            "status": "pass" if expected_psf and expected_psf in names else "review_required",
            "expected_hdu": expected_psf,
            "available": [name for name in ("EPSF", "PSF") if name in names]}

        for extension in ("FLAGS", "VARIANCE", "ZODI"):
            if extension not in names or science[names.index(extension)].data is None:
                continue
            hdu = science[names.index(extension)]
            array = np.asarray(hdu.data)
            aligned = array.shape == image.shape
            report["checks"][extension.lower() + "_alignment"] = {
                "status": "pass" if aligned else "fail",
                "shape": list(array.shape), "bunit": hdu.header.get("BUNIT")}
            if extension == "VARIANCE":
                values = array.astype(float)
                good = np.isfinite(values) & (values > 0)
                report["variance_quality"] = {
                    "finite_positive_fraction": float(good.mean()),
                    "nonpositive_or_nonfinite_pixels": int((~good).sum())}
            elif extension == "FLAGS":
                flag_header = hdu.header
                mp_cards = {key: flag_header[key] for key in flag_header
                            if str(key).startswith("MP_")}
                report["flags"] = {
                    "dtype": str(array.dtype),
                    "unique_values_sample": np.unique(array)[:32].tolist(),
                    "raw_mp_header_cards": mp_cards,
                    "header_flag_dictionary_present": bool(mp_cards)}
                report["checks"]["flags_integer_type"] = {
                    "status": "pass" if array.dtype.kind in "ui" else "fail"}

        try:
            celestial = WCS(image_hdu.header)
            report["checks"]["celestial_wcs"] = {
                "status": "pass" if celestial.has_celestial else "fail",
                "has_celestial": bool(celestial.has_celestial)}
        except Exception as exc:
            report["checks"]["celestial_wcs"] = {"status": "fail", "error": str(exc)}

        try:
            alternate = WCS(image_hdu.header, key="A")
            origin = detector_origin_offset(image_header)
            alternate_world_origin = alternate.all_pix2world([[0.0, 0.0]], 0)[0].tolist()
            report["alternate_wcs_a"] = {
                "wcsnamea": image_hdu.header.get("WCSNAMEA"),
                "crpix1a": image_hdu.header.get("CRPIX1A"),
                "crpix2a": image_hdu.header.get("CRPIX2A"),
                "world_at_cutout_origin": alternate_world_origin}
            report["cutout_parent_origin_xy"] = list(origin)
            report["checks"]["alternate_wcs_a"] = {"status": "pass"}
            report["checks"]["cutout_parent_origin"] = {"status": "pass"}
        except Exception as exc:
            report["checks"]["alternate_wcs_a"] = {"status": "review_required", "error": str(exc)}
            report["checks"]["cutout_parent_origin"] = {"status": "review_required", "error": str(exc)}

    with fits.open(spectral_wcs_path, memmap=True, checksum=True) as calibration:
        cal_names = [str(hdu.name).upper() for hdu in calibration]
        report["spectral_wcs_hdus"] = [
            {"name": hdu.name, "shape": list(hdu.data.shape) if hdu.data is not None else None,
             "bunit": hdu.header.get("BUNIT"), "header": _header_summary(hdu.header)}
            for hdu in calibration]
        missing_cal = [name for name in ("CWAVE", "CBAND") if name not in cal_names]
        if missing_cal:
            report["checks"]["cwave_cband"] = {"status": "fail", "missing": missing_cal}
        else:
            image_shape = tuple(report["image_shape"])
            with fits.open(science_path, memmap=True) as science:
                grid = science_wavelength_cutout(calibration["CWAVE"].data,
                    calibration["CBAND"].data, dict(science["IMAGE"].header), image_shape)
            report["checks"]["cwave_cband"] = {
                "status": "pass" if grid["invalid_pixels"] == 0 else "review_required",
                "native_origin_xy": grid["native_origin_xy"],
                "valid_fraction": grid["valid_fraction"], "invalid_pixels": grid["invalid_pixels"]}
            good = grid["valid_mask"]
            report["wavelength_summary"] = {
                "source": "CWAVE/CBAND",
                "cwave_min_um": float(np.min(grid["cwave_um"][good])) if good.any() else None,
                "cwave_max_um": float(np.max(grid["cwave_um"][good])) if good.any() else None,
                "cband_min_um": float(np.min(grid["cband_um"][good])) if good.any() else None,
                "cband_max_um": float(np.max(grid["cband_um"][good])) if good.any() else None}
        if solid_angle_path:
            with fits.open(solid_angle_path, memmap=True, checksum=True) as solid_angle:
                hdu = next((item for item in solid_angle if item.data is not None), None)
                if hdu is None:
                    report["checks"]["solid_angle"] = {"status": "fail", "reason": "no image array"}
                else:
                    area = np.asarray(hdu.data, dtype=float)
                    valid_area = np.isfinite(area) & (area > 0)
                    area_unit = str(hdu.header.get("BUNIT", "")).lower().replace(" ", "")
                    area_detector = str(hdu.header.get("DETECTOR", solid_angle[0].header.get("DETECTOR", ""))).strip()
                    detector_matches = bool(science_detector and area_detector and science_detector == area_detector)
                    report["solid_angle"] = {
                        "file": str(solid_angle_path), "sha256": sha256(solid_angle_path),
                        "shape": list(area.shape), "bunit": hdu.header.get("BUNIT"),
                        "positive_fraction": float(valid_area.mean())}
                    area_ok = (area.shape == (2040, 2040) and valid_area.all() and detector_matches
                               and area_unit in {"arcsec2", "arcsec**2", "arcsec^2"})
                    report["checks"]["solid_angle"] = {
                        "status": "pass" if area_ok else "review_required",
                        "science_detector": science_detector, "calibration_detector": area_detector,
                        "bunit": hdu.header.get("BUNIT")}
        else:
            report["checks"]["solid_angle"] = {
                "status": "review_required",
                "reason": "Matching detector solid-angle map was not supplied"}

    if compatibility_evidence:
        report["calibration_compatibility"] = compatibility_decision(
            compatibility_evidence["science"], compatibility_evidence["calibration"])
    else:
        report["calibration_compatibility"] = {
            "status": "review_required",
            "reason": "Explicit release, detector, pipeline, processing-date and coordinate-frame evidence was not supplied"}

    states = [item.get("status") for item in report["checks"].values() if isinstance(item, dict)]
    if "fail" in states:
        report["status"] = "FAILED"
    elif any(state != "pass" for state in states) or report["calibration_compatibility"]["status"] != "compatible":
        report["status"] = "STRUCTURE_OK_REVIEW_REQUIRED"
    else:
        report["status"] = "STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS"
    report["science_claim_boundary"] = (
        "This report checks file structure and supplied metadata. It does not establish empirical astrometric "
        "alignment, detector persistence, or scientific validity without independent real-file evidence.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("science_mef", type=Path)
    parser.add_argument("spectral_wcs", type=Path)
    parser.add_argument("--solid-angle", type=Path)
    parser.add_argument("--compatibility-evidence", type=Path)
    parser.add_argument("--science-uri")
    parser.add_argument("--spectral-wcs-uri")
    parser.add_argument("--out", type=Path, default=Path("native_mef_audit.json"))
    parser.add_argument("--summary", type=Path, default=Path("native_mef_audit.md"))
    args = parser.parse_args()
    evidence = json.loads(args.compatibility_evidence.read_text()) if args.compatibility_evidence else None
    result = audit(args.science_mef, args.spectral_wcs, solid_angle_path=args.solid_angle,
                   compatibility_evidence=evidence, science_uri=args.science_uri,
                   spectral_wcs_uri=args.spectral_wcs_uri)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, default=str))
    lines = ["# Native SPHEREx MEF audit", "", f"**Status:** {result['status']}", "",
             f"Science file: `{args.science_mef}`", f"SHA-256: `{result['science_sha256']}`",
             f"Spectral-WCS file: `{args.spectral_wcs}`", f"SHA-256: `{result['spectral_wcs_sha256']}`", "",
             f"IMAGE shape: `{result.get('image_shape')}`",
             f"IMAGE BUNIT: `{result.get('image_bunit')}`", "", "| Check | Result |", "|---|---|"]
    for name, check in result["checks"].items():
        lines.append(f"| {name} | {check.get('status', 'reported')} |")
    lines += ["", "## Boundary", "", result["science_claim_boundary"], "",
              "Scientific wavelengths are assigned from the separate CWAVE and CBAND maps, never from WCS-WAVE."]
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text("\n".join(lines) + "\n")
    print(result["status"])
    print(args.out)
    print(args.summary)
    if result["status"] == "FAILED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
