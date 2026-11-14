"""Observatory endpoints: one call investigates a whole field."""
import hashlib
import json
import math
import os
import re

import numpy as np
from fastapi import APIRouter, HTTPException

import connectors as cn
import core
import investigate as I
import sky

router = APIRouter()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache")
TARGETS = {}
MEMO = {}
FIELDS = {
    "demo": dict(name="Practice field", center=(150.11917, 2.20583), seed=3, note="A quiet patch with one of each kind of change planted."),
    "quiet": dict(name="Control field (nothing planted)", center=(210.8, 54.35), seed=4, events="none",
                  note="Stars only. Any candidate here is a false alarm."),
}


def parse_coords(q):
    """Decimal degrees, sexagesimal, or a target name. Returns ra, dec or None."""
    q = (q or "").strip()
    low = q.lower()
    for k, T in TARGETS.items():
        if low in (k, T["name"].lower()) or (len(low) > 3 and low in T["name"].lower()):
            ra, dec = core.catalog_at(T, core.SIM_T0)
            return float(ra), float(dec), k
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", q.replace("−", "-"))
    if re.search(r"\d+\s*[h:]\s*\d+", q) and len(nums) >= 6:
        h, m, s, d, dm, ds = (float(v) for v in nums[:6])
        sign = -1 if nums[3].startswith("-") else 1
        return 15 * (h + m / 60 + s / 3600), sign * (abs(d) + dm / 60 + ds / 3600), None
    if len(nums) >= 2:
        ra, dec = float(nums[0]), float(nums[1])
        if 0 <= ra < 360 and -90 <= dec <= 90:
            return ra, dec, None
    return None


def field_spec(key, ra=None, dec=None, size=49):
    if key in TARGETS:
        T = TARGETS[key]
        return sky.make_spec(100 + list(TARGETS).index(key), target=T, events="demo", size=size), T["name"]
    if key in FIELDS:
        F = FIELDS[key]
        return sky.make_spec(F["seed"], center=F["center"], events=F.get("events", "demo"), size=size), F["name"]
    if ra is not None and dec is not None:
        seed = int(hashlib.sha1(f"{ra:.4f},{dec:.4f}".encode()).hexdigest()[:6], 16)
        return sky.make_spec(seed, center=(ra, dec), events="demo", size=size), f"Practice sky at {ra:.4f}, {dec:.4f}"
    raise HTTPException(404, "Unknown field")


def validation():
    p = os.path.join(ROOT, "data", "validation.json")
    return json.load(open(p)) if os.path.exists(p) else None


def run_field(key="demo", mode="sim", ra=None, dec=None, size=49, fov=0.08, coll="spherex_dr1+spherex_qr3", n=96, deep=True):
    meta = dict(mode=mode, key=key, ra=ra, dec=dec, size=size, fov=fov, collection=coll if mode == "live" else None, n=n if mode == "live" else None)
    if mode == "sim":
        spec, name = field_spec(key, ra, dec, size)
        exps, truth, cat = sky.render(spec)
        meta.update(name=name, seed=spec["seed"], label="SIMULATION")
        out = I.investigate(exps, cat, center=spec["center"], size=size, meta=meta, truth=truth, spec=spec, deep=deep, val=validation())
        out["field"]["planted"] = [dict(id=t["id"], kind=t["kind"], sub=t.get("sub")) for t in truth]
        return out
    if key in TARGETS:
        T = TARGETS[key]
    elif ra is not None and dec is not None:
        T = dict(name=f"RA {ra:.4f} Dec {dec:.4f}", ra=ra, dec=dec, epoch=2016.0, pmra=0.0, pmdec=0.0, plx=0.0)
    else:
        raise HTTPException(400, "Give a target or coordinates.")
    exps = cn.live_exposures(T, coll, n, size=fov, det=0)
    if len(exps) < 4:
        raise HTTPException(404, f"Only {len(exps)} usable exposures here. CHRONOS needs at least four, in two visits. This is a valid result.")
    cat = cn.gaia_catalog(cn.REPORT.get("gaia", []))
    try:
        ra_c, dec_c = core.catalog_at(T, core.SIM_T0)
        for w in cn.wise_cone(ra_c, dec_c, fov):
            cat.append(dict(ra=w["ra"], dec=w["dec"], mag=w["w2"], source="AllWISE", name=f"AllWISE W2 {w['w2']:.1f}", overlay_only=True))
    except Exception:
        pass
    meta.update(name=T["name"], label="REAL SPHEREx", report={k: v for k, v in cn.REPORT.items() if k != "gaia"})
    n_ref = int(round(fov * 3600 / core.PIX)) | 1
    out = I.investigate(exps, [c for c in cat if not c.get("overlay_only")], center=core.catalog_at(T, core.SIM_T0), size=n_ref, meta=meta,
                        deep=deep, val=validation())
    out["field"]["overlay"] = [c for c in cat if c.get("overlay_only")]
    return out


def cached(key, mode, ra, dec, size, fov, deep=True):
    k = f"{key}_{mode}_{ra}_{dec}_{size}_{fov}_{int(deep)}"
    if k in MEMO:
        return MEMO[k]
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, "inv_" + hashlib.sha1(k.encode()).hexdigest()[:16] + ".json")
    if os.path.exists(p):
        MEMO[k] = json.load(open(p))
        return MEMO[k]
    out = json.loads(json.dumps(run_field(key, mode, ra, dec, size, fov, deep=deep), default=I_json))
    json.dump(out, open(p, "w"))
    MEMO[k] = out
    return out


def I_json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o) if math.isfinite(o) else None
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


@router.get("/api/fields")
def fields():
    out = [dict(key=k, name=T["name"], kind="target", traits=T.get("traits", [])) for k, T in TARGETS.items()]
    out += [dict(key=k, name=F["name"], kind="field", note=F["note"]) for k, F in FIELDS.items()]
    return out


