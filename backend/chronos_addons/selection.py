"""Completeness/null corrected tile counts. Low-completeness tiles are excluded, not floored."""
from __future__ import annotations
from typing import Any,Mapping,Sequence
import math

def selection_corrected_counts(tiles:Sequence[Mapping[str,Any]],minimum_completeness:float=.05)->dict[str,Any]:
    if not 0<minimum_completeness<=1:raise ValueError("minimum_completeness must be in (0,1]")
    out=[]; skipped=[]; total=variance=area_total=0.
    for t in tiles:
        name=str(t.get("tile_id","unknown")); sky=float(t["raw_sky_candidates"]); null=float(t["raw_null_candidates"]); c=float(t["completeness"]); n=int(t["n_injected"]); area=float(t["area_deg2"])
        if sky<0 or null<0 or n<=0 or area<=0 or not 0<=c<=1:raise ValueError(f"invalid tile inputs for {name}")
        if c<minimum_completeness:skipped.append({"tile_id":name,"reason":"below minimum completeness","completeness":c});continue
        excess=sky-null; est=excess/c; vc=c*(1-c)/n; var=(sky+null)/(c*c)+(excess*excess*vc)/(c**4)
        out.append({"tile_id":name,"raw_excess":excess,"completeness":c,"corrected_excess":est,"corrected_variance":var,"corrected_rate_per_deg2":est/area,"corrected_rate_sigma_per_deg2":math.sqrt(max(0,var))/area,"area_deg2":area})
        total+=est;variance+=var;area_total+=area
    return {"tiles":out,"skipped_tiles":skipped,"corrected_excess_total":total if out else None,"corrected_excess_sigma":math.sqrt(variance) if out else None,
      "area_deg2_included":area_total,"corrected_rate_per_deg2":total/area_total if area_total else None,"minimum_completeness":minimum_completeness,
      "assumptions":["Sky and null counts are independent Poisson variables.","Completeness is binomial from independent injections.","Spatial correlations and clustering are not modelled."]}
