"""Measure a pre-specified absorption/emission feature; does not identify species."""
from __future__ import annotations
from typing import Sequence
import numpy as np
from .spectral import Spectrum

def measure_equivalent_width(spectrum:Spectrum,feature_interval_um:Sequence[float],continuum_intervals_um:Sequence[Sequence[float]])->dict:
    if len(feature_interval_um)!=2 or len(continuum_intervals_um)!=2 or any(len(x)!=2 for x in continuum_intervals_um):
        raise ValueError("provide one feature interval and exactly two continuum sidebands")
    flo,fhi=map(float,feature_interval_um); sides=[tuple(map(float,x)) for x in continuum_intervals_um]
    if not flo<fhi or any(not a<b for a,b in sides) or not (sides[0][1]<flo and fhi<sides[1][0]):
        raise ValueError("continuum sidebands must bracket and not overlap the feature")
    s=spectrum.normalized(); fm=(s.wavelength_um>=flo)&(s.wavelength_um<=fhi)&s.valid
    sm=np.zeros(s.wavelength_um.size,bool)
    for lo,hi in sides:sm|=(s.wavelength_um>=lo)&(s.wavelength_um<=hi)&s.valid
    if fm.sum()<3 or sm.sum()<4: raise ValueError("need >=3 feature and >=4 continuum samples")
    x0=float(np.mean(s.wavelength_um[sm])); xs=s.wavelength_um[sm]-x0; xf=s.wavelength_um[fm]-x0
    X=np.column_stack([np.ones(xs.size),xs]); w=1/s.sigma[sm]**2 if s.sigma is not None else np.ones(xs.size)
    normal=X.T@(w[:,None]*X)
    if np.linalg.cond(normal)>1e12: raise ValueError("continuum sidebands do not constrain stable linear fit")
    cov=np.linalg.inv(normal); beta=cov@(X.T@(w*s.flux[sm])); Xf=np.column_stack([np.ones(xf.size),xf]); cont=Xf@beta
    if np.any(cont<=0) or np.any(~np.isfinite(cont)): raise ValueError("continuum must be finite and positive")
    wave=s.wavelength_um[fm]; dx=np.diff(wave); iw=np.empty(wave.size); iw[0]=dx[0]/2; iw[-1]=dx[-1]/2
    if wave.size>2:iw[1:-1]=(dx[:-1]+dx[1:])/2
    flux=s.flux[fm]; ew=float(np.sum(iw*(1-flux/cont))); ew_sigma=None; significance=None
    if s.sigma is not None:
        dflux=-iw/cont; dbeta=np.sum((iw*flux/cont**2)[:,None]*Xf,axis=0)
        var=float(np.sum((dflux*s.sigma[fm])**2)+dbeta@cov@dbeta); ew_sigma=float(np.sqrt(max(0,var))); significance=ew/ew_sigma if ew_sigma>0 else None
    return {"feature_interval_um":[flo,fhi],"continuum_intervals_um":[list(x) for x in sides],"equivalent_width_um":ew,
      "equivalent_width_sigma_um":ew_sigma,"equivalent_width_significance":significance,
      "continuum_model":{"type":"weighted_linear","intercept":float(beta[0]),"slope_per_um":float(beta[1]),"reference_wavelength_um":x0},
      "n_feature_samples":int(fm.sum()),"n_continuum_samples":int(sm.sum()),
      "interpretation":"Positive EW is absorption; negative EW is emission under this continuum convention.",
      "limitations":["Feature interval is user supplied; no molecule is identified.","Line-spread function, spectral resolution and blends are not modelled.","Continuum model must be inspected against source spectrum.","Uncertainty uses first-order propagation and independent-sample assumption."]}
