"""Connectors and plugins: IRSA SIA2 and cutouts, Gaia, JPL SBIdent, plain words. Add a plugin with @plugin("name")."""
import hashlib
import io
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests
from astropy.io import fits, votable
from astropy.time import Time
from astropy.wcs import WCS

import core
from core import SIM_T0, Exp, catalog_at as at, year  # noqa: F401  (at and year are part of the public interface)

SIA = "https://irsa.ipac.caltech.edu/SIA"
# First form: IRSA page "SPHEREx Cutout Tool". Second form: IRSA tutorial for spectral image cutouts.
CUTS = ("{url}?center={ra},{dec}&size={size}", "{url}?center={ra},{dec}d&size={size}")
CUT = CUTS[0]
CACHE = os.environ.get("CHRONOS_CACHE", "cache")
PLUGINS = {}
REPORT = {}


def plugin(name):
    def deco(f):
        PLUGINS[name] = f
        return f
    return deco


def fetch(url, params=None, cache=True):
    os.makedirs(CACHE, exist_ok=True)
    key = os.path.join(CACHE, hashlib.sha1((url + repr(sorted((params or {}).items()))).encode()).hexdigest())
    if cache and os.path.exists(key):
        return open(key, "rb").read()
    r = requests.get(url, params=params, timeout=180, headers={"User-Agent": "chronos_spherex"})
    r.raise_for_status()
    with open(key + ".part", "wb") as f:
        f.write(r.content)
    os.replace(key + ".part", key)
    return r.content


SEARCH_RADIUS = 0.005  # degrees. Every SPHEREx image that holds the target touches this small circle; IRSA times out on large circles.


def search(ra, dec, rad=SEARCH_RADIUS, coll="spherex_dr1", maxrec=2000):
    raw = fetch(SIA, {"COLLECTION": coll, "POS": f"CIRCLE {ra} {dec} {rad}", "MAXREC": maxrec})
    st = re.search(rb'name="QUERY_STATUS"\s+value="(\w+)"', raw)
    if st and st.group(1) == b"ERROR":
        msg = re.search(rb'name="QUERY_STATUS"[^>]*>([^<]*)<', raw)
        raise RuntimeError("IRSA search error: " + (msg.group(1).decode(errors="replace").strip() if msg else "no message"))
    # IRSA puts a self description resource before the results: take the results table, not the first table.
    tabs = list(votable.parse(io.BytesIO(raw), verify="ignore").iter_tables())
    if not tabs:
        return []
    t = max(tabs, key=lambda x: len(x.array)).to_table(use_names_over_ids=True)  # IRSA gives every FIELD an ID like col_0
    return [{c: (None if np.ma.is_masked(r[c]) else r[c]) for c in t.colnames} for r in t]


def row_detector(row):
    """Detector number from the file name (for example 1D2_spx means detector 2) or from the band name."""
    for txt in (str(row.get("access_url") or ""), str(row.get("energy_bandpassname") or ""), str(row.get("obs_id") or "")):
        m = re.search(r"D([1-6])_spx", txt) or re.search(r"D([1-6])\b", txt)
        if m:
            return int(m.group(1))
    return 0


def cutout(url, ra, dec, size):
    err = None
    for form in CUTS:
        try:
            return fetch(form.format(url=url, ra=f"{ra:.8f}", dec=f"{dec:.8f}", size=size))
        except Exception as e:  # try the second form
            err = e
    raise err


def flag_bits(h):
    """Flag table of this file from the MP_ keywords of the FLAGS header. The default table is the fallback."""
    bits = {}
    try:
        for k, v in h["FLAGS"].header.items():
            if k.startswith("MP_") and isinstance(v, (int, np.integer)) and 0 <= int(v) < 31:
                bits[k[3:]] = int(v)
    except Exception:
        pass
    return bits or dict(core.FLAG_BITS)


