#!/usr/bin/env python3
"""Propagate a published Planet Nine posterior/reference population as an ensemble.

This produces a probabilistic screening map, not a confirmed-planet ephemeris.
Every orbital column and the element epoch must be explicitly mapped from the
dataset README. A two-body model is used for fast screening; it is not a
long-term N-body ephemeris and must not be presented as validated Planet Nine
positions.
"""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
import numpy as np
import pandas as pd

ALIASES={
 "a_au":["a_au","a","sma","semimajor_axis_au","semimajor_axis"],
 "eccentricity":["eccentricity","e","ecc"],
 "inclination_deg":["inclination_deg","incl","i","inclination"],
 "ascending_node_deg":["ascending_node_deg","Omega","omega_node","node","om"],
 "argument_perihelion_deg":["argument_perihelion_deg","argperi","w","perihelion_argument","omega_peri"],
 "mean_anomaly_deg":["mean_anomaly_deg","M","mean_anomaly","mean_anomaly_at_epoch"],
 "weight":["weight","probability_weight","sample_weight","posterior_weight"]}


def resolve_columns(columns:list[str],mapping:dict[str,str]|None=None)->dict[str,str]:
    mapping=mapping or {}; out={}
    for key,aliases in ALIASES.items():
        if key=="weight":continue
        col=mapping.get(key)
        if col:
            if col not in columns: raise ValueError(f"Configured column {col!r} for {key} not found; available={columns}")
            out[key]=col;continue
        matches=[c for c in aliases if c in columns]
        if len(matches)==1:out[key]=matches[0]
        elif len(matches)>1:raise ValueError(f"Ambiguous columns for {key}: {matches}; provide an explicit map")
        else:raise ValueError(f"Cannot infer {key}. Inspect the dataset README and provide an explicit column map. Available={columns}")
    weight_col=mapping.get("weight")
    if weight_col:
        if weight_col not in columns:raise ValueError(f"Weight column {weight_col!r} not found")
        out["weight"]=weight_col
    return out


def _kepler_vector(mean_anomaly:np.ndarray,ecc:np.ndarray)->np.ndarray:
    M=(mean_anomaly+np.pi)%(2*np.pi)-np.pi
    E=np.where(ecc<0.8,M,np.sign(M)*np.pi)
    for _ in range(100):
        step=(E-ecc*np.sin(E)-M)/(1-ecc*np.cos(E));E-=step
        if np.nanmax(np.abs(step))<1e-12:break
    else:raise RuntimeError("Vectorized Kepler solver did not converge")
    return E


def _ecliptic_to_equatorial(v:np.ndarray)->np.ndarray:
    eps=np.deg2rad(23.439291111)
    x,y,z=v[...,0],v[...,1],v[...,2]
    return np.stack([x,y*np.cos(eps)-z*np.sin(eps),y*np.sin(eps)+z*np.cos(eps)],axis=-1)


def propagate_heliocentric_ecliptic(a,e,inc_deg,node_deg,argperi_deg,M_deg,epoch_mjd,target_mjd):
    """Vectorized two-body propagation of osculating elements in ecliptic J2000."""
    a=np.asarray(a,float);e=np.asarray(e,float);inc=np.deg2rad(np.asarray(inc_deg,float));node=np.deg2rad(np.asarray(node_deg,float));arg=np.deg2rad(np.asarray(argperi_deg,float));M0=np.deg2rad(np.asarray(M_deg,float))
    if np.any(~np.isfinite(a+e+inc+node+arg+M0)) or np.any(a<=0) or np.any((e<0)|(e>=1)):
        raise ValueError("Invalid orbit samples: require finite elements, a>0 and 0<=e<1")
    days=(np.asarray(target_mjd,dtype=float)-float(epoch_mjd))
    M=M0+2*np.pi*days/(365.256363004*a**1.5);E=_kepler_vector(M,e)
    xp=a*(np.cos(E)-e);yp=a*np.sqrt(1-e*e)*np.sin(E)
    cO,sO=np.cos(node),np.sin(node);cw,sw=np.cos(arg),np.sin(arg);ci,si=np.cos(inc),np.sin(inc)
    x=(cO*cw-sO*sw*ci)*xp+(-cO*sw-sO*cw*ci)*yp
    y=(sO*cw+cO*sw*ci)*xp+(-sO*sw+cO*cw*ci)*yp
    z=(sw*si)*xp+(cw*si)*yp
    return np.column_stack([x,y,z])


def earth_heliocentric_ecliptic(mjd,ephemeris:str="builtin")->np.ndarray:
    """Earth heliocentric vector(s) using Astropy's solar-system ephemeris."""
    try:
        from astropy.time import Time
        from astropy.coordinates import solar_system_ephemeris,get_body_barycentric
        import astropy.units as u
    except ImportError as exc:raise RuntimeError("Install astropy to obtain Earth ephemerides") from exc
    with solar_system_ephemeris.set(ephemeris):
        times=np.atleast_1d(np.asarray(mjd,dtype=float))
        t=Time(times,format="mjd",scale="tdb")
        earth=get_body_barycentric("earth",t).xyz.to_value(u.au)
        sun=get_body_barycentric("sun",t).xyz.to_value(u.au)
    helio_icrs=np.moveaxis(np.asarray(earth-sun,float),0,-1)
    # Inverse of the fixed J2000 ecliptic->equatorial rotation.
    eps=np.deg2rad(23.439291111);x,y,z=helio_icrs[...,0],helio_icrs[...,1],helio_icrs[...,2]
    result=np.stack([x,y*np.cos(eps)+z*np.sin(eps),-y*np.sin(eps)+z*np.cos(eps)],axis=-1)
    return result[0] if np.ndim(mjd)==0 else result


