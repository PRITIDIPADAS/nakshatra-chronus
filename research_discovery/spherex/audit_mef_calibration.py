#!/usr/bin/env python3
"""Audit a SPHEREx Level-2 MEF and related calibration products without guessing provenance."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from typing import Any
import numpy as np


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fits_name_metadata(path: Path) -> dict[str, Any]:
    name = path.name
    m = re.match(r"level2_(?P<obs>.+)D(?P<det>[1-6])_spx_l2b-v(?P<ver>\d+)-(?P<date>\d{4}-\d{3})\.fits$", name, re.I)
    return m.groupdict() if m else {}


def audit(science_path: Path, spectral_wcs_path: Path, template_paths: list[Path]) -> dict[str, Any]:
    try:
        from astropy.io import fits
    except ImportError as exc:
        raise RuntimeError("Install astropy to audit FITS files") from exc
    report: dict[str, Any] = {"science": str(science_path), "spectral_wcs": str(spectral_wcs_path),
        "status": "REVIEW_REQUIRED", "checks": {}, "template_products": [],
        "warning": "Filename/version similarity is not proof of calibration compatibility."}
    with fits.open(science_path, memmap=True) as hdul:
        names = [str(h.name).upper() for h in hdul]
        report["science_sha256"] = sha256(science_path)
        report["science_filename_metadata"] = _fits_name_metadata(science_path)
        report["science_hdus"] = [{"name": h.name, "shape": list(h.data.shape) if h.data is not None else None,
            "bunit": h.header.get("BUNIT"), "extver": h.header.get("EXTVER")} for h in hdul]
        missing = [x for x in ("IMAGE", "FLAGS", "VARIANCE", "ZODI", "EPSF", "WCS-WAVE") if x not in names]
        report["checks"]["required_science_hdus"] = {"passed": not missing, "missing": missing}
        image = hdul[names.index("IMAGE")]
        shape = tuple(image.data.shape) if image.data is not None else None
        report["checks"]["science_image_shape"] = {"shape": shape, "expected_native": (2040,2040),
            "is_native_full_frame": shape == (2040,2040)}
        for hname in ("FLAGS", "VARIANCE", "ZODI"):
            if hname in names:
                a = np.asarray(hdul[names.index(hname)].data)
                report["checks"][f"{hname.lower()}_shape_matches_image"] = {"passed": shape == tuple(a.shape), "shape": list(a.shape)}
        if "VARIANCE" in names:
            v = np.asarray(hdul[names.index("VARIANCE")].data, float)
            finite = np.isfinite(v)
            report["checks"]["variance_domain"] = {"finite_fraction": float(finite.mean()),
                "negative_finite_pixels": int(np.sum(v[finite] < 0)),
                "passed": bool(np.any(finite) and not np.any(v[finite] < 0))}
        report["science_image_header"] = {k: image.header.get(k) for k in
          ("DETECTOR", "OBSID", "DATE-OBS", "MJD-OBS", "CRPIX1A", "CRPIX2A", "WCSAXESA", "BUNIT") if k in image.header}
        report["science_primary_header"] = {k: hdul[0].header.get(k) for k in
          ("VERSION", "PROCDATE", "RELEASE", "ORIGIN") if k in hdul[0].header}
        report["checks"]["epsf_presence"] = {"passed": "EPSF" in names,
            "note": "DR1/QR3 ePSF should be used; old QR2 PSF handling is not silently substituted."}
    with fits.open(spectral_wcs_path, memmap=True) as cal:
        lookup = {str(h.name).upper(): h for h in cal}
        miss = [x for x in ("CWAVE", "CBAND") if x not in lookup or lookup[x].data is None]
        cal_shape = tuple(lookup["CWAVE"].data.shape) if "CWAVE" in lookup and lookup["CWAVE"].data is not None else None
        cband_shape = tuple(lookup["CBAND"].data.shape) if "CBAND" in lookup and lookup["CBAND"].data is not None else None
        report["spectral_wcs_sha256"] = sha256(spectral_wcs_path)
        report["spectral_wcs_hdus"] = names = [str(h.name).upper() for h in cal]
        report["checks"]["cwave_cband_present"] = {"passed": not miss, "missing": miss}
        report["checks"]["cwave_cband_shapes"] = {"cwave": cal_shape, "cband": cband_shape,
            "passed": cal_shape is not None and cal_shape == cband_shape}
        report["checks"]["science_spectral_grid_matches"] = {"passed": cal_shape == (2040,2040), "calibration_shape": cal_shape,
            "note": "A cutout requires the documented detector-origin mapping; shape equality alone does not align it."}
        if not miss and cal_shape == cband_shape:
            cw = np.asarray(lookup["CWAVE"].data, float)
            cb = np.asarray(lookup["CBAND"].data, float)
            cw_good = np.isfinite(cw) & (cw > 0)
            cb_good = np.isfinite(cb) & (cb > 0)
            report["checks"]["wavelength_value_domain"] = {
                "cwave_finite_positive_fraction": float(cw_good.mean()),
                "cband_finite_positive_fraction": float(cb_good.mean()),
                "cwave_min_um": float(np.nanmin(cw[cw_good])) if cw_good.any() else None,
                "cwave_max_um": float(np.nanmax(cw[cw_good])) if cw_good.any() else None,
                "passed": bool(cw_good.any() and cb_good.any())}
        sci_det = str(image.header.get("DETECTOR", "")).strip()
        cal_det = str(cal[0].header.get("DETECTOR", lookup["CWAVE"].header.get("DETECTOR", ""))).strip()
        report["checks"]["detector_id_consistency"] = {"science_detector": sci_det,
            "spectral_wcs_detector": cal_det,
            "passed": bool(sci_det and cal_det and sci_det == cal_det)}
    for p in template_paths:
        with fits.open(p, memmap=True) as hdul:
            shape = tuple(hdul[0].data.shape) if hdul[0].data is not None else None
            report["template_products"].append({"path": str(p), "sha256": sha256(p), "primary_shape": shape,
                "primary_header_detector": hdul[0].header.get("DETECTOR", hdul[0].header.get("DETID")),
                "filename": p.name})
    all_pass = all(v.get("passed", False) for v in report["checks"].values() if isinstance(v, dict) and "passed" in v)
    report["status"] = "STRUCTURE_OK_PROVENANCE_REVIEW_REQUIRED" if all_pass else "FAILED_OR_INCOMPLETE"
    report["compatibility"] = "NOT_ESTABLISHED_BY_THIS_AUDIT"
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("science_mef",type=Path);p.add_argument("spectral_wcs",type=Path)
    p.add_argument("--template",type=Path,action="append",default=[])
    p.add_argument("--out",type=Path,default=Path("spherex_audit.json"))
    a=p.parse_args(); r=audit(a.science_mef,a.spectral_wcs,a.template);a.out.write_text(json.dumps(r,indent=2,default=str));print(r["status"]);print(a.out)

if __name__=="__main__":main()