def wavelength(h, hd, x, y):
    """Color and channel width at a pixel from the W lookup table of the file. Display grade. Microns."""
    w = WCS(header=hd, fobj=h, key="W")
    w.sip = None
    lam, bw = w.pixel_to_world(x, y)
    val = []
    for q in (lam, bw):
        try:
            val.append(float(q.to_value("um")))
        except Exception:
            val.append(float(getattr(q, "value", q)))
    lam, bw = val
    if lam < 0.1:  # meters
        lam, bw = lam * 1e6, bw * 1e6
    if not (0.6 < lam < 5.3 and 0 < bw < 0.5):
        raise ValueError(f"wavelength out of range: {lam}")
    return lam, bw


def pick_psf(h, hd, x, y):
    """PSF zone nearest to cutout pixel x, y. Returns the prepared PSF and a note, or None and the reason.
    QR3 files hold an EPSF table (one 33 by 33 ePSF per detector zone, with XCENTER and YCENTER); QR2 files hold a PSF cube."""
    # Detector pixel (0 based) of the cutout pixel, from the alternate WCS A of the cutout.
    xd = float(hd.get("CRVAL1A", 0.0)) + (x + 1 - float(hd.get("CRPIX1A", 1.0)))
    yd = float(hd.get("CRVAL2A", 0.0)) + (y + 1 - float(hd.get("CRPIX2A", 1.0)))
    if "EPSF" in h and hasattr(h["EPSF"], "columns"):
        try:
            t, ph = h["EPSF"].data, h["EPSF"].header
            k = int(np.argmin((np.asarray(t["XCENTER"], float) - xd) ** 2 + (np.asarray(t["YCENTER"], float) - yd) ** 2))
            plane = np.asarray(t["EPSF"][k], float)
            if not np.isfinite(plane).all() or plane.sum() <= 0:
                return None, "EPSF plane is empty. Gaussian used."
            ovs = ph.get("OVERSAMP") or ph.get("OVERSAMPLE")
            if not ovs:  # from the effective area: samples of the ePSF against NEFF_MEAN native pixels
                p = np.clip(plane, 0, None)
                ovs = max(1, int(round(math.sqrt((p.sum() ** 2 / max((p * p).sum(), 1e-30)) / max(float(t["NEFF_MEAN"][k]), 1e-3)))))
            return core.epsf(plane, int(ovs)), f"EPSF zone from the file (zone {k}, oversampling {int(ovs)})"
        except Exception as err:
            return None, f"EPSF not read ({type(err).__name__}). Gaussian used."
    try:
        cube = np.asarray(h["PSF"].data, float)
        if cube.ndim == 2:
            cube = cube[None]
        if cube.ndim == 3 and cube.shape[0] == cube.shape[1] != cube.shape[2]:
            cube = np.moveaxis(cube, 2, 0)  # the zone axis goes first
        elif cube.ndim == 3 and cube.shape[0] == cube.shape[2] != cube.shape[1]:
            cube = np.moveaxis(cube, 1, 0)
        ph = h["PSF"].header
        ovs = int(ph.get("OVERSAMP", 10 if cube.shape[1] > 60 else 5))
        zones = [(i, ph.get(f"XCTR_{i + 1}"), ph.get(f"YCTR_{i + 1}")) for i in range(cube.shape[0])]
        zones = [z for z in zones if z[1] is not None and z[2] is not None]
        if zones:
            k, note = min(zones, key=lambda z: (z[1] - xd) ** 2 + (z[2] - yd) ** 2)[0], "PSF zone from the file"
        else:
            k, note = cube.shape[0] // 2, "PSF zone keywords not found. Center zone used."
        plane = cube[k]
        if not np.isfinite(plane).all() or plane.sum() <= 0:
            return None, "PSF plane is empty. Gaussian used."
        return core.epsf(plane, ovs), note
    except Exception as err:
        return None, f"PSF not read ({type(err).__name__}). Gaussian used."


def version_tuple(v):
    return tuple(int(n) for n in re.findall(r"\d+", str(v).split("+")[0])[:3])


