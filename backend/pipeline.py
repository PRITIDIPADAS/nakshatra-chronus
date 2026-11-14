"""CHRONOS field pipeline: register, co add, and find change with three independent methods.

P  catalog method. Find point sources in each visit, link them across visits, and fit position and brightness.
D  difference method. Subtract fair pairs of co added visits (same array, matched colors) and look for significant residue.
A  anomaly method. Describe the time behaviour of every pixel against its fair partners, and let three unsupervised
   models (isolation forest, local outlier factor, robust covariance) rank how unusual it is.

The three methods see the same pixels but fail in different ways. Their disagreement is a measurement in itself.
"""
import math

import numpy as np
from scipy.ndimage import convolve, map_coordinates, maximum_filter, median_filter
from scipy.optimize import least_squares

import core
from core import PIX, PSF_SIGMA, UJY

TH = dict(detect=5.0, change=5.0, link_px=1.5, cluster_px=2.5, fair_coadd=0.35, fair_single=0.5, motion_dbic=10.0, motion_sig=5.0,
          var_z=5.0, on_snr=5.0, off_snr=2.0, presence_min=7.0, anomaly_rank=0.95, anomaly_min=4.5, edge=4, epoch_gap_days=30.0)
FEATURES = ("mot_sig", "mot_dbic", "pm_px", "var_z", "amp", "n_on", "n_off", "presence", "a1", "a2", "a3", "a4", "a5", "a6",
            "sharp", "flagfrac", "partner", "deep_snr", "m_P", "m_D", "m_A", "dipole")


# ---------------------------------------------------------------- small tools

def kernel(sigma=PSF_SIGMA):
    k = core.gauss((7, 7), 3, 3, sigma)
    return k / math.sqrt((k * k).sum())


def mf(img, var, k):
    """Matched filter signal to noise. Missing pixels count as zero signal with huge noise."""
    good = np.isfinite(img) & np.isfinite(var) & (var > 0)
    a = np.where(good, img, 0.0)
    v = np.where(good, var, 1e12)
    out = convolve(a, k, mode="constant") / np.sqrt(convolve(v, k * k, mode="constant"))
    cover = convolve(good.astype(float), k * k, mode="constant") / float((k * k).sum())
    return np.where(cover > 0.6, out, np.nan)


def peaks(S, thr, edge=4, size=3, absval=False):
    a = np.abs(S) if absval else S
    a = np.where(np.isfinite(a), a, -1e9)
    m = (a == maximum_filter(a, size=size)) & (a > thr)
    m[:edge], m[-edge:], m[:, :edge], m[:, -edge:] = False, False, False, False
    ys, xs = np.nonzero(m)
    return [(float(x), float(y), float(S[y, x])) for x, y in zip(xs, ys)]


def forced(img, var, x, y, sigma=PSF_SIGMA, r=3, bad=None):
    """Linear PSF photometry at a fixed position. Image units times pixels; multiply by UJY for microJy."""
    h, w = img.shape
    xi, yi = int(round(x)), int(round(y))
    if not (0 <= xi < w and 0 <= yi < h):
        return float("nan"), float("nan")
    sl = (slice(max(0, yi - r), min(h, yi + r + 1)), slice(max(0, xi - r), min(w, xi + r + 1)))
    d, v = img[sl], var[sl]
    yy, xx = np.mgrid[sl]
    k = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma * sigma)) / (2 * math.pi * sigma * sigma)
    m = np.isfinite(d) & np.isfinite(v) & (v > 0)
    if bad is not None:
        m &= ~bad[sl]
    if m.sum() < 6 or k[m].sum() < 0.5:
        return float("nan"), float("nan")
    wt = 1 / v[m]
    den = float(np.sum(k[m] ** 2 * wt))
    return float(np.sum(d[m] * k[m] * wt) / den), float(1 / math.sqrt(den))


def gauss_fit(img, var, x, y, r=3):
    """Gaussian fit with a free width. Returns width over the PSF width (a cosmic ray or hot pixel is sharper than a star)."""
    h, w = img.shape
    xi, yi = int(round(x)), int(round(y))
    sl = (slice(max(0, yi - r), min(h, yi + r + 1)), slice(max(0, xi - r), min(w, xi + r + 1)))
    d, v = img[sl], var[sl]
    if d.size < 16 or not np.isfinite(d).all():
        return float("nan")
    yy, xx = np.mgrid[sl]
    sig = np.sqrt(np.maximum(v, 1e-12))
    bg = float(np.median(d))
    a0 = max(float(d.max() - bg), 1e-6)

    def res(p):
        return ((d - p[0] * np.exp(-((xx - p[1]) ** 2 + (yy - p[2]) ** 2) / (2 * p[3] ** 2)) - p[4]) / sig).ravel()

    try:
        s = least_squares(res, [a0, x, y, PSF_SIGMA, bg], bounds=([0, x - 1.5, y - 1.5, 0.15, -np.inf], [np.inf, x + 1.5, y + 1.5, 3.0, np.inf]))
        return float(s.x[3] / PSF_SIGMA)
    except Exception:
        return float("nan")


def slog(x):
    return math.copysign(math.log1p(abs(x)), x) if x is not None and math.isfinite(x) else 0.0


