#!/usr/bin/env python3
"""Blind injection/recovery experiment on a real SPHEREx Level-2 MEF.

The PSF stamp must be extracted from the matching DR1 ePSF product and
normalized to unit sum. This tool does not create a fake instrument PSF.
"""
from __future__ import annotations
import argparse, csv, json, hashlib
from pathlib import Path
import numpy as np
from scipy.signal import fftconvolve
from scipy.ndimage import maximum_filter



def normalize_psf(psf: np.ndarray) -> np.ndarray:
    """Validate and unit-normalize a native-pixel PSF without changing its phase."""
    p = np.asarray(psf, dtype=float)
    if p.ndim != 2 or any(n % 2 == 0 for n in p.shape):
        raise ValueError("PSF must be a 2D odd-sized stamp")
    if not np.isfinite(p).all() or np.any(p < 0):
        raise ValueError("PSF must be finite and nonnegative")
    total = float(p.sum())
    if not np.isfinite(total) or total <= 0:
        raise ValueError("PSF must have a finite positive sum")
    return p / total


def validate_electron_calibration_record(record):
    """Validate the exposure and absolute-gain provenance record; returns a copy."""
    if not isinstance(record, dict):
        raise ValueError("source Poisson noise requires an electron calibration record")
    required = ("verification_status", "science_file_sha256", "science_observation_id",
                "science_source_uri", "detector", "image_unit", "exposure_time_s",
                "calibration_product", "calibration_uri", "calibration_file_path",
                "calibration_sha256", "calibration_bunit", "conversion_method",
                "verified_by", "verified_utc")
    missing = [key for key in required if record.get(key) in (None, "")]
    if missing:
        raise ValueError("electron calibration record is missing: " + ", ".join(missing))
    if record["verification_status"] != "verified":
        raise ValueError("electron calibration is not marked verified; deterministic injection remains available")
    if record["calibration_product"] != "abs_gain_matrix":
        raise ValueError("SPHEREx source photon noise requires the detector-specific abs_gain_matrix")
    exposure_time = float(record["exposure_time_s"])
    if not np.isfinite(exposure_time) or exposure_time <= 0:
        raise ValueError("calibration record exposure_time_s must be finite and positive")
    import re
    for key in ("science_file_sha256", "calibration_sha256"):
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(record[key])):
            raise ValueError(f"{key} must be a 64-character SHA-256 hex digest")
    if not str(record["science_source_uri"]).startswith("https://"):
        raise ValueError("science_source_uri must be an HTTPS archive URI")
    if not str(record["calibration_uri"]).startswith("https://"):
        raise ValueError("calibration_uri must be an HTTPS source URI")
    if not str(record["calibration_bunit"]).strip():
        raise ValueError("absolute-gain calibration BUNIT must be recorded exactly")
    if record.get("detector") not in {"D1","D2","D3","D4","D5","D6"}:
        raise ValueError("detector must be the exact D1-D6 identifier")
    if str(record.get("science_native_file_sha256", record["science_file_sha256"])).lower() != str(record["science_file_sha256"]).lower():
        raise ValueError("science_native_file_sha256 must match the native science MEF SHA-256")
    if not str(record.get("conversion_method","")).strip():
        raise ValueError("conversion_method must document the physical unit derivation")
    from datetime import datetime
    try:
        verified_at = datetime.fromisoformat(str(record["verified_utc"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("verified_utc must be an ISO-8601 timestamp") from exc
    if verified_at.tzinfo is None:
        raise ValueError("verified_utc must include a timezone")
    calibration_path = Path(str(record["calibration_file_path"]))
    if not calibration_path.is_file():
        raise FileNotFoundError(f"absolute-gain calibration bytes are unavailable: {calibration_path}")
    digest = hashlib.sha256()
    with calibration_path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest().lower() != str(record["calibration_sha256"]).lower():
        raise ValueError("absolute-gain calibration file SHA-256 does not match the signed-off record")
    return dict(record)


def inject_source_patch(image: np.ndarray, variance: np.ndarray, flags: np.ndarray,
                        source_signal: np.ndarray, x: float, y: float, *,
                        rng: np.random.Generator,
                        electrons_per_image_unit: float | np.ndarray | None = None,
                        excluded_flag_bits: int = 0) -> dict:
    """Inject a full PSF patch; pixel map is e-/IMAGE-unit for each detector pixel."""
    image, variance, flags = np.asarray(image), np.asarray(variance), np.asarray(flags)
    signal = np.asarray(source_signal, dtype=float)
    if image.ndim != 2 or variance.shape != image.shape or flags.shape != image.shape:
        raise ValueError("IMAGE, VARIANCE and FLAGS must be aligned 2D arrays")
    if signal.ndim != 2 or any(n % 2 == 0 for n in signal.shape):
        raise ValueError("source_signal must be an odd-sized 2D PSF patch")
    if not np.isfinite(signal).all() or np.any(signal < 0):
        raise ValueError("source_signal must be finite and nonnegative")
    if not np.isfinite(x) or not np.isfinite(y):
        raise ValueError("source coordinates must be finite")
    py, px = np.array(signal.shape) // 2
    x0, y0 = int(np.floor(x)) - int(px), int(np.floor(y)) - int(py)
    x1, y1 = x0 + signal.shape[1], y0 + signal.shape[0]
    if x0 < 0 or y0 < 0 or x1 > image.shape[1] or y1 > image.shape[0]:
        raise ValueError("full PSF footprint falls outside the image; edge clipping is prohibited")
    sl = (slice(y0, y1), slice(x0, x1))
    image_patch = np.asarray(image[sl], dtype=float)
    variance_patch = np.asarray(variance[sl], dtype=float)
    if not np.isfinite(image_patch).all() or not np.isfinite(variance_patch).all() or np.any(variance_patch <= 0):
        raise ValueError("full PSF footprint touches invalid IMAGE or VARIANCE pixels")
    if excluded_flag_bits and np.any((flags[sl].astype(np.uint64) & np.uint64(excluded_flag_bits)) != 0):
        raise ValueError("full PSF footprint touches an excluded flag pixel")
    if electrons_per_image_unit is None:
        image[sl] += signal
        return {"mode": "deterministic", "variance_added_sum": 0.0}
    conversion = np.asarray(electrons_per_image_unit, dtype=float)
    if conversion.ndim == 0:
        gain_patch = np.full(signal.shape, float(conversion), dtype=float)
    elif conversion.shape == image.shape:
        gain_patch = conversion[sl]
    elif conversion.shape == signal.shape:
        gain_patch = conversion
    else:
        raise ValueError("electron conversion must be scalar in a unit test or align with IMAGE/PSF patch")
    active = signal > 0
    if not active.any() or not np.isfinite(gain_patch[active]).all() or np.any(gain_patch[active] <= 0):
        raise ValueError("absolute-gain conversion is invalid inside the PSF footprint")
    expected_electrons = np.zeros(signal.shape, dtype=float)
    expected_electrons[active] = signal[active] * gain_patch[active]
    realization = np.zeros(signal.shape, dtype=float)
    variance_added = np.zeros(signal.shape, dtype=float)
    realization[active] = rng.poisson(expected_electrons[active]) / gain_patch[active]
    variance_added[active] = expected_electrons[active] / (gain_patch[active] ** 2)
    image[sl] += realization
    variance[sl] += variance_added
    return {"mode": "source_poisson",
            "variance_added_sum": float(variance_added.sum())}


def matched_filter_flux_uncertainty_jy(
    psf: np.ndarray,
    variance_patch: np.ndarray,
    solid_angle_sr_patch: np.ndarray,
) -> float:
    """Return the known-covariance matched-filter 1-sigma flux error in Jy.

    IMAGE is in MJy/sr. A unit-integral ePSF p_i for integrated flux F_Jy
    produces image signal 1e-6 * F_Jy * p_i / Omega_i. With diagonal
    variance V_i, the Fisher information is
    1e-12 * sum((p_i / Omega_i)^2 / V_i).
    """
    p = normalize_psf(psf)
    var = np.asarray(variance_patch, dtype=float)
    omega = np.asarray(solid_angle_sr_patch, dtype=float)
    if var.shape != p.shape or omega.shape != p.shape:
        raise ValueError("PSF, variance and solid-angle patches must have identical shapes")
    if (np.any(~np.isfinite(var)) or np.any(var <= 0)
            or np.any(~np.isfinite(omega)) or np.any(omega <= 0)):
        raise ValueError("variance and solid-angle patches must be finite and positive")
    information_without_jy_scale = float(np.sum((p / omega) ** 2 / var))
    if not np.isfinite(information_without_jy_scale) or information_without_jy_scale <= 0:
        raise ValueError("matched-filter flux information must be finite and positive")
    return float(1.0e6 / np.sqrt(information_without_jy_scale))


def matched_filter_snr_jy(
    image: np.ndarray,
    variance: np.ndarray,
    psf: np.ndarray,
    solid_angle_sr_map: np.ndarray,
    *,
    region_center_xy: tuple[float, float],
    region_radius_px: float,
) -> np.ndarray:
    """Position-dependent matched-filter SNR for Jy sources in MJy/sr images.

    A local response p_i/Omega_i is evaluated for every candidate pixel, so
    the detector-aligned solid-angle map is included inside each PSF
    footprint. Only the requested local region is evaluated; pixels outside
    it remain NaN.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    data = np.asarray(image, dtype=float)
    var = np.asarray(variance, dtype=float)
    omega = np.asarray(solid_angle_sr_map, dtype=float)
    p = normalize_psf(psf)
    if data.ndim != 2 or var.shape != data.shape or omega.shape != data.shape:
        raise ValueError("image, variance and solid-angle map must be aligned 2D arrays")
    if not np.isfinite(region_radius_px) or region_radius_px <= 0:
        raise ValueError("region_radius_px must be positive and finite")
    if len(region_center_xy) != 2 or not np.all(np.isfinite(region_center_xy)):
        raise ValueError("region_center_xy must contain finite x,y coordinates")
    height, width = data.shape
    py, px = np.array(p.shape) // 2
    cx, cy = map(float, region_center_xy)
    x_first = max(px, int(np.ceil(cx - region_radius_px)))
    x_last = min(width - px - 1, int(np.floor(cx + region_radius_px)))
    y_first = max(py, int(np.ceil(cy - region_radius_px)))
    y_last = min(height - py - 1, int(np.floor(cy + region_radius_px)))
    output = np.full(data.shape, np.nan, dtype=float)
    if x_last < x_first or y_last < y_first:
        raise ValueError("requested local matched-filter region does not intersect the image")

    image_windows = sliding_window_view(data, p.shape)[
        y_first - py:y_last - py + 1,
        x_first - px:x_last - px + 1,
    ]
    variance_windows = sliding_window_view(var, p.shape)[
        y_first - py:y_last - py + 1,
        x_first - px:x_last - px + 1,
    ]
    omega_windows = sliding_window_view(omega, p.shape)[
        y_first - py:y_last - py + 1,
        x_first - px:x_last - px + 1,
    ]
    good = (
        np.all(np.isfinite(image_windows), axis=(-2, -1))
        & np.all(np.isfinite(variance_windows) & (variance_windows > 0), axis=(-2, -1))
        & np.all(np.isfinite(omega_windows) & (omega_windows > 0), axis=(-2, -1))
    )
    safe_var = np.where(np.isfinite(variance_windows) & (variance_windows > 0),
                        variance_windows, 1.0)
    safe_omega = np.where(np.isfinite(omega_windows) & (omega_windows > 0),
                          omega_windows, 1.0)
    response = p[None, None, :, :] / safe_omega
    weighted_response = response / safe_var
    numerator = np.sum(image_windows * weighted_response, axis=(-2, -1))
    denominator_squared = np.sum(response * weighted_response, axis=(-2, -1))
    local_snr = np.full(numerator.shape, np.nan, dtype=float)
    valid = good & np.isfinite(denominator_squared) & (denominator_squared > 0)
    local_snr[valid] = numerator[valid] / np.sqrt(denominator_squared[valid])
    output[y_first:y_last + 1, x_first:x_last + 1] = local_snr
    return output


def matched_filter_snr(image: np.ndarray, variance: np.ndarray, psf: np.ndarray) -> np.ndarray:
    image=np.asarray(image,float); variance=np.asarray(variance,float); psf=np.asarray(psf,float)
    if image.ndim!=2 or variance.shape!=image.shape: raise ValueError("image and variance must be same-sized 2D arrays")
    if psf.ndim!=2 or any(n%2==0 for n in psf.shape): raise ValueError("PSF stamp must be 2D with odd dimensions")
    if not np.isfinite(psf).all() or (psf<0).any() or psf.sum()<=0: raise ValueError("PSF must be finite, nonnegative and have positive sum")
    psf=psf/psf.sum()
    good=np.isfinite(image)&np.isfinite(variance)&(variance>0)
    invvar=np.zeros_like(variance); invvar[good]=1.0/variance[good]
    kernel=psf[::-1,::-1]
    numerator=fftconvolve(np.where(good,image,0.0)*invvar,kernel,mode="same")
    denominator2=fftconvolve(invvar,(psf*psf)[::-1,::-1],mode="same")
    snr=np.full(image.shape,np.nan,float)
    ok=denominator2>0
    snr[ok]=numerator[ok]/np.sqrt(denominator2[ok])
    return snr


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Two-sided Wilson score interval for a binomial proportion."""
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("require 0 <= successes <= total and total > 0")
    p = successes / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = (p + z2 / (2.0 * total)) / denom
    half = z * np.sqrt((p * (1.0 - p) / total) + z2 / (4.0 * total * total)) / denom
    return max(0.0, float(center - half)), min(1.0, float(center + half))


def detect_peaks(snr: np.ndarray, threshold: float=5.0, min_sep: int=5) -> np.ndarray:
    s=np.asarray(snr,float)
    good=np.isfinite(s)
    local=maximum_filter(np.where(good,s,-np.inf),size=2*min_sep+1,mode="constant",cval=-np.inf)
    yy,xx=np.where(good&(s>=threshold)&(s==local))
    if len(xx)==0: return np.empty((0,3),float)
    return np.column_stack([xx,yy,s[yy,xx]])


def _distance(a: np.ndarray,b: np.ndarray)->np.ndarray:
    if len(a)==0 or len(b)==0:return np.empty((len(a),len(b)))
    return np.sqrt(((a[:,None,:2]-b[None,:,:2])**2).sum(axis=2))


def _choose_positions(valid: np.ndarray,n: int,margin: int,rng: np.random.Generator,min_distance: int,
                      phase: tuple[float,float]=(0.0,0.0), reference_xy: tuple[float,float] | None=None,
                      region_radius: float | None=None)->np.ndarray:
    h,w=valid.shape; coords=[]; attempts=0; max_attempts=max(3000,n*300)
    while len(coords)<n and attempts<max_attempts:
        attempts+=1; ix=int(rng.integers(margin,w-margin)); iy=int(rng.integers(margin,h-margin))
        x=float(ix)+phase[0]; y=float(iy)+phase[1]
        if not valid[iy,ix]: continue
        if reference_xy is not None and region_radius is not None:
            if (x-reference_xy[0])**2+(y-reference_xy[1])**2 > region_radius**2: continue
        if coords and np.min(np.sqrt(((np.asarray(coords)-[x,y])**2).sum(axis=1)))<min_distance: continue
        coords.append((x,y))
    if len(coords)<n: raise RuntimeError(f"Could place only {len(coords)}/{n} injections; lower density, increase region radius, or relax masks")
    return np.asarray(coords,float)


def run_injection_recovery(image: np.ndarray, variance: np.ndarray, flags: np.ndarray,
                           psf: np.ndarray, *, flux_levels: list[float], n_per_level: int=100,
                           snr_threshold: float=5.0, match_radius: float=2.5,
                           excluded_flag_bits: int=0, seed: int=20261114,
                           min_injection_separation: int=16,
                           source_exclusion_radius: int=7,
                           solid_angle_sr_map: np.ndarray | None = None,
                           flux_unit: str = "image_sum",
                           psf_reference_xy: tuple[float,float] | None = None,
                           psf_region_radius: float | None = None,
                           background: np.ndarray | None = None,
                           electrons_per_image_unit: np.ndarray | None = None,
                           electron_calibration_record: dict | None = None,
                           detection_psf: np.ndarray | None = None) -> dict:
    image=np.asarray(image,float); variance=np.asarray(variance,float); flags=np.asarray(flags)
    if image.ndim!=2 or variance.shape!=image.shape or flags.shape!=image.shape: raise ValueError("IMAGE/VARIANCE/FLAGS must have equal 2D shapes")
    if not flux_levels or any((not np.isfinite(x)) or x<=0 for x in flux_levels): raise ValueError("injected flux levels must be finite and >0")
    if n_per_level <= 0: raise ValueError("n_per_level must be >0")
    if snr_threshold <= 0 or match_radius <= 0: raise ValueError("snr_threshold and match_radius must be >0")
    if min_injection_separation < 1: raise ValueError("min_injection_separation must be >=1")
    if background is not None:
        background=np.asarray(background,float)
        if background.shape != image.shape: raise ValueError("background model must be aligned to IMAGE and have the same shape")
        work_image=image-background
    else:
        work_image=image.copy()
    if flux_unit not in {"image_sum", "Jy"}: raise ValueError("flux_unit must be 'image_sum' or 'Jy'")
    if electrons_per_image_unit is not None:
        if electron_calibration_record is None:
            raise ValueError("A conversion map cannot be used without its signed calibration record")
        validate_electron_calibration_record(electron_calibration_record)
        electrons_per_image_unit = np.asarray(electrons_per_image_unit, dtype=float)
        if electrons_per_image_unit.shape != image.shape:
            raise ValueError("per-pixel electrons-per-image-unit map must align exactly with IMAGE")
        conversion_valid = np.isfinite(electrons_per_image_unit) & (electrons_per_image_unit > 0)
        if not conversion_valid.any():
            raise ValueError("absolute-gain map has no finite positive conversion pixels")
    elif electron_calibration_record is not None:
        raise ValueError("electron calibration record supplied without its derived per-pixel conversion map")
    omega = None
    if flux_unit == "Jy":
        if solid_angle_sr_map is None: raise ValueError("Jy injections require a detector-aligned solid-angle map in steradians")
        omega = np.asarray(solid_angle_sr_map, float)
        if omega.shape != image.shape: raise ValueError("solid-angle map must be aligned to IMAGE and have the same shape")
    p=normalize_psf(psf)
    # The injected source uses the integrated-flux ePSF. For calibrated Jy
    # images, the matched-filter template may additionally include the local
    # pixel-solid-angle conversion (surface brightness response).
    filter_psf = normalize_psf(detection_psf) if detection_psf is not None else p
    if filter_psf.shape != p.shape:
        raise ValueError("detection_psf must have the same stamp shape as the injected ePSF")
    py,px=np.array(p.shape)//2
    good=np.isfinite(work_image)&np.isfinite(variance)&(variance>0)
    if excluded_flag_bits: good &= (flags.astype(np.uint64)&np.uint64(excluded_flag_bits))==0
    if flux_unit == "Jy": good &= np.isfinite(omega) & (omega > 0)
    if electrons_per_image_unit is not None:
        good &= np.isfinite(electrons_per_image_unit) & (electrons_per_image_unit > 0)
    margin=max(px,py)+min_injection_separation//2+2
    if image.shape[0] <= 2*margin or image.shape[1] <= 2*margin:
        raise ValueError(f"image is too small for safe injection margins: shape={image.shape}, required dimension > {2*margin}")
    from scipy.ndimage import minimum_filter
    # The entire PSF footprint, not only its centre, must be unflagged and valid.
    valid=minimum_filter(good.astype(np.uint8),size=p.shape,mode="constant",cval=0)>0
    valid[:margin]=False;valid[-margin:]=False;valid[:,:margin]=False;valid[:,-margin:]=False
    # Do not score detections whose matched-filter footprint touches a flagged
    # or otherwise invalid pixel. Keep this mask separate from the later
    # exclusion of pre-existing source cores used only for injection placement.
    detection_valid = valid.copy()
    if psf_reference_xy is not None and psf_region_radius is None:
        raise ValueError("psf_region_radius is required when psf_reference_xy is supplied")
    if psf_region_radius is not None and (psf_reference_xy is None or psf_region_radius <= 0):
        raise ValueError("positive psf_region_radius requires psf_reference_xy")
    rng=np.random.default_rng(seed)
    if flux_unit == "Jy" and psf_reference_xy is not None and psf_region_radius is not None:
        baseline_snr = matched_filter_snr_jy(
            work_image, variance, p, omega,
            region_center_xy=psf_reference_xy, region_radius_px=psf_region_radius,
        )
    else:
        baseline_snr = matched_filter_snr(work_image,variance,filter_psf)
    baseline_snr[~detection_valid] = np.nan
    baseline=detect_peaks(baseline_snr,threshold=snr_threshold)
    # Do not inject on top of already-detected real sources: otherwise source
    # blending inflates or suppresses recovery in a way that is not controlled.
    if source_exclusion_radius < 0:
        raise ValueError("source_exclusion_radius must be >= 0")
    if len(baseline) and source_exclusion_radius:
        yy,xx=np.ogrid[:image.shape[0],:image.shape[1]]
        r2=source_exclusion_radius**2
        for sx,sy,_ in baseline:
            valid[(xx-sx)**2+(yy-sy)**2 <= r2] = False
    phase=(0.0,0.0) if psf_reference_xy is None else (float(psf_reference_xy[0])%1.0,float(psf_reference_xy[1])%1.0)
    rows=[]; all_detected=[]; injected=[]
    for level in flux_levels:
        xy=_choose_positions(valid,n_per_level,margin,rng,min_injection_separation,
            phase=phase,reference_xy=psf_reference_xy,region_radius=psf_region_radius)
        injected_img=work_image.copy()
        injected_variance=variance.copy()
        for x,y in xy:
            x0=int(np.floor(x))-px;y0=int(np.floor(y))-py
            if flux_unit == "Jy":
                # IMAGE is MJy/sr. Convert integrated source flux density F[Jy]
                # to pixel surface brightness through each pixel solid angle.
                omega_patch = omega[y0:y0+p.shape[0], x0:x0+p.shape[1]]
                source_signal = (level * 1e-6 / omega_patch) * p
            else:
                # This is deliberately an image-sum injection unit, not Jy.
                source_signal = level*p
            inject_source_patch(injected_img, injected_variance, flags, source_signal, x, y,
                rng=rng, electrons_per_image_unit=electrons_per_image_unit,
                excluded_flag_bits=excluded_flag_bits)
        if flux_unit == "Jy" and psf_reference_xy is not None and psf_region_radius is not None:
            injected_snr = matched_filter_snr_jy(
                injected_img, injected_variance, p, omega,
                region_center_xy=psf_reference_xy, region_radius_px=psf_region_radius,
            )
        else:
            injected_snr = matched_filter_snr(injected_img,injected_variance,filter_psf)
        injected_snr[~detection_valid] = np.nan
        peaks=detect_peaks(injected_snr,threshold=snr_threshold)
        distances=_distance(peaks,xy)
        recovered=set(); matched_peak=set()
        if distances.size:
            for idx in np.argsort(distances,axis=None):
                i,j=np.unravel_index(idx,distances.shape)
                if distances[i,j]>match_radius: break
                if int(j) not in recovered and int(i) not in matched_peak:
                    recovered.add(int(j));matched_peak.add(int(i))
        for j,(x,y) in enumerate(xy):
            rows.append({"flux_level":float(level),"x":float(x),"y":float(y),"recovered":int(j in recovered),
                         "nearest_detection_distance_px":float(np.min(distances[:,j])) if len(peaks) else None})
        # Only newly appearing peaks count as candidate false alarms. Genuine
        # pre-existing sky sources are not relabelled as false positives.
        new_peaks=[]
        n_outside_local_psf_region = 0
        for i,pk in enumerate(peaks):
            if i in matched_peak: continue
            if len(baseline) and np.min(_distance(np.asarray([pk]),baseline)[0])<=match_radius: continue
            if psf_reference_xy is not None and psf_region_radius is not None:
                if (pk[0]-psf_reference_xy[0])**2 + (pk[1]-psf_reference_xy[1])**2 > psf_region_radius**2:
                    n_outside_local_psf_region += 1
                    continue
            new_peaks.append(pk)
        all_detected.append({"flux_level":float(level),"new_unmatched_peaks_within_local_psf_region":len(new_peaks),
                             "unmatched_peaks_outside_local_psf_region_excluded":n_outside_local_psf_region})
        offsets=[float(np.min(distances[:,j])) for j in sorted(recovered)] if len(peaks) else []
        ci_low,ci_high=wilson_interval(len(recovered),len(xy))
        injected.append({"flux_level":float(level),"n_injected":len(xy),"n_recovered":len(recovered),
                         "completeness":len(recovered)/len(xy),"completeness_wilson95_low":ci_low,
                         "completeness_wilson95_high":ci_high,
                         "median_astrometric_offset_px":float(np.median(offsets)) if offsets else None,
                         "p95_astrometric_offset_px":float(np.percentile(offsets,95)) if offsets else None})
    return {"experiment":"SPHEREx DR1 real-image injection/recovery",
      "n_image_pixels":int(image.size),"image_shape":list(image.shape),"n_baseline_detections":int(len(baseline)),
      "psf_reference_xy":list(psf_reference_xy) if psf_reference_xy is not None else None,
      "psf_local_region_radius_px":float(psf_region_radius) if psf_region_radius is not None else None,
      "subpixel_phase_preserved":bool(psf_reference_xy is not None),
      "threshold_snr":float(snr_threshold),"match_radius_px":float(match_radius),
      "excluded_flag_bits":int(excluded_flag_bits),"flux_unit":flux_unit,
      "background_model_subtracted":bool(background is not None),
      "detection_template": {
          "uses_separate_surface_brightness_psf": detection_psf is not None,
          "unit_sum": float(filter_psf.sum()),
          "shape": list(filter_psf.shape),
          "note": "Injection morphology remains the integrated-flux ePSF; the optional detection template represents the same ePSF divided by the local pixel solid angle for MJy/sr data."
      },
      "source_photon_noise": {
          "enabled": electrons_per_image_unit is not None,
          "physically_modelled": electrons_per_image_unit is not None and electron_calibration_record is not None,
          "conversion_map_shape": list(electrons_per_image_unit.shape) if electrons_per_image_unit is not None else None,
          "conversion_map_valid_fraction": float(np.mean(np.isfinite(electrons_per_image_unit) & (electrons_per_image_unit > 0))) if electrons_per_image_unit is not None else None,
          "conversion": "exposure_time_s / abs_gain_matrix at each detector pixel" if electrons_per_image_unit is not None else None,
          "calibration_record": electron_calibration_record,
          "variance_update": "Added pixel-dependent source Poisson variance in IMAGE units" if electrons_per_image_unit is not None else "Not modelled; deterministic signal only",
      },
      "background_interpretation":"Caller-supplied aligned background model subtracted before matched filtering" if background is not None else "No background model subtracted; users should supply the matching ZODI/background or precomputed residual map for scientifically appropriate detection",
      "flux_interpretation":"Jy integrated source flux converted through a detector-aligned steradian pixel-area map" if flux_unit == "Jy" else "sum of per-pixel IMAGE units; not an integrated Jy flux",
      "source_exclusion_radius_px":int(source_exclusion_radius),
      "baseline_source_exclusion_applied":True,"seed":int(seed),"n_per_flux_level":int(n_per_level),
      "flux_summary":injected,"new_unmatched_peak_summary":all_detected,"injections":rows,
      "interpretation":"Completeness is measured conditional on this field, PSF, masks, flux levels and threshold. It is not all-sky performance.",
      "independence_warning":"Run on pre-registered, held-out fields not used to tune thresholds. Report per-field results and confidence intervals."}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("science_mef",type=Path);p.add_argument("psf_stamp",type=Path)
    p.add_argument("--image-hdu",default="IMAGE");p.add_argument("--variance-hdu",default="VARIANCE");p.add_argument("--flags-hdu",default="FLAGS")
    p.add_argument("--psf-hdu",default="0");p.add_argument("--flux",nargs="+",type=float,required=True)
    p.add_argument("--n",type=int,default=100);p.add_argument("--threshold",type=float,default=5.0)
    p.add_argument("--flag-policy",choices=("conservative-photometry", "photometry", "background", "none"),
                   default="conservative-photometry",help="Named SPHEREx Level-2 flag mask policy")
    p.add_argument("--flag-bits",type=int,default=0,help="Additional raw flag bits to exclude")
    p.add_argument("--seed",type=int,default=20261114)
    p.add_argument("--electron-calibration-record",type=Path,
                   help="Verified JSON binding this exact science MEF to its absolute-gain calibration")
    p.add_argument("--science-uri",help="Exact native HTTPS archive URI for this science MEF")
    p.add_argument("--exposure-time-s",type=float,
                   help="Exposure time in seconds from the matching archive record")
    p.add_argument("--source-exclusion-radius",type=int,default=7)
    p.add_argument("--flux-unit",choices=("image_sum","Jy"),default="image_sum")
    p.add_argument("--solid-angle-map",type=Path,help="Native detector pixel solid-angle FITS map")
    p.add_argument("--solid-angle-hdu",default="0")
    p.add_argument("--solid-angle-unit",choices=("arcsec2","sr"),default="arcsec2")
    p.add_argument("--background-hdu",default="ZODI",
                   help="Aligned MEF background model HDU (default ZODI); pass NONE to disable")
    p.add_argument("--psf-region-radius",type=float,default=30.0)
    p.add_argument("--out",type=Path,default=Path("injection_recovery"))
    a=p.parse_args()
    try:
        from astropy.io import fits
    except ImportError as exc:
        raise SystemExit("Install astropy to read FITS files") from exc
    psf_sel=int(a.psf_hdu) if a.psf_hdu.isdigit() else a.psf_hdu
    omega=None
    electron_record=json.loads(a.electron_calibration_record.read_text()) if a.electron_calibration_record else None
    electrons_per_image_unit=None
    with fits.open(a.science_mef,memmap=True) as sci, fits.open(a.psf_stamp,memmap=True) as pf:
        image_header=dict(sci[a.image_hdu].header)
        science_sha=hashlib.sha256(a.science_mef.read_bytes()).hexdigest()
        science_obsid=str(image_header.get("OBSID",sci[0].header.get("OBSID",""))).strip()
        science_detector=str(image_header.get("DETECTOR","")).strip()
        science_bunit=str(image_header.get("BUNIT","")).strip()
        image=np.asarray(sci[a.image_hdu].data,float)
        variance=np.asarray(sci[a.variance_hdu].data,float)
        flags=np.asarray(sci[a.flags_hdu].data)
        if image.ndim!=2 or variance.shape!=image.shape or flags.shape!=image.shape:
            raise ValueError("IMAGE, VARIANCE and FLAGS must be aligned 2D arrays")
        background=None
        if a.background_hdu.upper()!="NONE":
            if a.background_hdu not in sci:
                raise ValueError(f"background HDU {a.background_hdu!r} is not present")
            background=np.asarray(sci[a.background_hdu].data,float)
        psf=np.asarray(pf[psf_sel].data,float)
        psf_header=pf[psf_sel].header
        if "SRCX" not in psf_header or "SRCY" not in psf_header:
            raise ValueError("PSF stamp must include SRCX/SRCY metadata from extract_epsf_stamp.py")
        psf_reference_xy=(float(psf_header["SRCX"]),float(psf_header["SRCY"]))
        from research_discovery.spherex.coordinate_transform import detector_origin_offset
        origin_xy=detector_origin_offset(image_header)

        if a.solid_angle_map:
            hdu_sel=int(a.solid_angle_hdu) if a.solid_angle_hdu.isdigit() else a.solid_angle_hdu
            with fits.open(a.solid_angle_map,memmap=True,checksum=True) as om:
                hdu=om[hdu_sel]
                omega_native=np.asarray(hdu.data,float)
                sci_det=str(science_detector).upper().replace("D","")
                om_det=str(hdu.header.get("DETECTOR",om[0].header.get("DETECTOR",""))).upper().replace("D","")
                if not sci_det or not om_det or sci_det!=om_det:
                    raise ValueError(f"solid-angle calibration detector mismatch: science={science_detector!r}, calibration={om_det!r}")
                if omega_native.shape!=(2040,2040):
                    raise ValueError(f"solid-angle map must be native 2040x2040, got {omega_native.shape}")
                if not np.isfinite(omega_native).all() or np.any(omega_native<=0):
                    raise ValueError("solid-angle map contains invalid or nonpositive pixels; no interpolation/filling is allowed")
                x0,y0=origin_xy
                y1,x1=y0+image.shape[0],x0+image.shape[1]
                if x0<0 or y0<0 or x1>2040 or y1>2040:
                    raise ValueError("science cutout exceeds native solid-angle map")
                omega=omega_native[y0:y1,x0:x1].copy()
            if a.solid_angle_unit=="arcsec2":
                omega=omega*(np.pi/(180.0*3600.0))**2
        if electron_record is not None:
            if not a.science_uri or str(electron_record.get("science_source_uri",""))!=a.science_uri:
                raise ValueError("electron calibration record science_source_uri does not match --science-uri")
            if str(electron_record.get("science_native_file_sha256",electron_record.get("science_file_sha256",""))).lower()!=science_sha.lower():
                raise ValueError("electron calibration record native science MEF SHA-256 mismatch")
            if a.exposure_time_s is None or not np.isfinite(a.exposure_time_s) or a.exposure_time_s<=0:
                raise ValueError("--exposure-time-s from the matching archive record is required for photon-noise mode")
            validate_electron_calibration_record(electron_record)
            if not np.isclose(float(electron_record["exposure_time_s"]),a.exposure_time_s,rtol=0,atol=1e-6):
                raise ValueError("record exposure_time_s does not match --exposure-time-s")
            for key,actual in (("science_file_sha256",science_sha),("science_observation_id",science_obsid),
                               ("detector",science_detector),("image_unit",science_bunit)):
                if str(electron_record.get(key,"")).lower()!=str(actual).lower():
                    raise ValueError(f"electron calibration record {key} does not match this science MEF")
            from research_discovery.spherex.electron_conversion import derive_electrons_per_image_unit
            electrons_per_image_unit=derive_electrons_per_image_unit(
                calibration_path=electron_record["calibration_file_path"],
                expected_sha256=electron_record["calibration_sha256"],
                detector=science_detector,calibration_bunit=electron_record["calibration_bunit"],
                exposure_time_s=a.exposure_time_s,origin_xy=origin_xy,image_shape=image.shape,
                science_image_unit=science_bunit)
        elif a.exposure_time_s is not None:
            raise ValueError("--exposure-time-s is only valid with --electron-calibration-record")
    if a.flux_unit=="Jy" and omega is None:
        raise SystemExit("--flux-unit Jy requires --solid-angle-map")
    if electron_record is not None and electrons_per_image_unit is None:
        raise RuntimeError("absolute-gain conversion map was not derived")
    from research_discovery.spherex.flag_policy import policy_mask
    policy_bits,policy_names=policy_mask(a.flag_policy)
    excluded_bits=int(policy_bits)|int(a.flag_bits)
    result=run_injection_recovery(
        image,variance,flags,psf,flux_levels=a.flux,n_per_level=a.n,
        snr_threshold=a.threshold,excluded_flag_bits=excluded_bits,seed=a.seed,
        source_exclusion_radius=a.source_exclusion_radius,
        solid_angle_sr_map=omega,flux_unit=a.flux_unit,
        psf_reference_xy=psf_reference_xy,psf_region_radius=a.psf_region_radius,
        background=background,electrons_per_image_unit=electrons_per_image_unit,
        electron_calibration_record=electron_record)
    a.out.mkdir(parents=True,exist_ok=True)
    result["science_provenance"]={"native_uri":a.science_uri,"local_path":str(a.science_mef),
        "sha256":science_sha,"observation_id":science_obsid,"detector":science_detector,
        "image_unit":science_bunit,"exposure_time_s":a.exposure_time_s,"detector_origin_xy":list(origin_xy)}
    result["flag_policy"]={"name":a.flag_policy,"excluded_flag_names":list(policy_names),
        "excluded_flag_bits_additional":int(a.flag_bits),"excluded_flag_mask_combined":int(excluded_bits)}
    (a.out/"summary.json").write_text(json.dumps({k:v for k,v in result.items() if k!="injections"},indent=2))
    with (a.out/"injections.csv").open("w",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(result["injections"][0]) if result["injections"] else
            ["flux_level","x","y","recovered","nearest_detection_distance_px"])
        writer.writeheader();writer.writerows(result["injections"])
    print(json.dumps(result["flux_summary"],indent=2))
    print(f"Saved {a.out}")



if __name__=="__main__":main()
