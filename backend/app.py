"""CHRONOS API. Start with: python run.py"""
import io
import math

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from PIL import Image

import os

from fastapi.staticfiles import StaticFiles

import connectors as cn
import core
import extras
import observatory
from chronos_addons.api import router as chronos_addons_router

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONT = os.path.join(ROOT, "frontend")

app = FastAPI(title="CHRONOS", default_response_class=extras.Safe)
S = {"exps": [], "t": None, "key": "", "mode": "sim", "memo": {}}

# Positions, motions (mas per year) and parallaxes (arcseconds). The source of each value is in CITATIONS.md.
# sed is a brightness model for the forecast: AB magnitude at 4.5 micron and slope per micron. sim is the practice sky only.
TARGETS = {
    "barnard": dict(name="Barnard's Star", ra=269.44850252544, dec=4.73942005111, epoch=2016.0, pmra=-801.551, pmdec=10362.394, plx=0.5469759,
                    sed=[7.5, -0.42], band=2, traits=["fast", "bright"], sim=dict(sed=[11.8, -0.42])),
    "epsindib": dict(name="Epsilon Indi B", ra=331.04375, dec=-56.782778, epoch=2000.0, pmra=3976.0, pmdec=-2500.0, plx=0.2758,
                     sed=[13.0, 0.2], band=4, traits=["fast", "pair"],
                     sim=dict(sed=[13.2, 0.3], dips=[(1.4, 0.07, 0.6), (1.75, 0.08, 0.5), (2.25, 0.12, 0.5), (3.3, 0.25, 0.8)])),
    "wise0855": dict(name="WISE 0855", ra=133.764625, dec=-7.2426306, epoch=2023.919, pmra=-8118.0, pmdec=680.0, plx=0.449,
                     sed=[17.2, 2.4], band=6, traits=["fast", "faint"], sim=dict(sed=[17.2, 2.4])),
    "rwaur": dict(name="RW Aurigae", ra=76.95625, dec=30.40139, epoch=2000.0, pmra=0.0, pmdec=0.0, plx=0.0,
                  sed=[8.8, 0.0], band=2, traits=["variable", "pair"], sim=dict(sed=[11.5, 0.1], var=0.55, chroma=1.0)),
    "rdra": dict(name="R Draconis", ra=248.16758, dec=66.75498, epoch=2000.0, pmra=0.0, pmdec=0.0, plx=0.0,
                 sed=[4.0, 0.0], band=3, traits=["variable", "bright"],
                 sim=dict(sed=[10.5, 0.1], var=0.45, chroma=0.6, period=245.6, dips=[(1.9, 0.1, 0.25), (2.7, 0.2, 0.35)])),
}

extras.S, extras.TARGETS = S, TARGETS
observatory.TARGETS.update(TARGETS)
app.include_router(extras.router)
app.include_router(observatory.router)
app.include_router(chronos_addons_router)


def ex(i):
    try:
        return S["exps"][i]
    except IndexError:
        raise HTTPException(404, "Load a target first.")


def need():
    if not S["exps"]:
        raise HTTPException(404, "Load a target first.")
    return S["exps"], S["t"]


def memo(key, make):
    if key not in S["memo"]:
        S["memo"][key] = make()
    return S["memo"][key]


def sed():
    return (S["t"].get("sim", {}) if S["mode"] == "sim" else S["t"]).get("sed", [12.0, 0.0])


def rows():
    return memo("rows", lambda: core.spectrum(S["exps"]))


def fit():
    return memo("fit", lambda: core.motion_fit(core.track(S["exps"], S["t"])))


@app.get("/")
def home():
    return FileResponse(os.path.join(FRONT, "index.html"))


@app.get("/story")
def story():
    return FileResponse(os.path.join(FRONT, "story.html"))


@app.get("/api/targets")
def targets():
    return {k: dict(name=v["name"], traits=v["traits"], band=v["band"]) for k, v in TARGETS.items()}