# ---------------------------------------------------------------- state

def epochs_of(exps, gap=TH["epoch_gap_days"]):
    """Visit number of each exposure. A new visit starts after a gap of more than gap days. Near the ecliptic poles SPHEREx
    sees a field almost every day, with no such gap: there a visit also ends after gap days, so that change over weeks can be seen."""
    order = np.argsort([e.mjd for e in exps])
    out, g, prev, start = [0] * len(exps), 0, None, None
    for i in order:
        t = exps[i].mjd
        if prev is not None and (t - prev > gap or t - start > gap):
            g += 1
            start = t
        if start is None:
            start = t
        out[i], prev = g, t
    return out


def ref_wcs(exps, center=None, size=None):
    e = exps[0]
    n = size or e.img.shape[0]
    c0 = (n - 1) / 2
    if center is None:
        ra, dec = core.to_sky(e.wcs, (e.img.shape[1] - 1) / 2 - e.shift[0], (e.img.shape[0] - 1) / 2 - e.shift[1])
        center = (float(ra[0]), float(dec[0]))
    return core.make_wcs(center[0], center[1], c0, c0, 0.0), n, tuple(center)


def register(e, ref, n, shift=None, flags=True, order=3):
    """Resample one exposure onto the reference grid with its WCS and its star anchor shift."""
    yy, xx = np.mgrid[0:n, 0:n]
    ra, dec = core.to_sky(ref, xx.ravel(), yy.ravel())
    x2, y2 = core.to_pix(e.wcs, ra, dec)
    sx, sy = e.shift if shift is None else shift
    x2, y2 = (x2 + sx).reshape(n, n), (y2 + sy).reshape(n, n)
    h, w = e.img.shape
    inside = (x2 > -0.5) & (x2 < w - 0.5) & (y2 > -0.5) & (y2 < h - 0.5)
    img = map_coordinates(e.img, [y2, x2], order=order, mode="nearest")
    var = map_coordinates(e.var, [y2, x2], order=1, mode="nearest")
    bad = map_coordinates(((e.flags & e.bad) != 0).astype(float), [y2, x2], order=0, mode="nearest") > 0 if flags else np.zeros((n, n), bool)
    img, var = np.where(inside, img, np.nan), np.where(inside, var, np.nan)
    return img, var, bad, inside, (x2, y2)


def color_distance(a, b):
    return abs(a.lam - b.lam) / (0.5 * (a.bw + b.bw))


def build(exps, ref, n, catalog=None, opt=None):
    """Registered stack, gains, co adds and detection images. opt changes one choice for the counterfactual tests."""
    opt = opt or {}
    S = dict(exps=exps, ref=ref, n=n, opt=opt, ep=epochs_of(exps))
    S["E"] = max(S["ep"]) + 1
    S["dets"] = sorted({e.det for e in exps})
    S["mjd_ep"] = [float(np.mean([e.mjd for e, g in zip(exps, S["ep"]) if g == q])) for q in range(S["E"])]
    rng = np.random.default_rng(opt.get("seed", 0))
    R, RV, RB, IN, MAP = [], [], [], [], []
    for e in exps:
        sh = None
        if opt.get("no_anchor"):
            sh = (0.0, 0.0)
        elif opt.get("shift_error"):
            ang = rng.uniform(0, 2 * math.pi)
            er = getattr(e, "shift_err", 0.15)
            sh = (e.shift[0] + er * math.cos(ang), e.shift[1] + er * math.sin(ang))
        img, var, bad, inside, mp = register(e, ref, n, sh, flags=not opt.get("keep_flags"))
        if opt.get("worst_noise"):
            var = var * opt["worst_noise"] ** 2
        good = inside & ~bad & np.isfinite(img)
        if opt.get("local_bg"):
            bgimg = median_filter(np.where(good, img, np.nanmedian(img[good])), size=11, mode="nearest")
            img = img - bgimg
        else:
            img = img - (float(np.median(img[good])) if good.sum() > 20 else 0.0)
        img = np.where(bad, np.nan, img)
        R.append(img)
        RV.append(var)
        RB.append(bad)
        IN.append(inside)
        MAP.append(mp)
    S.update(R=np.array(R), RV=np.array(RV), RB=np.array(RB), IN=np.array(IN), MAP=MAP)
    S["drop"] = opt.get("drop_epoch")
    S["use"] = np.array([S["drop"] is None or g != S["drop"] for g in S["ep"]])
    S["sigma"] = PSF_SIGMA * opt.get("psf_scale", 1.0)
    S["K"] = kernel(S["sigma"])
    stars = []
    if catalog:
        for s in catalog:
            if s.get("pm_ra") or s.get("pm_dec") or s.get("mag", 99) > 16.5:
                continue
            x, y = core.to_pix(ref, s["ra"], s["dec"])
            if 3 <= x[0] < n - 3 and 3 <= y[0] < n - 3:
                stars.append((float(x[0]), float(y[0])))
    S["stars"] = stars
    gains(S)
    coadd(S)
    return S


