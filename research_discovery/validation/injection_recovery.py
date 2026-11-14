#!/usr/bin/env python3
"""Blind injection/recovery experiment on a real SPHEREx Level-2 MEF.

The PSF stamp must be extracted from the matching DR1 ePSF product and
normalized to unit sum. This tool does not create a fake instrument PSF.
"""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
import numpy as np
from scipy.signal import fftconvolve
from scipy.ndimage import maximum_filter


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
                           background: np.ndarray | None = None) -> dict:
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
    omega = None
    if flux_unit == "Jy":
        if solid_angle_sr_map is None: raise ValueError("Jy injections require a detector-aligned solid-angle map in steradians")
        omega = np.asarray(solid_angle_sr_map, float)
        if omega.shape != image.shape: raise ValueError("solid-angle map must be aligned to IMAGE and have the same shape")
    p=np.asarray(psf,float)
    if p.ndim!=2 or any(n%2==0 for n in p.shape): raise ValueError("PSF must be odd 2D stamp")
    if not np.isfinite(p).all() or (p < 0).any() or p.sum() <= 0: raise ValueError("PSF must be finite, nonnegative and have positive sum")
    p=p/p.sum(); py,px=np.array(p.shape)//2
    good=np.isfinite(work_image)&np.isfinite(variance)&(variance>0)
    if excluded_flag_bits: good &= (flags.astype(np.uint64)&np.uint64(excluded_flag_bits))==0
    if flux_unit == "Jy": good &= np.isfinite(omega) & (omega > 0)
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
    baseline_snr = matched_filter_snr(work_image,variance,p)
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
        for x,y in xy:
            x0=int(np.floor(x))-px;y0=int(np.floor(y))-py
            region=injected_img[y0:y0+p.shape[0],x0:x0+p.shape[1]]
            if flux_unit == "Jy":
                # IMAGE is MJy/sr. Convert integrated source flux density F[Jy]
                # to pixel surface brightness through each pixel solid angle.
                omega_patch = omega[y0:y0+p.shape[0], x0:x0+p.shape[1]]
                region += (level * 1e-6 / omega_patch) * p
            else:
                # This is deliberately an image-sum injection unit, not Jy.
                region += level*p
        injected_snr = matched_filter_snr(injected_img,variance,p)
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
                   default="conservative-photometry", help="Named SPHEREx Level-2 flag mask policy")
    p.add_argument("--flag-bits",type=int,default=0,
                   help="Additional raw flag bits to exclude, ORed with --flag-policy")
    p.add_argument("--seed",type=int,default=20261114)
    p.add_argument("--source-exclusion-radius",type=int,default=7,
                   help="Exclude positions near pre-existing >threshold peaks (pixels)")
    p.add_argument("--flux-unit",choices=("image_sum","Jy"),default="image_sum",
                   help="Use Jy only with --solid-angle-map; otherwise levels are sums of IMAGE pixel values")
    p.add_argument("--solid-angle-map",type=Path,
                   help="Detector solid-angle FITS map; required for --flux-unit Jy")
    p.add_argument("--solid-angle-hdu",default="0")
    p.add_argument("--solid-angle-unit",choices=("arcsec2","sr"),default="arcsec2")
    p.add_argument("--background-hdu",default="ZODI",
                   help="Aligned MEF background model HDU to subtract before detection (default ZODI); pass NONE to disable")
    p.add_argument("--psf-region-radius",type=float,default=30.0,
                   help="Injection radius around the PSF's extraction position; limits spatial PSF extrapolation")
    p.add_argument("--out",type=Path,default=Path("injection_recovery"))
    a=p.parse_args()
    try: from astropy.io import fits
    except ImportError as exc: raise SystemExit("Install astropy to read FITS files") from exc
    psf_sel=int(a.psf_hdu) if a.psf_hdu.isdigit() else a.psf_hdu
    omega=None
    with fits.open(a.science_mef,memmap=True) as sci, fits.open(a.psf_stamp,memmap=True) as pf:
        image=np.asarray(sci[a.image_hdu].data,float);variance=np.asarray(sci[a.variance_hdu].data,float);flags=np.asarray(sci[a.flags_hdu].data)
        background = None
        if a.background_hdu.upper() != "NONE":
            if a.background_hdu not in sci:
                raise ValueError(f"background HDU {a.background_hdu!r} is not present; pass --background-hdu NONE to disable")
            background = np.asarray(sci[a.background_hdu].data, float)
        psf=np.asarray(pf[psf_sel].data,float)
        psf_header=pf[psf_sel].header
        if "SRCX" not in psf_header or "SRCY" not in psf_header:
            raise ValueError("PSF stamp must be created by extract_epsf_stamp.py and include SRCX/SRCY metadata")
        psf_reference_xy=(float(psf_header["SRCX"]),float(psf_header["SRCY"]))
        if a.solid_angle_map:
            def _detector_offset(header):
                if int(header.get("NAXIS1", -1)) == 2040 and int(header.get("NAXIS2", -1)) == 2040:
                    return 0.0, 0.0
                if "CRPIX1A" in header and "CRPIX2A" in header:
                    return 1.0-float(header["CRPIX1A"]), 1.0-float(header["CRPIX2A"])
                raise ValueError("cutout IMAGE header missing CRPIX1A/CRPIX2A")
            hdu_sel=int(a.solid_angle_hdu) if a.solid_angle_hdu.isdigit() else a.solid_angle_hdu
            with fits.open(a.solid_angle_map,memmap=True) as om:
                omega_native=np.asarray(om[hdu_sel].data,float)
                sci_det=str(sci[a.image_hdu].header.get("DETECTOR","" )).strip()
                om_det=str(om[hdu_sel].header.get("DETECTOR",om[0].header.get("DETECTOR",""))).strip()
                if sci_det and om_det and sci_det != om_det:
                    raise ValueError(f"solid-angle map detector {om_det} does not match science detector {sci_det}")
                if omega_native.shape != (2040,2040):
                    raise ValueError(f"solid-angle map must be native 2040x2040, got {omega_native.shape}")
                offx,offy=_detector_offset(dict(sci[a.image_hdu].header))
                yy,xx=np.mgrid[:image.shape[0],:image.shape[1]]
                from scipy.ndimage import map_coordinates
                omega=map_coordinates(omega_native,[yy+offy,xx+offx],order=1,mode="constant",cval=np.nan,prefilter=False)
            if a.solid_angle_unit == "arcsec2":
                omega = omega * (np.pi / (180.0 * 3600.0))**2
    if a.flux_unit == "Jy" and omega is None:
        raise SystemExit("--flux-unit Jy requires --solid-angle-map")
    from research_discovery.spherex.flag_policy import policy_mask
    policy_bits, policy_names = policy_mask(a.flag_policy)
    excluded_bits = int(policy_bits) | int(a.flag_bits)
    r=run_injection_recovery(image,variance,flags,psf,flux_levels=a.flux,n_per_level=a.n,
        snr_threshold=a.threshold,excluded_flag_bits=excluded_bits,seed=a.seed,
        source_exclusion_radius=a.source_exclusion_radius,solid_angle_sr_map=omega,flux_unit=a.flux_unit,
        psf_reference_xy=psf_reference_xy,psf_region_radius=a.psf_region_radius,background=background)
    a.out.mkdir(parents=True,exist_ok=True)
    r["flag_policy"] = {"name": a.flag_policy, "excluded_flag_names": list(policy_names),
                        "excluded_flag_bits_additional": int(a.flag_bits),
                        "excluded_flag_mask_combined": int(excluded_bits)}
    (a.out/"summary.json").write_text(json.dumps({k:v for k,v in r.items() if k!="injections"},indent=2))
    with (a.out/"injections.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(r["injections"][0]) if r["injections"] else ["flux_level","x","y","recovered","nearest_detection_distance_px"]);w.writeheader();w.writerows(r["injections"])
    print(json.dumps(r["flux_summary"],indent=2));print(f"Saved {a.out}")

if __name__=="__main__":main()
