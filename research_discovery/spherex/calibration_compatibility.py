"""Conservative release, detector, pipeline and calibration pairing decisions."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Mapping
import numpy as np

def _detector(value):
    if value is None:return None
    s=str(value).strip().upper()
    if s.startswith("DETECTOR"):s=s.replace("DETECTOR","")
    if s.startswith("D"):s=s[1:]
    return "D"+s if s in {"1","2","3","4","5","6"} else None

def level2_filename_metadata(path):
    name=Path(path).name
    m=re.match(r"level2_(?P<obs>.+?)D(?P<det>[1-6])_spx_l2b-v(?P<version>[0-9.]+)-(?P<date>\d{4}-\d{3})\.fits$",name,re.I)
    return m.groupdict() if m else {}

def compatibility_decision(science:Mapping[str,Any],calibration:Mapping[str,Any],*,required_frame="native_detector"):
    """Only returns compatible when every required fact is explicitly present and equal.

    The caller must extract these values from actual FITS headers, archive path and HISTORY.
    Missing provenance remains review_required; it is never guessed from nearby filenames.
    """
    checks={}
    pairs=(("release","release"),("detector","detector"),("pipeline_version","pipeline_version"),
           ("processing_date","processing_date"),("coordinate_frame","coordinate_frame"))
    for key,calkey in pairs:
        a=science.get(key); b=calibration.get(calkey)
        if key=="detector": a,b=_detector(a),_detector(b)
        if not a or not b: checks[key]={"status":"unknown","science":a,"calibration":b}
        else: checks[key]={"status":"pass" if str(a).lower()==str(b).lower() else "fail","science":a,"calibration":b}
    frame=checks["coordinate_frame"]
    if frame["status"]=="pass" and str(frame["science"]).lower()!=required_frame.lower():
        frame["status"]="fail"
    cwave=np.asarray(calibration.get("cwave")) if calibration.get("cwave") is not None else None
    cband=np.asarray(calibration.get("cband")) if calibration.get("cband") is not None else None
    if cwave is not None and cband is not None:
        ok=(cwave.shape==(2040,2040) and cband.shape==(2040,2040) and
            np.isfinite(cwave).all() and np.isfinite(cband).all() and
            (cwave>0).all() and (cband>0).all())
        checks["wavelength_maps"]={"status":"pass" if ok else "fail",
            "cwave_shape":list(cwave.shape),"cband_shape":list(cband.shape),
            "native_grid_required":[2040,2040],"all_finite_positive":bool(
                np.isfinite(cwave).all() and np.isfinite(cband).all() and
                (cwave>0).all() and (cband>0).all())}
    else:
        import re
        audit_sha=str(calibration.get("wavelength_maps_audit_sha256",""))
        shape_ok=(calibration.get("cwave_shape")==[2040,2040] and
                  calibration.get("cband_shape")==[2040,2040])
        fraction=calibration.get("valid_fraction")
        summary_ok=(bool(re.fullmatch(r"[0-9a-fA-F]{64}",audit_sha)) and shape_ok and
                    isinstance(fraction,(int,float)) and float(fraction)==1.0)
        checks["wavelength_maps"]={"status":"pass" if summary_ok else "unknown",
            "audit_sha256":audit_sha or None,"cwave_shape":calibration.get("cwave_shape"),
            "cband_shape":calibration.get("cband_shape"),"valid_fraction":fraction,
            "note":"Requires a SHA-256-linked native MEF audit summary proving full science-footprint validity."}
    area=calibration.get("solid_angle_map")
    if not isinstance(area,Mapping):
        checks["solid_angle_map"]={"status":"unknown",
            "note":"A detector-matched pixel-area/solid-angle map with URI, SHA-256, native shape and unit is required."}
    else:
        area_detector=_detector(area.get("detector"))
        science_detector=_detector(science.get("detector"))
        area_shape=area.get("shape")
        area_unit=str(area.get("bunit","")).lower().replace(" ","")
        area_sha=str(area.get("sha256",""))
        area_uri=str(area.get("uri",""))
        area_valid=(area.get("status")=="pass" and area_detector==science_detector and
            area_shape==[2040,2040] and area_unit in {"arcsec2","arcsec**2","arcsec^2"} and
            bool(re.fullmatch(r"[0-9a-fA-F]{64}",area_sha)) and area_uri.startswith("https://"))
        checks["solid_angle_map"]={"status":"pass" if area_valid else "fail",
            "detector":area_detector,"science_detector":science_detector,"shape":area_shape,
            "bunit":area.get("bunit"),"sha256":area_sha or None,"uri":area_uri or None}
    states=[x["status"] for x in checks.values()]
    status="rejected" if "fail" in states else "compatible" if all(x=="pass" for x in states) else "review_required"
    return {"status":status,"checks":checks,
      "compatibility_group":(f"{science.get('release')}:{_detector(science.get('detector'))}:{science.get('pipeline_version')}:{science.get('processing_date')}"
         if status=="compatible" else None),
      "wavelength_source":"separate spectral-WCS calibration CWAVE/CBAND only",
      "warning":"A candidate directory listing, filename similarity or WCS-WAVE display table is not proof of compatibility."}
