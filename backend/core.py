"""CHRONOS core: practice sky, fair pair rules, false change meter, difference map, astrometry, photometry, checks."""
import math
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import convolve, map_coordinates, maximum_filter, spline_filter
from scipy.optimize import least_squares

PIX = 6.15
PSF_SIGMA = 0.65  # Gaussian stand in for the PSF, in pixels. Real files bring their own PSF.
OMEGA = (PIX / 206265.0) ** 2
SIM_T0 = 61359.0 + 2.0 / 3.0
UJY = OMEGA * 1e12  # one MJy per sr in one pixel, in microJy

# Detector bands: low edge, high edge (micron), resolving power.
BANDS = {1: (0.75, 1.09, 39), 2: (1.10, 1.62, 41), 3: (1.63, 2.41, 41), 4: (2.42, 3.82, 35), 5: (3.83, 4.41, 112), 6: (4.42, 5.00, 128)}
CHANNELS = 17

# Default flag bits. A real file gives its own table in the MP_ keywords of the FLAGS header. That table replaces this one.
FLAG_BITS = dict(TRANSIENT=0, OVERFLOW=1, SUR_ERROR=2, PHANTOM=4, REFERENCE=5, NONFUNC=6, DICHROIC=7, MISSING_DATA=9, HOT=10,
                 COLD=11, FULLSAMPLE=12, PHANMISS=14, NONLINEAR=15, PERSIST=17, OUTLIER=19, SOURCE=21)
CORE_NAMES = ("TRANSIENT", "OVERFLOW", "SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD", "NONLINEAR", "PERSIST",
              "BLOOM", "SNOWBALL", "HALO", "SATELLITE_HALO")
BAD_NAMES = CORE_NAMES + ("OUTLIER", "SOURCE")


def bitmask(bits, names):
    return sum(1 << bits[n] for n in names if n in bits)


@dataclass
class Exp:
    id: str
    mjd: float
    lam: float
    bw: float
    det: int
    rel: str
    label: str
    img: np.ndarray
    var: np.ndarray
    flags: np.ndarray
    zodi: float = 0.0
    wcs: object = None
    xy: tuple = (0.0, 0.0)
    ref: object = None
    psf: object = None
    rid: object = None
    bits: dict = field(default_factory=lambda: dict(FLAG_BITS))
    lam_src: str = "simulation"
    lam_ok: bool = True
    noise_k: float = 1.0
    shift: tuple = (0.0, 0.0)
    nanchor: int = 0
    notes: list = field(default_factory=list)
    dxy: tuple = (0.0, 0.0)  # detector pixel of cutout pixel 0, 0 (alternate WCS A in real files)
    frame: str = ""  # exposures with the same frame were taken at the same time (one array on each side of the dichroic)

    @property
    def core(self):
        return bitmask(self.bits, CORE_NAMES)

    @property
    def bad(self):
        return bitmask(self.bits, BAD_NAMES)


def flag_names(e, sl):
    """Names of the core flags that are set inside a slice of the image."""
    v = int(np.bitwise_or.reduce(e.flags[sl].ravel() & e.core)) if e.flags[sl].size else 0
    return [n for n in CORE_NAMES if n in e.bits and v >> e.bits[n] & 1]


def box(e, r=2):
    x, y = (int(round(v)) for v in e.xy)
    return slice(max(0, y - r), y + r + 1), slice(max(0, x - r), x + r + 1)


def meta(e, i, day0=None):
    return dict(i=i, id=e.id, mjd=e.mjd, day=None if day0 is None else round(e.mjd - day0, 2), lam=round(e.lam, 4), bw=round(e.bw, 4),
                det=e.det, rel=e.rel, label=e.label, lam_src=e.lam_src, noise_k=round(e.noise_k, 3), flags=flag_names(e, box(e)),
                anchors=e.nanchor, notes=e.notes)


# ---------------------------------------------------------------- sky geometry

def to_pix(w, ra, dec):
    x, y = w.all_world2pix(np.atleast_1d(ra), np.atleast_1d(dec), 0)
    return np.asarray(x, float), np.asarray(y, float)


def to_sky(w, x, y):
    ra, dec = w.all_pix2world(np.atleast_1d(x), np.atleast_1d(y), 0)
    return np.asarray(ra, float), np.asarray(dec, float)


def year(mjd):
    return 2000.0 + (np.asarray(mjd, float) - 51544.5) / 365.25


def plx_factors(mjd, ra, dec):
    """Parallax factors toward east and north for an observer at the Earth. Multiply by the parallax."""
    from astropy.coordinates import get_body_barycentric
    from astropy.time import Time
    X, Y, Z = get_body_barycentric("earth", Time(np.atleast_1d(np.asarray(mjd, float)), format="mjd")).xyz.to_value("au")
    a, d = math.radians(ra), math.radians(dec)
    return X * math.sin(a) - Y * math.cos(a), X * math.cos(a) * math.sin(d) + Y * math.sin(a) * math.sin(d) - Z * math.cos(d)


def catalog_at(t, mjd):
    """Catalog position of a target at an MJD from its proper motion (mas per year). No parallax."""
    dy = float(year(mjd)) - t["epoch"]
    return (t["ra"] + t["pmra"] / 3.6e6 / math.cos(math.radians(t["dec"])) * dy, t["dec"] + t["pmdec"] / 3.6e6 * dy)


