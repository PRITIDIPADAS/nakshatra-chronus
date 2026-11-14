"""Practice observatory fields.

A field holds many sources and several kinds of change and of artefact. The truth is kept aside, so that every
method can be scored. All images follow the SPHEREx rules that CHRONOS knows: six arrays, one color per pixel in each
exposure, colors that step through each band, surveys 3 and 4 shifted by half a channel, and two arrays (one on each
side of the dichroic) that look at the same place at the same time.
"""
import math

import numpy as np

import core
from core import BANDS, CHANNELS, PIX, SIGMA_DET, SIM_T0, UJY, Exp

CLASSES = ("moving", "variable", "transient", "artefact", "null")
EPOCH_DAYS = 182.6
PAIRS = {1: 4, 2: 5, 3: 6, 4: 1, 5: 2, 6: 3}  # arrays that see the same place at the same time
GHOST_COLUMNS = 128  # crosstalk copy two readout channels (2 x 64 columns) away, the strongest coupling in the Sky Simulator model


def flux_of(s, lam, mjd, epoch):
    """Flux of one practice source in microJy."""
    f = core.ab_to_ujy(s["mag"] + s.get("slope", 0.0) * (4.5 - lam))
    for c, w, depth in s.get("dips", []):
        f *= 1 - depth * math.exp(-0.5 * ((lam - c) / w) ** 2)
    if s.get("amp"):
        a = min(s["amp"] * (1.0 / lam) ** s.get("chroma", 0.0), 0.9)
        if s.get("period"):
            f *= 1 + a * math.sin(2 * math.pi * (mjd - SIM_T0) / s["period"] + s.get("phase", 0.0))
        else:
            f *= 1 - a / (1 + math.exp(-(mjd - SIM_T0 - s.get("step_day", 90.0)) / 15.0))
    on = s.get("on")
    if on is not None and epoch not in on:
        return 0.0
    return f * s.get("peak", {}).get(epoch, 1.0)


def pos_of(s, mjd):
    """Sky position of a source at an MJD: proper motion (arcsec per year) and parallax from SIM_T0."""
    dy = (mjd - SIM_T0) / 365.25
    cd = math.cos(math.radians(s["dec"]))
    ra, dec = s["ra"] + s.get("pm_ra", 0.0) * dy / 3600 / cd, s["dec"] + s.get("pm_dec", 0.0) * dy / 3600
    if s.get("plx"):
        fx, fy = core.plx_factors(mjd, s["ra"], s["dec"])
        ra, dec = ra + s["plx"] * fx[0] / 3600 / cd, dec + s["plx"] * fy[0] / 3600
    return ra, dec


def offset(center, dx, dy):
    """Sky position dx, dy pixels east and north of the center."""
    cd = math.cos(math.radians(center[1]))
    return center[0] + dx * PIX / 3600 / cd, center[1] + dy * PIX / 3600


def target_source(T):
    """A catalog target as a practice source: position at SIM_T0, motion, parallax and the practice brightness model."""
    sim = T.get("sim", {})
    ra, dec = core.catalog_at(T, SIM_T0)
    s = dict(id="target", kind="moving" if math.hypot(T["pmra"], T["pmdec"]) > 300 else ("variable" if sim.get("var") else "null"),
             ra=ra, dec=dec, pm_ra=T["pmra"] / 1000, pm_dec=T["pmdec"] / 1000, plx=T.get("plx", 0.0),
             mag=sim.get("sed", [12, 0])[0], slope=sim.get("sed", [12, 0])[1], dips=sim.get("dips", []), catalog=True, name=T["name"])
    if sim.get("var"):
        s.update(amp=sim["var"], chroma=sim.get("chroma", 0.0), period=sim.get("period"), step_day=90.0)
    return s


def free_spot(rng, used, size, margin=7, gap=6.0):
    c = (size - 1) / 2
    for _ in range(400):
        x, y = rng.uniform(margin - c, c - margin, 2)
        if all(math.hypot(x - u, y - v) > gap for u, v in used):
            used.append((x, y))
            return float(x), float(y)
    x, y = rng.uniform(margin - c, c - margin, 2)
    used.append((x, y))
    return float(x), float(y)