def load(row, ra, dec, size, coll):
    """Read one cutout into an exposure. The target must be inside the cutout."""
    h = fits.open(io.BytesIO(cutout(row["access_url"], ra, dec, size)))
    hd = h["IMAGE"].header
    img = np.asarray(h["IMAGE"].data, float)
    var = np.asarray(h["VARIANCE"].data, float)
    flags = np.asarray(h["FLAGS"].data).astype(np.int64)
    bits = flag_bits(h)
    lost = ~np.isfinite(img) | ~np.isfinite(var) | (var <= 0)
    if lost.all():
        raise ValueError("Empty cutout")
    if lost.any():
        bits.setdefault("MISSING_DATA", 9)
        flags = np.where(lost, flags | (1 << bits["MISSING_DATA"]), flags)
        img = np.where(lost, np.nanmedian(img[~lost]), img)
        var = np.where(lost, np.nanmax(var[~lost]), var)
    w = WCS(hd)
    x, y = (float(v[0]) for v in core.to_pix(w, ra, dec))
    if not (2 <= x < img.shape[1] - 2 and 2 <= y < img.shape[0] - 2):
        raise ValueError("Target outside the cutout")
    det = int(hd.get("DETECTOR", 0) or row_detector(row))
    notes, lam_ok, src = [], True, "W lookup table of the file (display grade)"
    try:
        lam, bw = wavelength(h, hd, x, y)
    except Exception as err:
        lo, hi, R = core.BANDS.get(det, (0.75, 5.0, 40))
        lam, bw, lam_ok, src = math.sqrt(lo * hi), math.sqrt(lo * hi) / R, False, "band center only"
        notes.append(f"Color at the target not read ({type(err).__name__}).")
    psf, pnote = pick_psf(h, hd, x, y)
    if psf is None or "not found" in pnote:
        notes.append(pnote)
    ver = str(hd.get("VERSION", ""))
    if coll.startswith("spherex_qr2") and ver and "psffix" not in ver and version_tuple(ver) and version_tuple(ver) < (6, 5, 6):
        notes.append("Old QR2 file. The PSF zone order can be wrong. Flux error near 5 percent.")
    if hd.get("FINAST") not in (None, 0):
        notes.append("Astrometry of this file is not fine grade.")
    zod = float(np.nanmedian(h["ZODI"].data)) if "ZODI" in h else 0.0
    dxy = (0.0, 0.0)
    try:
        wa = WCS(hd, key="A")  # alternate WCS A maps the cutout to detector pixels
        p = wa.wcs_pix2world([[0.0, 0.0]], 0)[0]
        dxy = (float(p[0]), float(p[1]))
    except Exception:
        notes.append("Detector position (WCS A) not read.")
    return Exp(str(hd.get("OBSID") or row.get("obs_id") or row["access_url"][-40:]) + (f"_D{det}" if det else ""), float(row["t_min"]), lam, bw, det,
               coll, "REAL SPHEREx", img, var, flags, zod, w, (x, y), psf=psf, bits=bits, lam_src=src, lam_ok=lam_ok, notes=notes,
               dxy=dxy, frame=f"{float(row['t_min']):.5f}")


@plugin("gaia")
def gaia_cone(ra, dec, rad=0.1, gmax=17.0):
    from astroquery.gaia import Gaia
    q = ("SELECT ra,dec,pmra,pmdec,parallax,phot_g_mean_mag FROM gaiadr3.gaia_source WHERE 1=CONTAINS("
         f"POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra},{dec},{rad})) AND phot_g_mean_mag<{gmax} AND ruwe<1.4")
    return [{c: float(r[c]) for c in ("ra", "dec", "pmra", "pmdec", "parallax", "phot_g_mean_mag")} for r in Gaia.launch_job(q).get_results()]