def make_wcs(ra, dec, cx, cy, theta_deg):
    from astropy.wcs import WCS
    w, th, s = WCS(naxis=2), math.radians(theta_deg), PIX / 3600.0
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval, w.wcs.crpix = [ra, dec], [cx + 1, cy + 1]
    w.wcs.cd = [[-s * math.cos(th), s * math.sin(th)], [s * math.sin(th), s * math.cos(th)]]
    return w


# ---------------------------------------------------------------- practice sky

def ab_to_ujy(m):
    return 3631e6 * 10 ** (-0.4 * m)


def model_mag(sed, lam):
    """AB magnitude model m = mag0 + slope * (4.5 minus lambda)."""
    return sed[0] + sed[1] * (4.5 - lam)


def sim_flux(sim, lam, mjd):
    """Flux of the practice target in microJy. Spectral dips, a wave and a dimming step are optional."""
    f = ab_to_ujy(model_mag(sim.get("sed", [12.0, 0.0]), lam))
    for c, w, depth in sim.get("dips", []):
        f *= 1 - depth * math.exp(-0.5 * ((lam - c) / w) ** 2)
    amp = sim.get("var", 0.0) * (1.0 / lam) ** sim.get("chroma", 0.0)
    if sim.get("period"):
        f *= 1 + min(amp, 0.9) * math.sin(2 * math.pi * (mjd - SIM_T0) / sim["period"])
    elif amp:
        f *= 1 - min(amp, 0.9) / (1 + math.exp(-(mjd - SIM_T0 - 90.0) / 15.0))
    return f


SIGMA_DET = {1: 0.008, 2: 0.008, 3: 0.008, 4: 0.010, 5: 0.025, 6: 0.035}  # assumed pixel noise of the practice sky, MJy per sr
DEMO = dict(name="Practice star", ra=150.0, dec=20.0, epoch=2016.0, pmra=5200.0, pmdec=1560.0, plx=0.0, sim=dict(sed=[12.0, 0.0]))


def zodi_level(lam):
    return 0.10 + 0.25 * math.exp(-(lam - 0.9)) + 0.5 * math.exp((lam - 5.0) / 0.6)


def psf_img(shape, x, y, s=PSF_SIGMA):
    yy, xx = np.indices(shape)
    return np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * s * s)) / (2 * math.pi * s * s)


def gauss(shape, x, y, s=PSF_SIGMA):
    return psf_img(shape, x, y, s) * (2 * math.pi * s * s)


def sim_field(target=None, seed=1, size=49, epochs=4, steps=3, stars=10, wcs_err=0.15, glitch=True, noise_bias=1.25, dets=(1, 2, 3, 4, 5, 6), catalog=False):
    """Practice sky that follows the SPHEREx rules.

    Each exposure sees the target in one color. The color steps inside each detector band. Surveys 3 and 4 are shifted by
    half a channel. Each exposure has its own WCS with a rotation, a pixel phase and a small error. The noise that the file
    declares for detectors 5 and 6 is too small by the factor noise_bias. The noise check must find this.
    """
    t = dict(DEMO, **(target or {}))
    sim = t.get("sim", DEMO["sim"])
    rng = np.random.default_rng(seed)
    cd = math.cos(math.radians(t["dec"]))
    ra_mid, dec_mid = catalog_at(t, SIM_T0 + 275.0)
    r, a = rng.uniform(8, size / 2 - 6, stars), rng.uniform(0, 2 * math.pi, stars)
    s_ra, s_dec = ra_mid + r * np.cos(a) * PIX / 3600 / cd, dec_mid + r * np.sin(a) * PIX / 3600
    s_mag = rng.uniform(12.5, 16.5, stars)
    chans = np.linspace(2, CHANNELS - 3, steps).round().astype(int)
    plan = [(ep, d, k) for ep in range(epochs) for d in dets for k in range(steps)]
    g_at = int(rng.integers(len(plan))) if glitch and plan else -1
    out = []
    for n, (ep, d, k) in enumerate(plan):
        lo, hi, R = BANDS[d]
        lam = lo * (hi / lo) ** ((chans[k] + 0.5 + (0.5 if ep >= 2 else 0.0) + rng.normal(0, 0.05)) / CHANNELS)
        mjd = SIM_T0 + 182.6 * ep + 3.0 * k + 0.02 * (d - dets[0])
        ra_c, dec_c = catalog_at(t, mjd)
        fx, fy = plx_factors(mjd, t["ra"], t["dec"])
        ra_t, dec_t = ra_c + t.get("plx", 0.0) * fx[0] / 3600 / cd, dec_c + t.get("plx", 0.0) * fy[0] / 3600
        c0 = (size - 1) / 2
        ph, er = rng.uniform(-0.5, 0.5, 2), rng.normal(0, wcs_err, 2)
        th = rng.normal(0, 5.0) + (180.0 if ep % 2 else 0.0)
        true = make_wcs(ra_c, dec_c, c0 + ph[0], c0 + ph[1], th)
        told = make_wcs(ra_c, dec_c, c0 + ph[0] + er[0], c0 + ph[1] + er[1], th)
        zod, sd = zodi_level(lam), SIGMA_DET[d]
        img = np.full((size, size), zod)
        tx, ty = to_pix(true, ra_t, dec_t)
        img += sim_flux(sim, lam, mjd) / UJY * psf_img(img.shape, tx[0], ty[0])
        sx, sy = to_pix(true, s_ra, s_dec)
        for x, y, m in zip(sx, sy, s_mag):
            img += ab_to_ujy(m + 0.35 * (lam - 1.0)) / UJY * psf_img(img.shape, x, y)
        var = sd * sd * np.clip(img, zod, None) / zod
        img = img + rng.normal(0, 1, img.shape) * np.sqrt(var)
        flags = np.zeros(img.shape, int)
        notes = []
        if n == g_at:
            cand = [(c0 + 10 * math.cos(q), c0 + 10 * math.sin(q)) for q in np.linspace(0, 2 * math.pi, 24, endpoint=False)]
            gx, gy = max(cand, key=lambda p: float(np.min(np.hypot(sx - p[0], sy - p[1]))))
            img += 60 * sd * gauss(img.shape, gx, gy, 0.4)
            notes.append(f"glitch at {gx:.1f},{gy:.1f}")
        if n % 11 == 5:
            flags[int(round(c0)) + 1, int(round(c0))] |= 1 << FLAG_BITS["HOT"]
        hx, hy = rng.integers(3, size - 3, 2)
        flags[hy, hx] |= 1 << FLAG_BITS["COLD"]
        ex, ey = to_pix(told, ra_c, dec_c)
        rx, ry = to_pix(told, s_ra, s_dec)
        out.append(Exp(f"sim_e{ep}_d{d}_s{k}", mjd, float(lam), float(lam / R), d, "SIM", "SIMULATION", img,
                       var / (noise_bias ** 2 if d >= 5 else 1.0), flags, zod, told, (float(ex[0]), float(ey[0])),
                       np.c_[rx, ry], None, np.arange(stars), notes=notes))
    if catalog:
        return out, [dict(ra=float(a), dec=float(b), pmra=0.0, pmdec=0.0, parallax=0.0, phot_g_mean_mag=float(m)) for a, b, m in zip(s_ra, s_dec, s_mag)]
    return out