def random_event(kind, rng, center, used, size, hard=1.0):
    """One event with random strength. hard above 1 makes events fainter on average."""
    x, y = free_spot(rng, used, size)
    ra, dec = offset(center, x, y)
    sub = None
    if kind == "moving":
        pm, ang = rng.uniform(0.5, 7.0), rng.uniform(0, 2 * math.pi)
        s = dict(ra=ra, dec=dec, pm_ra=pm * math.cos(ang), pm_dec=pm * math.sin(ang), plx=float(rng.uniform(0, 0.25)),
                 mag=float(rng.uniform(14.0, 18.0) + 0.6 * (hard - 1)), slope=float(rng.uniform(-0.6, 1.2)), catalog=bool(rng.random() < 0.4))
        sub = "mover"
    elif kind == "variable":
        s = dict(ra=ra, dec=dec, mag=float(rng.uniform(13.0, 17.5) + 0.6 * (hard - 1)), slope=float(rng.uniform(-0.6, 0.6)),
                 amp=float(rng.uniform(0.06, 0.6) / hard), chroma=float(rng.uniform(0, 1.2)), period=float(rng.uniform(140, 700)),
                 phase=float(rng.uniform(0, 2 * math.pi)), catalog=True)
        sub = "periodic"
    elif kind == "transient":
        sub = str(rng.choice(["flare", "appear", "vanish"]))
        k = int(rng.integers(1, 4)) if sub != "flare" else int(rng.integers(0, 4))
        on = {k} if sub == "flare" else set(range(k, 4)) if sub == "appear" else set(range(0, k))
        s = dict(ra=ra, dec=dec, mag=float(rng.uniform(14.5, 18.5) + 0.6 * (hard - 1)), slope=float(rng.uniform(-0.5, 0.8)),
                 on=on, catalog=sub == "vanish" and rng.random() < 0.5)
    else:
        raise ValueError(kind)
    return dict(s, kind=kind, sub=sub)


def random_artefact(rng, plan, used, size, hard=1.0):
    """A camera effect with no sky source behind it. Kinds: glitch, hot pixel, crosstalk ghost, flagged blob."""
    sub = str(rng.choice(["glitch", "hot", "ghost", "flagged"], p=[0.3, 0.25, 0.3, 0.15]))
    x, y = free_spot(rng, used, size)
    n = int(rng.integers(len(plan)))
    a = dict(kind="artefact", sub=sub, x=x, y=y, exposure=n, level=float(rng.uniform(12, 80) / hard))
    if sub == "ghost":
        a.update(det=int(rng.integers(1, 7)), level=float(rng.uniform(6, 30) / hard))
    return a


def ghost_parent(center, a):
    """The bright star that casts a crosstalk copy. It sits GHOST_COLUMNS columns away on the detector, outside the cutout."""
    ra, dec = offset(center, a["x"] + GHOST_COLUMNS, a["y"])
    return dict(id=f"parent_{a.get('id', 'ghost')}", kind="star", ra=ra, dec=dec, mag=8.0, slope=0.0, catalog=True, name="bright star (crosstalk parent)")