def gains(S):
    """Star ensemble gain of every exposure against the mean of its fair partners at the same array and color."""
    exps, R, RV = S["exps"], S["R"], S["RV"]
    g = np.ones(len(exps))
    ge = np.full(len(exps), np.nan)
    ns = np.zeros(len(exps), int)
    if len(S["stars"]) >= 3:
        F = np.array([[forced(R[i], RV[i], x, y, S["sigma"])[0] for x, y in S["stars"]] for i in range(len(exps))])
        for i, e in enumerate(exps):
            part = [j for j, o in enumerate(exps) if o.det == e.det and color_distance(e, o) <= TH["fair_single"] and S["use"][j]]
            if len(part) < 2:
                continue
            ref = np.nanmedian(F[part], axis=0)
            ok = np.isfinite(F[i]) & np.isfinite(ref) & (ref > 0)
            r = F[i][ok] / ref[ok]
            r = r[(r > 0.5) & (r < 2.0)]
            if len(r) >= 3:
                g[i] = float(np.median(r))
                ge[i] = float(1.2533 * np.std(r) / math.sqrt(len(r)))
                ns[i] = len(r)
    S["gain"], S["gain_err"], S["gain_n"] = g, ge, ns


def coadd(S):
    exps, E, dets = S["exps"], S["E"], S["dets"]
    n = S["n"]
    C, CV, CN, LAM = {}, {}, {}, {}
    for q in range(E):
        for d in dets:
            idx = [i for i, e in enumerate(exps) if S["ep"][i] == q and e.det == d and S["use"][i]]
            if not idx:
                continue
            num, den = np.zeros((n, n)), np.zeros((n, n))
            for i in idx:
                a, v = S["R"][i] / S["gain"][i], S["RV"][i] / S["gain"][i] ** 2
                ok = np.isfinite(a) & np.isfinite(v) & (v > 0)
                num += np.where(ok, a / np.where(ok, v, 1), 0)
                den += np.where(ok, 1 / np.where(ok, v, 1), 0)
            C[q, d] = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
            CV[q, d] = np.where(den > 0, 1 / np.where(den > 0, den, 1), np.nan)
            CN[q, d] = idx
            LAM[q, d] = [exps[i].lam for i in idx]
    S.update(C=C, CV=CV, CN=CN, LAM=LAM)
    # White light: each array scaled to unit pixel noise, then summed. Detection: matched filter on that sum.
    W, WV, DET = {}, {}, {}
    for q in range(E):
        if S["drop"] == q:
            continue
        num, var, k = np.zeros((n, n)), np.zeros((n, n)), 0
        for d in dets:
            if (q, d) not in C:
                continue
            s = float(np.sqrt(np.nanmedian(CV[q, d])))
            ok = np.isfinite(C[q, d])
            num += np.where(ok, C[q, d] / s, 0)
            var += np.where(ok, CV[q, d] / s / s, 0)
            k += 1
        if k:
            W[q] = np.where(var > 0, num, np.nan)
            WV[q] = np.where(var > 0, var, np.nan)
            DET[q] = mf(W[q], WV[q], S["K"])
    S.update(W=W, WV=WV, DET=DET)
    if W:
        num = sum(np.nan_to_num(W[q]) for q in W)
        var = sum(np.nan_to_num(WV[q]) for q in W)
        S["DEEP"] = np.where(var > 0, num, np.nan)
        S["DEEPV"] = np.where(var > 0, var, np.nan)
        S["DEEPS"] = mf(S["DEEP"], S["DEEPV"], S["K"])


# ---------------------------------------------------------------- P: catalog method