def generate_ensemble(csv_path:Path,column_map:dict[str,str],epoch_mjd:float,target_mjds:list[float],
                       *,max_samples:int=10000,seed:int=20261114,ephemeris:str="builtin"):
    df=pd.read_csv(csv_path);cols=resolve_columns(list(df.columns),column_map)
    def arr(key):return pd.to_numeric(df[cols[key]],errors="coerce").to_numpy(float)
    values={k:arr(k) for k in ("a_au","eccentricity","inclination_deg","ascending_node_deg","argument_perihelion_deg","mean_anomaly_deg")}
    valid=np.ones(len(df),dtype=bool)
    for key,vals in values.items():valid &= np.isfinite(vals)
    valid &= (values["a_au"]>0)&(values["eccentricity"]>=0)&(values["eccentricity"]<1)
    n_invalid=int(len(df)-int(valid.sum()))
    if not valid.any():raise ValueError("No valid orbital rows remain after numeric/domain checks")
    values={k:v[valid] for k,v in values.items()}
    if "weight" in cols:
        raw_weights=pd.to_numeric(df.loc[valid,cols["weight"]],errors="coerce").to_numpy(float)
        weights=np.where(np.isfinite(raw_weights)&(raw_weights>=0),raw_weights,0.0)
    else:weights=np.ones(int(valid.sum()),float)
    if weights.sum()<=0:raise ValueError("All posterior sample weights are zero or invalid")
    # If reducing the published population, preserve its posterior weighting.
    if max_samples < 1:raise ValueError("max_samples must be >= 1")
    if len(weights)>max_samples:
        rng=np.random.default_rng(seed)
        idx=rng.choice(len(weights),size=max_samples,replace=False,p=weights/weights.sum())
        values={k:v[idx] for k,v in values.items()};weights=weights[idx]
    weights=weights/weights.sum()
    a,e,inc,node,arg,M=(values[k] for k in ("a_au","eccentricity","inclination_deg","ascending_node_deg","argument_perihelion_deg","mean_anomaly_deg"))
    out=[]
    for date in target_mjds:
        reception=float(date)
        earth=earth_heliocentric_ecliptic(reception,ephemeris)
        # Per-sample iterative light-time correction (not a median-distance shift).
        emission=np.full(len(a),reception,dtype=float)
        obj=propagate_heliocentric_ecliptic(a,e,inc,node,arg,M,epoch_mjd,emission)
        for _ in range(3):
            dist=np.linalg.norm(obj-earth[None,:],axis=1)
            emission=reception-dist/173.144632674
            obj=propagate_heliocentric_ecliptic(a,e,inc,node,arg,M,epoch_mjd,emission)
        geo=obj-earth[None,:];dist=np.linalg.norm(geo,axis=1);eq=_ecliptic_to_equatorial(geo)
        ra=np.rad2deg(np.arctan2(eq[:,1],eq[:,0]))%360;dec=np.rad2deg(np.arcsin(np.clip(eq[:,2]/dist,-1,1)))
        for i in range(len(ra)):
            out.append({"target_mjd_tdb":reception,"sample_index":int(i),"ra_deg":float(ra[i]),"dec_deg":float(dec[i]),
                        "geocentric_distance_au":float(dist[i]),"normalized_sample_weight":float(weights[i]),
                        "model":"two-body Kepler ensemble; Earth position from Astropy; planetary perturbations of target omitted"})
    return out,{"input_csv":str(csv_path),"n_valid_samples":int(len(a)),"n_invalid_rows_dropped":n_invalid,
      "epoch_mjd_tdb":float(epoch_mjd),"target_mjds_tdb":[float(x) for x in target_mjds],"columns":cols,
      "ephemeris_backend":ephemeris,"reference_dataset":"CaltechDATA Planet Nine reference population v3 (Brown; 2023), subject to source verification",
      "status":"CANDIDATE_ENSEMBLE_ONLY_NOT_A_CONFIRMED_OR_VALIDATED_EPHEMERIS",
      "limitations":["The object is hypothetical; no observed orbit exists.","Two-body propagation omits perturbations from the giant planets and Galactic tide.","Per-sample light-time iteration is approximate; aberration, deflection and full astrometric reductions are omitted.","Posterior source, orbital epoch, element meanings, frame and units must be verified against its README before interpretation.","A model ensemble is not a probability of existence."]}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("csv",type=Path);p.add_argument("--column-map",type=Path,required=True,help="JSON map: a_au,eccentricity,inclination_deg,ascending_node_deg,argument_perihelion_deg,mean_anomaly_deg[,weight]")
    p.add_argument("--epoch-mjd",type=float,required=True,help="Orbital elements' documented epoch, TDB MJD")
    p.add_argument("--target-mjd",type=float,nargs="+",required=True);p.add_argument("--max-samples",type=int,default=10000);p.add_argument("--seed",type=int,default=20261114);p.add_argument("--ephemeris",default="builtin",help="Astropy backend or local JPL ephemeris kernel path")
    p.add_argument("--out",type=Path,default=Path("planet9_ensemble"));a=p.parse_args()
    mapping=json.loads(a.column_map.read_text());rows,meta=generate_ensemble(a.csv,mapping,a.epoch_mjd,a.target_mjd,max_samples=a.max_samples,seed=a.seed,ephemeris=a.ephemeris)
    a.out.mkdir(parents=True,exist_ok=True)
    with (a.out/"sky_ensemble.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (a.out/"run_metadata.json").write_text(json.dumps(meta,indent=2));print(json.dumps(meta,indent=2));print(f"Saved {a.out}")
if __name__=="__main__":main()