def make_spec(seed=1, center=(150.0, 20.0), target=None, events="demo", n_stars=14, size=49, epochs=4, steps=2, hard=1.0,
              n_events=None, release=None):
    """Plan of a practice field. events: demo (one of each kind), random, or none."""
    rng = np.random.default_rng(seed)
    if target is not None:
        center = core.catalog_at(target, SIM_T0 + 275.0)
    used = [(0.0, 0.0)] if target is not None else []
    sources, artefacts = [], []
    if target is not None:
        sources.append(target_source(target))
    for k in range(n_stars):
        x, y = free_spot(rng, used, size, margin=4, gap=4.5)
        ra, dec = offset(center, x, y)
        sources.append(dict(id=f"s{k}", kind="star", ra=ra, dec=dec, mag=float(rng.uniform(12.0, 17.0)), slope=float(rng.uniform(-0.6, 0.4)),
                            catalog=True))
    plan = [(ep, d, k) for ep in range(epochs) for d in range(1, 7) for k in range(steps)]
    if events == "demo":
        drng = np.random.default_rng(seed + 77)
        m = random_event("moving", drng, center, used, size)
        m.update(pm_ra=1.4, pm_dec=-0.9, plx=0.08, mag=16.4, slope=1.0, catalog=False, id="e_mover")
        v = random_event("variable", drng, center, used, size)
        v.update(amp=0.28, chroma=0.6, period=420.0, phase=0.4, mag=14.6, id="e_variable")
        f = random_event("transient", drng, center, used, size)
        f.update(sub="flare", on={1}, mag=15.8, catalog=False, id="e_flare")
        g = random_event("transient", drng, center, used, size)
        g.update(sub="appear", on={2, 3}, mag=16.0, catalog=False, id="e_appear")
        sources += [m, v, f, g]
        for sub, n, det, lvl in (("glitch", 17, None, 45.0), ("hot", 30, None, 40.0), ("ghost", 0, 1, 14.0)):
            x, y = free_spot(drng, used, size)
            a = dict(kind="artefact", sub=sub, x=x, y=y, exposure=n, level=lvl, id=f"a_{sub}")
            if det:
                a["det"] = det
                sources.append(ghost_parent(center, a))
            artefacts.append(a)
        release = release if release is not None else {(1, 4): ("QR2", 0.95)}
    elif events == "random":
        n = n_events if n_events is not None else int(rng.integers(3, 8))
        for j in range(n):
            kind = str(rng.choice(["moving", "variable", "transient", "artefact"], p=[0.25, 0.25, 0.25, 0.25]))
            if kind == "artefact":
                a = random_artefact(rng, plan, used, size, hard)
                a["id"] = f"a{j}"
                artefacts.append(a)
                if a["sub"] == "ghost":
                    sources.append(ghost_parent(center, a))
            else:
                e = random_event(kind, rng, center, used, size, hard)
                e["id"] = f"e{j}"
                sources.append(e)
        if release is None and rng.random() < 0.3:
            release = {(int(rng.integers(0, epochs)), int(rng.integers(1, 7))): ("QR2", float(rng.uniform(0.93, 0.97)))}
    return dict(seed=seed, center=tuple(center), size=size, epochs=epochs, steps=steps, sources=sources, artefacts=artefacts,
                release=release or {}, target=(target or {}).get("name"))


def frames(spec, rng):
    """Pointing of every frame. A frame is one moment: arrays d and d+3 share it."""
    out = {}
    for ep in range(spec["epochs"]):
        for p in (1, 2, 3):
            for k in range(spec["steps"]):
                mjd = SIM_T0 + EPOCH_DAYS * ep + 1.0 * (p - 1) + 3.0 * k + float(rng.uniform(0, 0.05))
                out[(ep, p, k)] = dict(mjd=mjd, jitter=rng.uniform(-1.5, 1.5, 2), theta=float(rng.normal(0, 3.0) + (180.0 if ep % 2 else 0.0)))
    return out


