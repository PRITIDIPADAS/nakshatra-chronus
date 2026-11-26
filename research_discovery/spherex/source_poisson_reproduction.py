"""Independent recomputation of M101 calibrated-Jy source-Poisson bookkeeping.

This verifier recomputes only the deterministic expectation and added variance
from the retained native image/calibration/ePSF bytes and recorded injection
positions. It does not reproduce the RNG stream, detection outcomes, instrument
calibration validity, or scientific acceptance. Those remain separate reviews.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

ARCSEC2_TO_SR = (math.pi / (180.0 * 3600.0)) ** 2
REPRODUCER_SCHEMA = "chronos-source-poisson-independent-recomputation/1.0"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def recompute_source_poisson_bins(
    injections: Sequence[Mapping[str, Any]],
    psf: np.ndarray,
    absolute_gain: np.ndarray,
    solid_angle_sr: np.ndarray,
    *,
    exposure_time_s: float,
) -> list[dict[str, float | int]]:
    """Recompute per-flux expected electrons and IMAGE variance from first principles."""
    p = np.asarray(psf, dtype=float)
    gain = np.asarray(absolute_gain, dtype=float)
    omega = np.asarray(solid_angle_sr, dtype=float)
    if p.ndim != 2 or any(n % 2 == 0 for n in p.shape):
        raise ValueError("the retained ePSF must be an odd-sized 2D stamp")
    if not np.isfinite(p).all() or np.any(p < 0) or p.sum() <= 0:
        raise ValueError("the retained ePSF must be finite, nonnegative and have positive integral")
    p = p / p.sum()
    if gain.ndim != 2 or omega.shape != gain.shape:
        raise ValueError("absolute-gain and solid-angle maps must be aligned 2D arrays")
    exposure = float(exposure_time_s)
    if not math.isfinite(exposure) or exposure <= 0:
        raise ValueError("exposure_time_s must be finite and positive")

    py, px = np.array(p.shape) // 2
    summary: dict[float, dict[str, float | int]] = {}
    for index, row in enumerate(injections):
        try:
            flux_jy = float(row["flux_level"])
            x, y = float(row["x"]), float(row["y"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"injection {index} is missing numeric flux_level/x/y") from None
        if not all(math.isfinite(v) for v in (flux_jy, x, y)) or flux_jy <= 0:
            raise ValueError(f"injection {index} has invalid flux or position")
        x0 = int(math.floor(x)) - int(px)
        y0 = int(math.floor(y)) - int(py)
        x1, y1 = x0 + p.shape[1], y0 + p.shape[0]
        if x0 < 0 or y0 < 0 or x1 > gain.shape[1] or y1 > gain.shape[0]:
            raise ValueError(f"injection {index} ePSF footprint falls outside the native detector")
        g = gain[y0:y1, x0:x1]
        om = omega[y0:y1, x0:x1]
        if not np.isfinite(g).all() or np.any(g <= 0):
            raise ValueError(f"injection {index} touches an invalid absolute-gain pixel")
        if not np.isfinite(om).all() or np.any(om <= 0):
            raise ValueError(f"injection {index} touches an invalid solid-angle pixel")

        # The integrated Jy source is converted to calibrated Level-2 IMAGE
        # surface brightness per pixel, then to expected added electrons.
        source_signal_mjy_sr = flux_jy * 1.0e-6 * p / om
        electrons_per_image_unit = exposure / g
        expected_electrons = source_signal_mjy_sr * electrons_per_image_unit
        added_variance_image_units2 = expected_electrons / electrons_per_image_unit**2

        bin_row = summary.setdefault(flux_jy, {
            "flux_level_jy": flux_jy,
            "n_injected": 0,
            "expected_electrons_recomputed": 0.0,
            "variance_added_image_units2_recomputed": 0.0,
        })
        bin_row["n_injected"] = int(bin_row["n_injected"]) + 1
        bin_row["expected_electrons_recomputed"] = (
            float(bin_row["expected_electrons_recomputed"]) + float(expected_electrons.sum())
        )
        bin_row["variance_added_image_units2_recomputed"] = (
            float(bin_row["variance_added_image_units2_recomputed"])
            + float(added_variance_image_units2.sum())
        )
    if not summary:
        raise ValueError("injection report contains no injection positions")
    return [summary[key] for key in sorted(summary)]


def _image_hdu(path: Path, label: str):
    from astropy.io import fits

    with fits.open(path, memmap=True, checksum=True) as hdul:
        candidates = [
            hdu for hdu in hdul
            if hdu.data is not None and np.asarray(hdu.data).ndim == 2
        ]
        if not candidates:
            raise ValueError(f"{label} FITS has no 2D image")
        hdu = next((item for item in candidates if str(item.name).upper() == "IMAGE"), candidates[0])
        data = np.asarray(hdu.data, dtype=float).copy()
        header = hdu.header.copy()
        return data, header


def reproduce_m101_audit(audit_dir: str | Path, *, rtol: float = 1e-8) -> dict[str, Any]:
    """Verify native inputs and compare formula-derived sums with the retained report."""
    root = Path(audit_dir)
    summary_path = root / "real_field_audit_summary.json"
    injection_path = root / "calibrated_injection" / "calibrated_jy_injection_recovery.json"
    native_audit_path = root / "native_mef_audit.json"
    science_path = root / "science" / "M101" / "level2_2025W19_2B_0346_1D2_spx_l2b-v27-2026-198.fits"
    gain_path = root / "calibrations" / "absolute_gain" / "abs_gain_matrix_D2_spx_cal-agm-v8-2026-191.fits"
    area_path = root / "calibrations" / "solid_angle" / "solid_angle_pixel_map_D2_spx_cal-sapm-v3-2026-191.fits"
    wcs_path = root / "calibrations" / "spectral_wcs" / "spectral_wcs_D2_spx_cal-swcs-v5-2026-191.fits"
    psf_path = root / "calibrated_injection" / "native_epsf_stamp_nonnegative.fits"

    for path in (
        summary_path, injection_path, native_audit_path, science_path,
        gain_path, area_path, wcs_path, psf_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(f"required retained audit input is missing: {path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    injection = json.loads(injection_path.read_text(encoding="utf-8"))
    native_audit = json.loads(native_audit_path.read_text(encoding="utf-8"))
    record = injection["source_photon_noise"]["calibration_record"]
    science_sha = sha256_file(science_path)
    gain_sha = sha256_file(gain_path)
    area_sha = sha256_file(area_path)
    wcs_sha = sha256_file(wcs_path)
    psf_sha = sha256_file(psf_path)
    summary_sha = sha256_file(summary_path)
    injection_sha = sha256_file(injection_path)
    native_audit_sha = sha256_file(native_audit_path)

    if record.get("verification_status") != "derived_pending_independent_review":
        raise ValueError("the retained source-Poisson record no longer declares pending independent review")
    if record.get("review_status") != "pending" or record.get("independent_human_reviewed") is True:
        raise ValueError("review state must remain pending; an automated script cannot sign calibration review")
    if record.get("science_file_sha256") != science_sha:
        raise ValueError("science MEF SHA-256 does not match the injection calibration record")
    if record.get("calibration_sha256") != gain_sha:
        raise ValueError("absolute-gain SHA-256 does not match the injection calibration record")
    provenance = summary.get("archive_provenance") or {}
    links = provenance.get("exact_product_links") or {}
    gain_link = links.get("absolute_gain") or {}
    wcs_link = links.get("spectral_wcs") or {}
    if gain_link.get("status") != "verified_from_live_irsa_foreign_key_query":
        raise ValueError("absolute-gain product has no verified live archive provenance link")
    if gain_link.get("calibration_sha256") != gain_sha:
        raise ValueError("absolute-gain SHA-256 disagrees with the live provenance record")
    if wcs_link.get("status") != "verified_from_live_irsa_foreign_key_query":
        raise ValueError("spectral-WCS product has no verified live archive provenance link")
    if wcs_link.get("calibration_sha256") != wcs_sha:
        raise ValueError("spectral-WCS SHA-256 disagrees with the live provenance record")
    if native_audit.get("status") != "STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS":
        raise ValueError("native MEF audit did not pass structural and compatibility checks")
    if native_audit.get("science_sha256") != science_sha:
        raise ValueError("native audit science SHA-256 does not match the retained science MEF")
    if native_audit.get("spectral_wcs_sha256") != wcs_sha:
        raise ValueError("native audit spectral-WCS SHA-256 does not match the retained WCS file")
    solid_audit_sha = (native_audit.get("solid_angle") or {}).get("sha256")
    if solid_audit_sha != area_sha:
        raise ValueError("native audit solid-angle SHA-256 does not match the retained map")

    science, science_header = _image_hdu(science_path, "science MEF")
    gain, gain_header = _image_hdu(gain_path, "absolute-gain")
    area_arcsec2, area_header = _image_hdu(area_path, "solid-angle")
    psf, _ = _image_hdu(psf_path, "corrected ePSF")

    if science.shape != (2040, 2040) or gain.shape != science.shape or area_arcsec2.shape != science.shape:
        raise ValueError("science, gain and solid-angle arrays must be aligned native 2040x2040 images")
    if str(science_header.get("BUNIT", "")).strip() != "MJy / sr":
        raise ValueError("science IMAGE BUNIT is not the expected MJy / sr")
    if str(gain_header.get("BUNIT", "")).strip() != record.get("calibration_bunit"):
        raise ValueError("absolute-gain FITS BUNIT does not match the provenance-derived calibration record")
    if str(gain_header.get("DETECTOR", "")).strip() not in {"2", "D2"}:
        raise ValueError("absolute-gain FITS detector is not D2")
    if str(area_header.get("BUNIT", "")).strip().lower() not in {"arcsec2", "arcsec^2", "arcsec**2"}:
        raise ValueError("solid-angle FITS BUNIT must be square arcseconds")
    if not np.isclose(float(summary["science"]["exposure_time_s"]), float(record["exposure_time_s"]), rtol=0, atol=1e-9):
        raise ValueError("science exposure time disagrees with the electron calibration record")
    if injection.get("flux_unit") != "Jy":
        raise ValueError("retained injection experiment is not an integrated-Jy injection")

    area_sr = area_arcsec2 * ARCSEC2_TO_SR
    bins = recompute_source_poisson_bins(
        injection.get("injections") or [],
        psf,
        gain,
        area_sr,
        exposure_time_s=float(record["exposure_time_s"]),
    )
    reported = injection.get("flux_summary") or []
    if len(bins) != len(reported):
        raise ValueError("recomputed flux-bin count differs from the retained injection report")

    comparisons = []
    for recomputed, original in zip(bins, sorted(reported, key=lambda row: float(row["flux_level"]))):
        if int(recomputed["n_injected"]) != int(original["n_injected"]):
            raise ValueError("injection count differs for a flux bin")
        for local_key, original_key in (
            ("expected_electrons_recomputed", "source_poisson_expected_electrons"),
            ("variance_added_image_units2_recomputed", "source_poisson_variance_added_image_units2"),
        ):
            actual = float(recomputed[local_key])
            expected = float(original[original_key])
            if not math.isclose(actual, expected, rel_tol=rtol, abs_tol=1e-12):
                raise ValueError(
                    f"{local_key} mismatch at {recomputed['flux_level_jy']} Jy: "
                    f"recomputed={actual:.12g}, report={expected:.12g}"
                )
        comparisons.append({
            **recomputed,
            "reported_expected_electrons": float(original["source_poisson_expected_electrons"]),
            "reported_variance_added_image_units2": float(original["source_poisson_variance_added_image_units2"]),
            "expected_electrons_relative_difference": (
                float(recomputed["expected_electrons_recomputed"])
                - float(original["source_poisson_expected_electrons"])
            ) / max(abs(float(original["source_poisson_expected_electrons"])), 1e-30),
            "variance_relative_difference": (
                float(recomputed["variance_added_image_units2_recomputed"])
                - float(original["source_poisson_variance_added_image_units2"])
            ) / max(abs(float(original["source_poisson_variance_added_image_units2"])), 1e-30),
            "recovered": int(original["n_recovered"]),
            "wilson95": [
                float(original["completeness_wilson95_low"]),
                float(original["completeness_wilson95_high"]),
            ],
        })

    return {
        "schema": REPRODUCER_SCHEMA,
        "status": "FORMULA_RECOMPUTATION_PASS_NOT_INSTRUMENT_SIGNOFF",
        "scientific_acceptance": "NOT_GRANTED_REQUIRES_INDEPENDENT_REVIEWER",
        "repository_commit_to_review": str(summary.get("repository_commit") or "not recorded in summary"),
        "science_observation_id": record["science_observation_id"],
        "detector": record["detector"],
        "release": summary.get("release"),
        "exposure_time_s": float(record["exposure_time_s"]),
        "input_sha256": {
            "science_mef": science_sha,
            "absolute_gain": gain_sha,
            "solid_angle": area_sha,
            "spectral_wcs": wcs_sha,
            "native_mef_audit": native_audit_sha,
            "corrected_epsf": psf_sha,
            "audit_summary": summary_sha,
            "injection_report": injection_sha,
        },
        "live_provenance_relation_count": int(provenance.get("input_relation_count", 0)),
        "calibration_record_status": record["verification_status"],
        "independent_human_reviewed": False,
        "comparisons": comparisons,
        "what_was_not_reproduced": [
            "The actual Poisson random sequence/realized electrons (the original random stream includes placement selection and is not reconstructed here).",
            "The matched-filter peak finder, detection outcomes, or completeness values from the detector output.",
            "Mission-level validity of the gain/noise interpretation or absence of variance double counting.",
            "Any blind-benchmark or independent astronomical acceptance gate.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    result = reproduce_m101_audit(args.audit_dir)
    output = args.output or (args.audit_dir / "source_poisson_independent_recomputation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