@app.get("/api/load")
def load(t: str = "barnard", mode: str = "sim", coll: str = "spherex_dr1+spherex_qr3", n: int = 48, det: int = -1):
    T = TARGETS.get(t)
    if not T:
        raise HTTPException(404, "Unknown target")
    try:
        if mode == "sim":
            e = core.sim_field(T, seed=7 + list(TARGETS).index(t))
        else:
            e = cn.live_exposures(T, coll, n, det=T["band"] if det < 0 else det)
    except Exception as err:
        raise HTTPException(502, f"Data error. {err}")
    if not e:
        why = "; ".join(f"{k} ({v} files)" for k, v in cn.REPORT.get("failed", {}).items()) if mode != "sim" else ""
        raise HTTPException(404, "No exposure of this target could be used. This is a valid result. " + (f"Found {cn.REPORT.get('found', 0)} files. {why}" if mode != "sim" else ""))
    core.prepare(e)
    S.update(exps=e, t=T, key=t, mode=mode, memo={})
    day0 = min(x.mjd for x in e)
    out = []
    for i, x in enumerate(e):
        m = core.meta(x, i, day0)
        snr, tag, mag = core.forecast(x, sed())
        m.update(forecast=tag, forecast_snr=round(snr, 1))
        out.append(m)
    fair = sum(core.pair_score(a, b)[1] for i, a in enumerate(e) for b in e[i + 1:] if a.det == b.det)
    ks = [x.noise_k for x in e]
    return dict(label=e[0].label, target=T["name"], key=t, traits=T["traits"], exposures=out, fair_pairs=fair,
                span_days=max(x.mjd for x in e) - day0, noise=dict(median=float(np.median(ks)), low=float(min(ks)), high=float(max(ks))),
                anchors=float(np.median([x.nanchor for x in e])), report=dict(cn.REPORT) if mode != "sim" else None,
                brightness_model="practice sky model" if mode == "sim" else "catalog magnitudes, approximate")


