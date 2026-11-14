"""Explicit readers for official SPHEREx calibration and instrument products."""
from __future__ import annotations
from typing import Any,Mapping
import os
import numpy as np

def _fits():
    try: from astropy.io import fits
    except ImportError as exc: raise RuntimeError("Astropy is required to read SPHEREx FITS products") from exc
    return fits

def load_named_image(path:str,hdu:str|int=0):
    if not os.path.isfile(path):raise FileNotFoundError(path)
    with _fits().open(path,memmap=True) as hdul:
        item=hdul[hdu]
        if item.data is None:raise ValueError(f"HDU {hdu!r} has no data")
        return np.asarray(item.data),dict(item.header)

def load_spectral_wcs(path:str)->dict[str,Any]:
    if not os.path.isfile(path):raise FileNotFoundError(path)
    with _fits().open(path,memmap=True) as hdul:
        named={str(h.name).upper():h for h in hdul}
        missing=[k for k in ("CWAVE","CBAND") if k not in named or named[k].data is None]
        if missing:raise ValueError(f"spectral WCS product missing {missing}")
        wave=np.asarray(named["CWAVE"].data,float); band=np.asarray(named["CBAND"].data,float)
        if wave.shape!=band.shape:raise ValueError("CWAVE and CBAND shapes differ")
        return {"cwave_um":wave,"cband_um":band,"header":dict(hdul[0].header),"science_wavelength_source":"CWAVE/CBAND"}

def load_named_hdus(path:str,hdu_names:list[str])->dict[str,Any]:
    if not os.path.isfile(path):raise FileNotFoundError(path)
    with _fits().open(path,memmap=True) as hdul:
        lookup={str(h.name).upper():h for h in hdul}; missing=[n for n in hdu_names if n.upper() not in lookup or lookup[n.upper()].data is None]
        if missing:raise ValueError(f"missing HDUs {missing}; available={list(lookup)}")
        return {n:{"data":np.asarray(lookup[n.upper()].data),"header":dict(lookup[n.upper()].header)} for n in hdu_names}

def load_ecsv_table(path:str)->dict[str,Any]:
    try:from astropy.table import Table
    except ImportError as exc:raise RuntimeError("Astropy is required to read ECSV calibration tables") from exc
    if not os.path.isfile(path):raise FileNotFoundError(path)
    table=Table.read(path,format="ascii.ecsv"); rows=[]
    for r in table:
        item={}
        for name in table.colnames:
            try:item[name]=np.asarray(r[name]).tolist()
            except Exception:item[name]=str(r[name])
        rows.append(item)
    return {"path":os.path.abspath(path),"columns":list(table.colnames),"units":{n:str(table[n].unit) if table[n].unit is not None else None for n in table.colnames},"meta":dict(table.meta),"rows":rows}

def load_instrument_products(paths:Mapping[str,str])->dict[str,Any]:
    allowed={"aurora_template","he_template","shuttle_glow_template","nonfunctional_pixels","dichroic","absolute_gain_matrix","flux_correction"}
    unknown=set(paths)-allowed
    if unknown:raise ValueError(f"unsupported image products {sorted(unknown)}; ECSV tables need load_ecsv_table")
    out={}
    for key,path in paths.items():
        data,header=load_named_image(path,0);out[key]={"data":data,"header":header,"path":os.path.abspath(path)}
    return out

def template_scores(candidate_mask:np.ndarray,products:Mapping[str,Mapping[str,Any]])->dict[str,float]:
    from .forensics import template_overlap_score
    mask=np.asarray(candidate_mask,bool); out={}
    for name,p in products.items():
        a=np.asarray(p["data"])
        if a.shape!=mask.shape:raise ValueError(f"{name} shape {a.shape} != candidate mask {mask.shape}; reproject explicitly")
        out[name]=template_overlap_score(a,mask)
    return out

def load_spherex_forensic_bundle(*,image_products=None,multi_extension_products=None,ecsv_products=None)->dict[str,Any]:
    images=load_instrument_products(image_products or {}); multi={}
    for key,spec in (multi_extension_products or {}).items():
        if not isinstance(spec,Mapping) or "path" not in spec or "hdus" not in spec:raise ValueError(f"{key} needs path and hdus")
        multi[key]={"path":os.path.abspath(str(spec["path"])),"extensions":load_named_hdus(str(spec["path"]),list(spec["hdus"]))}
    tables={k:load_ecsv_table(v) for k,v in (ecsv_products or {}).items()}
    return {"image_products":images,"multi_extension_products":multi,"ecsv_parameter_tables":tables,
      "warning":"Verify detector, product version, processing date and pixel-grid alignment before diagnosis."}
