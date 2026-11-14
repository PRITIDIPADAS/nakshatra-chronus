"""Offline spherical catalogue cross-match; positional matches are not identifications."""
from __future__ import annotations
from typing import Any,Mapping,Sequence
import math,csv

def angular_separation_arcsec(ra1,dec1,ra2,dec2):
    v=[ra1,dec1,ra2,dec2]
    if any(not math.isfinite(float(x)) for x in v):raise ValueError("coordinates must be finite")
    if not(0<=ra1<360 and 0<=ra2<360 and -90<=dec1<=90 and -90<=dec2<=90):raise ValueError("RA/Dec outside valid bounds")
    r1,d1,r2,d2=map(math.radians,v); a=math.sin((d2-d1)/2)**2+math.cos(d1)*math.cos(d2)*math.sin((r2-r1)/2)**2
    return math.degrees(2*math.asin(min(1,math.sqrt(max(0,a)))))*3600

def crossmatch_catalog(candidates:Sequence[Mapping[str,Any]],catalogue_rows:Sequence[Mapping[str,Any]],*,candidate_ra="ra",candidate_dec="dec",catalogue_ra="ra",catalogue_dec="dec",radius_arcsec=5.,catalogue_name="catalogue"):
    if radius_arcsec<=0:raise ValueError("radius_arcsec must be positive")
    matches=[]; unmatched=[]
    for c in candidates:
        ra,dec=float(c[candidate_ra]),float(c[candidate_dec]); best=None
        for r in catalogue_rows:
            try:sep=angular_separation_arcsec(ra,dec,float(r[catalogue_ra]),float(r[catalogue_dec]))
            except (KeyError,TypeError,ValueError):continue
            if best is None or sep<best[0]:best=(sep,r)
        if best is None or best[0]>radius_arcsec:unmatched.append(str(c.get("candidate_id","unknown")))
        else:matches.append({"candidate_id":c.get("candidate_id"),"catalogue":catalogue_name,"separation_arcsec":best[0],"catalogue_row":dict(best[1]),"association_type":"nearest positional match; not a confirmed counterpart"})
    return {"catalogue":catalogue_name,"radius_arcsec":radius_arcsec,"candidate_count":len(candidates),"match_count":len(matches),"unmatched_candidate_ids":unmatched,"matches":matches,
      "limitations":["No proper-motion/parallax propagation.","No probabilistic or physical association calculated.","Inspect crowded fields and epoch compatibility."]}

def read_catalog_csv(path,ra_column,dec_column):
    with open(path,newline="",encoding="utf-8-sig") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or ra_column not in reader.fieldnames or dec_column not in reader.fieldnames:raise ValueError(f"CSV must contain {ra_column!r}, {dec_column!r}")
        return [dict(x) for x in reader]