# ---------------------------------------------------------------- point spread function and fits

def epsf(arr, os):
    """Prepare an oversampled PSF plane. The sum over native pixels is 1 for a source at the center."""
    k = np.asarray(arr, float)
    k = k / k.sum() * os * os
    return spline_filter(k, order=3), os, (k.shape[0] - 1) / 2.0


def gauss_psf(s=PSF_SIGMA, os=5, n=33):
    y, x = np.indices((n, n))
    c = (n - 1) / 2
    return epsf(np.exp(-(((x - c) / os) ** 2 + ((y - c) / os) ** 2) / (2 * s * s)), os)


def kern(psf, xx, yy, x0, y0, s=PSF_SIGMA):
    """PSF value in each native pixel for a unit flux source at x0, y0. Gaussian when no ePSF is given."""
    if psf is None:
        return np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * s * s)) / (2 * math.pi * s * s)
    kc, os, c = psf
    return map_coordinates(kc, [(yy - y0) * os + c, (xx - x0) * os + c], order=3, prefilter=False, mode="constant", cval=0.0)


def centroid(img, var, x0, y0, s=PSF_SIGMA, r=4, psf=None, reach=2.0):
    """Measure lane. PSF fit on native pixels. The position cannot leave a box of size reach around the start.

    Returns x, y, error of x, error of y, total flux, flux signal to noise.
    """
    h, w = img.shape
    xi, yi = int(round(x0)), int(round(y0))
    sl = (slice(max(0, yi - r), min(h, yi + r + 1)), slice(max(0, xi - r), min(w, xi + r + 1)))
    d, v = img[sl], np.maximum(var[sl], 1e-12)
    if d.size < 9:
        return x0, y0, 9.0, 9.0, 0.0, 0.0
    yy, xx = np.mgrid[sl]
    ok = np.isfinite(d) & np.isfinite(v)
    if ok.sum() < 9 or not (math.isfinite(x0) and math.isfinite(y0)):
        return x0, y0, 9.0, 9.0, 0.0, 0.0
    if not ok.all():  # real files can hold a few bad values: give them the median and a huge variance
        d, v = np.where(ok, d, np.median(d[ok])), np.where(ok, v, 1e12)
    sig = np.sqrt(v)

    def res(p):
        return ((d - p[0] * kern(psf, xx, yy, p[1], p[2], s) - p[3]) / sig).ravel()

    k0 = float(kern(psf, np.array([float(x0)]), np.array([float(y0)]), x0, y0, s)[0])
    bg = float(np.median(d))
    a0 = float(d.max() - bg) / max(k0 if math.isfinite(k0) else 0.0, 1e-3)
    a0 = a0 if math.isfinite(a0) and a0 > 1e-6 else 1e-6
    sol = least_squares(res, [a0, x0, y0, bg], loss="soft_l1", x_scale=[max(a0, 1e-6), 1.0, 1.0, max(abs(bg), 1e-3)],
                        bounds=([-np.inf, x0 - reach, y0 - reach, -np.inf], [np.inf, x0 + reach, y0 + reach, np.inf]))
    try:
        c = np.linalg.inv(sol.jac.T @ sol.jac)
        ea, ex, ey = (math.sqrt(abs(c[i, i])) for i in (0, 1, 2))
    except np.linalg.LinAlgError:
        ea, ex, ey = abs(sol.x[0]) + 1.0, 9.0, 9.0
    return float(sol.x[1]), float(sol.x[2]), ex, ey, float(sol.x[0]), float(sol.x[0] / max(ea, 1e-12))