def wise_cone(ra, dec, rad=0.1, w2max=16.0):
    """AllWISE sources from the IRSA TAP service, for the overlay."""
    q = ("SELECT ra,dec,w1mpro,w2mpro FROM allwise_p3as_psd WHERE CONTAINS(POINT('ICRS',ra,dec),"
         f"CIRCLE('ICRS',{ra},{dec},{rad}))=1 AND w2mpro<{w2max}")
    r = fetch("https://irsa.ipac.caltech.edu/TAP/sync", dict(QUERY=q, FORMAT="csv"))
    lines = r.decode().strip().splitlines()
    head = lines[0].split(",")
    out = []
    for ln in lines[1:]:
        v = dict(zip(head, ln.split(",")))
        try:
            out.append(dict(ra=float(v["ra"]), dec=float(v["dec"]), w1=float(v["w1mpro"] or "nan"), w2=float(v["w2mpro"] or "nan")))
        except (KeyError, ValueError):
            continue
    return out


def gaia_catalog(g, t0=SIM_T0):
    """Gaia rows as CHRONOS catalog entries: position at SIM_T0, motion in arcseconds per year."""
    dy = float(year(t0)) - 2016.0
    out = []
    for s in g:
        cd = math.cos(math.radians(s["dec"]))
        out.append(dict(ra=s["ra"] + s["pmra"] / 3.6e6 / cd * dy, dec=s["dec"] + s["pmdec"] / 3.6e6 * dy, pm_ra=s["pmra"] / 1000, pm_dec=s["pmdec"] / 1000,
                        plx=(s.get("parallax") or 0) / 1000, mag=s["phot_g_mean_mag"], source="Gaia DR3", name=f"Gaia G {s['phot_g_mean_mag']:.1f}"))
    return out


def choose(rows, n, det):
    """Pick exposures. One detector: all of it, because fair pairs live inside one detector. All detectors: spread in time."""
    if det:
        rows = [r for r in rows if r["_det"] == det]
        return rows[::max(1, math.ceil(len(rows) / n))][:n]
    out = []
    for d in sorted({r["_det"] for r in rows}):
        g = [r for r in rows if r["_det"] == d]
        k = max(1, n // 6)
        out += g[::max(1, math.ceil(len(g) / k))][:k]
    return sorted(out, key=lambda r: float(r["t_min"]))


def live_exposures(t, coll="spherex_dr1", n=48, size=0.08, det=0):
    """Real SPHEREx exposures of a target. The cutout follows the target with its catalog motion."""
    ra_m, dec_m = at(t, SIM_T0)
    rows, errs, seen = [], [], set()
    for c in coll.split("+"):
        try:
            for r in search(ra_m, dec_m, SEARCH_RADIUS, c):
                if r.get("access_url") and r.get("t_min") is not None and r["access_url"] not in seen:
                    seen.add(r["access_url"])
                    rows.append(dict(r, _c=c, _det=row_detector(r)))
        except Exception as err:
            errs.append(f"{c}: {type(err).__name__}: {err}")
    REPORT.clear()
    REPORT.update(found=len(rows), search_errors=errs, by_detector={d: sum(r["_det"] == d for r in rows) for d in range(7)}, failed={})
    if not rows and errs:
        raise RuntimeError("The archive did not answer. " + "; ".join(errs))
    rows.sort(key=lambda r: float(r["t_min"]))
    rows = choose(rows, n, det)
    try:
        g = [s for s in gaia_cone(ra_m, dec_m) if math.isfinite(s["pmra"]) and math.isfinite(s["pmdec"])]
    except Exception as err:
        g = []
        REPORT["gaia_error"] = f"{type(err).__name__}: {err}"
    REPORT["gaia"] = g

    def warm(r):
        try:
            ra, dec = at(t, float(r["t_min"]))
            cutout(r["access_url"], ra, dec, size)
        except Exception:
            pass

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(warm, rows))
    out = []
    for r in rows:
        mjd = float(r["t_min"])
        ra, dec = at(t, mjd)
        try:
            e = load(r, ra, dec, size, r["_c"])
        except Exception as err:
            k = f"{type(err).__name__}: {err}"[:120]
            REPORT["failed"][k] = REPORT["failed"].get(k, 0) + 1
            continue
        if g:
            dy = float(year(mjd)) - 2016.0
            sra = np.array([s["ra"] + s["pmra"] / 3.6e6 / math.cos(math.radians(s["dec"])) * dy for s in g])
            sdec = np.array([s["dec"] + s["pmdec"] / 3.6e6 * dy for s in g])
            px, py = core.to_pix(e.wcs, sra, sdec)
            h, w = e.img.shape
            ok = (px > 5) & (px < w - 5) & (py > 5) & (py < h - 5) & (np.hypot(px - e.xy[0], py - e.xy[1]) > 5)
            e.ref, e.rid = np.c_[px[ok], py[ok]][:14], np.where(ok)[0][:14]
        out.append(e)
    REPORT["loaded"] = len(out)
    return out