def png(a, scale=8):
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    b = io.BytesIO()
    im.resize((im.width * scale, im.height * scale), Image.NEAREST).save(b, "PNG")
    return Response(b.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/frame/{i}.png")
def frame(i: int, flags: int = 0, to: int = -1):
    """One exposure. With to set, the image is resampled onto the grid of exposure to. Flags show in red."""
    e = ex(i)
    img = core.align(e, ex(to))[0] if to >= 0 and to != i else e.img
    g = 1 - extras.stretch(img)  # a negative, like a glass plate: dark stars on a light sky
    rgb = np.stack([0.93 * g + 0.02, 0.95 * g + 0.02, 0.97 * g + 0.02], -1)
    if flags and (to < 0 or to == i):
        m = (e.flags & e.bad & ~(1 << e.bits.get("SOURCE", 62))) != 0
        rgb[m] = np.array([0.82, 0.16, 0.12])
    return png(rgb * 255)


@app.get("/api/partners")
def partners(ref: int):
    """Every exposure on the detector of ref, with its pair score. The page lights the fair ones."""
    r, out = ex(ref), []
    for i, e in enumerate(S["exps"]):
        if i != ref and e.det == r.det:
            s, fair, _, parts = core.pair_score(r, e)
            out.append(dict(i=i, score=s, fair=fair, color=parts["color"], days=parts["days"]))
    return out


def chips(A, B, parts):
    w = core.snr_map(B)[core.box(B)]
    snr = float(np.nanmax(w)) if np.isfinite(w).any() else 0.0
    d, days = parts["color"], parts["days"]
    nfl = len(parts["flags"])
    return [dict(k="color", v=None if d is None else round(d, 2), c="r" if d is None or d > 0.5 else "a" if d > 0.3 else "g"),
            dict(k="signal", v=round(snr, 1), c="g" if snr > 10 else "a" if snr > 5 else "r"),
            dict(k="flags", v=nfl, c="g" if nfl == 0 else "r"),
            dict(k="baseline", v=round(days), c="g" if days > 90 else "a" if days > 10 else "r"),
            dict(k="release", v="same" if A.rel == B.rel else "different", c="g" if A.rel == B.rel else "r"),
            dict(k="anchors", v=min(A.nanchor, B.nanchor), c="g" if min(A.nanchor, B.nanchor) >= 3 else "a")]


@app.get("/api/pair")
def pair(a: int, b: int):
    A, B = ex(a), ex(b)
    s, fair, why, parts = core.pair_score(A, B)
    z, k, fsys = core.zmap(A, B)
    zz = np.where(np.isfinite(z), np.abs(z), 0)
    iy, ix = np.unravel_index(np.argmax(zz), z.shape)
    return dict(a=a, b=b, score=s, fair=fair, why=why, parts=parts, chips=chips(A, B, parts), false_change=core.false_change(rows(), a, b),
                scale=k, resample_error=fsys, zmax=float(zz[iy, ix]), at=[int(ix), int(iy)], size=list(z.shape[::-1]), label=B.label)


@app.get("/api/z/{a}/{b}.png")
def zpng(a: int, b: int):
    z = np.nan_to_num(core.zmap(ex(a), ex(b))[0])
    z = np.sign(z) * np.clip((np.abs(z) - 1.5) / 4.5, 0, 1)  # values below 1.5 are noise and stay pale
    return png(np.stack([1 - np.clip(-z, 0, 1) * 0.85, 1 - np.abs(z) * 0.75, 1 - np.clip(z, 0, 1) * 0.85], -1) * 250)


@app.get("/api/witness")
def witness(i: int, x: float, y: float):
    need()
    return dict(core.witness(S["exps"], i, x, y), label=ex(i).label)


@app.get("/api/motion")
def motion():
    E, T = need()
    f = fit()
    truth = math.hypot(T["pmra"], T["pmdec"]) / 1000.0
    out = dict(label=E[0].label, fit=f, expected_arcsec_per_year=truth, expected_ra=T["pmra"] / 1000.0, expected_dec=T["pmdec"] / 1000.0,
               expected_parallax=T.get("plx") or None)
    if f.get("err"):
        out.update(pull=(f["pm"] - truth) / f["err"], pull_ra=(f["pm_ra"] - T["pmra"] / 1000.0) / f["e_ra"], pull_dec=(f["pm_dec"] - T["pmdec"] / 1000.0) / f["e_dec"])
        if f.get("parallax_err") and T.get("plx"):
            out["pull_parallax"] = (f["parallax"] - T["plx"]) / f["parallax_err"]
    return out


@app.get("/api/spectrum")
def spectrum():
    E, _ = need()
    r = rows()
    rr = memo("ratio", lambda: core.ratio_rows(E, r))
    return dict(label=E[0].label, rows=r, ratio=rr, variability=extras.var_stat(rr))


@app.get("/api/noise")
def noise():
    E, _ = need()
    return dict(label=E[0].label, rows=[dict(i=i, det=e.det, k=e.noise_k) for i, e in enumerate(E)],
                note="1 means that the error in the file is right. Above 1 means that the file error was too small. All later errors use the corrected value.")


@app.get("/api/recovery")
def recovery():
    E, _ = need()
    r = memo("rec", lambda: core.recovery(E))
    if r.get("threshold") is not None and "control" not in r:
        r["control"] = core.false_alarm_rate(E, r["threshold"])
    r["label"] = "INJECTED INTO " + ("REAL SPHEREx" if S["mode"] == "live" else "SIMULATION")
    return r


@app.get("/api/behavior")
def behavior():
    E, _ = need()
    return extras.behavior_of(fit(), memo("ratio", lambda: core.ratio_rows(E, rows())))


@app.post("/api/explain")
def explain(body: dict):
    return cn.explain(body.get("card", {}), body.get("lang", "en"))


@app.get("/api/doctor")
def doctor(t: str = "barnard", coll: str = "spherex_dr1+spherex_qr3"):
    return cn.doctor(TARGETS.get(t, TARGETS["barnard"]), coll)


@app.get("/api/lab")
def lab_view(key: str = "demo"):
    """CHRONOS 4D: the ten laboratories for one simulated field (or the loaded live field)."""
    import json as _j
    import lab
    import observatory as O
    f = _j.loads(_j.dumps(O.run_field(key, "sim"), default=O.I_json))
    rd = lambda n: _j.load(open(os.path.join(ROOT, "data", n))) if os.path.exists(os.path.join(ROOT, "data", n)) else None
    return lab.laboratory(f, rd("validation.json"), rd("real_injection.json"))


@app.get("/api/plugins")
def plugins():
    return sorted(cn.PLUGINS)


@app.post("/api/plugin/{name}")
def plugin(name: str, args: dict):
    f = cn.PLUGINS.get(name)
    if not f:
        raise HTTPException(404, "No such plugin")
    try:
        return f(**args)
    except Exception as err:
        raise HTTPException(502, str(err))


app.mount("/data", StaticFiles(directory=os.path.join(ROOT, "data")), name="data")
app.mount("/", StaticFiles(directory=FRONT), name="front")