def anchor(e):
    """Median shift of the reference stars against their catalog pixels. This removes the WCS error of the exposure."""
    dx, dy = [], []
    for rx, ry in (e.ref if e.ref is not None else []):
        if (e.flags[box_at(e, rx, ry)] & e.core).any():
            continue
        px, py, ex, ey, _, snr = centroid(e.img, e.var, rx, ry, psf=e.psf)
        if snr > 10 and ex < 0.3 and ey < 0.3 and abs(px - rx) < 1.8 and abs(py - ry) < 1.8:
            dx.append(px - rx)
            dy.append(py - ry)
    n = len(dx)
    if n == 0:
        e.shift, e.nanchor = (0.0, 0.0), 0
        return 0.0, 0.0, 0.15, 0
    mx, my = float(np.median(dx)), float(np.median(dy))
    sc = 0.15 if n < 3 else max(1.4826 * float(np.median(np.abs(np.r_[np.array(dx) - mx, np.array(dy) - my]))) / math.sqrt(n), 0.01)
    e.shift, e.nanchor = (mx, my), n
    e.shift_err = sc
    return mx, my, sc, n


def box_at(e, x, y, r=2):
    x, y = int(round(float(x))), int(round(float(y)))
    return slice(max(0, y - r), y + r + 1), slice(max(0, x - r), x + r + 1)


def prepare(exps):
    """Run once after loading: noise check and star anchors for every exposure."""
    for e in exps:
        noise_check(e)
        anchor(e)
    return exps


def track(exps, t):
    """Anchored astrometry. Offsets of the target east and north of a fixed sky point, in arcseconds."""
    ra0, dec0 = catalog_at(t, exps[0].mjd)
    cd, rows, skipped = math.cos(math.radians(dec0)), [], 0
    for i, e in enumerate(exps):
        cx, cy, ex, ey, _, snr = centroid(e.img, e.var, *e.xy, psf=e.psf)
        if snr < 4 or ex > 0.5 or ey > 0.5 or (e.flags[box(e, 1)] & e.core).any():
            skipped += 1
            continue
        sc = getattr(e, "shift_err", 0.15)
        ra, dec = to_sky(e.wcs, cx - e.shift[0], cy - e.shift[1])
        rows.append((e.mjd, (ra[0] - ra0) * cd * 3600, (dec[0] - dec0) * 3600, math.hypot(ex, sc) * PIX, math.hypot(ey, sc) * PIX, e.nanchor, i))
    if not rows:
        return None
    a = np.array(sorted(rows))
    return dict(mjd0=float(a[0, 0]), mjd=a[:, 0], t=(a[:, 0] - a[0, 0]) / 365.25, X=a[:, 1], Y=a[:, 2], eX=a[:, 3], eY=a[:, 4],
                nref=a[:, 5].astype(int).tolist(), idx=a[:, 6].astype(int).tolist(), skipped=skipped, ra=t["ra"], dec=t["dec"])


def motion_fit(d):
    """Motion court. H0 fixed, H1 linear motion, H2 linear motion with parallax. Arcseconds and years. Lowest BIC wins."""
    if d is None:
        return dict(verdict="Inconclusive", why="The target was not measured in any frame.", frames=0)
    t, n = np.asarray(d["t"]), len(d["t"])
    if n < 4 or np.ptp(t) < 0.02:
        return dict(verdict="Inconclusive", why="Too few frames or the baseline is too short.", frames=n, baseline_days=float(np.ptp(t) * 365.25) if n else 0.0)
    fx, fy = plx_factors(d["mjd"], d["ra"], d["dec"])
    w = np.r_[1 / np.asarray(d["eX"]) ** 2, 1 / np.asarray(d["eY"]) ** 2]
    y = np.r_[d["X"], d["Y"]]
    O, Z0, tc = np.ones(n), np.zeros(n), t - t.mean()
    cols = [np.r_[O, Z0], np.r_[Z0, O], np.r_[tc, Z0], np.r_[Z0, tc], np.r_[fx, fy]]
    sw, m = np.sqrt(w), {}
    for name, k in (("H0", 2), ("H1", 4), ("H2", 5)):
        if name == "H2" and (n < 6 or np.ptp(t) < 0.25):
            continue
        A = np.c_[tuple(cols[:k])]
        p, *_ = np.linalg.lstsq(A * sw[:, None], y * sw, rcond=None)
        chi = float(np.sum(w * (y - A @ p) ** 2))
        cov = np.linalg.pinv((A * sw[:, None]).T @ (A * sw[:, None]))
        m[name] = dict(chi2=chi, k=k, p=p, cov=cov, A=A)
    s2 = max(1.0, min(v["chi2"] / max(2 * n - v["k"], 1) for v in m.values()))
    for v in m.values():
        v["bic"] = v["chi2"] / s2 + v["k"] * math.log(2 * n)
    mov = min((k for k in m if k != "H0"), key=lambda k: m[k]["bic"])
    dbic = m["H0"]["bic"] - m[mov]["bic"]
    p, cov = m[mov]["p"], m[mov]["cov"] * s2
    pm = math.hypot(p[2], p[3])
    err = math.sqrt(max((p[2] ** 2 * cov[2, 2] + p[3] ** 2 * cov[3, 3] + 2 * p[2] * p[3] * cov[2, 3]) / max(pm * pm, 1e-18), 0.0))
    v = "Motion model preferred" if dbic > 10 else "Fixed position preferred" if dbic < -2 else "Inconclusive"
    fit = (m[mov]["A"] @ p)
    out = dict(verdict=v, model=mov, dbic=dbic, pm_ra=float(p[2]), pm_dec=float(p[3]), e_ra=math.sqrt(cov[2, 2]), e_dec=math.sqrt(cov[3, 3]),
               pm=pm, err=err, sigma=pm / max(err, 1e-9), baseline_days=float(np.ptp(t) * 365.25), frames=n, skipped=d.get("skipped", 0),
               reduced_chi2=s2, bic={k: v2["bic"] for k, v2 in m.items()},
               points=dict(day=(t * 365.25).tolist(), X=np.asarray(d["X"]).tolist(), Y=np.asarray(d["Y"]).tolist(), eX=np.asarray(d["eX"]).tolist(),
                           eY=np.asarray(d["eY"]).tolist(), fX=fit[:n].tolist(), fY=fit[n:].tolist(), idx=d["idx"]))
    if "H2" in m:
        out["parallax"], out["parallax_err"] = float(m["H2"]["p"][4]), math.sqrt(m["H2"]["cov"][4, 4] * s2)
    return out