def doctor(t, coll="spherex_dr1+spherex_qr3"):
    """Live check. Tests each step of the real data path and says in plain words what works."""
    steps, row = [], None
    ra, dec = at(t, SIM_T0)
    for c in coll.split("+"):
        try:
            rows = [r for r in search(ra, dec, SEARCH_RADIUS, c) if r.get("access_url")]
            steps.append(dict(step=f"Search {c}", ok=bool(rows), detail=f"{len(rows)} exposures. Columns: {', '.join(sorted(rows[0])[:12]) if rows else 'none'}"))
            row = row or (dict(rows[0], _c=c) if rows else None)
        except Exception as err:
            steps.append(dict(step=f"Search {c}", ok=False, detail=f"{type(err).__name__}. The archive did not answer. Check the internet connection."))
    if row is None:
        return steps
    try:
        ra, dec = at(t, float(row["t_min"]))
        h = fits.open(io.BytesIO(cutout(row["access_url"], ra, dec, 0.08)))
        names = [(x.name, getattr(x.data, "shape", None)) for x in h]
        need = {"IMAGE", "FLAGS", "VARIANCE"}
        steps.append(dict(step="Cutout", ok=need <= {n for n, _ in names}, detail=str(names)))
        hd = h["IMAGE"].header
        steps.append(dict(step="Keywords", ok=hd.get("DETECTOR") is not None, detail=str({k: hd.get(k) for k in ("DETECTOR", "OBSID", "BUNIT", "VERSION", "FINAST", "CRPIX1A", "CRPIX2A")})))
        x, y = (float(v[0]) for v in core.to_pix(WCS(hd), ra, dec))
        steps.append(dict(step="Target in cutout", ok=0 <= x < hd["NAXIS1"] and 0 <= y < hd["NAXIS2"], detail=f"pixel {x:.1f}, {y:.1f}"))
        try:
            lam, bw = wavelength(h, hd, x, y)
            steps.append(dict(step="Color at the target", ok=True, detail=f"{lam:.4f} micron, width {bw:.4f}"))
        except Exception as err:
            steps.append(dict(step="Color at the target", ok=False, detail=f"{type(err).__name__}: {err}"))
        psf, note = pick_psf(h, hd, x, y)
        steps.append(dict(step="PSF", ok=psf is not None, detail=f"{note} Shape {getattr(h['PSF'].data, 'shape', None) if 'PSF' in h else None}"))
        b = flag_bits(h)
        steps.append(dict(step="Flag table", ok=any(k.startswith("MP_") for k in h["FLAGS"].header), detail=str(b)))
    except Exception as err:
        steps.append(dict(step="Cutout", ok=False, detail=f"{type(err).__name__}: {err}"))
    try:
        steps.append(dict(step="Gaia", ok=True, detail=f"{len(gaia_cone(ra, dec))} reference stars"))
    except Exception as err:
        steps.append(dict(step="Gaia", ok=False, detail=f"{type(err).__name__}: {err}"))
    return steps


