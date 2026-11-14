"""Low-precision two-body orbit visualizer; not an ephemeris or discovery tool."""
from __future__ import annotations
from typing import Mapping,Sequence
import math
import numpy as np
DAYS_PER_YEAR=365.256363004; OBLIQUITY_DEG=23.4392911

def _kepler(m,e):
    m=(m+math.pi)%(2*math.pi)-math.pi; E=m if e<.8 else math.copysign(math.pi,m or 1)
    for _ in range(80):
        step=(E-e*math.sin(E)-m)/(1-e*math.cos(E)); E-=step
        if abs(step)<1e-13:return E
    raise RuntimeError("Kepler solver did not converge")
def heliocentric_position_au(mjd:float,elements:Mapping[str,float])->np.ndarray:
    a=float(elements["a_au"]); e=float(elements["eccentricity"])
    if a<=0 or not 0<=e<1 or not math.isfinite(mjd):raise ValueError("require a_au>0, 0<=eccentricity<1 and finite MJD")
    inc,node,arg=map(math.radians,[elements["inclination_deg"],elements["ascending_node_deg"],elements["argument_perihelion_deg"]])
    m0=math.radians(float(elements["mean_anomaly_deg"])); epoch=float(elements["epoch_mjd"])
    M=m0+2*math.pi*(float(mjd)-epoch)/(DAYS_PER_YEAR*a**1.5); E=_kepler(M,e)
    xp=a*(math.cos(E)-e); yp=a*math.sqrt(1-e*e)*math.sin(E); cO,sO=math.cos(node),math.sin(node); cw,sw=math.cos(arg),math.sin(arg); ci,si=math.cos(inc),math.sin(inc)
    rot=np.array([[cO*cw-sO*sw*ci,-cO*sw-sO*cw*ci],[sO*cw+cO*sw*ci,-sO*sw+cO*cw*ci],[sw*si,cw*si]])
    return rot@np.array([xp,yp])
def earth_heliocentric_position_au(mjd):
    e={"a_au":1.00000011,"eccentricity":.01671022,"inclination_deg":.00005,"ascending_node_deg":-11.26064,"argument_perihelion_deg":114.20783,"mean_anomaly_deg":357.51716,"epoch_mjd":51544.5}
    return heliocentric_position_au(mjd,e)
def apparent_equatorial(mjd,elements):
    obj=heliocentric_position_au(mjd,elements); earth=earth_heliocentric_position_au(mjd); geo=obj-earth; x,y,z=geo; eps=math.radians(OBLIQUITY_DEG)
    ye=y*math.cos(eps)-z*math.sin(eps); ze=y*math.sin(eps)+z*math.cos(eps); r=float(np.linalg.norm(geo))
    return {"mjd":float(mjd),"ra_deg":math.degrees(math.atan2(ye,x))%360,"dec_deg":math.degrees(math.asin(max(-1,min(1,ze/r)))),"geocentric_distance_au":r,
      "heliocentric_position_au":obj.tolist(),"earth_position_au":earth.tolist(),"model":"low-precision two-body Keplerian scenario; not a validated ephemeris"}
def apparent_track(mjds:Sequence[float],elements:Mapping[str,float]):return [apparent_equatorial(float(t),elements) for t in mjds]