# ---------------------------------------------------------------- brightness

def photometry(e, x=None, y=None):
    """Forced PSF photometry in microJy at the anchored target position. Returns flux, error, flagged pixel count."""
    if x is None:
        x, y = e.xy[0] + e.shift[0], e.xy[1] + e.shift[1]
    yy, xx = np.indices(e.img.shape)
    rr = np.hypot(xx - x, yy - y)
    an = (rr > 6) & (rr < 10) & ((e.flags & e.bad) == 0)
    bg = float(np.median(e.img[an])) if an.sum() > 8 else float(np.median(e.img))
    m = (rr <= 5) & ((e.flags & e.core) == 0)
    nf = int(((e.flags & e.core) != 0)[rr <= 2].sum())
    k = kern(e.psf, xx, yy, x, y)
    wt = 1 / np.maximum(e.var, 1e-12)
    den = float(np.sum(k[m] ** 2 * wt[m]))
    if den <= 0:
        return float("nan"), float("nan"), nf
    return float(np.sum((e.img[m] - bg) * k[m] * wt[m]) / den * UJY), float(UJY / math.sqrt(den)), nf


def spectrum(exps, gap=30.0):
    """One row per exposure: color, flux, error and an epoch number. A gap of 30 days starts a new epoch."""
    rows = []
    for i, e in enumerate(exps):
        f, er, nf = photometry(e)
        rows.append(dict(i=i, lam=e.lam, bw=e.bw, det=e.det, mjd=e.mjd, f=f, e=er, flagged=nf, rel=e.rel))
    g = 0
    srt = sorted(rows, key=lambda r: r["mjd"])
    for j, r in enumerate(srt):
        if j and r["mjd"] - srt[j - 1]["mjd"] > gap:
            g += 1
        r["epoch"] = g
    return rows


def false_change(rows, a, b):
    """False change meter. The flux change that the color difference alone creates, from the spectrum slope of the source.

    Model on one detector: ln F = offset of the epoch + slope * ln(lambda). The offsets absorb real brightness changes.
    The fit uses the colors near the pair when enough exist, and the full detector band if not. Structure that the fit
    cannot follow (for example a narrow molecular band) goes into the error of the prediction.
    """
    ra, rb = rows[a], rows[b]
    if ra["det"] != rb["det"]:
        return None
    band = [r for r in rows if r["det"] == ra["det"] and np.isfinite(r["f"]) and r["f"] > 3 * r["e"] and not r["flagged"]]
    mid = 0.5 * (math.log(ra["lam"]) + math.log(rb["lam"]))

    def usable(u):
        x = sorted({round(math.log(r["lam"]), 4) for r in u})
        return len(u) >= len({r["epoch"] for r in u}) + 2 and len(x) >= 3 and any(
            len({round(math.log(r["lam"]), 4) for r in u if r["epoch"] == q}) >= 2 for q in {r["epoch"] for r in u})

    near = [r for r in band if abs(math.log(r["lam"]) - mid) < 0.06]
    use, scope = (near, "local") if usable(near) else (band, "band")
    if not usable(use):
        return None
    eps = sorted({r["epoch"] for r in use})
    x = np.array([math.log(r["lam"]) for r in use])
    A = np.c_[tuple((np.array([r["epoch"] for r in use]) == q).astype(float) for q in eps) + (x - x.mean(),)]
    y, w = np.array([math.log(r["f"]) for r in use]), np.array([r["f"] / r["e"] for r in use])
    p, *_ = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)
    res = y - A @ p
    dof = max(len(use) - A.shape[1], 1)
    s2 = max(1.0, float(np.sum((w * res) ** 2)) / dof)
    es = math.sqrt(np.linalg.pinv((A * w[:, None]).T @ (A * w[:, None]))[-1, -1] * s2)
    xs = np.unique(np.round(x, 4))
    scatter = 1.4826 * float(np.median(np.abs(res))) * math.sqrt(len(use) / dof)
    es_local = math.hypot(es, scatter / max(float(np.median(np.diff(xs))), 1e-3)) if s2 > 4 else es
    dl = math.log(rb["lam"] / ra["lam"])
    pred = math.exp(p[-1] * dl) - 1
    out = dict(slope=float(p[-1]), slope_err=es_local, points=len(use), scope=scope, model_scatter=scatter, predicted=pred,
               predicted_err=abs(dl) * es_local * (1 + pred))
    if all(np.isfinite(r["f"]) and r["f"] > 0 for r in (ra, rb)):
        meas = rb["f"] / ra["f"] - 1
        me = (1 + meas) * math.hypot(ra["e"] / ra["f"], rb["e"] / rb["f"])
        out.update(measured=meas, measured_err=me, excess_sigma=(meas - pred) / max(math.hypot(me, out["predicted_err"]), 1e-9))
    return out


