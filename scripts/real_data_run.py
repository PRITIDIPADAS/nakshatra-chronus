"""Real-data run of the CHRONOS 4D case studies. Needs internet (run it on GitHub Actions: workflow 'real data').
Every step records success or the exact failure; nothing is invented. Output: data/real_data_run.json"""
import io
import json
import os
import re
import sys
import time
import traceback

import numpy as np
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from astropy.io import fits, votable  # noqa: E402
from astropy.wcs import WCS  # noqa: E402

UA = {"User-Agent": "chronos_spherex"}
OUT = dict(started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), steps={})
TARGETS = dict(rwaur=(76.95625, 30.40139), rdra=(248.16758, 66.75498), nep=(270.0, 66.56))


def step(name):
    def deco(f):
        try:
            OUT["steps"][name] = dict(ok=True, result=f())
        except Exception as e:
            OUT["steps"][name] = dict(ok=False, error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-600:])
        print(name, "OK" if OUT["steps"][name]["ok"] else OUT["steps"][name]["error"], flush=True)
        return f
    return deco


def sia(coll, ra, dec, rad=0.01):
    r = requests.get("https://irsa.ipac.caltech.edu/SIA", params={"COLLECTION": coll, "POS": f"CIRCLE {ra} {dec} {rad}", "MAXREC": 5000}, headers=UA, timeout=300)
    r.raise_for_status()
    tabs = list(votable.parse(io.BytesIO(r.content), verify="ignore").iter_tables())
    if not tabs:
        return []
    t = max(tabs, key=lambda x: len(x.array)).to_table(use_names_over_ids=True)
    return [{c: (None if np.ma.is_masked(x[c]) else x[c]) for c in t.colnames} for x in t]


@step("sia_counts_by_release")
def _():
    out = {}
    for k, (ra, dec) in TARGETS.items():
        out[k] = {}
        for c in ("spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep", "spherex_dr1_cube"):
            try:
                rows = sia(c, ra, dec)
                t = sorted(float(x["t_min"]) for x in rows if x.get("t_min") is not None)
                out[k][c] = dict(n=len(rows), first_mjd=t[0] if t else None, last_mjd=t[-1] if t else None)
            except Exception as e:
                out[k][c] = dict(error=f"{type(e).__name__}: {e}"[:200])
    return out


@step("dr1_cube_spectrum")
def _():
    ra, dec = TARGETS["rwaur"]
    rows = sia("spherex_dr1_cube", ra, dec)
    if not rows:
        raise RuntimeError("no spherex_dr1_cube rows at RW Aur")
    url = str(rows[0]["access_url"])
    path = "/tmp/cube.fits"  # the cutout service answers 503 for cubes: read the whole HEALPix tile
    with requests.get(url, headers=UA, timeout=1800, stream=True) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for b in r.iter_content(1 << 22):
                f.write(b)
    h = fits.open(path, memmap=True)
    names = [x.name for x in h]
    img = np.asarray(h["IMAGE"].data, float)
    ax = [i for i, n in enumerate(img.shape) if n == 102]
    img = np.moveaxis(img, ax[0], 0) if ax else img
    w = WCS(h["IMAGE"].header, fobj=h).celestial
    x, y = (int(round(float(v))) for v in w.world_to_pixel_values(ra, dec))
    spec = img[:, y, x]
    hits = np.moveaxis(np.asarray(h["NHITS"].data, float), ax[0], 0)[:, y, x] if "NHITS" in names and ax else None
    blank = h["IMAGE"].header.get("BLANKCH") or h[0].header.get("BLANKCH")
    wave = None
    if "SPECTRAL_CHANNELS" in names:
        t = h["SPECTRAL_CHANNELS"].data
        col = next((c for c in t.columns.names if "WAV" in c.upper() or "LAM" in c.upper() or "CENT" in c.upper()), None)
        wave = np.asarray(t[col], float).ravel().tolist() if col else None
    return dict(access_url=url, hdus=names, shape=list(np.shape(h["IMAGE"].data)), pixel=[x, y], BLANKCH=str(blank),
                flux_MJy_sr=[None if not np.isfinite(v) else round(float(v), 5) for v in spec], nhits=None if hits is None else hits.tolist(),
                wavelength_um=wave, finite_channels=int(np.isfinite(spec).sum()),
                note="Zodiacal light is subtracted in the cube. NHITS counts contributing pixels; it is not an uncertainty.")


