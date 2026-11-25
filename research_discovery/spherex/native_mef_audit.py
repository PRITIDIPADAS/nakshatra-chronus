"""Native SPHEREx MEF structure audit and CWAVE/CBAND science wavelength extraction."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any
import numpy as np
from research_discovery.spherex.coordinate_transform import detector_origin_offset
from research_discovery.spherex.calibration_compatibility import compatibility_decision,level2_filename_metadata

def sha256(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()

def _header_values(header):
 return {k:header.get(k) for k in header if k in {"DETECTOR","OBSID","DATE-OBS","MJD-OBS","VERSION","PROCDATE","RELEASE","BUNIT","WCSNAME","WCSNAMEA","CRPIX1A","CRPIX2A","CTYPE1","CTYPE2","CTYPE1A","CTYPE2A","CUNIT1","CUNIT2","WCSAXESA"} or str(k).startswith("MP_")}

def science_wavelength_cutout(cwave,cband,image_header,image_shape):
 """Slice native CWAVE/CBAND maps to the science IMAGE grid. Never interpolates invalid pixels."""
 cw=np.asarray(cwave,float); cb=np.asarray(cband,float)
 if cw.ndim!=2 or cb.shape!=cw.shape:raise ValueError("CWAVE and CBAND must be equal-shaped 2D maps")
 if cw.shape!=(2040,2040):raise ValueError(f"science calibration maps must use the native 2040x2040 detector grid, got {cw.shape}")
 ox,oy=detector_origin_offset(image_header)
 h,w=map(int,image_shape)
 if ox<0 or oy<0 or ox+w>cw.shape[1] or oy+h>cw.shape[0]:raise ValueError("science cutout exceeds CWAVE/CBAND native map; refusing extrapolation")
 sw=cw[oy:oy+h,ox:ox+w].copy(); bw=cb[oy:oy+h,ox:ox+w].copy()
 valid=np.isfinite(sw)&(sw>0)&np.isfinite(bw)&(bw>0)
 sw[~valid]=np.nan; bw[~valid]=np.nan
 return {"cwave_um":sw,"cband_um":bw,"valid_mask":valid,"native_origin_xy":[ox,oy],
         "invalid_pixels":int((~valid).sum()),"valid_fraction":float(valid.mean())}

def audit(science_path,spectral_wcs_path,*,solid_angle_path=None,compatibility_evidence=None):
 try: from astropy.io import fits
 except ImportError as exc:raise RuntimeError("Install astropy to audit native SPHEREx MEF files") from exc
 science_path=Path(science_path); spectral_wcs_path=Path(spectral_wcs_path)
 report={"science_file":str(science_path),"science_sha256":sha256(science_path),
         "spectral_wcs_file":str(spectral_wcs_path),"spectral_wcs_sha256":sha256(spectral_wcs_path),
         "checks":{},"status":"review_required","wavelength_authority":"CWAVE and CBAND in the separate spectral-WCS calibration",
         "not_used_for_science_wavelengths":"WCS-WAVE"}
 with fits.open(science_path,memmap=True,checksum=True) as sci:
  names=[str(h.name).upper() for h in sci]
  report["science_hdus"]=[{"index":i,"name":h.name,"shape":list(h.data.shape) if h.data is not None else None,
     "bunit":h.header.get("BUNIT"),"extver":h.header.get("EXTVER"),"header":_header_values(h.header)}
     for i,h in enumerate(sci)]
  req=["IMAGE","FLAGS","VARIANCE","ZODI","WCS-WAVE"]
  missing=[n for n in req if n not in names]
  report["checks"]["required_hdus"]={"status":"pass" if not missing else "fail","missing":missing}
  if "IMAGE" not in names:raise ValueError("MEF has no IMAGE HDU")
  im=sci[names.index("IMAGE")]
  if im.data is None or np.asarray(im.data).ndim!=2:raise ValueError("IMAGE HDU must contain a 2D array")
  image=np.asarray(im.data)
  report["image_shape"]=list(image.shape)
  report["image_bunit"]=im.header.get("BUNIT")
  report["checks"]["image_unit"]={"status":"pass" if im.header.get("BUNIT")=="MJy/sr" else "review_required","bunit":im.header.get("BUNIT")}
  release=str(sci[0].header.get("RELEASE","")).lower()
  if not release: release="dr1" if "dr1" in str(science_path).lower() else "unknown"
  if release in {"dr1","qr3"}:psf_needed="EPSF"
  elif release=="qr2":psf_needed="PSF"
  else:psf_needed=None
  report["checks"]["release_psf"]={"status":"pass" if psf_needed and psf_needed in names else "review_required",
      "expected_psf_hdu":psf_needed,"available":["EPSF" if "EPSF" in names else None,"PSF" if "PSF" in names else None]}
  if psf_needed is None:report["checks"]["release_psf"]["note"]="Release not explicit in primary header or file path; PSF family cannot be inferred."
  for key in ("FLAGS","VARIANCE","ZODI"):
   if key in names and sci[names.index(key)].data is not None:
    arr=np.asarray(sci[names.index(key)].data)
    same=arr.shape==image.shape
    report["checks"][f"{key.lower()}_aligned"]={"status":"pass" if same else "fail","shape":list(arr.shape)}
    if key=="VARIANCE":
     v=arr.astype(float); valid=np.isfinite(v)&(v>0)
     report["variance"]={"finite_positive_fraction":float(valid.mean()),"nonpositive_or_nonfinite_pixels":int((~valid).sum())}
    if key=="FLAGS":report["flags"]={"dtype":str(arr.dtype),"unique_values_sample":np.unique(arr)[:32].tolist(),"raw_mp_header_cards":{k:im.header[k] for k in im.header if str(k).startswith("MP_")}}
  if "FLAGS" in names and np.asarray(sci[names.index("FLAGS")].data).dtype.kind not in "ui":
   report["checks"]["flags_integer_type"]={"status":"fail"}
  else:report["checks"]["flags_integer_type"]={"status":"pass" if "FLAGS" in names else "fail"}
  try:
   from astropy.wcs import WCS
   w=WCS(im.header)
   report["checks"]["celestial_wcs"]={"status":"pass" if w.has_celestial else "fail","has_celestial":bool(w.has_celestial)}
   wa=WCS(im.header,key="A")
   report["checks"]["alternate_wcs_a"]={"status":"pass" if wa.has_celestial else "review_required","has_celestial":bool(wa.has_celestial),
      "wcsnamea":im.header.get("WCSNAMEA"),"crpix1a":im.header.get("CRPIX1A"),"crpix2a":im.header.get("CRPIX2A")}
  except Exception as exc:
   report["checks"]["celestial_wcs"]={"status":"fail","error":str(exc)}
  try:report["cutout_parent_origin_xy"]=list(detector_origin_offset(dict(im.header)))
  except Exception as exc:report["checks"]["cutout_origin"]={"status":"review_required","error":str(exc)}
 with fits.open(spectral_wcs_path,memmap=True,checksum=True) as cal:
  cn=[str(h.name).upper() for h in cal]
  report["spectral_wcs_hdus"]=[{"name":h.name,"shape":list(h.data.shape) if h.data is not None else None,"bunit":h.header.get("BUNIT"),"header":_header_values(h.header)} for h in cal]
  if "CWAVE" not in cn or "CBAND" not in cn:report["checks"]["cwave_cband"]={"status":"fail","missing":[n for n in ("CWAVE","CBAND") if n not in cn]}
  else:
   with fits.open(science_path,memmap=True) as sci:
    im=sci["IMAGE"]
    grid=science_wavelength_cutout(cal["CWAVE"].data,cal["CBAND"].data,dict(im.header),im.data.shape)
    report["checks"]["cwave_cband"]={"status":"pass" if grid["invalid_pixels"]==0 else "review_required","native_origin_xy":grid["native_origin_xy"],"valid_fraction":grid["valid_fraction"],"invalid_pixels":grid["invalid_pixels"]}
    report["wavelength_summary"]={"source":"CWAVE/CBAND","cwave_min_um":float(np.nanmin(grid["cwave_um"])) if grid["valid_mask"].any() else None,
      "cwave_max_um":float(np.nanmax(grid["cwave_um"])) if grid["valid_mask"].any() else None,
      "cband_min_um":float(np.nanmin(grid["cband_um"])) if grid["valid_mask"].any() else None,
      "cband_max_um":float(np.nanmax(grid["cband_um"])) if grid["valid_mask"].any() else None}
  if solid_angle_path:
   with fits.open(solid_angle_path,memmap=True,checksum=True) as om:
    hdu=next((h for h in om if h.data is not None),None)
    if hdu is None:report["checks"]["solid_angle"]={"status":"fail","reason":"no image array"} 
    else:
     a=np.asarray(hdu.data,float)
     valid=np.isfinite(a)&(a>0)
     report["solid_angle"]={"file":str(solid_angle_path),"sha256":sha256(solid_angle_path),"shape":list(a.shape),"bunit":hdu.header.get("BUNIT"),"positive_fraction":float(valid.mean())}
     sci_det=str(sci["IMAGE"].header.get("DETECTOR","")).strip(); cal_det=str(hdu.header.get("DETECTOR",om[0].header.get("DETECTOR",""))).strip()
     report["checks"]["solid_angle"]={"status":"pass" if a.shape==(2040,2040) and valid.all() and sci_det and cal_det and sci_det==cal_det else "review_required","science_detector":sci_det,"calibration_detector":cal_det}
  else:report["checks"]["solid_angle"]={"status":"review_required","reason":"matching pixel solid-angle calibration was not supplied"}
 if compatibility_evidence:
  report["calibration_compatibility"]=compatibility_decision(compatibility_evidence["science"],compatibility_evidence["calibration"])
 else: report["calibration_compatibility"]={"status":"review_required","reason":"explicit provenance evidence for release, detector, pipeline version, processing date and coordinate frame was not supplied"}
 states=[x.get("status") for x in report["checks"].values() if isinstance(x,dict)]
 report["status"]="FAILED" if "fail" in states else "STRUCTURE_OK_REVIEW_REQUIRED" if any(x!="pass" for x in states) or report["calibration_compatibility"]["status"]!="compatible" else "STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS"
 report["science_claim_boundary"]="Structural and metadata checks only; landmark alignment and empirical instrument compatibility require independent real-file evidence."
 return report

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("science_mef",type=Path);p.add_argument("spectral_wcs",type=Path)
 p.add_argument("--solid-angle",type=Path);p.add_argument("--out",type=Path,default=Path("native_mef_audit.json"))
 a=p.parse_args();result=audit(a.science_mef,a.spectral_wcs,solid_angle_path=a.solid_angle)
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,default=str));print(result["status"])
 if result["status"]=="FAILED":raise SystemExit(2)
if __name__=="__main__":main()