def star_gain(a, b):
    """Relative gain of b against a from reference stars seen in both. Use the official flux correction when you have it."""
    if a.rid is None or b.rid is None or a.ref is None or b.ref is None:
        return 1.0, 0
    ia, ib, r = {int(k): j for j, k in enumerate(a.rid)}, {int(k): j for j, k in enumerate(b.rid)}, []
    for k in sorted(set(ia) & set(ib)):
        fa = photometry(a, a.ref[ia[k]][0] + a.shift[0], a.ref[ia[k]][1] + a.shift[1])
        fb = photometry(b, b.ref[ib[k]][0] + b.shift[0], b.ref[ib[k]][1] + b.shift[1])
        if fa[0] > 10 * fa[1] and fb[0] > 10 * fb[1] and not fa[2] and not fb[2]:
            r.append(fb[0] / fa[0])
    return (float(np.median(r)), len(r)) if len(r) >= 3 else (1.0, 0)


def ratio_rows(exps, rows):
    """Later epoch over first epoch at matched colors, divided by the star gain and by the color term of the false change meter.

    For each color of the first epoch the partner is the latest exposure with a close color match (0.25 of a channel width).
    If none exists, the latest exposure inside the fair limit (0.50) is used and the color term carries its error.
    """
    g = max(r["epoch"] for r in rows) if rows else 0
    ok = lambda r: r["f"] > 3 * r["e"] and not r["flagged"]
    out = []
    for a in [r for r in rows if r["epoch"] == 0 and ok(r)] if g else []:
        c = [r for r in rows if r["det"] == a["det"] and r["epoch"] > 0 and ok(r) and abs(r["lam"] - a["lam"]) <= 0.5 * a["bw"]]
        tight = [r for r in c if abs(r["lam"] - a["lam"]) <= 0.25 * a["bw"]]
        if not c:
            continue
        b = max(tight or c, key=lambda r: (r["epoch"], -abs(r["lam"] - a["lam"])))
        gn, ns = star_gain(exps[a["i"]], exps[b["i"]])
        fc = false_change(rows, a["i"], b["i"]) or dict(predicted=0.0, predicted_err=0.05)
        c = b["f"] / a["f"] / gn / (1 + fc["predicted"])
        out.append(dict(lam=a["lam"], a=a["i"], b=b["i"], epoch=b["epoch"], days=b["mjd"] - a["mjd"], ratio=b["f"] / a["f"], gain=gn, stars=ns,
                        color_term=fc["predicted"], tight=bool(tight), corrected=c,
                        err=c * math.sqrt((a["e"] / a["f"]) ** 2 + (b["e"] / b["f"]) ** 2 + (0.02 if ns else 0.05) ** 2 + fc["predicted_err"] ** 2)))
    return sorted(out, key=lambda r: r["lam"])


def forecast(e, sed):
    """Expected signal to noise of the target in one exposure from an AB magnitude model. Made before any measurement."""
    m = model_mag(sed, e.lam)
    yy, xx = np.indices(e.img.shape)
    x, y = e.xy
    k = kern(e.psf, xx, yy, x, y)
    sel = np.hypot(xx - x, yy - y) <= 5
    snr = ab_to_ujy(m) / (UJY / math.sqrt(float(np.sum(k[sel] ** 2 / np.maximum(e.var[sel], 1e-12)))))
    tag = "very bright" if m < 8 else "visible" if snr > 5 else "marginal" if snr > 2 else "not visible"
    return snr, tag, m


# ---------------------------------------------------------------- fair pair engine

