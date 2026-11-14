"""Expected-information-gain follow-up planner for supplied physical forecasts."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import math
import numpy as np

def _entropy(p):
    p=np.asarray(p,float); p=p[p>0]; return float(-np.sum(p*np.log2(p)))
def _pdf(x,mu,sigma):
    z=(x-mu)/sigma; return np.exp(-.5*z*z)/(math.sqrt(2*math.pi)*sigma)

def expected_information_gain(predictions: Mapping[str,Mapping[str,float]], priors: Mapping[str,float]|None=None,
                              measurement_sigma: float=1.0, quadrature_points: int=401)->dict[str,Any]:
    names=list(predictions)
    if len(names)<2: raise ValueError("at least two hypotheses are required")
    if measurement_sigma<=0 or not math.isfinite(measurement_sigma) or quadrature_points<21: raise ValueError("invalid measurement sigma/quadrature")
    prior=np.array([float((priors or {}).get(n,1)) for n in names]);
    if np.any(~np.isfinite(prior)) or np.any(prior<=0): raise ValueError("priors must be finite and positive")
    prior/=prior.sum(); means=[]; sigmas=[]
    for n in names:
        mu=float(predictions[n]["mean"]); s=float(predictions[n].get("sigma",0))
        if not math.isfinite(mu) or not math.isfinite(s) or s<0: raise ValueError(f"invalid forecast for {n}")
        means.append(mu); sigmas.append(math.hypot(s,measurement_sigma))
    means=np.asarray(means); sigmas=np.asarray(sigmas); lo=float(np.min(means-7*sigmas)); hi=float(np.max(means+7*sigmas))
    y=np.linspace(lo,hi,quadrature_points); dy=float(y[1]-y[0]); like=np.vstack([_pdf(y,means[i],sigmas[i]) for i in range(len(names))])
    mix=np.sum(prior[:,None]*like,axis=0); post=prior[:,None]*like/np.maximum(mix[None,:],1e-300)
    expected=float(sum(mix[j]*_entropy(post[:,j]) for j in range(y.size))*dy)
    hprior=_entropy(prior); eig=max(0,hprior-expected)
    return {"hypotheses":names,"prior":dict(zip(names,prior.tolist())),"predictive_mean":dict(zip(names,means.tolist())),
      "predictive_total_sigma":dict(zip(names,sigmas.tolist())),"prior_entropy_bits":hprior,
      "expected_posterior_entropy_bits":expected,"expected_information_gain_bits":eig,"quadrature_points":quadrature_points,
      "note":"Gaussian predictive approximation; forecasts must come from physical models or measurements."}

def plan_observations(candidates: Sequence[Mapping[str,Any]], priors=None, measurement_sigma: float=1.0)->dict[str,Any]:
    if not candidates: raise ValueError("at least one candidate time is required")
    ranked=[]; rejected=[]
    for c in candidates:
        if c.get("visible",True) is False or c.get("feasible",True) is False:
            rejected.append({"time":c.get("time"),"reason":c.get("reason","not visible/feasible")}); continue
        s=expected_information_gain(c.get("predictions") or {},priors,measurement_sigma)
        ranked.append({"time":c.get("time"),"information_gain":s["expected_information_gain_bits"],"score":s,"constraints":dict(c.get("constraints") or {})})
    ranked.sort(key=lambda x:x["information_gain"],reverse=True)
    if not ranked: raise ValueError("no feasible observation forecasts")
    return {"recommended":ranked[0],"ranked":ranked,"rejected":rejected,"method":"expected reduction in Shannon entropy",
      "limitations":["Visibility and seasonal constraints must be computed externally.","Inputs must be physical forecasts, not guessed values.","This does not schedule or command a telescope."]}
