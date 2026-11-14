"""Whole sky tiles: a change map corrected for coverage, on the practice sky.

The sky is cut into 48 equal area HEALPix tiles (nside 2). Each tile gets one practice field at its center. The depth
follows the SPHEREx scan: fields near the ecliptic poles get more visits. The crowding follows the Galaxy: fields near
the galactic plane get more stars. Each tile also gets a null twin with no planted change, which measures the false
alarm rate of that tile, and an injection twin with twelve planted changes, which measures its completeness.

For each tile the map gives the raw rate (candidates that the engine calls a sky change, per square degree) and the
corrected rate: raw minus the false alarms of the null twin, divided by the completeness measured in the injection
twin. The truth of the science field is used only to score the map. On the real sky the completeness comes from injection into real exposures (scripts/inject_real.py).

Run: python scripts/make_sky_tiles.py   (about six minutes on two cores). Writes data/sky_tiles.json and docs/figures/sky_tiles.png.
"""
import json
import math
import os
import sys
import time
import warnings
from multiprocessing import Pool

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
warnings.filterwarnings("ignore")

import core  # noqa: E402
import engine  # noqa: E402
import pipeline as P  # noqa: E402
import sky  # noqa: E402

NSIDE = int(os.environ.get("NSIDE", "2"))
SKY_KINDS = ("moving", "variable", "transient")
AREA = (49 * core.PIX / 3600) ** 2  # square degrees of one practice field