def pair_score(a, b):
    """Fair pair rules. Returns score, fair flag, reasons and the parts of the score."""
    parts = dict(color=None, flags=[], release=a.rel == b.rel, zodi=None, days=abs(b.mjd - a.mjd))
    if a.det != b.det:
        return 0, False, ["Different detector. The two images show different colors. Do not compare them."], parts
    s, why = 100.0, []
    bw = 0.5 * (a.bw + b.bw)
    d = abs(a.lam - b.lam) / bw
    parts["color"] = d
    s -= 40 * min(1.0, d / 0.5)
    if not (a.lam_ok and b.lam_ok):
        s, d = s - 40, 9.0
        parts["color"] = None
        why.append("The color at the target is not known for this file. The pair cannot be called fair.")
    elif d > 0.5:
        why.append(f"The colors differ by {d:.2f} of one channel width. The limit is 0.50.")
    elif d > 0.3:
        why.append(f"The colors differ by {d:.2f} of one channel width. This is close to the limit of 0.50.")
    for e in (a, b):
        fl = flag_names(e, box(e))
        if fl:
            s -= 30
            parts["flags"].append(e.id)
            why.append(f"Bad pixels near the target in {e.id}: {', '.join(fl)}." + (" The star is too bright for this exposure." if "OVERFLOW" in fl else ""))
    if a.rel != b.rel:
        s -= 35
        why.append("Different data releases. Brightness needs the flux correction first. Positions can still be compared.")
    z = abs(a.zodi / max(b.zodi, 1e-9) - 1)
    parts["zodi"] = z
    if z > 0.2:
        s -= 15
        why.append("The sky background differs by more than 20 percent.")
    fair = s >= 70 and d <= 0.5
    if fair:
        why.insert(0, f"Same detector and matched color. {parts['days']:.0f} days apart.")
    return int(max(s, 0)), fair, why, parts


def align(a, ref):
    """Show lane only. Resample image a onto the grid of ref with the WCS."""
    if a.wcs is None or ref.wcs is None:
        return a.img, a.var
    h, w = ref.img.shape
    yy, xx = np.mgrid[0:h, 0:w]
    ra, dec = to_sky(ref.wcs, (xx - ref.shift[0]).ravel(), (yy - ref.shift[1]).ravel())
    x2, y2 = to_pix(a.wcs, ra, dec)
    x2, y2 = (x2 + a.shift[0]).reshape(h, w), (y2 + a.shift[1]).reshape(h, w)
    return map_coordinates(a.img, [y2, x2], order=3, mode="nearest"), map_coordinates(a.var, [y2, x2], order=1, mode="nearest")


def zmap(a, b):
    """Significance map Z of b minus a, for the eye only.

    Resampling an undersampled image is never exact, so every star leaves a residual. The reference stars measure this
    residual as a fraction of the star signal. That fraction goes into the error. A star that did not change then gives
    a value near 1.
    """
    i1, v1 = align(a, b)
    d1, d2 = i1 - np.nanmedian(i1), b.img - np.nanmedian(b.img)
    yy, xx = np.indices(d2.shape)
    away = np.hypot(xx - b.xy[0], yy - b.xy[1]) > 5
    good = (b.flags & b.core) == 0
    m = away & good & (d2 > np.nanpercentile(d2, 92))
    k = float(np.nansum(d1[m] * d2[m]) / max(np.nansum(d1[m] ** 2), 1e-12)) if m.sum() > 5 else 1.0
    k = k if 0.2 < k < 5 else 1.0
    diff, sig = d2 - k * d1, maximum_filter(np.maximum(np.abs(d2), np.abs(k * d1)), size=5)
    near = np.zeros(d2.shape, bool)
    for x, y in (b.ref if b.ref is not None else []):
        near |= np.hypot(xx - x - b.shift[0], yy - y - b.shift[1]) < 1.6
    near &= good & (sig > 5 * np.sqrt(b.var))
    fsys = float(np.clip(np.percentile(np.abs(diff[near]) / sig[near], 84), 0.05, 0.8)) if near.sum() >= 6 else 0.4
    z = diff / np.sqrt(b.var + k * k * v1 + (fsys * sig) ** 2)
    return z / max(1.4826 * float(np.nanmedian(np.abs(z - np.nanmedian(z)))), 1.0), k, fsys


def mf_kernel():
    k = gauss((7, 7), 3, 3)
    return k / math.sqrt((k * k).sum())


def source_mask(e):
    """True near the target and near every catalog star. A bright source hides a larger circle."""
    k = mf_kernel()
    raw = convolve(e.img - np.median(e.img), k, mode="nearest") / np.sqrt(convolve(e.var, k * k, mode="nearest"))
    yy, xx = np.indices(e.img.shape)
    m = np.zeros(e.img.shape, bool)
    for x, y in [e.xy] + [tuple(p) for p in (e.ref if e.ref is not None else [])]:
        x, y = x + e.shift[0], y + e.shift[1]
        if -8 < x < e.img.shape[1] + 8 and -8 < y < e.img.shape[0] + 8:
            v = raw[box_at(e, x, y, 1)]
            r = 2 * PSF_SIGMA * math.sqrt(math.log(max(float(v.max()) if v.size else 1.0, math.e))) + 2.0
            m |= np.hypot(xx - x, yy - y) < r
    return m


def snr_map(e, hide_sources=False):
    """Matched filter signal to noise in every pixel. Flagged pixels give NaN."""
    k = mf_kernel()
    s = convolve(e.img - np.median(e.img), k, mode="nearest") / np.sqrt(convolve(e.var, k * k, mode="nearest"))
    s = np.where((e.flags & e.bad) == 0, s, np.nan)
    if hide_sources:
        s[source_mask(e)] = np.nan
    return s