@plugin("known_movers")
def known_movers(ra, dec, mjd, hw=0.05):
    """Known asteroids and comets near a position from the JPL SBIdent API."""
    def hms(v):
        h = v / 15.0
        return f"{int(h):02d}-{int(h % 1 * 60):02d}-{h * 3600 % 60:05.2f}"

    def dms(v):
        a = abs(v)
        return ("M" if v < 0 else "") + f"{int(a):02d}-{int(a % 1 * 60):02d}-{a * 3600 % 60:05.2f}"

    p = {"sb-kind": "a", "lat": 0, "lon": 0, "alt": 0, "obs-time": Time(mjd, format="mjd").iso[:19].replace(" ", "_"), "two-pass": "true",
         "fov-ra-center": hms(ra), "fov-dec-center": dms(dec), "fov-ra-hwidth": hw, "fov-dec-hwidth": hw, "vmag-lim": 22}
    j = requests.get("https://ssd-api.jpl.nasa.gov/sb_ident.api", params=p, timeout=60).json()
    return dict(fields=j.get("fields"), data=j.get("n_second_pass") and j.get("data_second_pass") or j.get("data_first_pass") or j.get("data"), message=j.get("message"),
                note="Observer on the ground. The telescope is in Earth orbit, so a main belt object can be off by about one pixel.")


VERD = {"Motion model preferred": ("it moves", "এটি সরছে"), "Fixed position preferred": ("it stays in place", "এটি এক জায়গায় আছে"),
        "Inconclusive": ("the data cannot decide", "তথ্য থেকে সিদ্ধান্ত নেওয়া যায় না")}
LABEL = {"SIMULATION": ("a practice sky (simulation)", "অনুশীলনের আকাশ (সিমুলেশন)"), "REAL SPHEREx": ("real SPHEREx data", "SPHEREx এর আসল তথ্য")}
BEHAVE = {"Motion candidate": "গতিশীল বস্তুর প্রার্থী", "Variable source candidate": "পরিবর্তনশীল উৎসের প্রার্থী", "Moving and variable candidate": "গতিশীল ও পরিবর্তনশীল প্রার্থী",
          "Approximately stable source": "মোটামুটি স্থির উৎস", "Inconclusive": "সিদ্ধান্ত নেওয়া যায় না"}


