"""Bridge CHRONOS forced PSF photometry to calibrated source F(lambda,t).

The caller must sample the separate official CWAVE/CBAND calibration maps at
WCS-A detector coordinates and supply calibration groups. This bridge refuses
to substitute the current display-grade WCS-WAVE value stored as exposure.lam.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence, Callable
import math
import numpy as np


def sample_cwave(cwave_map: np.ndarray, cband_map: np.ndarray, detector_x: float, detector_y: float) -> dict[str,float]:
    wave=np.asarray(cwave_map,float); band=np.asarray(cband_map,float)
    if wave.shape!=band.shape or wave.ndim!=2: raise ValueError("CWAVE and CBAND must be same-shape 2-D maps")
    x,y=int(round(detector_x)),int(round(detector_y))
    if not (0<=x<wave.shape[1] and 0<=y<wave.shape[0]): raise ValueError("detector coordinate outside calibration maps")
    lam,bw=float(wave[y,x]),float(band[y,x])
    if not (math.isfinite(lam) and lam>0 and math.isfinite(bw) and bw>0): raise ValueError("invalid CWAVE/CBAND sample")
    return {"wavelength_um":lam,"bandwidth_um":bw,"source":"CWAVE/CBAND"}


def measure_candidate_exposures(exposures: Sequence[Any], wavelength_solutions: Mapping[str,Mapping[str,Any]], *,
                                photometry_fn: Callable[[Any],tuple[float,float,int]]|None=None,
                                source_id: str|None=None) -> list[dict[str,Any]]:
    if photometry_fn is None:
        try:
            import core as chronos_core
            photometry_fn=chronos_core.photometry
        except ImportError as exc: raise RuntimeError("add CHRONOS backend to PYTHONPATH or pass photometry_fn") from exc
    rows=[]
    for e in exposures:
        key=str(e.id)
        if key not in wavelength_solutions: raise ValueError(f"missing CWAVE/CBAND solution for {key}")
        s=wavelength_solutions[key]
        if s.get("source")!="CWAVE/CBAND": raise ValueError(f"{key}: wavelength source must be CWAVE/CBAND, not display-grade WCS-WAVE")
        group=s.get("calibration_group")
        if not group: raise ValueError(f"{key}: calibration_group is required")
        lam,bw=float(s["wavelength_um"]),float(s["bandwidth_um"])
        if not (math.isfinite(lam) and lam>0 and math.isfinite(bw) and bw>0): raise ValueError(f"{key}: invalid wavelength/bandwidth")
        flux,sigma,flagged=photometry_fn(e)
        flux,sigma=float(flux),float(sigma)
        rows.append({"source_id":source_id,"observation_id":key,"frame":str(getattr(e,"frame","")),
          "mjd":float(e.mjd),"wavelength_um":lam,"bandwidth_um":bw,"flux":flux,"sigma":sigma,
          "flux_unit":"microJy","valid":math.isfinite(flux) and math.isfinite(sigma) and sigma>0,
          "flagged_core_pixels":int(flagged),"detector":int(e.det),"release":str(e.rel),
          "calibration_group":str(group),"wavelength_source":"CWAVE/CBAND",
          "photometry_method":"CHRONOS core.photometry (forced ePSF/PSF fit)"})
    return rows


def assemble_channel_epochs(measurements: Sequence[Mapping[str,Any]], wavelength_grid_um: Sequence[float], *,
                            epoch_gap_days: float=30.0, min_channel_hits: int=1) -> list[dict[str,Any]]:
    grid=np.asarray(wavelength_grid_um,float)
    if grid.ndim!=1 or grid.size<2 or np.any(~np.isfinite(grid)) or np.any(grid<=0) or np.any(np.diff(grid)<=0):
        raise ValueError("wavelength grid must be finite, positive and strictly increasing")
    if epoch_gap_days<=0 or min_channel_hits<1: raise ValueError("epoch_gap_days and min_channel_hits must be positive")
    rows=[dict(r) for r in measurements if r.get("valid",True)]
    for r in rows:
        if r.get("wavelength_source")!="CWAVE/CBAND" or not r.get("calibration_group"): raise ValueError("all rows need CWAVE/CBAND and calibration_group")
        for k in ("mjd","wavelength_um","bandwidth_um","flux","sigma"):
            if not math.isfinite(float(r[k])): raise ValueError(f"invalid {k}")
        if float(r["sigma"])<=0: raise ValueError("sigma must be positive")
    edges=np.empty(grid.size+1); edges[1:-1]=(grid[:-1]+grid[1:])/2
    edges[0]=grid[0]-(grid[1]-grid[0])/2; edges[-1]=grid[-1]+(grid[-1]-grid[-2])/2
    outputs=[]
    for group in sorted({str(r["calibration_group"]) for r in rows}):
        group_rows=sorted([r for r in rows if str(r["calibration_group"])==group],key=lambda r:float(r["mjd"]))
        epochs=[]
        for r in group_rows:
            if not epochs or float(r["mjd"])-float(epochs[-1][-1]["mjd"])>epoch_gap_days: epochs.append([r])
            else: epochs[-1].append(r)
        for ei,erows in enumerate(epochs):
            numerator=np.zeros(grid.size); denom=np.zeros(grid.size); count=np.zeros(grid.size,int)
            ids=[[] for _ in grid]; dets=[set() for _ in grid]; releases=[set() for _ in grid]
            for r in erows:
                lam=float(r["wavelength_um"]); i=int(np.searchsorted(edges,lam,side="right")-1)
                if i<0 or i>=grid.size or abs(lam-grid[i])>max(float(r["bandwidth_um"])/2,1e-12): continue
                w=1/float(r["sigma"])**2; numerator[i]+=float(r["flux"])*w; denom[i]+=w; count[i]+=1
                ids[i].append(str(r.get("observation_id","unknown")))
                if r.get("detector") is not None: dets[i].add(int(r["detector"]))
                releases[i].add(str(r.get("release","unspecified")))
            ok=(denom>0)&(count>=min_channel_hits); flux=np.full(grid.size,np.nan); sigma=np.full(grid.size,np.nan)
            flux[ok]=numerator[ok]/denom[ok]; sigma[ok]=np.sqrt(1/denom[ok]); mjd=[float(r["mjd"]) for r in erows]
            outputs.append({"source_id":erows[0].get("source_id"),"epoch_index":ei,"mjd_start":min(mjd),"mjd_end":max(mjd),
              "mjd_mean":float(np.mean(mjd)),"calibration_group":group,"wavelength_um":grid.tolist(),"flux":flux.tolist(),
              "sigma":sigma.tolist(),"valid":ok.tolist(),"measurements_per_channel":count.tolist(),
              "observation_ids_by_channel":ids,"detectors_by_channel":[sorted(x) for x in dets],
              "release_labels_by_channel":[sorted(x) for x in releases],"flux_unit":erows[0].get("flux_unit","unspecified"),
              "wavelength_source":"CWAVE/CBAND","missing_channel_policy":"No interpolation; channels without data remain NaN."})
    return outputs
