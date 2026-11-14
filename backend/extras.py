"""Lab tools and helpers: safe JSON, image stretch, behavior label, fair time lapse, Planet X reach and search, sky path, movers, blind test, protocol."""
import hashlib
import io
import json
import math
import os

import numpy as np
from scipy.ndimage import convolve, map_coordinates
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image

import connectors as cn
import core

S, TARGETS = {}, {}
router = APIRouter()
THRESHOLDS = dict(color_limit_channel_width=0.5, fair_score_min=70, release_penalty=35, flag_penalty=30, zodi_ratio_limit=0.2,
                  motion_dbic_strong=10, motion_dbic_fixed=-2, target_snr_min=4, variability_z=5, real_change_sigma=3,
                  witness_snr=5, conformal_alpha=0.05, epoch_gap_days=30)


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(o) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


class Safe(JSONResponse):
    def render(self, content):
        return json.dumps(clean(content), ensure_ascii=False).encode("utf8")


def ex(i):
    try:
        return S["exps"][i]
    except (IndexError, KeyError):
        raise HTTPException(404, "Load a target first.")


def png(a, scale=8):
    b = io.BytesIO()
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    im.resize((im.width * scale, im.height * scale), Image.NEAREST).save(b, "PNG")
    return Response(b.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


def stretch(img):
    a = img - np.nanmedian(img)
    lo, hi = np.nanpercentile(a, 2), np.nanpercentile(a, 99.8)
    return np.arcsinh(8 * np.clip((a - lo) / max(hi - lo, 1e-12), 0, 1)) / np.arcsinh(8)


def var_stat(rr):
    """Is the brightness change real, and does it depend on color?"""
    if len(rr) < 3:
        return dict(points=len(rr), z=None)
    c, e, x = np.array([r["corrected"] for r in rr]), np.array([r["err"] for r in rr]), np.log(np.array([r["lam"] for r in rr]))
    w = 1 / e ** 2
    chi = float(np.sum(w * (c - 1) ** 2))
    mean = float(np.sum(w * c) / np.sum(w))
    A = np.c_[np.ones(len(c)), x - np.average(x, weights=w)]
    p, *_ = np.linalg.lstsq(A * np.sqrt(w)[:, None], c * np.sqrt(w), rcond=None)
    cov = np.linalg.pinv((A * np.sqrt(w)[:, None]).T @ (A * np.sqrt(w)[:, None]))
    return dict(points=len(rr), z=(chi - len(rr)) / math.sqrt(2 * len(rr)), mean_ratio=mean, mean_err=1 / math.sqrt(np.sum(w)),
                color_slope=float(p[1]), color_slope_err=math.sqrt(cov[1, 1]), color_sigma=float(p[1] / max(math.sqrt(cov[1, 1]), 1e-12)))


def behavior_of(fit, rr):
    v = var_stat(rr)
    z = v.get("z")
    moving, still, varying = fit.get("verdict") == "Motion model preferred", fit.get("verdict") == "Fixed position preferred", z is not None and z > THRESHOLDS["variability_z"]
    label = ("Moving and variable candidate" if moving and varying else "Motion candidate" if moving else
             "Variable source candidate" if varying else "Approximately stable source" if still and z is not None else "Inconclusive")
    chroma = bool(varying and abs(v.get("color_sigma") or 0) > 3)
    return dict(label=label, moving=moving, varying=varying, color_dependent=chroma, motion_verdict=fit.get("verdict"), variability=v,
                note="Candidate labels only. Check the flags and the trust marks.")


@router.get("/api/lapse")
def lapse(ref: int):
    r = ex(ref)
    out = []
    for i, e in enumerate(S["exps"]):
        s, fair, *_ = core.pair_score(r, e)
        if fair or i == ref:
            out.append(dict(i=i, mjd=e.mjd, score=s))
    return sorted(out, key=lambda d: d["mjd"])


@router.get("/api/bestpair")
def bestpair():
    """The pair to show first: the band where the target is best seen, a close color match, then the longest baseline."""
    E, best = S.get("exps") or [], None
    band = (S.get("t") or {}).get("band")
    for i, a in enumerate(E):
        for j in range(i + 1, len(E)):
            if a.det != E[j].det:
                continue
            s, fair, _, parts = core.pair_score(a, E[j])
            k = (a.det == band, parts["color"] is not None and parts["color"] <= 0.25, round(parts["days"] / 30), s)
            if fair and (best is None or k > best[0]):
                best = (k, i, j)
    if not best:
        raise HTTPException(404, "No fair pair exists in these exposures. The coverage plot shows why. This is a valid result.")
    a, b = sorted(best[1:], key=lambda i: E[i].mjd)
    return dict(a=a, b=b, days=abs(E[b].mjd - E[a].mjd), score=best[0][3])


@router.get("/api/path")
def path(t: str = ""):
    T = TARGETS.get(t) or S.get("t") or TARGETS["barnard"]
    now, pts = core.SIM_T0, []
    for back in (70, 35, 28, 16, 10, 0):
        ra, dec = cn.at(T, now - back * 365.25)
        pts.append(dict(years_ago=back, ra=ra, dec=dec))
    return dict(name=T["name"], points=pts, moved_arcsec=math.hypot(T["pmra"], T["pmdec"]) / 1000.0 * 70)


@router.get("/api/planetx")
def planetx(d: float = 500.0, radius: float = 3.0, albedo: float = 0.3, limit: float = 19.0):
    D = 2 * radius * 6371.0
    H = 5 * math.log10(1329.0 / (D * math.sqrt(albedo)))
    reach = lambda lim: 10 ** ((lim - H) / 10)
    return dict(H=H, magnitude_at_distance=H + 10 * math.log10(d), single_visit_reach_au=reach(limit),
                four_visit_reach_au=reach(limit + 0.75), parallax_amplitude_arcsec=206265.0 / d,
                parallax_amplitude_pixels=206265.0 / d / core.PIX,
                note="Estimate. Zero phase angle, equal albedo at all colors, AB equal to V, equal distance from the Sun and the Earth. The depth limit is an assumption.")


@router.get("/api/movers")
def movers(i: int):
    e = ex(i)
    if S.get("mode") != "live":
        return dict(note="Known mover checks need real sky coordinates. Use Live SPHEREx mode.", data=[])
    ra, dec = cn.at(S["t"], e.mjd)
    try:
        return cn.known_movers(ra, dec, e.mjd)
    except Exception as err:
        raise HTTPException(502, f"The JPL service did not answer. {type(err).__name__}")


def blind_pair(k):
    """Two practice images. The source moved by 3 pixels in half of the cases. Five signal levels."""
    q, moved = (4, 6, 8, 12, 20)[k % 5], (k // 5) % 2 == 0
    rng = np.random.default_rng(1000 + k)
    st = np.c_[rng.uniform(4, 37, 8), rng.uniform(4, 37, 8), rng.uniform(15, 120, 8)]
    x, y = rng.uniform(10, 30, 2)
    ang = rng.uniform(0, 2 * math.pi)
    out = []
    for j in range(2):
        img = np.zeros((41, 41))
        for sx, sy, f in st:
            img += f * core.gauss(img.shape, sx, sy)
        dx, dy = (3.0 * math.cos(ang), 3.0 * math.sin(ang)) if moved and j else (0.0, 0.0)
        img += q * 1.02 * core.gauss(img.shape, x + dx, y + dy)
        out.append((img + rng.normal(0, 1, img.shape), np.ones(img.shape)))
    return out[0], out[1], moved, q, (float(x), float(y))


@router.get("/api/blind/{k}/{w}.png")
def blind_img(k: int, w: int):
    a, b, *_ = blind_pair(k)
    return png((1 - stretch((a, b)[w % 2][0])) * 245 + 5, 6)


@router.get("/api/blind/{k}/answer")
def blind_answer(k: int):
    a, b, moved, q, (x, y) = blind_pair(k)
    kk = core.mf_kernel()
    s = convolve(b[0] - a[0], kk, mode="nearest") / math.sqrt(2.0)
    yy, xx = np.indices(s.shape)
    near = np.hypot(xx - x, yy - y) < 6
    peak = float(np.abs(s[near]).max())
    return dict(moved=moved, snr=q, algo=bool(peak > 4.0), difference_snr=peak)


def planet_maps(inject_d, q, seed=21, n=24, size=256):
    """Signal to noise maps of empty practice sky over two years. A source on a parallax track is optional."""
    rng = np.random.default_rng(seed)
    mjd, ra, dec = core.SIM_T0 + np.arange(n) * 30.4, 90.0, 20.0
    fx, fy = core.plx_factors(mjd, ra, dec)
    M, k, maps = np.array([[-1.0, 0.0], [0.0, 1.0]]) * core.PIX / 3600.0, core.mf_kernel(), []
    for i in range(n):
        img = rng.normal(0, 1, (size, size))
        if inject_d:
            P = np.linalg.solve(M, np.array([206265.0 / inject_d * fx[i], 206265.0 / inject_d * fy[i]]) / 3600.0)
            img += q / math.sqrt((core.gauss((7, 7), 3, 3) ** 2).sum()) * core.gauss(img.shape, size / 2 + P[0], size / 2 + P[1])
        maps.append(convolve(img, k, mode="nearest"))
    return maps, mjd, ra, dec, M


def ishift(a, dy, dx):
    """Shift by whole pixels. Empty places get zero."""
    out = np.zeros_like(a)
    h, w = a.shape
    if abs(dy) >= h or abs(dx) >= w:
        return out
    out[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = a[max(0, -dy):h + min(0, -dy), max(0, -dx):w + min(0, -dx)]
    return out


def distance_grid(lo=300.0, hi=3000.0, step_px=1.0):
    """Trial distances in AU. One step changes the parallax swing by about one pixel."""
    amp, out = 206265.0 / hi / core.PIX, []
    while 206265.0 / amp / core.PIX >= lo:
        out.append(206265.0 / amp / core.PIX)
        amp += step_px
    return out[::-1]


def stack_search(maps, mjd, ra, dec, M, dgrid, edge=12):
    """Shift and add signal to noise maps along parallax tracks. Trial: distance and orbital motion."""
    fx, fy = core.plx_factors(mjd, ra, dec)
    t, n, out = (mjd - mjd.mean()) / 365.25, len(maps), []
    for d in dgrid:
        m = 1.3e6 / d ** 1.5
        for mx in (-m, 0.0, m):
            for my in (-m, 0.0, m):
                P = np.rint(np.linalg.solve(M, np.vstack([206265.0 / d * fx + mx * t, 206265.0 / d * fy + my * t]) / 3600.0)).astype(int)
                s = sum(ishift(a, -P[1, i], -P[0, i]) for i, a in enumerate(maps))[edge:-edge, edge:-edge] / math.sqrt(n)
                j = np.unravel_index(np.argmax(s), s.shape)
                out.append(dict(d=float(d), mu_east=float(mx), mu_north=float(my), snr=float(s[j]), x=int(j[1] + edge), y=int(j[0] + edge)))
    return sorted(out, key=lambda r: -r["snr"])


def warp(m, src, ref):
    h, w = ref.img.shape
    yy, xx = np.mgrid[0:h, 0:w]
    ra, dec = core.to_sky(ref.wcs, xx.ravel(), yy.ravel())
    x2, y2 = core.to_pix(src.wcs, ra, dec)
    return map_coordinates(m, [y2.reshape(h, w), x2.reshape(h, w)], order=1, mode="constant", cval=0.0)


@router.get("/api/planetsearch")
def planetsearch(inject: int = 1, d: float = 800.0, q: float = 2.0, live: int = 0):
    if live and S.get("exps") and S.get("mode") == "live":
        E = S["exps"]
        maps = [np.nan_to_num(warp(np.nan_to_num(core.snr_map(e, hide_sources=True)), e, E[0])) for e in E]
        mjd, (ra, dec), M, tag = np.array([e.mjd for e in E]), cn.at(S["t"], E[0].mjd), E[0].wcs.pixel_scale_matrix, "REAL SPHEREx"
    else:
        maps, mjd, ra, dec, M = planet_maps(d if inject else None, q)
        tag = "INJECTED INTO SIMULATION" if inject else "SIMULATION"
    res = stack_search(maps, mjd, ra, dec, M, distance_grid())
    npix = max((maps[0].shape[0] - 24) * (maps[0].shape[1] - 24), 1)
    for r in res[:5]:
        r["expected_false_alarms"] = len(res) * npix * 0.5 * math.erfc(r["snr"] / math.sqrt(2))
    return dict(label=tag, injected_distance_au=d if inject and not live else None, injected_snr_per_frame=q if inject and not live else None,
                frames=len(maps), tracks_tested=len(res), top=res[:5],
                note="The stacked value assumes unit Gaussian noise. A candidate needs a small expected false alarm count. Parallax shifts can exceed a small cutout.")


@router.get("/api/protocol")
def protocol():
    here = os.path.dirname(os.path.abspath(__file__))
    files = {f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest() for f in ("core.py", "connectors.py", "extras.py", "app.py", "pipeline.py", "investigate.py")}
    body = dict(sha256=files, thresholds=THRESHOLDS)
    seal = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return dict(body, seal=seal, rule="Save this file before you look at the test fields. Do not change a threshold after you see a result. The seal changes if any file or threshold changes.")
