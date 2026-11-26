"""Print a compact per-field summary of injection/recovery diagnostics.

Walks a pilot output folder, reads every calibrated_jy_injection_recovery.json and,
for each flux level, reports how many injections were recovered and why the rest
were missed: no signal above threshold, a peak suppressed by a brighter neighbour,
or a peak found outside the match radius. If native FITS files are present it also
reports the local image statistics around the injection region.

Usage: python -m research_discovery.spherex.summarize_injection_diagnostics DIR [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _med(rows, key):
    vals = [x for x in (_num(r.get(key)) for r in rows) if x is not None]
    return round(median(vals), 3) if vals else None


def _rows(report):
    for key in ("injections", "per_injection", "injection_rows", "rows"):
        if isinstance(report.get(key), list) and report[key] and isinstance(report[key][0], dict):
            return report[key]
    for v in report.values():
        if isinstance(v, dict):
            got = _rows(v)
            if got:
                return got
    return []


def miss_reason(r, threshold):
    if r.get("recovered"):
        return "recovered"
    peak = _num(r.get("post_injection_local_max_snr_within_match_radius"))
    if r.get("post_injection_local_peak_suppressed_by_stronger_neighbor"):
        return "suppressed_by_brighter_neighbour"
    if peak is None:
        return "no_valid_snr"
    if peak < threshold:
        return "below_threshold"
    return "peak_not_selected_or_outside_radius"


def summarize_report(path: Path, threshold: float = 5.0) -> dict:
    report = json.loads(path.read_text())
    rows = _rows(report)
    levels = sorted({_num(r.get("flux_level")) for r in rows if _num(r.get("flux_level")) is not None})
    out = []
    for lv in levels:
        sub = [r for r in rows if _num(r.get("flux_level")) == lv]
        reasons = {}
        for r in sub:
            k = miss_reason(r, threshold)
            reasons[k] = reasons.get(k, 0) + 1
        out.append({
            "flux_level": lv,
            "n": len(sub),
            "recovered": sum(1 for r in sub if r.get("recovered")),
            "source_only_recovered": sum(1 for r in sub if r.get("source_only_peak_list_recovered")),
            "median_baseline_snr": _med(sub, "baseline_local_max_snr_within_match_radius"),
            "median_post_snr": _med(sub, "post_injection_local_max_snr_within_match_radius"),
            "median_source_only_snr": _med(sub, "source_only_local_max_snr_within_match_radius"),
            "median_source_only_snr_preinjection_var": _med(sub, "source_only_reference_local_max_snr_preinjection_variance"),
            "median_snr_delta": _med(sub, "local_snr_delta_within_match_radius"),
            "median_nearest_peak_px": _med(sub, "nearest_selected_peak_distance_px"),
            "reasons": reasons,
        })
    keys = ("snr_threshold", "match_radius", "psf_reference_xy", "psf_region_radius", "baseline_detection_count",
            "source_exclusion_radius", "excluded_flag_bits")
    meta = {k: report.get(k) for k in keys if k in report}
    return {"report": str(path), "levels": out, "meta": meta, "row_count": len(rows),
            "structured_background_variant": report.get("structured_background_variant"),
            "top_keys": sorted(report)[:40] if not rows else None}


def image_stats(fits_path: Path, xy=None, radius=100):
    import numpy as np
    from astropy.io import fits
    with fits.open(fits_path, memmap=False) as h:
        names = [x.name for x in h]
        if "IMAGE" not in names:
            return None
        img = np.asarray(h["IMAGE"].data, float)
        var = np.asarray(h["VARIANCE"].data, float) if "VARIANCE" in names else None
        flg = np.asarray(h["FLAGS"].data) if "FLAGS" in names else None
        zodi = np.asarray(h["ZODI"].data, float) if "ZODI" in names else None
    ny, nx = img.shape
    cx, cy = (nx / 2, ny / 2) if xy is None else xy
    yy, xx = np.ogrid[:ny, :nx]
    m = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2

    def st(a, mask):
        v = a[mask & np.isfinite(a)]
        if v.size == 0:
            return None
        med = float(np.median(v))
        return {"median": round(med, 5), "mad_sigma": round(float(1.4826 * np.median(np.abs(v - med))), 5)}
    out = {"file": fits_path.name, "region_image": st(img, m), "global_image": st(img, np.ones_like(m))}
    if var is not None:
        out["region_sqrt_variance_median"] = round(float(np.sqrt(np.nanmedian(var[m]))), 5)
        out["global_sqrt_variance_median"] = round(float(np.sqrt(np.nanmedian(var))), 5)
        r = out["region_image"]
        if r and out["region_sqrt_variance_median"]:
            out["region_noise_excess"] = round(r["mad_sigma"] / out["region_sqrt_variance_median"], 3)
    if flg is not None:
        out["region_flagged_fraction"] = round(float(np.mean(flg[m] != 0)), 4)
    if zodi is not None:
        out["region_zodi_median"] = round(float(np.nanmedian(zodi[m])), 5)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--threshold", type=float, default=5.0)
    a = ap.parse_args(argv)
    fields = []
    for rep in sorted(a.root.rglob("calibrated_jy_injection_recovery.json")):
        s = summarize_report(rep, a.threshold)
        field_dir = rep.parents[2] if len(rep.parents) > 2 else rep.parent
        fits_files = sorted(p for p in field_dir.rglob("*.fits") if "spx_l2b" in p.name)
        if fits_files:
            xy = s["meta"].get("psf_reference_xy")
            try:
                s["image"] = image_stats(fits_files[0], tuple(xy) if xy else None, s["meta"].get("psf_region_radius") or 100)
            except Exception as err:
                s["image"] = {"error": f"{type(err).__name__}: {err}"}
        fields.append(s)
        print(f"== {rep}")
        for lv in s["levels"]:
            print(f"  flux {lv['flux_level']:.3f}: {lv['recovered']}/{lv['n']} recovered, source-only {lv['source_only_recovered']}, "
                  f"SNR base {lv['median_baseline_snr']} post {lv['median_post_snr']} src {lv['median_source_only_snr']} "
                  f"src(pre-var) {lv['median_source_only_snr_preinjection_var']} delta {lv['median_snr_delta']} reasons {lv['reasons']}")
        print("  meta", json.dumps(s["meta"], default=str))
        if s.get("structured_background_variant"):
            print("  structured", json.dumps(s["structured_background_variant"], default=str))
        if s.get("image"):
            print("  image", json.dumps(s["image"], default=str))
        if s.get("top_keys"):
            print("  no per-injection rows; keys:", s["top_keys"])
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(fields, indent=1, default=str))
    return fields


if __name__ == "__main__":
    main()