def render(spec, noise_bias=1.25):
    """Images of a field. Returns the exposures and the truth list."""
    rng = np.random.default_rng(spec["seed"] + 1000)
    size, steps = spec["size"], spec["steps"]
    c0 = (size - 1) / 2
    center = spec["center"]
    chans = np.linspace(3, CHANNELS - 4, steps).round().astype(int) if steps > 1 else np.array([CHANNELS // 2])
    fr = frames(spec, rng)
    plan = [(ep, d, k) for ep in range(spec["epochs"]) for d in range(1, 7) for k in range(steps)]
    catalog = [s for s in spec["sources"] if s.get("catalog")]
    static_ref = [s for s in catalog if not s.get("pm_ra") and not s.get("pm_dec") and not s.get("on") and s["mag"] < 16.5]
    arts = spec["artefacts"]
    out = []
    for n, (ep, d, k) in enumerate(plan):
        lo, hi, R = BANDS[d]
        lam = lo * (hi / lo) ** ((chans[k] + 0.5 + (0.5 if ep >= 2 else 0.0) + rng.normal(0, 0.05)) / CHANNELS)
        p = (d - 1) % 3 + 1
        f = fr[(ep, p, k)]
        mjd = f["mjd"]
        true = core.make_wcs(center[0], center[1], c0 + f["jitter"][0], c0 + f["jitter"][1], f["theta"])
        er = rng.normal(0, 0.15, 2)
        told = core.make_wcs(center[0], center[1], c0 + f["jitter"][0] + er[0], c0 + f["jitter"][1] + er[1], f["theta"])
        zod, sd = core.zodi_level(lam), SIGMA_DET[d]
        rel, gain = spec["release"].get((ep, d), ("QR3", 1.0))
        img = np.full((size, size), zod)
        for s in spec["sources"]:
            fl = flux_of(s, lam, mjd, ep)
            if fl <= 0:
                continue
            ra, dec = pos_of(s, mjd)
            x, y = core.to_pix(true, ra, dec)
            if -6 < x[0] < size + 6 and -6 < y[0] < size + 6:
                img += gain * fl / UJY * core.psf_img(img.shape, x[0], y[0])
        var = sd * sd * np.clip(img, zod, None) / zod
        img = img + rng.normal(0, 1, img.shape) * np.sqrt(var)
        flags = np.zeros(img.shape, int)
        dxy = (float(200 + 120 * chans[k] + 7 * ep), float(900 + 30 * ep))
        notes = []
        for a in arts:
            if a["sub"] == "ghost":
                continue
            if a["exposure"] != n:
                continue
            ax, ay = core.to_pix(true, *offset(center, a["x"], a["y"]))
            x, y = float(ax[0]), float(ay[0])
            if a["sub"] == "glitch":
                img += a["level"] * sd * core.gauss(img.shape, x, y, 0.38)
            elif a["sub"] == "hot":
                img[int(round(y)), int(round(x))] += a["level"] * sd
            elif a["sub"] == "flagged":
                img += a["level"] * sd * core.gauss(img.shape, x, y, 0.8)
                yy, xx = np.indices(img.shape)
                flags[np.hypot(xx - x, yy - y) < 2.2] |= 1 << core.FLAG_BITS["PERSIST"]
            notes.append(f"{a['sub']} at {x:.1f},{y:.1f}")
        for a in arts:
            if a["sub"] != "ghost" or a["det"] != d:
                continue
            # The parent is a bright star GHOST_COLUMNS columns to the left on the detector. The copy lands here only when
            # the sky is not turned by 180 degrees, so it shows in some visits and not in others.
            if ep % 2 == 0:
                ax, ay = core.to_pix(true, *offset(center, a["x"], a["y"]))
                x, y = float(ax[0]) + f["jitter"][0] * 0.8, float(ay[0]) + f["jitter"][1] * 0.8
                img += a["level"] * sd * core.gauss(img.shape, x, y)
                notes.append(f"ghost at {x:.1f},{y:.1f}")
        if n % 11 == 5:
            flags[int(rng.integers(3, size - 3)), int(rng.integers(3, size - 3))] |= 1 << core.FLAG_BITS["HOT"]
        hx, hy = rng.integers(3, size - 3, 2)
        flags[hy, hx] |= 1 << core.FLAG_BITS["COLD"]
        ex, ey = core.to_pix(told, center[0], center[1])
        rx, ry = core.to_pix(told, np.array([s["ra"] for s in static_ref]), np.array([s["dec"] for s in static_ref]))
        inside = (rx > 4) & (rx < size - 5) & (ry > 4) & (ry < size - 5)
        e = Exp(f"f{spec['seed']}_e{ep}_d{d}_s{k}", mjd, float(lam), float(lam / R), d, rel, "SIMULATION", img,
                var / (noise_bias ** 2 if d >= 5 else 1.0), flags, zod, told, (float(ex[0]), float(ey[0])), np.c_[rx[inside], ry[inside]], None,
                np.arange(len(static_ref))[inside], notes=notes, dxy=dxy, frame=f"f{ep}_{p}_{k}")
        e.epoch_true = ep
        out.append(e)
    truth = truth_list(spec)
    cat = [dict(id=s.get("id", ""), ra=s["ra"], dec=s["dec"], pm_ra=s.get("pm_ra", 0.0), pm_dec=s.get("pm_dec", 0.0), plx=s.get("plx", 0.0),
                mag=s["mag"], name=s.get("name", "")) for s in catalog]
    return out, truth, cat


def truth_list(spec):
    """Every planted change with its sky position at SIM_T0. A camera effect gets the sky position where it was placed."""
    out = []
    for s in spec["sources"]:
        if s["kind"] in ("moving", "variable", "transient"):
            out.append(dict(id=s.get("id", "target"), kind=s["kind"], sub=s.get("sub") or ("mover" if s["kind"] == "moving" else "periodic"),
                            ra=s["ra"], dec=s["dec"], pm=[s.get("pm_ra", 0.0), s.get("pm_dec", 0.0)], mag=s["mag"], amp=s.get("amp"),
                            on=sorted(s["on"]) if s.get("on") is not None else None, catalog=bool(s.get("catalog")), name=s.get("name", "")))
    for a in spec["artefacts"]:
        ra, dec = offset(spec["center"], a["x"], a["y"])
        out.append(dict(id=a.get("id", a["sub"]), kind="artefact", sub=a["sub"], ra=ra, dec=dec, level=a["level"], det=a.get("det"),
                        exposure=a["exposure"]))
    return out
