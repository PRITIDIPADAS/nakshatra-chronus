"""Injection into real exposures.

Known sources (movers, variables, transients) are planted in copies of real SPHEREx exposures, with the PSF of each file
when it has one. The pipeline then runs as usual. Because the truth of the planted sources is known, completeness and
the accuracy of the engine can be measured on real noise, real backgrounds and real artefacts. Candidates that the
real field already had before planting are kept apart: their truth is not known.

Used by scripts/inject_real.py. Without an exact exposure-bound calibration record, source photon noise remains
deterministic and is explicitly labelled.
"""
import copy
import math
import hashlib
from pathlib import Path
from collections.abc import Mapping

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


def _calibrated_gain(exposure, record):
    """Check calibration provenance against the exact image bytes used by this exposure."""
    required = ("verification_status", "electrons_per_image_unit", "science_file_sha256",
                "science_observation_id", "science_source_uri", "detector", "image_unit",
                "calibration_uri", "calibration_file_path", "calibration_sha256",
                "conversion_method", "verified_by", "verified_utc")
    if not isinstance(record, Mapping):
        raise ValueError(f"{exposure.id}: calibration record must be an object")
    missing = [key for key in required if record.get(key) in (None, "")]
    if missing:
        raise ValueError(f"{exposure.id}: calibration record missing " + ", ".join(missing))
    if record["verification_status"] != "verified":
        raise ValueError(f"{exposure.id}: calibration conversion is not verified")
    if str(record["science_observation_id"]) != str(exposure.id):
        raise ValueError(f"{exposure.id}: observation identity mismatch")
    if str(record["science_file_sha256"]).lower() != str(exposure.source_sha256).lower():
        raise ValueError(f"{exposure.id}: science cutout checksum mismatch")
    if str(record["science_source_uri"]) != str(exposure.source_uri):
        raise ValueError(f"{exposure.id}: science source URI mismatch")
    if str(record["detector"]).upper().replace("D", "") != str(exposure.det):
        raise ValueError(f"{exposure.id}: detector mismatch")
    if str(record["image_unit"]).strip() != str(exposure.image_unit).strip() or not exposure.image_unit:
        raise ValueError(f"{exposure.id}: IMAGE unit mismatch or unavailable")
    if not str(record["calibration_uri"]).startswith("https://"):
        raise ValueError(f"{exposure.id}: calibration URI must be HTTPS")
    calibration_path = Path(str(record["calibration_file_path"]))
    if not calibration_path.is_file():
        raise FileNotFoundError(f"{exposure.id}: calibration bytes unavailable: {calibration_path}")
    digest = hashlib.sha256(calibration_path.read_bytes()).hexdigest()
    if digest.lower() != str(record["calibration_sha256"]).lower():
        raise ValueError(f"{exposure.id}: calibration file SHA-256 mismatch")
    gain = float(record["electrons_per_image_unit"])
    if not math.isfinite(gain) or gain <= 0:
        raise ValueError(f"{exposure.id}: electrons_per_image_unit must be finite and positive")
    return gain


def plant(exps, sources, pad=10, *, electron_calibration_records=None,
          electrons_per_image_unit=None, seed=1):
    """Plant sources in copies of exposures.

    Source shot noise is enabled only through one signed-off calibration record
    per exact exposure. Records are matched to exposure ID, detector, archive URI,
    cutout SHA-256 and IMAGE unit, and their local calibration bytes are re-hashed.
    A bare numeric gain is rejected. Without a record, the deterministic path remains.
    """
    if electrons_per_image_unit is not None:
        raise ValueError("A numeric gain alone is not accepted; use electron_calibration_records keyed by exposure ID.")
    records = electron_calibration_records or {}
    if not isinstance(records, Mapping):
        raise TypeError("electron_calibration_records must map exposure IDs to calibration records")
    rng = np.random.default_rng(seed)
    ep = P.epochs_of(exps)
    out = []
    for i, original in enumerate(exps):
        e = copy.deepcopy(original)
        h, w = e.img.shape
        if e.var.shape != e.img.shape or e.flags.shape != e.img.shape:
            raise ValueError(f"{e.id}: IMAGE, VARIANCE and FLAGS are not aligned")
        yy, xx = np.mgrid[-pad:h + pad, -pad:w + pad]
        record = records.get(str(e.id))
        gain = _calibrated_gain(e, record) if record is not None else None
        for source in sources:
            fl = sky.flux_of(source, e.lam, e.mjd, ep[i])
            if not math.isfinite(float(fl)) or fl <= 0:
                continue
            ra, dec = sky.pos_of(source, e.mjd)
            x, y = (float(v[0]) for v in core.to_pix(e.wcs, ra, dec))
            if not (-3 < x < w + 3 and not (-3 < y < h + 3)):
                continue
            kernel = np.asarray(core.kern(e.psf, xx, yy, x, y), dtype=float)
            if not np.isfinite(kernel).all() or np.any(kernel < 0):
                e.notes.append("Injection skipped: PSF kernel is non-finite or negative.")
                continue
            total = float(kernel.sum())
            if not math.isfinite(total) or total <= 0:
                e.notes.append("Injection skipped: PSF kernel has no positive integral.")
                continue
            support = kernel > kernel.max() * 1e-8
            support_y, support_x = np.where(support)
            detector_x = support_x - pad
            detector_y = support_y - pad
            if (detector_x.min() < 0 or detector_y.min() < 0 or
                detector_x.max() >= w or detector_y.max() >= h):
                e.notes.append("Injection skipped: complete PSF support would be clipped at the cutout edge.")
                continue
            source_signal = fl / core.UJY * (kernel / total)[pad:pad + h, pad:pad + w]
            footprint = source_signal > source_signal.max() * 1e-6
            invalid = (~np.isfinite(e.img) | ~np.isfinite(e.var) | (e.var <= 0) |
                       ((e.flags & e.bad) != 0))
            if np.any(footprint & invalid):
                e.notes.append("Injection skipped: PSF footprint intersects invalid variance or a bad-flagged pixel.")
                continue
            if gain is None:
                e.img = e.img + source_signal
                e.notes.append("Injection source photon noise not modelled: deterministic source signal; no verified exposure calibration record.")
            else:
                expected_electrons = source_signal * gain
                if not np.isfinite(expected_electrons).all():
                    raise ValueError(f"{e.id}: source electron expectation is non-finite")
                e.img = e.img + rng.poisson(expected_electrons) / gain
                e.var = e.var + expected_electrons / (gain * gain)
                e.notes.append("Injection source photon noise and variance were simulated from the exposure-bound calibration record.")
        out.append(e)
    return out


def verdict(c):
    p = engine.posterior(c["f"])
    if not p.get("ready"):
        return None
    return "unknown" if p["unknown"] else p["verdict"]


def trials(exps, cat, center, size, n_trials=4, per=6, seed=1, mags=(14.0, 18.5),
           electron_calibration_records=None, electrons_per_image_unit=None):
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
        S = P.run(core.prepare(plant(
            exps, src, electron_calibration_records=electron_calibration_records,
            electrons_per_image_unit=electrons_per_image_unit, seed=seed + 7919 * t
        )), cat, center=center, size=size)
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