def tiles(nside=NSIDE):
    """Centers and outlines of the HEALPix tiles, with ecliptic and galactic latitude."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astropy_healpix import HEALPix
    hp = HEALPix(nside=nside, order="nested")
    out = []
    for k in range(hp.npix):
        lon, lat = hp.healpix_to_lonlat([k])
        blon, blat = hp.boundaries_lonlat([k], step=4)
        c = SkyCoord(lon[0], lat[0], frame="icrs")
        out.append(dict(id=k, ra=float(lon[0].to_value(u.deg)), dec=float(lat[0].to_value(u.deg)),
                        elat=float(c.barycentricmeanecliptic.lat.deg), glat=float(c.galactic.b.deg),
                        outline=[[float(a), float(b)] for a, b in zip(blon[0].to_value(u.deg), blat[0].to_value(u.deg))]))
    return out


def plan(t):
    """Depth and crowding of a tile: more visits near the ecliptic poles, more stars near the galactic plane."""
    epochs = 6 if abs(t["elat"]) > 60 else 4
    n_stars = int(round(10 + 16 * math.exp(-abs(t["glat"]) / 15)))
    return epochs, n_stars


def called_sky(S):
    """Candidates that the engine calls a sky change, and how many of them sit on a planted sky change."""
    n = hit = 0
    for c in S["cands"]:
        p = engine.posterior(c["f"])
        if p.get("ready") and not p["unknown"] and p["verdict"] in SKY_KINDS:
            n += 1
            hit += int(c.get("truth") in SKY_KINDS)
    return n, hit


def one(t, seed0=70000):
    """Three fields per tile: the science field, a null twin for false alarms, and an injection twin for completeness.
    The correction never uses the truth of the science field; that truth is kept only to score the map."""
    epochs, n_stars = plan(t)
    out = dict(t, epochs=epochs, n_stars=n_stars)
    for kind, seed in (("field", seed0 + 3 * t["id"]), ("null", seed0 + 3 * t["id"] + 1), ("inject", seed0 + 3 * t["id"] + 2)):
        ev = dict(field="random", null="none", inject="random")[kind]
        spec = sky.make_spec(seed, center=(t["ra"], t["dec"]), events=ev, n_stars=n_stars, epochs=epochs, n_events=6 if kind == "inject" else None)
        E, truth, cat = sky.render(spec)
        core.prepare(E)
        S = P.run(E, cat, center=spec["center"])
        _, found, missed = P.match_truth(S, truth)
        planted = sum(x["kind"] in SKY_KINDS for x in found + missed)
        n, hit = called_sky(S)
        if kind == "field":
            pairs = P.fair_coadd_pairs(S)
            out.update(exposures=len(E), visits=int(S["E"]), fair_pairs=int(sum(p["fair"] for p in pairs)), pairs=len(pairs),
                       candidates=len(S["cands"]), called=n, called_true=hit, planted=planted, found=sum(x["kind"] in SKY_KINDS for x in found),
                       artefacts_planted=sum(x["kind"] == "artefact" for x in truth))
        elif kind == "null":
            out.update(null_candidates=len(S["cands"]), null_called=n)
        else:
            out.update(inject_planted=planted, inject_called_true=hit)
    out["true_rate"] = out["planted"] / AREA
    out["raw_rate"] = out["called"] / AREA
    return out


def figure(res, path, pair=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.collections import PolyCollection
    for f in ("EBGaramond-400-normal.ttf", "EBGaramond-600-normal.ttf"):
        p = os.path.join(ROOT, "scripts", "fonts", f)
        if os.path.exists(p):
            font_manager.fontManager.addfont(p)
    plt.rcParams.update({"font.family": "EB Garamond", "font.size": 13})

    def moll(outline):
        lon = [math.radians(((180 - ra + 180) % 360) - 180) for ra, dec in outline]
        lat = [math.radians(dec) for ra, dec in outline]
        body = [v for v, b in zip(lon, lat) if abs(b) < math.radians(89.9)]
        ref = body[len(body) // 2] if body else 0.0
        out = []
        for v, b in zip(lon, lat):
            if abs(b) >= math.radians(89.9):
                v = ref  # at a pole the longitude is free: keep the tile in one piece
            elif v - ref > math.pi:
                v -= 2 * math.pi
            elif ref - v > math.pi:
                v += 2 * math.pi
            out.append((max(-math.pi, min(math.pi, v)), b))
        return out

    fig, axes = plt.subplots(1, 2 if pair else 3, figsize=(12, 3.6) if pair else (16, 3.7), subplot_kw=dict(projection="mollweide"))
    fig.patch.set_facecolor("#f5f0e6")
    layers = [("visits", "Visits (depth of the scan)", "BuPu"), ("raw_rate", "Raw rate: called sky changes per square degree", "Purples"),
              ("corrected_rate", "Corrected for completeness and false alarms", "Purples")]
    if pair:
        layers = [("raw_rate", "Raw: what the survey sees", "Purples"), ("corrected_rate", "Corrected for completeness and false alarms", "Purples")]
    vmax = max(max(r["raw_rate"] for r in res), max(r["corrected_rate"] for r in res))
    for ax, (key, title, cmap) in zip(axes, layers):
        ax.set_facecolor("#fbf8f2")
        polys = [moll(r["outline"]) for r in res]
        vals = np.array([r[key] for r in res], float)
        pc = PolyCollection(polys, array=vals, cmap=cmap, edgecolor="#d8cfbf", linewidth=0.6)
        if key != "visits":
            pc.set_clim(0, vmax)
        ax.add_collection(pc)
        ax.set_title(title, fontsize=14, color="#2e2a33", pad=12)
        ax.set_xticklabels([])
        ax.tick_params(labelsize=10, colors="#5d5763")
        ax.grid(color="#d8cfbf", linewidth=0.5)
        fig.colorbar(pc, ax=ax, orientation="horizontal", fraction=0.05, pad=0.06)
    if not pair:
        fig.suptitle("Whole sky tiles on the practice sky: 48 equal area tiles, each with a science field, a null twin and an injection twin", fontsize=15, color="#2e2a33", y=1.02)
    fig.savefig(path, dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def klass(r):
    return ("deep" if r["epochs"] > 4 else "normal") + ("_crowded" if abs(r["glat"]) < 20 else "")


def correct(res):
    """Completeness and false alarms by class of tile (depth and crowding), pooled over the twins of that class,
    as a survey does with many injections. The truth of the science fields is not used."""
    cls = {}
    for r in res:
        q = cls.setdefault(klass(r), dict(tiles=0, planted=0, called_true=0, null_called=0))
        q["tiles"] += 1
        q["planted"] += r["inject_planted"]
        q["called_true"] += r["inject_called_true"]
        q["null_called"] += r["null_called"]
    for q in cls.values():
        q["completeness"] = q["called_true"] / max(q["planted"], 1)
        q["lo"], q["hi"] = core.wilson(q["called_true"], max(q["planted"], 1))
        q["false_per_field"] = q["null_called"] / q["tiles"]
    for r in res:
        q = cls[klass(r)]
        comp = max(q["completeness"], 0.2)
        r["class"], r["completeness"], r["false_expected"] = klass(r), q["completeness"], q["false_per_field"]
        r["corrected_rate"] = max(r["called"] - q["false_per_field"], 0) / comp / AREA
        r["rate_error"] = math.sqrt(r["called"] + 1) / comp / AREA
    return cls


def summary(res, cls):
    ok = [r for r in res if r["planted"]]
    within = [abs(r["corrected_rate"] - r["true_rate"]) <= 2 * r["rate_error"] for r in ok]
    tr = np.array([r["true_rate"] for r in ok])
    raw = np.array([r["raw_rate"] for r in ok])
    cor = np.array([r["corrected_rate"] for r in ok])
    deep = [r for r in res if r["epochs"] > 4]
    crowd = [r for r in res if abs(r["glat"]) < 20]
    by = {}
    for k in cls:
        g = [r for r in ok if r["class"] == k]
        t = sum(r["true_rate"] for r in g)
        by[k] = dict(cls[k], raw_over_true=sum(r["raw_rate"] for r in g) / t if t else None,
                     corrected_over_true=sum(r["corrected_rate"] for r in g) / t if t else None)
    return dict(tiles=len(res), nside=NSIDE, field_area_deg2=AREA, by_class=by,
                total_true=float(tr.sum()), total_raw=float(raw.sum()), total_corrected=float(cor.sum()),
                raw_over_true=float(raw.sum() / tr.sum()), corrected_over_true=float(cor.sum() / tr.sum()),
                median_abs_error_raw=float(np.median(np.abs(raw - tr) / tr)), median_abs_error_corrected=float(np.median(np.abs(cor - tr) / tr)),
                completeness_deep=float(np.mean([r["completeness"] for r in deep])) if deep else None,
                completeness_crowded=float(np.mean([r["completeness"] for r in crowd])) if crowd else None,
                completeness_all=float(np.mean([r["completeness"] for r in res])),
                null_called_mean=float(np.mean([r["null_called"] for r in res])),
                within_two_errors=float(np.mean(within)),
                note="Practice sky only. One small field samples each tile. The rate is per square degree of the sampled field. Completeness and false alarms are pooled by class of tile.")


def main():
    t0 = time.time()
    T = tiles()
    with Pool(max(1, os.cpu_count() or 1)) as pool:
        res = pool.map(one, T, chunksize=2)
    cls = correct(res)
    out = dict(summary=summary(res, cls), tiles=res)
    json.dump(out, open(os.path.join(ROOT, "data", "sky_tiles.json"), "w"), indent=1)
    figure(res, os.path.join(ROOT, "docs", "figures", "sky_tiles.png"))
    figure(res, os.path.join(ROOT, "docs", "figures", "sky_tiles_pair.png"), pair=True)
    print(json.dumps(out["summary"], indent=1))
    print(f"{len(res)} tiles in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    if sys.argv[1:] == ["--figure"]:  # redraw the figure from data/sky_tiles.json
        T = json.load(open(os.path.join(ROOT, "data", "sky_tiles.json")))["tiles"]
        figure(T, os.path.join(ROOT, "docs", "figures", "sky_tiles.png"))
        figure(T, os.path.join(ROOT, "docs", "figures", "sky_tiles_pair.png"), pair=True)
    else:
        main()