@step("splices_near_rwaur")
def _():
    tap = "https://irsa.ipac.caltech.edu/TAP/sync"
    r = requests.get(tap, params=dict(QUERY="SELECT table_name FROM TAP_SCHEMA.tables WHERE LOWER(table_name) LIKE '%splices%'", FORMAT="csv"), headers=UA, timeout=300)
    r.raise_for_status()
    names = [n.strip('"') for n in r.text.split()[1:]]
    if not names:
        raise RuntimeError("no SPLICES table in TAP_SCHEMA")
    ra, dec = TARGETS["rwaur"]
    q = f"SELECT TOP 20 * FROM {names[0]} WHERE CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra},{dec},0.25))=1"
    r = requests.get(tap, params=dict(QUERY=q, FORMAT="csv"), headers=UA, timeout=300)
    r.raise_for_status()
    lines = r.text.strip().splitlines()
    return dict(tables=names, columns=lines[0].split(",")[:30] if lines else [], n=max(0, len(lines) - 1), first_rows=lines[1:6])


@step("calibration_products_dr1_detector1")
def _():
    out = {}
    s3 = "https://nasa-irsa-spherex.s3.amazonaws.com/"  # public bucket; IRSA directory browsing answers 404 to scripts
    for rel in ("dr1", "qr3"):
        for fam in ("he_template", "aurora_template", "shuttle_glow_template", "nonfunc_v2", "spectral_wcs", "epsf", "xtalk_class1"):
            try:
                rr = requests.get(s3, params={"list-type": 2, "prefix": f"{rel}/{fam}/", "max-keys": 200}, headers=UA, timeout=120)
                rr.raise_for_status()
                keys = re.findall(r"<Key>([^<]+)</Key>", rr.text)
                out[f"{rel}/{fam}"] = dict(n=len(keys), files=[s3 + k for k in keys if "/1/" in k or "/5/" in k][:4] or [s3 + k for k in keys][:4])
            except Exception as e:
                out[f"{rel}/{fam}"] = dict(error=f"{type(e).__name__}: {e}"[:200])
    return out


@step("helium_template_stats")
def _():
    R = OUT["steps"]["calibration_products_dr1_detector1"]["result"]
    f = R.get("dr1/he_template", {}).get("files", []) + R.get("qr3/he_template", {}).get("files", [])
    f = [x for x in f if x.endswith(".fits")]
    if not f:
        raise RuntimeError("no helium template FITS listed")
    r = requests.get(f[0], headers=UA, timeout=600)
    r.raise_for_status()
    h = fits.open(io.BytesIO(r.content))
    out = dict(file=f[0], hdus=[(x.name, list(getattr(x.data, "shape", []) or [])) for x in h])
    for x in h:
        if getattr(x.data, "ndim", 0) == 2:
            a = np.asarray(x.data, float)
            v = a[np.isfinite(a)]
            out[x.name] = dict(median=float(np.median(v)), p99=float(np.percentile(v, 99)), max=float(v.max()), nonzero=float(np.mean(v != 0)))
    return out


@step("3i_atlas_spherex_coverage")
def _():
    out = []
    for day in ("2025-08-07", "2025-08-15", "2025-12-15", "2025-12-22"):
        r = requests.get("https://ssd.jpl.nasa.gov/api/horizons.api", params=dict(format="json", COMMAND="'C/2025 N1'", EPHEM_TYPE="OBSERVER", CENTER="'500@399'",
                         START_TIME=f"'{day}'", STOP_TIME=f"'{day} 01:00'", STEP_SIZE="'1h'", QUANTITIES="'1'", ANG_FORMAT="DEG", CSV_FORMAT="YES"), timeout=120)
        r.raise_for_status()
        txt = r.json().get("result", "")
        body = txt.split("$$SOE")[-1].split("$$EOE")[0].strip().splitlines()
        if "$$SOE" not in txt or not body:
            out.append(dict(date=day, error="Horizons position not parsed", head=txt[:300]))
            continue
        cells = [c.strip() for c in body[0].split(",")]
        nums = [float(c) for c in cells[1:] if re.fullmatch(r"[-+]?\d+\.\d+", c)]
        ra, dec = nums[0], nums[1]
        rows = []
        for c in ("spherex_dr1", "spherex_qr3"):
            try:
                rows += [dict(coll=c, t=float(x["t_min"]), obs=str(x.get("obs_id"))) for x in sia(c, ra, dec, 0.02) if x.get("t_min") is not None]
            except Exception:
                pass
        out.append(dict(date=day, ra=ra, dec=dec, images_within_0p02deg=len(rows), sample=rows[:5]))
    return out


OUT["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
OUT["summary"] = {k: v["ok"] for k, v in OUT["steps"].items()}
json.dump(OUT, open(os.path.join(ROOT, "data", "real_data_run.json"), "w"), indent=1, default=str)
print(json.dumps(OUT["summary"]))