def template(card, lang):
    """Plain words made only from numbers that the tool computed."""
    bn = lang == "bn"
    p, m, b = card.get("pair") or {}, (card.get("motion") or {}).get("fit") or {}, card.get("behavior") or {}
    fc = p.get("false_change") or {}
    way = lambda x: (("ম্লান" if x < 0 else "উজ্জ্বল") if bn else ("fainter" if x < 0 else "brighter"))
    out = []
    lab = LABEL.get(card.get("label"), (str(card.get("label", "?")),) * 2)[bn]
    out.append(f"তথ্যের ধরন: {lab}।" if bn else f"Data: {lab}.")
    if p:
        if p.get("fair"):
            out.append(f"ছবি দুটি একই রঙে তোলা, তাই তুলনাটি ন্যায্য (স্কোর ১০০ এর মধ্যে {p.get('score')})।" if bn else
                       f"The two pictures show the same color, so the comparison is fair (score {p.get('score')} of 100).")
        else:
            out.append(f"এই দুটি ছবির তুলনা ন্যায্য নয় (স্কোর ১০০ এর মধ্যে {p.get('score')})।" if bn else
                       f"The comparison of these two pictures is not fair (score {p.get('score')} of 100).")
        if fc.get("predicted") is not None:
            pr = 100 * fc["predicted"]
            out.append(f"শুধু রঙের পার্থক্যের কারণেই তারাটি {abs(pr):.1f} শতাংশ বেশি {way(pr)} দেখায়।" if bn else
                       f"The color difference alone makes the star look {abs(pr):.1f} percent {way(pr)}.")
            if fc.get("measured") is not None:
                ms, real = 100 * fc["measured"], abs(fc.get("excess_sigma", 0)) > 3
                out.append((f"ছবিতে দেখা যায় {abs(ms):.1f} শতাংশ বেশি {way(ms)}। " + ("রঙের প্রভাব বাদ দিলেও একটি আসল পরিবর্তন থাকে।" if real else "রঙের প্রভাব বাদ দিলে আসল পরিবর্তনের প্রমাণ নেই।")) if bn else
                           (f"The pictures show it {abs(ms):.1f} percent {way(ms)}. " + ("A real change remains after the color effect is removed." if real else
                                                                                      "No real change remains after the color effect is removed.")))
    if m.get("verdict"):
        v = VERD.get(m["verdict"], (m["verdict"],) * 2)[bn]
        if m.get("pm") is not None and m.get("err") is not None:
            out.append(f"অবস্থান মেপে দেখা গেল: {v}। গতি বছরে {m['pm']:.2f} ± {m['err']:.2f} আর্কসেকেন্ড, {m.get('frames', 0)}টি ছবি থেকে।" if bn else
                       f"The position measurements say: {v}. The motion is {m['pm']:.2f} plus or minus {m['err']:.2f} arcseconds per year, from {m.get('frames', 0)} pictures.")
        else:
            out.append(f"অবস্থান মেপে দেখা গেল: {v}।" if bn else f"The position measurements say: {v}.")
        mo = card.get("motion") or {}
        if mo.get("pull") is not None and (mo.get("expected_arcsec_per_year") or 0) > 0.05:
            out.append(f"ক্যাটালগের মানের সাথে পার্থক্য ত্রুটিসীমার {abs(mo['pull']):.1f} গুণ।" if bn else
                       f"The difference from the catalog value is {abs(mo['pull']):.1f} times the error.")
    v = b.get("variability") or {}
    if b.get("varying") and v.get("mean_ratio"):
        ch = 100 * (v["mean_ratio"] - 1)
        out.append((f"পরের পর্যবেক্ষণে তারাটি গড়ে {abs(ch):.0f} শতাংশ বেশি {way(ch)}।" + (" পরিবর্তনটি রঙের উপর নির্ভর করে।" if b.get("color_dependent") else "")) if bn else
                   (f"In the later visit the star is {abs(ch):.0f} percent {way(ch)} on average." + (" The change depends on color." if b.get("color_dependent") else "")))
    if b.get("label"):
        out.append(f"সারসংক্ষেপ: {BEHAVE.get(b['label'], b['label'])}। এটি প্রার্থী মাত্র, আবিষ্কার নয়।" if bn else
                   f"Summary: {b['label'].lower()}. This is a candidate label and not a discovery.")
    return " ".join(out)


@plugin("explain")
def explain(card, lang="en"):
    """Plain words made only from the computed numbers."""
    return dict(text=template(card, lang), source="template")


ALERCE_TAP = "https://tap.alerce.online/tap/sync"


def table_rows(raw):
    """Rows of a TAP answer in CSV or VOTable form."""
    txt = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    if txt.lstrip().startswith("<"):
        t = votable.parse_single_table(io.BytesIO(txt.encode())).to_table()
        return [{c: (None if np.ma.is_masked(r[c]) else r[c]) for c in t.colnames} for r in t]
    import csv
    return list(csv.DictReader(io.StringIO(txt)))