def detect_catalog(S):
    """Point sources in every visit, linked across visits by friends of friends."""
    dets = []
    for q, D in S["DET"].items():
        for x, y, v in peaks(D, TH["detect"], TH["edge"]):
            cx, cy, ex, ey, fl, snr = core.centroid(S["W"][q], S["WV"][q], x, y, s=S["sigma"], r=3, reach=1.5)
            if snr > TH["detect"] and ex < 1 and ey < 1:
                dets.append(dict(q=q, x=cx, y=cy, ex=ex, ey=ey, snr=float(snr)))
    parent = list(range(len(dets)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(dets)):
        for j in range(i + 1, len(dets)):
            if dets[i]["q"] != dets[j]["q"] and math.hypot(dets[i]["x"] - dets[j]["x"], dets[i]["y"] - dets[j]["y"]) < TH["link_px"]:
                parent[root(i)] = root(j)
    groups = {}
    for i, d in enumerate(dets):
        groups.setdefault(root(i), []).append(d)
    out = []
    for g in groups.values():
        by = {}
        for d in g:
            if d["q"] not in by or d["snr"] > by[d["q"]]["snr"]:
                by[d["q"]] = d
        out.append(sorted(by.values(), key=lambda d: d["q"]))
    S["groups"] = out
    S["floor"] = astro_floor(S)
    return out


def astro_floor(S):
    """Extra position error that makes bright sources seen in every visit agree with a fixed position. Pixels."""
    r2, e2 = [], []
    for g in S["groups"]:
        if len(g) == len(S["DET"]) and min(d["snr"] for d in g) > 20:
            x, y = np.array([d["x"] for d in g]), np.array([d["y"] for d in g])
            r2 += list((x - x.mean()) ** 2 + (y - y.mean()) ** 2)
            e2 += [d["ex"] ** 2 + d["ey"] ** 2 for d in g]
    if len(r2) < 6:
        return 0.03
    k = len(S["DET"])
    r2, e2 = np.array(r2), np.array(e2)
    keep = r2 <= np.percentile(r2, 90)
    f2 = float(np.mean(r2[keep])) / 0.744 * k / (2 * max(k - 1, 1)) - float(np.mean(e2[keep])) / 2
    return float(np.clip(math.sqrt(max(f2, 0.0)), 0.01, 0.2))


def motion(pts, mjd_ep, floor):
    """Fixed position against linear motion from visit centroids. Returns significance, delta BIC and motion in pixels per year."""
    if len(pts) < 2:
        return dict(n=len(pts), sig=0.0, dbic=0.0, pm=0.0, pm_x=0.0, pm_y=0.0, err=float("nan"))
    t = np.array([(mjd_ep[d["q"]] - mjd_ep[0]) / 365.25 for d in pts])
    out = dict(n=len(pts))
    chi0 = chi1 = 0.0
    p, cov = [], []
    for c, ec in (("x", "ex"), ("y", "ey")):
        v = np.array([d[c] for d in pts])
        w = 1 / (np.array([d[ec] for d in pts]) ** 2 + floor ** 2)
        m0 = np.sum(w * v) / np.sum(w)
        chi0 += float(np.sum(w * (v - m0) ** 2))
        A = np.c_[np.ones(len(t)), t - np.average(t, weights=w)]
        q, *_ = np.linalg.lstsq(A * np.sqrt(w)[:, None], v * np.sqrt(w), rcond=None)
        chi1 += float(np.sum(w * (v - A @ q) ** 2))
        cv = np.linalg.pinv((A * np.sqrt(w)[:, None]).T @ (A * np.sqrt(w)[:, None]))
        p.append(float(q[1]))
        cov.append(float(cv[1, 1]))
    k = len(pts)
    s2 = max(1.0, chi1 / max(2 * k - 4, 1)) if k > 2 else 1.0
    pm = math.hypot(*p)
    err = math.sqrt(max((p[0] ** 2 * cov[0] + p[1] ** 2 * cov[1]) / max(pm * pm, 1e-18), 0.0) * s2)
    out.update(pm=pm, pm_x=p[0], pm_y=p[1], err=err, sig=pm / max(err, 1e-9), dbic=(chi0 - chi1) / s2 - 2 * math.log(2 * k), chi1=chi1,
               t=t.tolist(), x=[d["x"] for d in pts], y=[d["y"] for d in pts], ex=[math.hypot(d["ex"], floor) for d in pts],
               ey=[math.hypot(d["ey"], floor) for d in pts], q=[d["q"] for d in pts])
    return out


def visit_snr(S, x, y):
    out = {}
    for q, D in S["DET"].items():
        xi, yi = int(round(x)), int(round(y))
        if 1 <= xi < S["n"] - 1 and 1 <= yi < S["n"] - 1:
            w = D[yi - 1:yi + 2, xi - 1:xi + 2]
            out[q] = float(np.nanmax(w)) if np.isfinite(w).any() else float("nan")
    return out


def fluxes(S, x, y, track=None):
    """Forced photometry of every co add in microJy. track maps a visit to a position for a moving source."""
    out = {}
    for (q, d), C in S["C"].items():
        px, py = track.get(q, (x, y)) if track else (x, y)
        f, e = forced(C, S["CV"][q, d], px, py, S["sigma"])
        out[q, d] = (f * UJY, e * UJY)
    return out


def phot_floor(S):
    """Fractional brightness error per array that makes catalog stars agree with a constant. Measured, not assumed.

    It holds the gain error, the resampling error and the small color shift between surveys."""
    out = {}
    for d in S["dets"]:
        r2, e2 = [], []
        for x, y in S["stars"]:
            v = [forced(S["C"][q, d], S["CV"][q, d], x, y, S["sigma"]) for q in range(S["E"]) if (q, d) in S["C"]]
            v = [(f, e) for f, e in v if math.isfinite(f) and f > 20 * e]
            if len(v) < 2:
                continue
            f = np.array([a[0] for a in v])
            m = f.mean()
            k = len(v)
            r2 += list(((f - m) / m) ** 2 * k / (k - 1))
            e2 += [(a[1] / m) ** 2 for a in v]
        if len(r2) >= 4:
            r2, e2 = np.array(r2), np.array(e2)
            out[d] = float(np.clip(math.sqrt(max(float(np.mean(r2)) - float(np.mean(e2)), 0.0)), 0.005, 0.1))
        else:
            out[d] = 0.02
    S["pfloor"] = out
    return out


def variability(fl, dets, floor=None):
    """Constant brightness test per array with the measured floor. Returns a combined z score and the largest fractional change."""
    chi = dof = 0.0
    amp = 0.0
    for d in dets:
        v = [(q, f, e) for (q, dd), (f, e) in fl.items() if dd == d and math.isfinite(f) and math.isfinite(e) and e > 0]
        if len(v) < 2:
            continue
        f, e = np.array([a[1] for a in v]), np.array([a[2] for a in v])
        if floor:
            e = np.sqrt(e ** 2 + (floor.get(d, 0.02) * np.abs(np.median(f))) ** 2)
        w = 1 / e ** 2
        m = float(np.sum(w * f) / np.sum(w))
        chi += float(np.sum(w * (f - m) ** 2))
        dof += len(v) - 1
        if m > 5 * math.sqrt(1 / np.sum(w)):
            amp = max(amp, float((f.max() - f.min()) / abs(m)))
    z = (chi - dof) / math.sqrt(2 * dof) if dof else 0.0
    return float(z), float(amp), chi, dof


# ---------------------------------------------------------------- D: difference method

def fair_coadd_pairs(S):
    out = []
    for q1 in range(S["E"]):
        for q2 in range(q1 + 1, S["E"]):
            for d in S["dets"]:
                if (q1, d) not in S["C"] or (q2, d) not in S["C"]:
                    continue
                A, B = [S["exps"][i] for i in S["CN"][q1, d]], [S["exps"][i] for i in S["CN"][q2, d]]
                ab = [min(color_distance(a, b) for b in B) for a in A] + [min(color_distance(a, b) for a in A) for b in B]
                rel = {a.rel for a in A} == {b.rel for b in B}
                out.append(dict(q1=q1, q2=q2, det=d, color=float(np.mean(ab)), worst=float(max(ab)), release_same=rel,
                                fair=bool(np.mean(ab) <= TH["fair_coadd"] and max(ab) <= 0.6)))
    return out


def diff_map(S, q1, q2, d):
    """Matched filter significance of visit q2 minus visit q1 on one array, with the resampling error measured on stars."""
    C1, C2, V1, V2 = S["C"][q1, d], S["C"][q2, d], S["CV"][q1, d], S["CV"][q2, d]
    D = C2 - C1
    sig = maximum_filter(np.nan_to_num(np.maximum(np.abs(C1), np.abs(C2))), size=5)
    vals = []
    for x, y in S["stars"]:
        xi, yi = int(round(x)), int(round(y))
        w = (slice(max(0, yi - 1), yi + 2), slice(max(0, xi - 1), xi + 2))
        s = sig[w]
        dd = D[w]
        ok = np.isfinite(dd) & (s > 5 * np.sqrt(np.nan_to_num(V2[w], nan=1e9)))
        vals += list(np.abs(dd[ok]) / s[ok])
    fsys = float(np.clip(np.percentile(vals, 84), 0.01, 0.5)) if len(vals) >= 6 else 0.05
    return mf(D, V1 + V2 + (fsys * sig) ** 2, S["K"]), fsys


def detect_difference(S):
    pairs = fair_coadd_pairs(S)
    maps, out = {}, []
    for q1 in range(S["E"]):
        for q2 in range(q1 + 1, S["E"]):
            if S["drop"] in (q1, q2):
                continue
            use = [p for p in pairs if p["q1"] == q1 and p["q2"] == q2 and p["fair"] and p["release_same"]]
            if len(use) < 2:
                continue
            per = {}
            for p in use:
                per[p["det"]], p["fsys"] = diff_map(S, q1, q2, p["det"])
            stack = np.array([per[d] for d in per])
            cnt = np.sum(np.isfinite(stack), axis=0)
            comb = np.where(cnt >= 2, np.nansum(stack, axis=0) / np.sqrt(np.maximum(cnt, 1)), np.nan)
            maps[q1, q2] = dict(comb=comb, per=per)
            pk = peaks(comb, TH["change"], TH["edge"], absval=True)
            pos = [p for p in pk if p[2] > 0]
            neg = [p for p in pk if p[2] < 0]
            for x, y, v in pk:
                other = neg if v > 0 else pos
                dip = [o for o in other if math.hypot(o[0] - x, o[1] - y) < 3.2]
                out.append(dict(x=x, y=y, s=v, q1=q1, q2=q2, dipole=bool(dip)))
    S["pairs"], S["dmaps"] = pairs, maps
    return out


# ---------------------------------------------------------------- A: anomaly method

def residual_cube(S):
    """Each exposure minus the mean of its fair partners from other visits, as matched filter significance."""
    exps, n = S["exps"], S["n"]
    Ecube = np.full((len(exps), n, n), np.nan)
    for i, e in enumerate(exps):
        if not S["use"][i]:
            continue
        part = [j for j, o in enumerate(exps) if j != i and S["ep"][j] != S["ep"][i] and o.det == e.det and color_distance(e, o) <= TH["fair_single"]
                and S["use"][j]]
        if not part:
            continue
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                M = np.nanmean([S["R"][j] / S["gain"][j] for j in part], axis=0)
                MV = np.nanmean([S["RV"][j] / S["gain"][j] ** 2 for j in part], axis=0) / len(part)
        a = S["R"][i] / S["gain"][i]
        sig = maximum_filter(np.nan_to_num(np.abs(M)), size=5)
        Ecube[i] = mf(a - M, S["RV"][i] / S["gain"][i] ** 2 + MV + (0.04 * sig) ** 2, S["K"])
    S["Ecube"] = Ecube
    return Ecube


def pixel_features(S):
    E = S["Ecube"]
    n = S["n"]
    A = np.abs(E)
    have = np.isfinite(E)
    cnt = have.sum(0)
    a1 = np.where(cnt > 0, np.nanmax(np.where(have, A, -1), 0), 0)
    a2 = np.where(cnt > 0, np.sum(np.where(have, A > 3, False), 0) / np.maximum(cnt, 1), 0)
    top = np.nanargmax(np.where(have, A, -1), 0)
    sgn = np.sign(np.take_along_axis(np.where(have, E, 0), top[None], 0)[0])
    srt = -np.sort(-np.where(have, sgn[None] * E, -1e9), axis=0)
    a4 = np.clip((srt[0] - np.maximum(srt[1], 0)) / np.maximum(srt[0], 1.0), 0, 1)
    ep = np.array(S["ep"])
    a3 = np.zeros((n, n))
    for q in range(S["E"]):
        sel = ep == q
        k = np.sum(have[sel], 0)
        m = np.where(k > 0, np.nansum(np.where(have[sel], E[sel], 0), 0) / np.maximum(k, 1) * np.sqrt(np.maximum(k, 1)), 0)
        a3 = np.maximum(a3, np.abs(m))
    dets = np.array([e.det for e in S["exps"]])
    tot = np.nansum(np.where(have, E * E, 0), 0)
    a5 = np.zeros((n, n))
    for d in S["dets"]:
        a5 = np.maximum(a5, np.nansum(np.where(have[dets == d], E[dets == d] ** 2, 0), 0) / np.maximum(tot, 1e-9))
    strong = have & (A > 3)
    a6 = np.abs(np.sum(np.where(strong, np.sign(E), 0), 0)) / np.maximum(np.sum(strong, 0), 1)
    a7 = np.log10(1 + np.abs(np.nan_to_num(S["DEEPS"])))
    a8 = np.mean(np.array([maximum_filter(b.astype(float), size=3) for b in S["RB"]]), 0)
    F = np.stack([a1, a2, a3, a4, a5, a6, a7, a8], -1)
    S["pixfeat"] = F
    return F


def detect_anomaly(S):
    """Ensemble of three unsupervised models on pixel time behaviour. Model spread is kept: it is a disagreement too."""
    from sklearn.covariance import MinCovDet
    from sklearn.ensemble import IsolationForest
    from sklearn.neighbors import LocalOutlierFactor
    residual_cube(S)
    F = pixel_features(S)
    n = S["n"]
    e = TH["edge"]
    X = F[e:-e, e:-e].reshape(-1, F.shape[-1])
    med, mad = np.median(X, 0), 1.4826 * np.median(np.abs(X - np.median(X, 0)), 0) + 1e-6
    Z = (X - med) / mad
    scores = []
    iso = IsolationForest(n_estimators=150, random_state=0).fit(Z)
    scores.append(-iso.score_samples(Z))
    lof = LocalOutlierFactor(n_neighbors=35).fit(Z)
    scores.append(-lof.negative_outlier_factor_)
    try:
        mcd = MinCovDet(random_state=0, support_fraction=0.8).fit(Z)
        scores.append(mcd.mahalanobis(Z))
    except Exception:
        scores.append(np.sum(Z * Z, 1))
    ranks = np.array([np.argsort(np.argsort(s)) / (len(s) - 1) for s in scores])
    ens, spread = ranks.mean(0), ranks.std(0)
    M, SP = np.zeros((n, n)), np.zeros((n, n))
    M[e:-e, e:-e], SP[e:-e, e:-e] = ens.reshape(n - 2 * e, n - 2 * e), spread.reshape(n - 2 * e, n - 2 * e)
    S["anom"], S["anom_spread"], S["anom_models"] = M, SP, [r.reshape(n - 2 * e, n - 2 * e) for r in ranks]
    a1 = F[..., 0]
    cand = np.where((M >= TH["anomaly_rank"]) & (a1 >= TH["anomaly_min"]), M, 0)
    out = []
    for x, y, v in peaks(cand, 0.0, e, size=5):
        out.append(dict(x=x, y=y, s=float(v), a1=float(a1[int(y), int(x)]), spread=float(SP[int(y), int(x)])))
    return out


# ---------------------------------------------------------------- candidates and features

def detect_all(S):
    phot_floor(S)
    groups = detect_catalog(S)
    pdet = []
    for g in groups:
        x, y = float(np.mean([d["x"] for d in g])), float(np.mean([d["y"] for d in g]))
        mo = motion(g, S["mjd_ep"], S["floor"])
        vs = visit_snr(S, x, y)
        on = [v for v in vs.values() if math.isfinite(v)]
        pres = (max(on) >= TH["presence_min"] and min(on) <= TH["off_snr"]) if on else False
        fl = fluxes(S, x, y, {d["q"]: (d["x"], d["y"]) for d in g})
        vz, amp, *_ = variability(fl, S["dets"], S["pfloor"])
        moving = mo["n"] >= 3 and mo["dbic"] > TH["motion_dbic"] and mo["sig"] > TH["motion_sig"]
        if pres or moving or vz > TH["var_z"]:
            pdet.append(dict(x=x, y=y, s=max(mo["sig"] if moving else 0, vz if vz > TH["var_z"] else 0, max(on) if pres else 0),
                             why=[w for w, c in (("presence", pres), ("motion", moving), ("brightness", vz > TH["var_z"])) if c]))
    ddet = detect_difference(S)
    adet = detect_anomaly(S)
    S["det_P"], S["det_D"], S["det_A"] = pdet, ddet, adet
    return candidates(S)


def candidates(S):
    items = [("P", d) for d in S["det_P"]] + [("D", d) for d in S["det_D"]] + [("A", d) for d in S["det_A"]]
    parent = list(range(len(items)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if math.hypot(items[i][1]["x"] - items[j][1]["x"], items[i][1]["y"] - items[j][1]["y"]) < TH["cluster_px"]:
                parent[root(i)] = root(j)
    cl = {}
    for i, it in enumerate(items):
        cl.setdefault(root(i), []).append(it)
    out = []
    for members in cl.values():
        m = {k: [d for kk, d in members if kk == k] for k in "PDA"}
        lead = (max(m["P"], key=lambda d: d["s"]) if m["P"] else max(m["D"], key=lambda d: abs(d["s"])) if m["D"] else max(m["A"], key=lambda d: d["s"]))
        if not m["P"] and m["D"]:
            pos = [d for d in m["D"] if d["s"] > 0] or m["D"]
            lead = max(pos, key=lambda d: abs(d["s"]))
        out.append(dict(x=float(lead["x"]), y=float(lead["y"]), methods="".join(k for k in "PDA" if m[k]),
                        P=m["P"], D=m["D"], A=m["A"]))
    return out


def track_for(S, x, y):
    """Visit positions near x, y from the catalog groups, or None."""
    best = None
    for g in S["groups"]:
        gx, gy = np.mean([d["x"] for d in g]), np.mean([d["y"] for d in g])
        r = math.hypot(gx - x, gy - y)
        if r < TH["cluster_px"] and (best is None or r < best[0]):
            best = (r, g)
    return best[1] if best else None


def measure(S, c):
    """All measurements of one candidate on one state."""
    x, y = c["x"], c["y"]
    g = track_for(S, x, y)
    pts = []
    for q in sorted(S["W"]):
        if g and any(d["q"] == q for d in g):
            pts.append(next(d for d in g if d["q"] == q))
            continue
        cx, cy, ex, ey, fl, snr = core.centroid(S["W"][q], S["WV"][q], x, y, s=S["sigma"], r=3, reach=1.2)
        if snr > TH["detect"] and ex < 1 and ey < 1:
            pts.append(dict(q=q, x=cx, y=cy, ex=ex, ey=ey, snr=float(snr)))
    mo = motion(pts, S["mjd_ep"], S["floor"])
    trk = {d["q"]: (d["x"], d["y"]) for d in pts}
    if mo["n"] >= 3 and mo["dbic"] > TH["motion_dbic"]:
        for q in S["W"]:
            if q not in trk:
                t = (S["mjd_ep"][q] - S["mjd_ep"][0]) / 365.25 - np.mean(mo["t"])
                trk[q] = (float(np.mean(mo["x"]) + mo["pm_x"] * t), float(np.mean(mo["y"]) + mo["pm_y"] * t))
    fl = fluxes(S, x, y, trk)
    vz, amp, chi, dof = variability(fl, S["dets"], S["pfloor"])
    vs = {q: visit_snr(S, *trk.get(q, (x, y))).get(q, float("nan")) for q in S["DET"]}
    on = [v for v in vs.values() if math.isfinite(v)]
    n_on = sum(v >= TH["on_snr"] for v in on)
    n_off = sum(v <= TH["off_snr"] for v in on)
    presence = (max(on) - min(on)) / math.sqrt(2) if on else 0.0
    dval = 0.0
    for (q1, q2), mp in S.get("dmaps", {}).items():
        xi, yi = int(round(x)), int(round(y))
        w = mp["comb"][max(0, yi - 1):yi + 2, max(0, xi - 1):xi + 2]
        if np.isfinite(w).any():
            dval = max(dval, float(np.nanmax(np.abs(w))))
    return dict(track=pts, motion=mo, fluxes=fl, var_z=vz, amp=amp, chi=chi, dof=dof, visit_snr=vs, n_on=n_on, n_off=n_off, presence=presence,
                dval=dval, trk=trk)


def direct_snr(S, c, m):
    """Signal to noise of the source itself in every exposure, at its position in that visit."""
    out = np.full(len(S["exps"]), np.nan)
    for i in range(len(S["exps"])):
        px, py = m["trk"].get(S["ep"][i], (c["x"], c["y"]))
        f, e = forced(S["R"][i] / S["gain"][i], S["RV"][i] / S["gain"][i] ** 2, px, py, S["sigma"])
        if math.isfinite(f) and e > 0:
            out[i] = f / e
    m["snr_exp"] = out
    return out


def features(S, c, m):
    """The fingerprint of one candidate: numbers that the hypothesis engine reads."""
    x, y = c["x"], c["y"]
    xi, yi = int(round(x)), int(round(y))
    w = (slice(max(0, yi - 1), yi + 2), slice(max(0, xi - 1), xi + 2))
    P = S["pixfeat"][w].reshape(-1, S["pixfeat"].shape[-1])
    j = int(np.argmax(P[:, 0]))
    pf = P[j]
    snr_exp = direct_snr(S, c, m)
    E = S["Ecube"][:, w[0], w[1]]
    if np.nanmax(snr_exp) > TH["detect"] if np.isfinite(snr_exp).any() else False:
        best = int(np.nanargmax(snr_exp))
    else:
        best = int(np.nanargmax(np.where(np.isfinite(E), np.abs(E), -1).reshape(len(S["exps"]), -1).max(1))) if np.isfinite(E).any() else None
    sharp, partner = float("nan"), 0.5
    if best is not None:
        e = S["exps"][best]
        x2, y2 = S["MAP"][best]
        ex = float(map_coordinates(x2, [[y], [x]], order=1)[0])
        ey = float(map_coordinates(y2, [[y], [x]], order=1)[0])
        if 3 <= ex < e.img.shape[1] - 3 and 3 <= ey < e.img.shape[0] - 3:
            sharp = gauss_fit(e.img, e.var, ex, ey)
        mates = [i for i, o in enumerate(S["exps"]) if o.frame and o.frame == e.frame and i != best and np.isfinite(snr_exp[i])]
        if mates:
            partner = 1.0 if max(snr_exp[i] for i in mates) > 3 else 0.0
    flagfrac = float(np.mean([S["RB"][i][w].any() for i in range(len(S["exps"]))]))
    deep = float(np.nanmax(S["DEEPS"][w])) if np.isfinite(S["DEEPS"][w]).any() else 0.0
    mo = m["motion"]
    f = dict(mot_sig=slog(mo["sig"] if mo["n"] >= 2 else 0.0), mot_dbic=slog(mo["dbic"] if mo["n"] >= 3 else 0.0),
             pm_px=slog(mo["pm"] * 10 if mo["n"] >= 2 else 0.0), var_z=slog(m["var_z"]), amp=min(m["amp"], 3.0), n_on=m["n_on"], n_off=m["n_off"],
             presence=slog(m["presence"]), a1=slog(pf[0]), a2=float(pf[1]), a3=slog(pf[2]), a4=float(pf[3]), a5=float(pf[4]), a6=float(pf[5]),
             sharp=float(sharp) if math.isfinite(sharp) else 1.0, flagfrac=flagfrac, partner=partner, deep_snr=slog(deep),
             m_P=float("P" in c["methods"]), m_D=float("D" in c["methods"]), m_A=float("A" in c["methods"]),
             dipole=float(any(d.get("dipole") for d in c["D"])))
    return f, dict(best_exposure=None if best is None else int(best), sharp=sharp, partner=partner, deep_snr=deep)


def run(exps, catalog=None, center=None, size=None, opt=None):
    """Full field pass. Returns the state with candidates, measurements and features."""
    ref, n, center = ref_wcs(exps, center, size)
    S = build(exps, ref, n, catalog, opt)
    S["center"] = center
    cands = detect_all(S)
    for c in cands:
        c["m"] = measure(S, c)
        c["f"], c["fx"] = features(S, c, c["m"])
    S["cands"] = cands
    return S


def match_truth(S, truth, radius=2.5):
    """Label each candidate with the planted change it sits on, or null."""
    lab = []
    pos = []
    for t in truth:
        mjd = float(np.mean(S["mjd_ep"]))
        ra, dec = t["ra"], t["dec"]
        if t["kind"] != "artefact" and any(t.get("pm", [0, 0])):
            cd = math.cos(math.radians(dec))
            dy = (mjd - core.SIM_T0) / 365.25
            ra, dec = ra + t["pm"][0] * dy / 3600 / cd, dec + t["pm"][1] * dy / 3600
        x, y = core.to_pix(S["ref"], ra, dec)
        pos.append((float(x[0]), float(y[0])))
    used = set()
    for c in S["cands"]:
        best = None
        for k, (t, (x, y)) in enumerate(zip(truth, pos)):
            r = math.hypot(c["x"] - x, c["y"] - y)
            lim = radius + (abs(t.get("pm", [0, 0])[0]) + abs(t.get("pm", [0, 0])[1])) / PIX * 0.8 if t["kind"] == "moving" else radius
            if r < lim and (best is None or r < best[0]):
                best = (r, k)
        if best:
            c["truth"] = truth[best[1]]["kind"]
            c["truth_id"] = truth[best[1]]["id"]
            c["truth_sub"] = truth[best[1]].get("sub")
            used.add(best[1])
        else:
            c["truth"], c["truth_id"], c["truth_sub"] = "null", None, None
        lab.append(c["truth"])
    missed = [dict(truth[k], x=pos[k][0], y=pos[k][1]) for k in range(len(truth)) if k not in used and 2 <= pos[k][0] < S["n"] - 2 and 2 <= pos[k][1] < S["n"] - 2]
    found = [dict(truth[k], x=pos[k][0], y=pos[k][1]) for k in range(len(truth)) if k in used]
    return lab, found, missed
