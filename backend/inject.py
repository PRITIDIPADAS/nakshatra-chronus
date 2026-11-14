"""Injection into real exposures.

Known sources (movers, variables, transients) are planted in copies of real SPHEREx exposures, with the PSF of each file
when it has one. The pipeline then runs as usual. Because the truth of the planted sources is known, completeness and
the accuracy of the engine can be measured on real noise, real backgrounds and real artefacts. Candidates that the
real field already had before planting are kept apart: their truth is not known.

Used by scripts/inject_real.py. Source photon noise is not added; for the faint planted sources it is small against
the background noise.
"""
import copy
import math

import numpy as np

import core
import engine
import pipeline as P
import sky

SKY_KINDS = ("moving", "variable", "transient")


def offsets(center, ra, dec):
    """Pixel offsets east and north of the center."""
    cd = math.cos(math.radians(center[1]))
    return (np.asarray(ra) - center[0]) * cd * 3600 / core.PIX, (np.asarray(dec) - center[1]) * 3600 / core.PIX


def plan_sources(rng, center, size, avoid, n, n_epochs, mags=(14.0, 18.5)):
    """n sources in turn moving, variable and transient, at free places away from the stars and the field's own candidates."""
    used = [tuple(map(float, a)) for a in avoid]
    out = []
    for k in range(n):
        kind = SKY_KINDS[k % 3]
        s = sky.random_event(kind, rng, center, used, size)
        s["id"], s["mag"] = f"inj{k}", float(rng.uniform(*mags))
        if kind == "transient":
            sub = s["sub"]
            if sub == "flare":
                s["on"] = {int(rng.integers(0, n_epochs))}
            else:
                j = int(rng.integers(1, n_epochs))
                s["on"] = set(range(j, n_epochs)) if sub == "appear" else set(range(0, j))
        out.append(s)
    return out


def plant(exps, sources, pad=10):
    """Copies of the exposures with the sources added, in the units of each file."""
    ep = P.epochs_of(exps)
    out = []
    for i, e in enumerate(exps):
        e = copy.deepcopy(e)
        h, w = e.img.shape
        yy, xx = np.mgrid[-pad:h + pad, -pad:w + pad]
        for s in sources:
            fl = sky.flux_of(s, e.lam, e.mjd, ep[i])
            if fl <= 0:
                continue
            ra, dec = sky.pos_of(s, e.mjd)
            x, y = (float(v[0]) for v in core.to_pix(e.wcs, ra, dec))
            if not (-3 < x < w + 3 and -3 < y < h + 3):
                continue
            k = core.kern(e.psf, xx, yy, x, y)
            tot = float(k.sum())
            if tot <= 0:
                continue
            e.img = e.img + fl / core.UJY * (k / tot)[pad:pad + h, pad:pad + w]
        out.append(e)
    return out


def verdict(c):
    p = engine.posterior(c["f"])
    if not p.get("ready"):
        return None
    return "unknown" if p["unknown"] else p["verdict"]


def trials(exps, cat, center, size, n_trials=4, per=6, seed=1, mags=(14.0, 18.5)):
    """Plant, run and score. Returns the scores and the labelled rows for training."""
    base = P.run(core.prepare(copy.deepcopy(exps)), cat, center=center, size=size)
    bx, by = [c["x"] for c in base["cands"]], [c["y"] for c in base["cands"]]
    avoid = []
    if cat:
        dx, dy = offsets(center, [c["ra"] for c in cat], [c["dec"] for c in cat])
        avoid += list(zip(dx, dy))
    for c in base["cands"]:
        ra, dec = core.to_sky(base["ref"], c["x"], c["y"])
        dx, dy = offsets(center, ra, dec)
        avoid.append((float(np.ravel(dx)[0]), float(np.ravel(dy)[0])))
    n_ep = max(P.epochs_of(exps)) + 1
    if n_ep < 2:
        raise ValueError("All usable exposures fall in one visit. Change needs at least two visits.")
    rows, events, extra = [], [], 0
    for t in range(n_trials):
        rng = np.random.default_rng(seed + 7919 * t)
        src = plan_sources(rng, center, size, avoid, per, n_ep, mags)
        S = P.run(core.prepare(plant(exps, src)), cat, center=center, size=size)
        truth = sky.truth_list(dict(sources=src, artefacts=[], center=center))
        _, found, missed = P.match_truth(S, truth)
        for c in S["cands"]:
            if c["truth"] in SKY_KINDS:
                rows.append(dict(f=c["f"], y=c["truth"], sub=c["truth_sub"], methods=c["methods"], trial=t, engine=verdict(c)))
            elif not any(math.hypot(c["x"] - a, c["y"] - b) < 3 for a, b in zip(bx, by)):
                extra += 1
        for x in found + missed:
            events.append(dict(kind=x["kind"], sub=x.get("sub"), mag=x.get("mag"), found=x in found, trial=t))
    return dict(base_candidates=len(base["cands"]), base_verdicts=[verdict(c) for c in base["cands"]], n_epochs=n_ep,
                exposures=len(exps), rows=rows, events=events, new_unplanted=extra, trials=n_trials, per=per)


def score(res):
    """Completeness by kind and brightness, and the accuracy of the current engine on the planted sources."""
    comp = {}
    for e in res["events"]:
        b = str(int(math.floor(e["mag"]))) if e.get("mag") is not None else "?"
        q = comp.setdefault(e["kind"], {}).setdefault(b, dict(n=0, found=0))
        q["n"] += 1
        q["found"] += int(e["found"])
    for d in comp.values():
        for q in d.values():
            q["fraction"] = q["found"] / q["n"]
            q["lo"], q["hi"] = core.wilson(q["found"], q["n"])
    rows = [r for r in res["rows"] if r["engine"] is not None]
    decided = [r for r in rows if r["engine"] != "unknown"]
    right = sum(r["engine"] == r["y"] for r in decided)
    found = sum(e["found"] for e in res["events"])
    return dict(planted=len(res["events"]), found=found, completeness=found / max(len(res["events"]), 1), by_kind=comp,
                engine_rows=len(rows), engine_unknown=len(rows) - len(decided), engine_right_when_decided=right / max(len(decided), 1),
                engine_called_artefact=sum(r["engine"] == "artefact" for r in decided),
                new_unplanted_per_trial=res["new_unplanted"] / max(res["trials"], 1))