@plugin("rubin")
def rubin_cone(ra, dec, rad_arcsec=12.0, limit=50):
    """Rubin LSST alert objects (DIA objects) near a position, from the ALeRCE broker TAP service."""
    q = ("SELECT TOP {n} oid, ra, dec, ndiasources, firstdiasourcemjdtai, lastdiasourcemjdtai, r_psffluxmean, i_psffluxmean "
         "FROM alerce_tap.lsst_dia_object WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {r}))").format(
        n=int(limit), ra=float(ra), dec=float(dec), r=float(rad_arcsec) / 3600)
    raw = fetch(ALERCE_TAP, dict(REQUEST="doQuery", LANG="ADQL", RESPONSEFORMAT="csv", QUERY=q), cache=False)  # alerts change every night
    out = []
    for r in table_rows(raw):
        try:
            a, d = float(r["ra"]), float(r["dec"])
        except (KeyError, TypeError, ValueError):
            continue
        sep = 3600 * math.degrees(math.acos(min(1.0, math.sin(math.radians(dec)) * math.sin(math.radians(d)) +
                                                math.cos(math.radians(dec)) * math.cos(math.radians(d)) * math.cos(math.radians(ra - a)))))

        def num(k):
            try:
                v = float(r.get(k))
                return v if math.isfinite(v) else None
            except (TypeError, ValueError):
                return None
        out.append(dict(oid=str(r.get("oid")), ra=a, dec=d, sep_arcsec=sep, n=num("ndiasources"), first_mjd=num("firstdiasourcemjdtai"),
                        last_mjd=num("lastdiasourcemjdtai"), r_flux_njy=num("r_psffluxmean"), i_flux_njy=num("i_psffluxmean")))
    return sorted(out, key=lambda x: x["sep_arcsec"])


def crossmatch(ra, dec, mjd, rad_arcsec=12.0):
    """Other surveys at the place of a candidate: Rubin alerts (ALeRCE) and known small bodies (JPL). Each part can fail alone."""
    res = dict(ra=ra, dec=dec, radius_arcsec=rad_arcsec, rubin=None, known_bodies=None, errors={},
               neo_surveyor="NEO Surveyor has not launched (NASA plans no earlier than September 2027). When its detections are public, they join here.")
    try:
        res["rubin"] = rubin_cone(ra, dec, rad_arcsec)
    except Exception as err:
        res["errors"]["rubin"] = f"{type(err).__name__}: {str(err)[:120]}"
    try:
        kb = known_movers(ra, dec, mjd, hw=max(rad_arcsec / 3600, 0.01))
        res["known_bodies"] = dict(n=len(kb.get("data") or []), fields=kb.get("fields"), data=(kb.get("data") or [])[:10], note=kb.get("note"))
    except Exception as err:
        res["errors"]["known_bodies"] = f"{type(err).__name__}: {str(err)[:120]}"
    n_r = len(res["rubin"] or [])
    res["summary"] = (f"{n_r} Rubin alert object{'s' if n_r != 1 else ''} within {rad_arcsec:.0f} arcsec. " if res["rubin"] is not None else "Rubin check failed. ") + \
        (f"{res['known_bodies']['n']} known small bod{'ies' if res['known_bodies']['n'] != 1 else 'y'} nearby." if res["known_bodies"] else "Known body check failed.") + \
        " A match is a lead to check, not a confirmation: the surveys see different colors at different times."
    return res


def publish_hf(package, repo, token=None, private=False):
    """Put a sealed investigation package in a Hugging Face dataset repository, so that anyone can download and rerun it."""
    from huggingface_hub import HfApi
    token = token or os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("Set HF_TOKEN on the server to publish to Hugging Face.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or ""):
        raise ValueError("The repository name must look like owner/name.")
    seal = str((package.get("record") or {}).get("seal") or "")
    if not re.fullmatch(r"[0-9a-f]{12,64}", seal):
        raise ValueError("The package has no seal.")
    api = HfApi(token=token)
    api.create_repo(repo, repo_type="dataset", private=private, exist_ok=True)
    path = f"records/{seal[:16]}.json"
    api.upload_file(path_or_fileobj=json.dumps(package, default=str).encode(), path_in_repo=path, repo_id=repo, repo_type="dataset",
                    commit_message=f"CHRONOS sealed record {seal[:16]}")
    return dict(ok=True, repo=repo, path=path, url=f"https://huggingface.co/datasets/{repo}/blob/main/{path}")