def witness(exps, i, x, y, level=5.0):
    """Sky or camera test. Does a spot in exposure i appear again at the same sky position in the other exposures?"""
    e = exps[i]
    ra, dec = to_sky(e.wcs, x - e.shift[0], y - e.shift[1])
    seen = same = same_seen = total = 0
    rows = []
    for j, o in enumerate(exps):
        if j == i:
            continue
        px, py = to_pix(o.wcs, ra, dec)
        px, py = px[0] + o.shift[0], py[0] + o.shift[1]
        h, w = o.img.shape
        if not (3 <= px < w - 3 and 3 <= py < h - 3):
            continue
        s = snr_map(o)[box_at(o, px, py, 1)]
        v = float(np.nanmax(s)) if np.isfinite(s).any() else float("nan")
        if not math.isfinite(v):
            continue
        total += 1
        hit = v > level
        seen += hit
        if o.det == e.det:
            same += 1
            same_seen += hit
        rows.append(dict(i=j, snr=v, seen=bool(hit), det=o.det))
    here = snr_map(e)[box_at(e, x, y, 1)]
    here = float(np.nanmax(here)) if np.isfinite(here).any() else float("nan")
    frac = seen / total if total else 0.0
    once = total > 0 and frac < 0.08
    verdict = ("No other frame covers this place." if total == 0 else "Part of the sky. It appears again in the other frames." if frac >= 0.5 else
               "One frame only. A camera glitch, a cosmic ray, or an object that moved away." if once else
               "Seen again in some frames only. Faint, variable, or seen in some colors only.")
    return dict(ra=float(ra[0]), dec=float(dec[0]), snr_here=here, frames=total, seen=int(seen), same_detector=same,
                same_detector_seen=int(same_seen), verdict=verdict, kind="sky" if frac >= 0.5 else "single" if once else "mixed", rows=rows)


# ---------------------------------------------------------------- proof layer

def noise_check(e):
    """Noise reality check. Differences of neighbor pixels on empty sky, divided by the declared error. The width must be 1.

    The declared variance is multiplied by the square of the measured width.
    """
    ok = ~source_mask(e) & ((e.flags & e.bad) == 0)
    d = ((e.img[:, 1:] - e.img[:, :-1]) / np.sqrt(e.var[:, 1:] + e.var[:, :-1]))[ok[:, 1:] & ok[:, :-1]]
    if d.size < 40:
        return e.noise_k, int(d.size)
    k = float(np.clip(1.4826 * np.median(np.abs(d - np.median(d))), 0.4, 4.0))
    e.var = e.var * k * k
    e.noise_k *= k
    return k, int(d.size)


def wilson(h, n, z=1.96):
    p, d = h / n, 1 + z * z / n
    c, w = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - w, c + w


def recovery(frames, snrs=(2, 3, 4, 6, 8, 12), trials=40, alpha=0.05, seed=5):
    """Injection test on empty sky. The threshold is a conformal quantile of the largest values in untouched frames."""
    rng = np.random.default_rng(seed)
    g = gauss((7, 7), 3, 3)
    base = [snr_map(e, hide_sources=True) for e in frames]
    ok = [i for i, s in enumerate(base) if np.isfinite(s[6:-6, 6:-6]).sum() > 30]
    if not ok:
        return dict(threshold=None, alpha=alpha, trials=0, curve=[], why="No empty sky in these frames.")
    mx = sorted(float(np.nanmax(base[i][6:-6, 6:-6])) for i in ok)
    thr = mx[min(len(mx) - 1, math.ceil((len(mx) + 1) * (1 - alpha)) - 1)]
    curve = []
    for q in snrs:
        hit = n = 0
        for _ in range(trials):
            i = ok[rng.integers(len(ok))]
            e = frames[i]
            free = np.argwhere(np.isfinite(base[i][8:-8, 8:-8]))
            if not len(free):
                continue
            y, x = free[rng.integers(len(free))] + 8 + rng.uniform(-0.5, 0.5, 2)
            amp = q * math.sqrt(float(e.var[int(round(y)), int(round(x))])) / math.sqrt((g * g).sum())
            f = Exp(e.id, e.mjd, e.lam, e.bw, e.det, e.rel, e.label, e.img + amp * gauss(e.img.shape, x, y), e.var, e.flags, bits=e.bits)
            s = snr_map(f)
            yy, xx = np.indices(s.shape)
            near = np.hypot(xx - x, yy - y) < 2.5
            n += 1
            hit += int(np.isfinite(s[near]).any() and np.nanmax(s[near]) > thr)
        lo, hi = wilson(hit, max(n, 1))
        curve.append(dict(snr=q, completeness=hit / max(n, 1), lo=lo, hi=hi))
    return dict(threshold=thr, alpha=alpha, trials=trials, frames=len(ok), curve=curve)


def false_alarm_rate(frames, thr, n=200, seed=9):
    """Negative control. Fraction of empty places with a signal above the threshold."""
    rng, hit, tot = np.random.default_rng(seed), 0, 0
    for _ in range(n):
        s = snr_map(frames[rng.integers(len(frames))], hide_sources=True)[6:-6, 6:-6]
        free = np.argwhere(np.isfinite(s))
        if len(free):
            y, x = free[rng.integers(len(free))]
            tot += 1
            hit += int(s[y, x] > thr)
    lo, hi = wilson(hit, max(tot, 1))
    return dict(places=tot, alarms=hit, rate=hit / max(tot, 1), lo=lo, hi=hi)