@router.get("/api/resolve")
def resolve(q: str):
    r = parse_coords(q)
    if r is None:
        raise HTTPException(404, "Could not read a position. Try: 269.448 4.739, or 17h57m48s +04d44m36s, or a target name.")
    return dict(ra=r[0], dec=r[1], key=r[2])


@router.get("/api/investigate")
def investigate(key: str = "demo", mode: str = "sim", ra: float = None, dec: float = None, size: int = 49, fov: float = 0.08, deep: int = 1):
    size = int(min(max(size, 33), 65)) | 1
    try:
        return cached(key, mode, ra, dec, size, fov, bool(deep))
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(502, f"{type(err).__name__}: {err}")


@router.get("/api/validation")
def get_validation():
    v = validation()
    if v is None:
        raise HTTPException(404, "Run scripts/calibrate_engine.py first.")
    return v


@router.post("/api/reproduce")
def reproduce(record: dict):
    """Run the recorded investigation again from its inputs and compare the output digest."""
    meta = (record.get("inputs") or {}).get("meta") or {}
    if meta.get("mode") != "sim":
        return dict(ok=None, note="Live runs depend on the archive at the time of the request. Rerun them with the same exposure list.")
    out = json.loads(json.dumps(run_field(meta.get("key", "demo"), "sim", meta.get("ra"), meta.get("dec"), meta.get("size", 49)), default=I_json))
    same = out["record"]["output_digest"] == record.get("output_digest")
    return dict(ok=same, old=record.get("output_digest"), new=out["record"]["output_digest"], code_now=out["record"]["code"],
                code_then=record.get("code"), note="Same digest: the analysis is reproduced." if same else
                "Different digest. Compare the code hashes: a change of code or thresholds explains it.")


@router.get("/api/crossmatch")
def crossmatch(ra: float, dec: float, mjd: float = core.SIM_T0, mode: str = "sim", radius: float = 12.0):
    """Rubin alerts and known small bodies at the place of a candidate. Real coordinates only."""
    if mode != "live":
        return dict(note="The practice sky has no counterpart in other surveys. Cross matching runs on real coordinates in Live SPHEREx mode.",
                    rubin=None, known_bodies=None, errors={})
    return cn.crossmatch(ra, dec, mjd, min(max(radius, 2.0), 60.0))


@router.post("/api/publish_hf")
def publish_hf(body: dict):
    """Publish a sealed package to a Hugging Face dataset repository. Needs HF_TOKEN on the server."""
    try:
        return cn.publish_hf(body.get("package") or {}, body.get("repo") or os.environ.get("HF_REPO", ""), private=bool(body.get("private")))
    except (RuntimeError, ValueError) as err:
        raise HTTPException(400, str(err))
    except Exception as err:
        raise HTTPException(502, f"Hugging Face did not accept the upload. {type(err).__name__}")


def planck_ab(T, lam_um, radius_km, d_au):
    """AB magnitude of the thermal glow of a sphere of temperature T seen from distance d."""
    h, c, k = 6.626e-34, 2.998e8, 1.381e-23
    lam = lam_um * 1e-6
    nu = c / lam
    x = h * nu / (k * T)
    if x > 700:
        return float("inf")
    B = 2 * h * nu ** 3 / c ** 2 / math.expm1(x)
    omega = math.pi * (radius_km * 1e3 / (d_au * 1.496e11)) ** 2
    f = B * omega
    return -2.5 * math.log10(f / 3631e-26)


@router.get("/api/planetlab")
def planetlab(d: float = 500.0, mass: float = 6.0, albedo: float = 0.4, temp: float = 40.0, limit: float = 19.0, lat: float = 30.0):
    """Planet X sandbox. Every number follows a stated assumption, listed in the answer."""
    radius_e = mass ** 0.55
    D = 2 * radius_e * 6371.0
    H = 5 * math.log10(1329.0 / (D * math.sqrt(albedo)))
    refl = H + 10 * math.log10(d)
    therm = planck_ab(temp, 4.5, radius_e * 6371.0, d)
    crowd = 0.5 if abs(lat) < 10 else 0.0
    eff = limit - crowd
    reach = 10 ** ((eff - H) / 10)
    par = 206265.0 / d
    orbit = 29.78 / math.sqrt(d) * 3.156e7 / (d * 1.496e8) * 206265
    t_need = None
    for T in range(20, 2000, 5):
        if planck_ab(T, 4.5, radius_e * 6371.0, d) < eff:
            t_need = T
            break
    seen = refl < eff
    return dict(radius_earth=radius_e, H=H, reflected_ab=refl, thermal_ab_4p5=therm if math.isfinite(therm) else None, limit=eff, visible=seen,
                reach_au=reach, parallax_arcsec=par, parallax_px=par / core.PIX, orbit_arcsec_yr=orbit, temperature_needed_k=t_need,
                ladder=["Theoretical prediction: orbits of distant objects suggest a mass. No light seen.",
                        "Observational candidate: a source that moves the right way in some images.",
                        "Statistically supported detection: the motion is measured, artefacts are excluded, the false alarm rate is small.",
                        "Confirmed discovery: independent telescopes recover it on a predicted orbit."],
                status="NASA states that Planet X (Planet Nine) has not been discovered and that its existence is debated. CHRONOS can at most produce a candidate.",
                assumptions=["Radius from mass with R = M to the power 0.55 (Earth units), a rough sub Neptune relation.",
                             "Reflected light at opposition, equal distance from the Sun and the Earth, AB equal to V.",
                             "Thermal glow of a blackbody sphere at 4.5 micron.", f"Depth limit {limit} AB is an assumption, minus 0.5 mag near the galactic plane."])
