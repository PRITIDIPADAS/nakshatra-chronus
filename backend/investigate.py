"""CHRONOS investigator.

For one field it runs the pipeline, then for every candidate it asks five questions: what changed, where, is it real,
what is it, and what would prove the answer wrong. Every sentence of the report points to a measurement.
The investigator coordinates measurement tools. It does not invent results: when a test cannot run, it says so.
"""
import base64
import hashlib
import json
import math
import os
import platform

import numpy as np
from scipy.ndimage import map_coordinates

import core
import engine
import pipeline as P
from core import PIX, UJY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HYP = ("moving", "variable", "transient", "artefact", "null")
SKY = ("moving", "variable", "transient")
VARIANTS = [("baseline", "Baseline", {}), ("keep_flags", "Flagged pixels kept", {"keep_flags": True}),
            ("local_bg", "Local background instead of one sky level", {"local_bg": True}),
            ("worst_noise", "Noise at the worst measured level", None), ("shift", "Star anchors moved by their error", {"shift_error": True, "seed": 3}),
            ("psf_wide", "PSF 15 percent wider", {"psf_scale": 1.15})]


# ---------------------------------------------------------------- encoding

def stretch_range(arrs):
    """One display range for a family of images, so that a blink never shows a change made by the display."""
    v = np.concatenate([np.ravel(a[np.isfinite(a)] - np.nanmedian(a)) for a in arrs if np.isfinite(a).any()])
    return (float(np.percentile(v, 2)), float(np.percentile(v, 99.9))) if v.size else (0.0, 1.0)


def enc(a, lo=None, hi=None, stretch=False):
    """Image as bytes for the page: 0 means no data, 1 to 255 the value from lo to hi. stretch may be a shared (lo, hi) range."""
    a = np.asarray(a, float)
    fin = np.isfinite(a)
    if stretch is not False:
        b = a - np.nanmedian(a[fin]) if fin.any() else a
        l2, h2 = stretch if isinstance(stretch, tuple) else stretch_range([a])
        q = np.arcsinh(25 * np.clip((b - l2) / max(h2 - l2, 1e-12), 0, 1)) / np.arcsinh(25)
    else:
        lo = float(np.nanmin(a[fin])) if lo is None and fin.any() else (lo or 0.0)
        hi = float(np.nanmax(a[fin])) if hi is None and fin.any() else (hi or 1.0)
        q = np.clip((a - lo) / max(hi - lo, 1e-12), 0, 1)
    u = np.where(fin, 1 + np.round(q * 254), 0).astype(np.uint8)
    return dict(w=int(a.shape[1]), h=int(a.shape[0]), lo=lo, hi=hi, b64=base64.b64encode(u.tobytes()).decode())


def r(v, k=3):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return v
    return round(v, k) if math.isfinite(v) else None


# ---------------------------------------------------------------- variants for the counterfactual test

def variant_state(base, exps, catalog, opt):
    S = P.build(exps, base["ref"], base["n"], catalog, opt)
    P.phot_floor(S)
    P.detect_catalog(S)
    P.detect_difference(S)
    return S


def statistic(S, c, kind):
    """The number that carries the main claim of the candidate on one state."""
    m = P.measure(S, c)
    if kind == "moving":
        return m["motion"]["sig"] if m["motion"]["n"] >= 3 else 0.0, "motion significance"
    if kind == "variable":
        return m["var_z"], "brightness change z"
    if kind == "transient":
        return m["presence"], "visit contrast"
    return max(m["dval"], m["presence"], min(m["var_z"], 50.0)), "change significance"


# ---------------------------------------------------------------- per candidate reasoning

def drift(S):
    """Visit by visit shift of the catalog stars against their mean position. The registration error, in pixels."""
    rows = {q: [] for q in S["W"]}
    for g in S["groups"]:
        if len(g) == len(S["W"]) and min(d["snr"] for d in g) > 15 and S["stars"]:
            gx, gy = np.mean([d["x"] for d in g]), np.mean([d["y"] for d in g])
            if min(math.hypot(gx - x, gy - y) for x, y in S["stars"]) < 1.5:
                for d in g:
                    rows[d["q"]].append((d["x"] - gx, d["y"] - gy))
    out = {}
    for q, v in rows.items():
        if v:
            a = np.array(v)
            out[q] = (float(np.median(a[:, 0])), float(np.median(a[:, 1])), len(v))
    return out


def catalog_match(S, x, y, catalog):
    best = None
    mjd = float(np.mean(S["mjd_ep"]))
    for s in catalog or []:
        dy = (mjd - core.SIM_T0) / 365.25
        cd = math.cos(math.radians(s["dec"]))
        ra, dec = s["ra"] + s.get("pm_ra", 0.0) * dy / 3600 / cd, s["dec"] + s.get("pm_dec", 0.0) * dy / 3600
        px, py = core.to_pix(S["ref"], ra, dec)
        rr = math.hypot(px[0] - x, py[0] - y)
        if rr < 3.0 and (best is None or rr < best[0]):
            best = (rr, s)
    return best


def det_xy(S, i, x, y):
    """Detector pixel of reference grid point x, y in exposure i."""
    x2, y2 = S["MAP"][i]
    ex = float(map_coordinates(x2, [[y], [x]], order=1)[0])
    ey = float(map_coordinates(y2, [[y], [x]], order=1)[0])
    e = S["exps"][i]
    return ex + e.dxy[0], ey + e.dxy[1], ex, ey


def seen_in(S, x, y, level=3.0):
    """Exposures where the residual at x, y passes the level. Sign of the strongest one decides the direction."""
    xi, yi = int(round(x)), int(round(y))
    w = (slice(max(0, yi - 1), yi + 2), slice(max(0, xi - 1), xi + 2))
    vals = []
    for i in range(len(S["exps"])):
        a = S["Ecube"][i][w]
        if np.isfinite(a).any():
            v = float(a[np.unravel_index(np.nanargmax(np.abs(np.nan_to_num(a))), a.shape)])
            vals.append((i, v))
    if not vals:
        return [], 0.0
    sgn = math.copysign(1, max(vals, key=lambda t: abs(t[1]))[1])
    return [i for i, v in vals if sgn * v > level], sgn


def challenges(S, c, m, top, catalog, cands):
    """The self questioning machine. Tests that try to break the leading explanation. None of them feeds the engine."""
    x, y = c["x"], c["y"]
    mo, f, fx = m["motion"], c["f"], c["fx"]
    out = []

    def add(q, method, result, outcome, **nums):
        out.append(dict(id=f"Q{len(out) + 1}", question=q, method=method, result=result, outcome=outcome, numbers={k: r(v) for k, v in nums.items()}))

    seen, sgn = seen_in(S, x, y)
    arrays = sorted({S["exps"][i].det for i in seen})
    if top == "moving":
        dr = drift(S)
        if mo["n"] >= 2 and dr:
            q0, q1 = mo["q"][0], mo["q"][-1]
            dd = math.hypot(dr.get(q1, (0, 0, 0))[0] - dr.get(q0, (0, 0, 0))[0], dr.get(q1, (0, 0, 0))[1] - dr.get(q0, (0, 0, 0))[1])
            shift = math.hypot(mo["x"][-1] - mo["x"][0], mo["y"][-1] - mo["y"][0])
            ok = shift > 5 * max(dd, S["floor"])
            add("What if the shift comes from a bad alignment of the images?", "Catalog stars measured in the same visits.",
                f"The source moved {shift:.3f} pixels. The stars moved {dd:.3f} pixels between the same visits.", "supports" if ok else "challenges",
                source_shift_px=shift, star_shift_px=dd, floor_px=S["floor"])
        else:
            add("What if the shift comes from a bad alignment of the images?", "Catalog stars measured in the same visits.",
                "Not enough catalog stars or visits to test.", "not run")
        if mo["n"] >= 4:
            sig, ang = [], []
            for k in range(mo["n"]):
                sub = [dict(q=mo["q"][j], x=mo["x"][j], y=mo["y"][j], ex=mo["ex"][j], ey=mo["ey"][j]) for j in range(mo["n"]) if j != k]
                mk = P.motion(sub, S["mjd_ep"], 0.0)
                sig.append(mk["sig"])
                ang.append(math.degrees(math.atan2(mk["pm_y"], mk["pm_x"])))
            a0 = math.degrees(math.atan2(mo["pm_y"], mo["pm_x"]))
            spread = max(abs((a - a0 + 180) % 360 - 180) for a in ang)
            ok = min(sig) > 2 and spread < 45
            add("What if the source does not move at all?", "Leave one visit out and fit again, once for each visit.",
                f"The weakest fit still gives {min(sig):.1f} sigma. The direction changes by at most {spread:.0f} degrees.", "supports" if ok else "challenges",
                weakest_sigma=min(sig), direction_spread_deg=spread, delta_bic=mo["dbic"])
        else:
            add("What if the source does not move at all?", "Leave one visit out.", f"Only {mo['n']} visits measured. At least four are needed.", "not run")
        good = []
        for d in S["dets"]:
            k = sum(1 for (q, dd), (fl, er) in m["fluxes"].items() if dd == d and math.isfinite(fl) and fl > 5 * er)
            if k >= 2:
                good.append(d)
        add("What if it is a detector artefact?", "Count the arrays that see the source in two or more visits.",
            f"Seen in {len(good)} of {len(S['dets'])} arrays.", "supports" if len(good) >= 3 else "challenges" if len(good) <= 1 else "neutral", arrays=len(good))
        cm = catalog_match(S, x, y, catalog)
        if cm and (cm[1].get("pm_ra") or cm[1].get("pm_dec")):
            pm_cat = math.hypot(cm[1]["pm_ra"], cm[1]["pm_dec"]) / PIX
            pull = (mo["pm"] - pm_cat) / max(mo["err"], 1e-6)
            add("What if it is a known moving object?", "Catalog position and motion, carried to the mean visit time.",
                f"Catalog object {cm[1].get('name') or cm[1].get('id') or ''} sits {cm[0]:.2f} pixels away with {pm_cat:.3f} pixels per year. "
                f"The measured motion differs by {abs(pull):.1f} times its error.", "supports" if abs(pull) < 3 else "challenges",
                separation_px=cm[0], catalog_pm_px_yr=pm_cat, pull=pull)
        elif cm:
            add("What if it is a known object?", "Catalog cross match.", "A catalog object with no motion sits here. A known star should not move.", "challenges",
                separation_px=cm[0])
        else:
            add("What if it is a known moving object?", "Catalog cross match. Live mode also asks the JPL small body service.",
                "No catalog object explains this position. The motion is not explained by the catalog.", "neutral")
        near = [o for o in cands if o is not c and math.hypot(o["x"] - x, o["y"] - y) < 3.0]
        add("What if a neighbor blends with it and fakes the shift?", "Distance to the nearest other candidate.",
            "No other candidate within 3 pixels." if not near else f"{len(near)} other candidates within 3 pixels.", "supports" if not near else "challenges",
            neighbors=len(near))
    elif top == "variable":
        fl = S["pfloor"]
        floor = max(fl.values()) if fl else 0.02
        add("What if the change is a calibration drift?", "Brightness scatter of the catalog stars on the same arrays.",
            f"Change {100 * m['amp']:.1f} percent. Star scatter up to {100 * floor:.1f} percent.", "supports" if m["amp"] > 5 * floor else "challenges",
            change=m["amp"], star_scatter=floor)
        add("What if the colors of the compared visits differ?", "Was the change seen in a fair pair (same array, matched colors)?",
            "Yes. The difference method saw it in a fair pair." if "D" in c["methods"] else "No. The change crosses visits without a fair color match.",
            "supports" if "D" in c["methods"] else "neutral")
        same = 0
        for d in S["dets"]:
            v = sorted(((q, fl2, er) for (q, dd), (fl2, er) in m["fluxes"].items() if dd == d and math.isfinite(fl2)), key=lambda t: t[0])
            if len(v) >= 2 and any(abs(a[1] - b[1]) > 3 * math.hypot(a[2], b[2]) for a in v for b in v):
                same += 1
        add("What if only one array sees it?", "Count arrays with a change above 3 sigma.", f"{same} arrays.", "supports" if same >= 2 else "challenges", arrays=same)
        near = [o for o in cands if o is not c and math.hypot(o["x"] - x, o["y"] - y) < 3.0]
        add("What if a moving neighbor passes over it?", "Other candidates within 3 pixels.", f"{len(near)} found.", "supports" if not near else "challenges",
            neighbors=len(near))
        rel = sorted({S["exps"][i].rel for i in range(len(S["exps"]))})
        add("What if a new data release changed the calibration?", "Release of every exposure.",
            "All exposures share one release." if len(rel) == 1 else f"Releases {', '.join(rel)}. The star ensemble corrected the gain before this test.",
            "supports" if len(rel) == 1 else "neutral", releases=len(rel))
    elif top == "transient":
        on_visit = [q for q, v in m["visit_snr"].items() if math.isfinite(v) and v >= P.TH["on_snr"]]
        se = m.get("snr_exp", np.full(len(S["exps"]), np.nan))
        inside = [i for i in range(len(S["exps"])) if S["ep"][i] in on_visit and np.isfinite(se[i]) and se[i] > P.TH["detect"]]
        add("What if it is a single cosmic ray?", "Count exposures inside the bright visits that show it.",
            f"{len(inside)} exposures.", "supports" if len(inside) >= 2 else "challenges", exposures=len(inside))
        sh = fx.get("sharp")
        add("Does it have the shape of a star?", "Gaussian fit with a free width, divided by the PSF width.",
            "No fit." if sh is None or not math.isfinite(sh) else f"Width ratio {sh:.2f}. A star gives about 1.", "not run" if sh is None or not math.isfinite(sh)
            else "supports" if 0.75 <= sh <= 1.4 else "challenges", width_ratio=sh)
        add("Does the other array see it at the same moment?", "The two arrays behind the dichroic look at the same place at the same time.",
            "Yes." if f["partner"] == 1 else "No." if f["partner"] == 0 else "No partner exposure.",
            "supports" if f["partner"] == 1 else "challenges" if f["partner"] == 0 else "not run")
        add("Is it on flagged pixels?", "Flag table of every exposure.", f"Flagged in {100 * f['flagfrac']:.0f} percent of exposures.",
            "supports" if f["flagfrac"] < 0.1 else "challenges", flagged_fraction=f["flagfrac"])
        jumps = []
        for q in on_visit:
            pts = []
            for i in [i for i in inside if S["ep"][i] == q]:
                cx, cy, ex, ey, fl2, snr = core.centroid(np.nan_to_num(S["R"][i]), np.nan_to_num(S["RV"][i], nan=1e9), x, y, r=3, reach=1.5)
                if snr > 5:
                    pts.append((cx, cy))
            if len(pts) >= 2:
                jumps.append(max(math.hypot(a[0] - b[0], a[1] - b[1]) for a in pts for b in pts))
        add("What if a fast asteroid passed through?", "Position inside one visit, exposure by exposure. Live mode also asks JPL.",
            "Too few exposures to test." if not jumps else f"Largest jump inside a visit: {max(jumps):.2f} pixels.",
            "not run" if not jumps else "supports" if max(jumps) < 0.7 else "challenges", jump_px=max(jumps) if jumps else None)
    elif top == "artefact":
        add("Would a real source show in the other array at the same moment?", "Frame partner behind the dichroic.",
            "The partner sees it too." if f["partner"] == 1 else "The partner does not see it." if f["partner"] == 0 else "No partner exposure.",
            "challenges" if f["partner"] == 1 else "supports" if f["partner"] == 0 else "not run")
        pos = [det_xy(S, i, x, y) for i in seen]
        if len(pos) >= 2:
            spread = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a in pos for b in pos)
            add("Is it fixed to detector pixels?", "Detector position of the spot in every exposure that shows it.",
                f"The detector positions spread over {spread:.1f} pixels.", "supports" if spread < 1.0 else "neutral", spread_px=spread)
        else:
            add("Is it fixed to detector pixels?", "Detector position in every exposure that shows it.", "Only one exposure shows it. Cannot test.", "not run")
        hit = None
        for i in seen:
            e = S["exps"][i]
            gx, gy, cx, cy = det_xy(S, i, x, y)
            for s in catalog or []:
                if s.get("mag", 99) > 11:
                    continue
                px, py = core.to_pix(e.wcs, s["ra"], s["dec"])
                dx, dy = cx - px[0], cy - py[0]
                for k in (1, -1, 2, -2):
                    if abs(dy) < 1.5 and abs(dx - 64 * k) < 2.0:
                        hit = (e.id, s.get("name") or s.get("id"), k)
        add("Is it a crosstalk copy of a bright star?", "Bright catalog stars one or two readout channels (64 or 128 columns) away on the same detector row.",
            f"Yes. A bright star sits {64 * abs(hit[2])} columns to the {'left' if hit[2] > 0 else 'right'} on the same row in {hit[0]}." if hit else "No bright star at the crosstalk offset.",
            "supports" if hit else "neutral")
        sh = fx.get("sharp")
        add("Is it sharper than the optics allow?", "Gaussian fit with a free width.", "No fit." if sh is None or not math.isfinite(sh) else f"Width ratio {sh:.2f}.",
            "not run" if sh is None or not math.isfinite(sh) else "supports" if sh < 0.7 else "neutral", width_ratio=sh)
        add("Does it touch flagged pixels?", "Flag table.", f"{100 * f['flagfrac']:.0f} percent of exposures.", "supports" if f["flagfrac"] >= 0.1 else "neutral",
            flagged_fraction=f["flagfrac"])
        add("Is it seen by one array only?", "Share of the residual signal in the strongest array.", f"{100 * f['a5']:.0f} percent in one array.",
            "supports" if f["a5"] > 0.8 else "neutral", one_array_share=f["a5"])
    else:
        add("Is there a change at all?", "Strongest change measure of all three methods.",
            f"Difference {m['dval']:.1f}, visit contrast {m['presence']:.1f}, brightness z {m['var_z']:.1f}.", "neutral",
            difference=m["dval"], contrast=m["presence"], z=m["var_z"])
    return out


def robustness(states, c, kind):
    rows = []
    for key, label, S in states:
        v, what = statistic(S, c, kind)
        thr = 6.0 if key == "strict" else 5.0
        rows.append(dict(key=key, label=label, value=r(v, 2), threshold=thr, survives=bool(v >= thr)))
    n = len(rows)
    return dict(statistic=what, rows=rows, survived=sum(x["survives"] for x in rows), total=n, fraction=sum(x["survives"] for x in rows) / max(n, 1))


def debate(c, m, post, tests):
    f, mo = c["f"], m["motion"]
    q = {t["question"]: t for t in tests}
    a = []
    if mo["n"] >= 3 and mo["dbic"] > P.TH["motion_dbic"] and mo["sig"] > P.TH["motion_sig"]:
        a.append(dict(who="Motion analyst", claim="It moves.", strength="strong" if mo["sig"] > 8 else "moderate",
                      evidence=[f"{mo['pm']:.3f} plus or minus {mo['err']:.3f} pixels per year", f"delta BIC {mo['dbic']:.1f}", f"{mo['n']} visits"]))
    elif mo["n"] >= 3:
        a.append(dict(who="Motion analyst", claim="No evidence of motion.", strength="moderate",
                      evidence=[f"{mo['pm']:.3f} plus or minus {mo['err']:.3f} pixels per year", f"delta BIC {mo['dbic']:.1f}"]))
    else:
        a.append(dict(who="Motion analyst", claim="Cannot judge motion.", strength="none", evidence=[f"measured in {mo['n']} visits"]))
    if m["n_on"] and m["n_off"]:
        a.append(dict(who="Photometry analyst", claim="It appears or disappears.", strength="strong" if m["presence"] > 10 else "moderate",
                      evidence=[f"bright in {m['n_on']} visits, absent in {m['n_off']}", f"visit contrast {m['presence']:.1f}"]))
    elif m["var_z"] > P.TH["var_z"]:
        a.append(dict(who="Photometry analyst", claim="Its brightness changes.", strength="strong" if m["var_z"] > 20 else "moderate",
                      evidence=[f"z {m['var_z']:.1f}", f"largest change {100 * m['amp']:.0f} percent"]))
    else:
        a.append(dict(who="Photometry analyst", claim="Its brightness is steady.", strength="moderate", evidence=[f"z {m['var_z']:.1f}"]))
    inst = []
    if f["flagfrac"] >= 0.1:
        inst.append(f"flagged pixels in {100 * f['flagfrac']:.0f} percent of exposures")
    if f["sharp"] < 0.7:
        inst.append(f"sharper than the PSF (ratio {f['sharp']:.2f})")
    if f["a4"] > 0.6:
        inst.append(f"one exposure carries the signal (dominance {f['a4']:.2f})")
    if f["a5"] > 0.8:
        inst.append(f"one array carries {100 * f['a5']:.0f} percent of the signal")
    if f["partner"] == 0 and f["a4"] > 0.4:
        inst.append("the array behind the dichroic saw nothing at the same moment")
    a.append(dict(who="Instrument analyst", claim="An instrument effect explains it." if len(inst) >= 2 else "A weak instrument warning." if inst else
                  "No instrument explanation found.", strength="strong" if len(inst) >= 2 else "weak" if inst else "moderate", evidence=inst or ["clean pixels, star shaped, seen in several arrays"]))
    sky_claim = a[0]["claim"] == "It moves." or a[1]["claim"] in ("It appears or disappears.", "Its brightness changes.")
    inst_claim = len(inst) >= 2
    if sky_claim and inst_claim:
        syn = "Unresolved. The motion or brightness analyst sees a sky change, but the instrument analyst finds a camera explanation. Keep both open."
    elif sky_claim:
        syn = "The analysts agree on a sky change. The instrument analyst finds no camera explanation."
    elif inst_claim:
        syn = "The analysts agree: no sky change survives, and the instrument analyst explains the signal."
    else:
        syn = "No analyst makes a strong claim. More data is needed."
    return dict(analysts=a, synthesis=syn, unresolved=bool(sky_claim and inst_claim))


def chain(S, m):
    """The memory of the sky: what happened at this place, visit by visit."""
    ev = []
    t0 = S["mjd_ep"][0]
    prev = None
    track = {d["q"]: d for d in m["track"]}
    for q in sorted(S["W"]):
        snr = m["visit_snr"].get(q, float("nan"))
        tot = [(fl, er) for (qq, d), (fl, er) in m["fluxes"].items() if qq == q and math.isfinite(fl)]
        flux = sum(a for a, _ in tot) if tot else float("nan")
        st = dict(visit=q + 1, day=r(S["mjd_ep"][q] - t0, 1), snr=r(snr, 1), seen=bool(math.isfinite(snr) and snr >= P.TH["on_snr"]), flux_sum=r(flux, 1))
        words = []
        if not st["seen"]:
            words.append("not detected" if not math.isfinite(snr) or snr < P.TH["off_snr"] else "faint, below the detection level")
        elif prev is None or not prev["seen"]:
            words.append("first seen" if prev is None or prev is not None and not prev["seen"] else "seen")
        if prev is not None and st["seen"] and prev["seen"] and prev["flux_sum"] and math.isfinite(flux) and prev["flux_sum"] > 0:
            ch = flux / prev["flux_sum"] - 1
            if abs(ch) > 0.05:
                words.append(f"{'brighter' if ch > 0 else 'fainter'} by {100 * abs(ch):.0f} percent")
            else:
                words.append("steady")
        if q in track and prev is not None and prev.get("x") is not None:
            d = math.hypot(track[q]["x"] - prev["x"], track[q]["y"] - prev["y"])
            if d > 3 * S["floor"] + 0.05:
                words.append(f"shifted {d:.2f} pixels")
        if q in track:
            st["x"], st["y"] = r(track[q]["x"]), r(track[q]["y"])
        st["event"] = ", ".join(words) if words else "seen"
        ev.append(st)
        prev = dict(st, x=track[q]["x"] if q in track else (prev or {}).get("x"), y=track[q]["y"] if q in track else (prev or {}).get("y"))
    return ev


def graph(S, c, m, catalog, cands):
    nodes = [dict(id="C", kind="candidate", label=c["id"])]
    edges = []
    for st in m["track"]:
        nodes.append(dict(id=f"V{st['q'] + 1}", kind="visit", label=f"Visit {st['q'] + 1}", snr=r(st["snr"], 1)))
        edges.append(dict(a="C", b=f"V{st['q'] + 1}", w=1.0, why="detected at this place"))
    for q in sorted(S["W"]):
        if not any(st["q"] == q for st in m["track"]):
            nodes.append(dict(id=f"V{q + 1}", kind="absent", label=f"Visit {q + 1}", snr=r(m["visit_snr"].get(q), 1)))
            edges.append(dict(a="C", b=f"V{q + 1}", w=0.2, why="covered but not detected"))
    cm = catalog_match(S, c["x"], c["y"], catalog)
    if cm:
        sep = cm[0]
        p = math.exp(-0.5 * (sep / 0.6) ** 2)
        nodes.append(dict(id="K", kind="catalog", label=(cm[1].get("name") or "Catalog source"), sep_px=r(sep, 2)))
        edges.append(dict(a="C", b="K", w=r(p, 3), why=f"{sep:.2f} pixels apart after motion"))
    for o in cands:
        if o is not c and math.hypot(o["x"] - c["x"], o["y"] - c["y"]) < 5:
            nodes.append(dict(id=o["id"], kind="neighbor", label=o["id"]))
            edges.append(dict(a="C", b=o["id"], w=r(math.exp(-0.5 * (math.hypot(o["x"] - c["x"], o["y"] - c["y"]) / 2.0) ** 2), 3), why="near on the sky"))
    return dict(nodes=nodes, edges=edges)


def oracle(S, c, m, post):
    p = post.get("probs", {})
    srt = sorted(p, key=p.get, reverse=True)
    a, b = (srt + ["null", "null"])[:2]
    pair = frozenset((a, b))
    rec = {frozenset(("moving", "null")): "One more visit. It extends the time baseline and shrinks the motion error.",
           frozenset(("moving", "artefact")): "A second array at the same moment. A sky source shows in both arrays behind the dichroic.",
           frozenset(("variable", "null")): "A fair pair across the visits with no color match today. Then the change is free of color effects.",
           frozenset(("variable", "artefact")): "The star ensemble gain of the same visits. A calibration step moves every star.",
           frozenset(("transient", "artefact")): "A second exposure in the same visit at the same color. A cosmic ray never repeats.",
           frozenset(("transient", "variable")): "A visit between the bright and the faint ones. A transient rises and falls once.",
           frozenset(("transient", "null")): "A deeper image of the faint visits, by co adding more exposures.",
           frozenset(("artefact", "null")): "Check the flag table and the detector position in the raw frames.",
           frozenset(("moving", "variable")): "Fit motion and brightness together. A moving source changes its blend with neighbors.",
           frozenset(("moving", "transient")): "Look for the source at the predicted position in the absent visits."}
    out = dict(top=a, second=b, entropy=r(post.get("entropy"), 3), next_measurement=rec.get(pair, "More visits of this field."))
    mo = m["motion"]
    if a == "moving" and mo["n"] >= 2:
        t = np.array(mo["t"])
        e = np.array(mo["ex"])
        def sig_pm(times, errs):
            w = 1 / errs ** 2
            tc = times - np.average(times, weights=w)
            return 1 / math.sqrt(float(np.sum(w * tc * tc)))
        now = sig_pm(t, e)
        nxt = t.max() + 182.6 / 365.25
        later = sig_pm(np.r_[t, nxt], np.r_[e, np.median(e)])
        out.update(motion_error_now=r(now, 4), motion_error_after_next_visit=r(later, 4), gain=r(now / later, 2),
                   next_visit_day=r((nxt - t.min()) * 365.25 + S["mjd_ep"][mo["q"][0]] - S["mjd_ep"][0], 0))
    sig = max(m["dval"], m["presence"], min(m["var_z"], 50.0), mo.get("sig", 0.0))
    out["priority"] = r(post.get("entropy", 1.0) * min(1.0, sig / 10.0) + (0.3 if a in SKY else 0.0), 3)
    return out


def cutouts(S, c, m, half=7, det=None):
    """Visit by visit cutouts. White light, or the one array that carries the change when one array dominates."""
    x, y = c["x"], c["y"]
    n = S["n"]
    xi, yi = int(round(x)), int(round(y))
    sl = (slice(max(0, yi - half), min(n, yi + half + 1)), slice(max(0, xi - half), min(n, xi + half + 1)))
    src = {q: S["W"][q] for q in S["W"]} if det is None else {q: S["C"][q, det] for q in range(S["E"]) if (q, det) in S["C"]}
    stack = [src[q][sl] for q in sorted(src)]
    allv = np.concatenate([np.ravel(s[np.isfinite(s)]) for s in stack]) if stack else np.array([0.0])
    lo, hi = (float(np.percentile(allv, 1)), float(np.percentile(allv, 99.8))) if allv.size else (0, 1)
    vis = [dict(visit=q + 1, img=enc(np.arcsinh(5 * (src[q][sl] - lo) / max(hi - lo, 1e-9)), 0, math.asinh(5))) for q in sorted(src)]
    out = dict(visits=vis, x0=sl[1].start, y0=sl[0].start, source="white light, all arrays" if det is None else f"array {det} only")
    cx, cy = xi - sl[1].start, yi - sl[0].start
    win = (slice(max(0, cy - 1), cy + 2), slice(max(0, cx - 1), cx + 2))
    mo = m["motion"]
    if mo["n"] >= 3 and mo["dbic"] > P.TH["motion_dbic"]:
        tm = np.mean(mo["t"])
        plain, moved = [], []
        for q in sorted(S["W"]):
            t = (S["mjd_ep"][q] - S["mjd_ep"][0]) / 365.25 - tm
            yy, xx = np.mgrid[sl]
            moved.append(map_coordinates(np.nan_to_num(S["W"][q]), [yy + mo["pm_y"] * t, xx + mo["pm_x"] * t], order=3, mode="nearest"))
            plain.append(np.nan_to_num(S["W"][q][sl]))
        pm, mm = np.mean(plain, 0), np.mean(moved, 0)
        hi2 = float(max(pm.max(), mm.max()))
        out["plain_stack"] = enc(np.arcsinh(5 * pm / max(hi2, 1e-9)), 0, math.asinh(5))
        out["motion_stack"] = enc(np.arcsinh(5 * mm / max(hi2, 1e-9)), 0, math.asinh(5))
        out["peak_plain"], out["peak_motion"] = r(pm[win].max(), 1), r(mm[win].max(), 1)
    return out


def spectral(S, c, m):
    """Flux at the candidate in every exposure: the temporal spectral fingerprint F(lambda, t)."""
    rows = []
    for i, e in enumerate(S["exps"]):
        q = S["ep"][i]
        px, py = m["trk"].get(q, (c["x"], c["y"]))
        fl, er = P.forced(S["R"][i] / S["gain"][i], S["RV"][i] / S["gain"][i] ** 2, px, py, S["sigma"])
        rows.append(dict(i=i, visit=q + 1, lam=r(e.lam, 4), det=e.det, f=r(fl * UJY, 2), e=r(er * UJY, 2)))
    # Spectral identity across visits: do the visits share one spectrum shape?
    by = {}
    for row in rows:
        if row["f"] is not None and row["e"]:
            by.setdefault(row["visit"], []).append(row)
    chi, dof = 0.0, 0
    vis = sorted(by)
    if len(vis) >= 2:
        for d in S["dets"]:
            pts = [(v, [w for w in by[v] if w["det"] == d]) for v in vis]
            pts = [(v, w) for v, w in pts if w]
            if len(pts) < 2:
                continue
            means = [(np.mean([w["f"] for w in ws]), math.sqrt(sum(w["e"] ** 2 for w in ws)) / len(ws)) for _, ws in pts]
            f = np.array([a for a, _ in means])
            e = np.array([b for _, b in means])
            if f.mean() > 5 * e.mean():
                chi += float(np.sum(((f / f.mean()) - 1) ** 2 / ((e / f.mean()) ** 2 + 0.02 ** 2)))
                dof += len(f) - 1
    return dict(rows=rows, shape_chi2=r(chi, 2), shape_dof=dof)


def evidence_and_report(c, m, post, tests, rob, deb):
    ev, sent = [], []

    def E(what, value, source):
        k = f"E{len(ev) + 1}"
        ev.append(dict(id=k, what=what, value=value, source=source))
        return k

    mo, f = m["motion"], c["f"]
    k_meth = E("Methods that flagged it", c["methods"], "P catalog, D difference, A anomaly")
    names = dict(P="the catalog method", D="the difference method", A="the anomaly method")
    sent.append((f"{c['id']} was flagged by {', '.join(names[k] for k in c['methods'])}" +
                 ("" if len(c["methods"]) == 3 else f", and not by {', '.join(names[k] for k in 'PDA' if k not in c['methods'])}") + ".", [k_meth]))
    if mo["n"] >= 3:
        k1 = E("Motion", f"{mo['pm']:.3f} plus or minus {mo['err']:.3f} pixels per year ({mo['pm'] * PIX:.2f} arcseconds per year)", "visit centroids, linear fit")
        k2 = E("Fixed position against motion", f"delta BIC {mo['dbic']:.1f}", "motion court")
        if mo["dbic"] > P.TH["motion_dbic"]:
            sent.append((f"It shifted by {mo['pm'] * (mo['t'][-1] - mo['t'][0]):.2f} pixels over {365.25 * (mo['t'][-1] - mo['t'][0]):.0f} days, "
                         f"and a fixed position fits worse.", [k1, k2]))
        else:
            sent.append(("A fixed position explains its visit positions.", [k1, k2]))
    if m["n_on"] and m["n_off"]:
        k3 = E("Visits with and without the source", f"bright in {m['n_on']}, absent in {m['n_off']}", "matched filter per visit")
        sent.append((f"It is bright in {m['n_on']} visits and absent in {m['n_off']}.", [k3]))
    elif m["var_z"] > P.TH["var_z"]:
        k3 = E("Brightness change", f"z {m['var_z']:.1f}, largest change {100 * m['amp']:.0f} percent", "forced photometry with the measured floor")
        sent.append((f"Its brightness changed by up to {100 * m['amp']:.0f} percent, more than the catalog stars allow.", [k3]))
    inst = [t for t in tests if t["outcome"] == "challenges"]
    sup = [t for t in tests if t["outcome"] == "supports"]
    kt = E("Challenges survived", f"{len(sup)} support, {len(inst)} argue against, {len(tests) - len(sup) - len(inst)} neutral or not run", "self questioning tests")
    if inst:
        sent.append(("It failed: " + "; ".join(t["question"].lower().rstrip("?") + " (" + t["result"].rstrip(".") + ")" for t in inst[:2]) + ".", [kt]))
    elif sup:
        sent.append((f"It passed {len(sup)} tests that tried to break the leading explanation.", [kt]))
    kr = E("Robustness", f"{rob['survived']} of {rob['total']} analysis choices keep it above the threshold", "counterfactual reanalysis")
    sent.append((f"It survives {rob['survived']} of {rob['total']} reasonable changes to the analysis.", [kr]))
    if post.get("ready"):
        p = post["probs"]
        kp = E("Hypothesis probabilities", ", ".join(f"{engine.NAMES[h].split(' ', 1)[0]} {100 * p[h]:.0f} percent" for h in HYP), "five hypothesis engine, equal priors")
        if post["unknown"]:
            sent.append(("The engine says unknown: " + " ".join(post["why_unknown"]), [kp]))
        else:
            sent.append((f"The most likely explanation is {engine.NAMES[post['top']].split(' ', 1)[1].lower()} at {100 * p[post['top']]:.0f} percent.", [kp]))
    if deb["unresolved"]:
        sent.append(("The analysts disagree, and the disagreement stays on the record.", [E("Debate", deb["synthesis"], "three analysts")]))
    return ev, [dict(text=t, refs=k) for t, k in sent]


def status(post, tests, rob):
    v = post.get("verdict", "null")
    ch = [t for t in tests if t["outcome"] == "challenges"]
    if post.get("unknown"):
        return "Unknown. The evidence does not separate the explanations.", "unknown"
    if v in SKY:
        if ch:
            return "Contested. A test argues against the leading explanation.", "contested"
        if rob["fraction"] >= 0.75:
            return "Worth further investigation. Not a confirmed discovery.", "worth"
        return "Fragile. It depends on analysis choices.", "fragile"
    if v == "artefact":
        return "Most consistent with an instrumental artefact.", "artefact"
    return "No established change.", "none"


def disagreement(c, f, post):
    """Why the three methods agree or disagree, and the test that the disagreement asks for."""
    k = c["methods"]
    table = {
        "PDA": ("All three methods agree.", "Agreement is not proof: a camera effect fools every method that reads the same pixels. The instrument tests decide."),
        "PD": ("Catalog and difference agree; the anomaly model finds the pixel time behaviour ordinary.",
               "A slow, steady change looks normal pixel by pixel. Check the change in the fair pair directly."),
        "PA": ("Catalog and anomaly agree; no fair pair shows it.", "The change falls between visits with no color match, or it is a camera effect in one array. "
               "Test: compare the brightness across the color gap with the false change meter, and check the partner array."),
        "DA": ("Difference and anomaly agree; the catalog never linked a source here.", "A faint change below the catalog level. Test: co add more exposures."),
        "P": ("Only the catalog method sees it.", "Often a slow motion that moves the centroid but leaves little residue, or a change between visits without a fair pair. "
              "Test: leave one visit out and fit again."),
        "D": ("Only the difference method sees it.", "Often a resampling residue near a bright star, or a small motion seen as a dipole. "
              "Test: measure the star residue and look for a matching negative lobe."),
        "A": ("Only the anomaly model sees it.", "Often a single exposure event: a cosmic ray, a hot pixel or a ghost, which the co adds wash out. "
              "Test: the partner array at the same moment, and the detector position."),
    }
    head, why = table.get(k, ("", ""))
    return dict(pattern=k, headline=head, meaning=why)


# ---------------------------------------------------------------- field products

def guardian(S):
    rows = []
    for q in range(S["E"]):
        for d in S["dets"]:
            idx = [i for i, e in enumerate(S["exps"]) if S["ep"][i] == q and e.det == d]
            if not idx:
                continue
            rel = sorted({S["exps"][i].rel for i in idx})
            g = float(np.mean([S["gain"][i] for i in idx]))
            ge = [S["gain_err"][i] for i in idx if math.isfinite(S["gain_err"][i])]
            ge = float(np.mean(ge)) / math.sqrt(len(ge)) if ge else float("nan")
            z = (g - 1) / ge if ge and math.isfinite(ge) and ge > 0 else float("nan")
            rows.append(dict(visit=q + 1, det=d, release=",".join(rel), gain=r(g, 4), gain_err=r(ge, 4), z=r(z, 1), stars=int(np.mean([S["gain_n"][i] for i in idx]))))
    rels = [x["release"] for x in rows]
    common = max(set(rels), key=rels.count) if rels else ""
    for x in rows:
        odd = x["release"] != common
        step = x["z"] is not None and abs(x["z"]) > 5
        x["verdict"] = ("Release differs and the stars show a gain step. Brightness was corrected by the star ensemble. Difference images skip this cell."
                        if odd and step else "Release differs. Difference images skip this cell." if odd else
                        "Gain step without a release change. Check the calibration." if step else "Consistent.")
        x["warn"] = bool(odd or step)
    return dict(rows=rows, common_release=common)


def layers(S, q1, q2, d):
    """The difference microscope: the same pair with more corrections at each layer. Counts of spots above 5 sigma."""
    exps = S["exps"]
    ia = [i for i in S["CN"].get((q1, d), [])]
    ib = [i for i in S["CN"].get((q2, d), [])]
    if not ia or not ib:
        return None
    a = ia[0]
    b = min(ib, key=lambda j: P.color_distance(exps[a], exps[j]))
    A, B = exps[a], exps[b]
    n = S["n"]
    K = S["K"]
    out = []

    def count(z):
        return len(P.peaks(np.nan_to_num(z), 5.0, P.TH["edge"], absval=True))

    va, vb = getattr(A, "var0", A.var), getattr(B, "var0", B.var)
    h = min(A.img.shape[0], B.img.shape[0], n)
    raw = (B.img[:h, :h] - A.img[:h, :h])
    z0 = P.mf(raw, va[:h, :h] + vb[:h, :h], K)
    out.append(("raw", "Raw difference. Pixel grids laid on top, no alignment.", z0))
    ra, rva, *_ = P.register(A, S["ref"], n, shift=(0.0, 0.0))
    rb, rvb, *_ = P.register(B, S["ref"], n, shift=(0.0, 0.0))
    var_dec = lambda e, s: P.register(type(e)(e.id, e.mjd, e.lam, e.bw, e.det, e.rel, e.label, e.img, getattr(e, "var0", e.var), e.flags, wcs=e.wcs, bits=e.bits), S["ref"], n, shift=s)[1]
    z1 = P.mf(rb - ra, var_dec(A, (0.0, 0.0)) + var_dec(B, (0.0, 0.0)), K)
    out.append(("wcs", "Aligned with the WCS of each file.", z1))
    ra2, *_ = P.register(A, S["ref"], n)
    rb2, *_ = P.register(B, S["ref"], n)
    z2 = P.mf(rb2 - ra2, var_dec(A, A.shift) + var_dec(B, B.shift), K)
    out.append(("anchor", "Anchored to catalog stars.", z2))
    da = ra2 - np.nanmedian(ra2)
    db = rb2 - np.nanmedian(rb2)
    ga, gb = S["gain"][a], S["gain"][b]
    z3 = P.mf(db / gb - da / ga, var_dec(A, A.shift) / ga ** 2 + var_dec(B, B.shift) / gb ** 2, K)
    out.append(("background", "Sky level removed and star gain matched.", z3))
    va4, vb4 = S["RV"][a] / ga ** 2, S["RV"][b] / gb ** 2
    sig = np.maximum(np.abs(np.nan_to_num(da / ga)), np.abs(np.nan_to_num(db / gb)))
    from scipy.ndimage import maximum_filter
    sig = maximum_filter(sig, size=5)
    z4 = P.mf(db / gb - da / ga, va4 + vb4 + (0.05 * sig) ** 2, K)
    out.append(("noise", "Honest noise: measured noise factor and the resampling error of stars.", z4))
    if (q1, q2) in S.get("dmaps", {}) and d in S["dmaps"][q1, q2]["per"]:
        z5 = S["dmaps"][q1, q2]["per"][d]
        out.append(("coadd", "Fair co adds of the whole visit, matched colors.", z5))
    res = []
    for key, label, z in out:
        res.append(dict(key=key, label=label, count=count(z), img=enc(np.clip(np.nan_to_num(z, nan=0.0), -10, 10), -10, 10)))
    return dict(q1=q1 + 1, q2=q2 + 1, det=d, a=A.id, b=B.id, color=r(P.color_distance(A, B), 3), layers=res)


def uncertainty_maps(S, flux_ujy=300.0):
    """Coverage, single visit depth (5 sigma, microJy) in the best array, and the position error of a source of flux_ujy."""
    from scipy.ndimage import convolve
    n = S["n"]
    cov = np.sum(np.array([np.isfinite(S["R"][i]) for i in range(len(S["exps"]))]), 0)
    kp = core.gauss((7, 7), 3, 3)
    kp = kp / kp.sum()
    depth, best = {}, None
    for d in S["dets"]:
        per = []
        for q in range(S["E"]):
            if (q, d) in S["CV"]:
                v = S["CV"][q, d]
                inv = np.where(np.isfinite(v) & (v > 0), 1 / np.where(np.isfinite(v) & (v > 0), v, 1), 0)
                c = convolve(inv, kp * kp, mode="constant")
                per.append(np.where(c > 0, 1 / np.sqrt(np.maximum(c, 1e-30)), np.nan))
        if not per:
            continue
        f5 = 5 * np.nanmedian(np.array(per), 0) * UJY
        depth[d] = f5
        best = f5 if best is None else np.fmin(best, f5)
    snr = flux_ujy / np.where(np.isfinite(best), best / 5, np.nan)
    pos = math.sqrt(2) * core.PSF_SIGMA / np.maximum(snr, 1e-6)
    return dict(coverage=cov, depth=best, pos=pos, depth_by_det={d: float(np.nanmedian(v)) for d, v in depth.items()})


def controls(base, exps, catalog, spec):
    out = {}
    st = mv = 0
    for g in base["groups"]:
        if len(g) == base["E"] and min(d["snr"] for d in g) > 10:
            mo = P.motion(g, base["mjd_ep"], base["floor"])
            if catalog_match(base, np.mean([d["x"] for d in g]), np.mean([d["y"] for d in g]), [s for s in catalog or [] if not s.get("pm_ra") and not s.get("pm_dec")]):
                st += 1
                mv += int(mo["dbic"] > P.TH["motion_dbic"] and mo["sig"] > P.TH["motion_sig"])
    out["static_stars"] = dict(tested=st, called_moving=mv, meaning="Catalog stars with no motion that the motion court calls moving.")
    if spec is not None:
        import sky
        twin = dict(spec, sources=[s for s in spec["sources"] if s.get("kind") == "star"], artefacts=[], release={})
        E2, _, cat2 = sky.render(twin)
        core.prepare(E2)
        S2 = P.run(E2, cat2, center=spec["center"])
        out["null_twin"] = dict(candidates=len(S2["cands"]), patterns=[c["methods"] for c in S2["cands"]],
                                meaning="The same field with every planted change removed. Each candidate here is a false alarm.")
    tshuf = []
    for g in base["groups"]:
        if len(g) >= 4:
            mo = P.motion(g, base["mjd_ep"], base["floor"])
            if mo["dbic"] > P.TH["motion_dbic"]:
                import itertools
                worse = 0
                tot = 0
                for perm in itertools.permutations(range(len(g))):
                    if list(perm) == list(range(len(g))):
                        continue
                    gg = [dict(d, q=g[p]["q"]) for d, p in zip(g, perm)]
                    tot += 1
                    worse += int(P.motion(gg, base["mjd_ep"], base["floor"])["dbic"] >= mo["dbic"])
                tshuf.append(dict(x=r(np.mean([d["x"] for d in g]), 1), y=r(np.mean([d["y"] for d in g]), 1), dbic=r(mo["dbic"], 1),
                                  shuffles=tot, as_strong=worse, p=r((worse + 1) / (tot + 1), 3)))
    out["time_shuffle"] = dict(rows=tshuf, meaning="Visit times shuffled for every moving source. A real motion loses its fit when time order is broken.")
    return out


def research_questions(cands, val):
    """Suggestions, not findings. Each comes with the numbers behind it and a test that could falsify it."""
    out = []
    if val:
        ap = val.get("agreement_patterns", {})
        if ap:
            best = max(ap.items(), key=lambda kv: kv[1]["sky_fraction"] if kv[1]["n"] >= 10 else -1)
            worst = min(ap.items(), key=lambda kv: kv[1]["sky_fraction"] if kv[1]["n"] >= 10 else 2)
            out.append(dict(q=f"Is a candidate flagged by {best[0]} more often a real sky change than one flagged by {worst[0]}?",
                            numbers=f"{best[0]}: {100 * best[1]['sky_fraction']:.0f} percent of {best[1]['n']}. {worst[0]}: {100 * worst[1]['sky_fraction']:.0f} percent of {worst[1]['n']}.",
                            test="Compare the two fractions on new fields with a two proportion test.", falsified_if="The intervals overlap on fresh fields."))
        adv = val.get("adversarial", {})
        if adv:
            hard = min(adv.items(), key=lambda kv: kv[1]["rejected"])
            out.append(dict(q=f"Why is the {hard[0]} artefact the hardest to reject?", numbers=f"Rejected in {100 * hard[1]['rejected']:.0f} percent of {hard[1]['n']} cases.",
                            test="Add a feature for this artefact (for example the detector position) and test again on held out fields.",
                            falsified_if="Rejection does not rise above its interval."))
        comp = val.get("completeness", {})
        if "moving" in comp:
            out.append(dict(q="Does motion detection depend on brightness more than on the size of the motion?",
                            numbers="See the completeness table by magnitude for moving sources.",
                            test="Fit completeness against magnitude and motion together.", falsified_if="The motion term is as strong as the magnitude term."))
    arr = [c for c in cands if c.get("post", {}).get("verdict") == "artefact"]
    if arr:
        dets = [c["dossier"]["artefact_array"] for c in arr if c["dossier"].get("artefact_array")]
        if dets:
            out.append(dict(q="Are artefacts in this field concentrated on one array?", numbers=f"Arrays of the artefacts: {', '.join(map(str, dets))}.",
                            test="Count artefacts per array over many fields, divided by the exposure count per array.", falsified_if="The rate per exposure is equal across arrays."))
    unk = [c for c in cands if c.get("post", {}).get("unknown")]
    if unk:
        out.append(dict(q="What do the unknown candidates share?", numbers=f"{len(unk)} unknown here: {', '.join(c['id'] for c in unk)}.",
                        test="Compare their fingerprints with the decided ones.", falsified_if="No feature separates them."))
    return out


# ---------------------------------------------------------------- record

def versions():
    out = dict(python=platform.python_version())
    for mod in ("numpy", "scipy", "astropy", "sklearn"):
        try:
            out[mod] = __import__(mod).__version__
        except Exception:
            out[mod] = None
    return out


def code_hashes():
    out = {}
    for f in ("core.py", "pipeline.py", "investigate.py", "engine.py", "sky.py", "connectors.py"):
        p = os.path.join(ROOT, "backend", f)
        if os.path.exists(p):
            out[f] = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    ep = os.path.join(ROOT, "data", "engine.json")
    if os.path.exists(ep):
        out["engine.json"] = hashlib.sha256(open(ep, "rb").read()).hexdigest()[:16]
    return out


# ---------------------------------------------------------------- main entry

def investigate(exps, catalog=None, center=None, size=None, meta=None, truth=None, spec=None, deep=True, val=None):
    meta = dict(meta or {})
    for e in exps:
        if not hasattr(e, "var0"):
            e.var0 = e.var.copy()
    core.prepare(exps)
    S = P.run(exps, catalog, center, size)
    cands = sorted(S["cands"], key=lambda c: -max(c["m"]["dval"], c["m"]["presence"], min(c["m"]["var_z"], 50), c["m"]["motion"].get("sig", 0)))
    for k, c in enumerate(cands):
        c["id"] = f"C{k + 1:02d}"
    if truth is not None:
        P.match_truth(S, truth)
    states = [("baseline", "Baseline", S)]
    if deep:
        ks = [e.noise_k for e in exps]
        worst = max(ks) / max(float(np.median(ks)), 1e-6)
        for key, label, opt in VARIANTS[1:]:
            o = opt if opt is not None else {"worst_noise": worst}
            states.append((key, label, variant_state(S, exps, catalog, o)))
        for q in range(S["E"]):
            states.append((f"drop{q + 1}", f"Visit {q + 1} left out", variant_state(S, exps, catalog, {"drop_epoch": q})))
        states.append(("strict", "Stricter threshold: 6 sigma", S))
    out_c = []
    for c in cands:
        m = c["m"]
        post = engine.posterior(c["f"])
        top = post.get("top", "null") if post.get("ready") else "null"
        lead = top if top != "null" else max((h for h in SKY + ("artefact",)), key=lambda h: post.get("probs", {}).get(h, 0))
        tests = challenges(S, c, m, lead, catalog, cands)
        rob = robustness(states, c, lead if lead in SKY else "other")
        deb = debate(c, m, post, tests)
        ev, rep = evidence_and_report(c, m, post, tests, rob, deb)
        st, code = status(post, tests, rob)
        seen, sgn = seen_in(S, c["x"], c["y"])
        art_det = None
        if seen and c["f"]["a5"] > 0.6:
            dets = [S["exps"][i].det for i in seen]
            art_det = max(set(dets), key=dets.count)
        ra, dec = core.to_sky(S["ref"], c["x"], c["y"])
        mo = m["motion"]
        dossier = dict(
            disagreement=disagreement(c, c["f"], post), tests=tests, robustness=rob, debate=deb, chain=chain(S, m), graph=graph(S, c, m, catalog, cands),
            evidence=ev, report=rep, oracle=oracle(S, c, m, post), cutouts=cutouts(S, c, m, det=art_det if c["f"]["a5"] > 0.6 else None),
            spectral=spectral(S, c, m),
            motion=dict(n=mo["n"], pm_px_yr=r(mo.get("pm"), 4), err=r(mo.get("err"), 4), sig=r(mo.get("sig"), 2), dbic=r(mo.get("dbic"), 2),
                        pm_arcsec_yr=r(mo.get("pm", 0) * PIX, 3), pa_deg=r(math.degrees(math.atan2(-mo.get("pm_x", 0), mo.get("pm_y", 0))) % 360, 1) if mo["n"] >= 2 else None,
                        pm_x=r(mo.get("pm_x"), 4), pm_y=r(mo.get("pm_y"), 4),
                        track=[dict(visit=q + 1, day=r((S["mjd_ep"][q] - S["mjd_ep"][0]), 1), x=r(x), y=r(y), ex=r(ex, 4), ey=r(ey, 4))
                               for q, x, y, ex, ey in zip(mo.get("q", []), mo.get("x", []), mo.get("y", []), mo.get("ex", []), mo.get("ey", []))]),
            light=[dict(visit=q + 1, det=d, day=r(S["mjd_ep"][q] - S["mjd_ep"][0], 1), f=r(fl, 2), e=r(er, 2)) for (q, d), (fl, er) in sorted(m["fluxes"].items())],
            court=court(c, m, S), artefact_array=art_det, status=st, status_code=code, seen_in=[S["exps"][i].id for i in seen][:12])
        out_c.append(dict(id=c["id"], x=r(c["x"], 2), y=r(c["y"], 2), ra=r(float(ra[0]), 6), dec=r(float(dec[0]), 6), methods=c["methods"],
                          features={k: r(v, 3) for k, v in c["f"].items()}, post=post, dossier=dossier, truth=c.get("truth"), truth_id=c.get("truth_id"),
                          truth_sub=c.get("truth_sub"),
                          scores=dict(P=r(max([d["s"] for d in c["P"]], default=0), 1), D=r(max([abs(d["s"]) for d in c["D"]], default=0), 1),
                                      A=r(max([d["s"] for d in c["A"]], default=0), 3), A_spread=r(max([d["spread"] for d in c["A"]], default=0), 3))))
    field = field_products(S, exps, catalog, spec, out_c, deep)
    rq = research_questions(out_c, val)
    rec = record(meta, S, exps, out_c)
    score = None
    if truth is not None:
        _, found, missed = P.match_truth(S, truth)
        ok = sum(1 for c in out_c if c["truth"] is not None and (c["post"].get("verdict") == c["truth"] or (c["truth"] == "null" and c["post"].get("unknown"))))
        score = dict(found=[dict(id=t["id"], kind=t["kind"], sub=t.get("sub")) for t in found], missed=[dict(id=t["id"], kind=t["kind"], sub=t.get("sub"), x=r(t["x"], 1), y=r(t["y"], 1)) for t in missed],
                     verdict_correct=ok, candidates=len(out_c), truth=truth)
    return dict(meta=meta, n=S["n"], center=list(S["center"]), pixel_arcsec=PIX, visits=S["E"], arrays=S["dets"], mjd_visits=[r(v, 4) for v in S["mjd_ep"]],
                candidates=out_c, field=field, research=rq, record=rec, score=score, thresholds=P.TH, engine=engine_info(), pfloor=S["pfloor"],
                astro_floor=r(S["floor"], 4))


def engine_info():
    m = engine.model()
    if m is None:
        return None
    return dict(classes=m["classes"], unknown_p=m["unknown_p"], ood_threshold=r(m["ood_threshold"], 2), trained_on=m["trained_on"], temperature=m["temperature"])


def court(c, m, S):
    """The artefact court: each examination and its answer."""
    f = c["f"]
    return [dict(exam="Pixel quality", q="Does it sit on flagged pixels?", a=f"Flagged in {100 * f['flagfrac']:.0f} percent of exposures.",
                 ok=f["flagfrac"] < 0.1),
            dict(exam="Variance", q="Is it significant against the honest noise?", a=f"Strongest residual {math.expm1(abs(f['a1'])):.1f} sigma.", ok=math.expm1(abs(f["a1"])) > 5),
            dict(exam="PSF", q="Does its shape match the optics?", a=f"Width ratio {f['sharp']:.2f}.", ok=0.75 <= f["sharp"] <= 1.4),
            dict(exam="Crosstalk and arrays", q="Is it confined to one array or one exposure?", a=f"One array carries {100 * f['a5']:.0f} percent; one exposure dominance {f['a4']:.2f}.",
                 ok=f["a5"] < 0.8 and f["a4"] < 0.6),
            dict(exam="Background", q="Does it survive a local background?", a="See the robustness table.", ok=None),
            dict(exam="Registration", q="Does it survive anchor errors?", a="See the robustness table.", ok=None),
            dict(exam="Release", q="Do the compared exposures share a release?", a=", ".join(sorted({e.rel for e in S["exps"]}))),
            dict(exam="Simultaneous array", q="Does the partner array see it at the same moment?", a={1: "Yes.", 0: "No.", 0.5: "No partner."}.get(f["partner"], "?"),
                 ok=None if f["partner"] == 0.5 else f["partner"] == 1)]


def field_products(S, exps, catalog, spec, cands, deep):
    n = S["n"]
    t0 = min(e.mjd for e in exps)
    ex_rows = []
    for i, e in enumerate(exps):
        fl = {}
        for name, b in e.bits.items():
            k = int(((e.flags >> b) & 1).sum())
            if k:
                fl[name] = k
        ex_rows.append(dict(i=i, id=e.id, visit=S["ep"][i] + 1, day=r(e.mjd - t0, 2), mjd=r(e.mjd, 5), lam=r(e.lam, 4), bw=r(e.bw, 4), det=e.det, rel=e.rel,
                            label=e.label, frame=e.frame, noise_k=r(e.noise_k, 3), anchors=e.nanchor, shift=[r(e.shift[0], 3), r(e.shift[1], 3)],
                            gain=r(S["gain"][i], 4), flags=fl, flagged_pixels=int(((e.flags & e.bad) != 0).sum()), lam_src=e.lam_src, notes=e.notes,
                            coverage=r(float(np.isfinite(S["R"][i]).mean()), 3)))
    wr = stretch_range(list(S["W"].values()))
    cr = {d: stretch_range([C for (q, dd), C in S["C"].items() if dd == d]) for d in S["dets"]}
    maps = dict(white={q + 1: enc(S["W"][q], stretch=wr) for q in S["W"]}, deep=enc(S["DEEP"], stretch=True),
                coadd={f"{q + 1}_{d}": enc(C, stretch=cr[d]) for (q, d), C in S["C"].items()},
                cube=[enc(np.where(np.isfinite(S["R"][i]), S["R"][i] / np.sqrt(np.nanmedian(S["RV"][i])), np.nan), -3, 30) for i in range(len(exps))],
                diff={f"{q1 + 1}_{q2 + 1}": enc(np.clip(np.nan_to_num(v["comb"]), -10, 10), -10, 10) for (q1, q2), v in S.get("dmaps", {}).items()},
                anomaly=enc(S["anom"], 0, 1), anomaly_spread=enc(S["anom_spread"], 0, 0.5),
                anomaly_models=[enc(np.pad(a, P.TH["edge"]), 0, 1) for a in S["anom_models"]])
    um = uncertainty_maps(S)
    maps["coverage"] = enc(um["coverage"].astype(float), 0, len(exps))
    lg = np.log10(np.clip(um["depth"], 1, 1e5))
    maps["depth"] = enc(lg, float(np.nanpercentile(lg, 1)), float(np.nanpercentile(lg, 99)))
    maps["pos_err"] = enc(np.clip(um["pos"], 0, 0.3), 0, 0.3)
    fair = P.fair_coadd_pairs(S)
    micro = []
    if deep:
        for p in fair:
            if p["fair"] and p["release_same"]:
                L = layers(S, p["q1"], p["q2"], p["det"])
                if L:
                    L["fair"] = True
                    micro.append(L)
        unfair = [p for p in fair if not p["fair"]]
        if unfair:
            p = min(unfair, key=lambda p: (abs(p["color"] - 0.6), p["det"]))
            L = layers(S, p["q1"], p["q2"], p["det"])
            if L:
                L["fair"] = False
                micro.append(L)
    cat = []
    for s in catalog or []:
        mjd = float(np.mean(S["mjd_ep"]))
        dy = (mjd - core.SIM_T0) / 365.25
        cd = math.cos(math.radians(s["dec"]))
        ra, dec = s["ra"] + s.get("pm_ra", 0.0) * dy / 3600 / cd, s["dec"] + s.get("pm_dec", 0.0) * dy / 3600
        x, y = core.to_pix(S["ref"], ra, dec)
        if -2 < x[0] < n + 1 and -2 < y[0] < n + 1:
            cat.append(dict(x=r(x[0], 2), y=r(y[0], 2), mag=r(s.get("mag"), 2), moving=bool(s.get("pm_ra") or s.get("pm_dec")), name=s.get("name") or s.get("id"),
                            source=s.get("source", "catalog")))
    ctl = controls(S, exps, catalog, spec) if deep else {}
    if micro:
        cnt = lambda key: sum(next((x["count"] for x in L["layers"] if x["key"] == key), 0) for L in micro if L["fair"])
        ctl["alignment_stress"] = dict(wcs_only=cnt("wcs"), anchored=cnt("anchor"), final=cnt("coadd"),
                                       meaning="Spots above 5 sigma in the fair pairs when only the file WCS aligns the images, after the star anchors, and in the final fair co adds.")
    return dict(exposures=ex_rows, maps=maps, guardian=guardian(S), pairs=[{k: (r(v) if isinstance(v, float) else v) for k, v in p.items()} for p in fair],
                microscope=micro, catalog=cat, controls=ctl, depth_by_det={d: r(v, 1) for d, v in um["depth_by_det"].items()},
                detections=dict(P=len(S["det_P"]), D=len(S["det_D"]), A=len(S["det_A"])), area_deg2=r((n * PIX / 3600) ** 2, 5))


def record(meta, S, exps, cands):
    body = dict(inputs=dict(meta=meta, exposures=[e.id for e in exps], releases=sorted({e.rel for e in exps})), thresholds=P.TH, versions=versions(),
                code=code_hashes(), outputs=[dict(id=c["id"], x=c["x"], y=c["y"], methods=c["methods"], verdict=c["post"].get("verdict"),
                                                   p={k: r(v, 3) for k, v in c["post"].get("probs", {}).items()}) for c in cands])
    seal = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    outs = hashlib.sha256(json.dumps(body["outputs"], sort_keys=True, default=str).encode()).hexdigest()
    return dict(body, seal=seal, output_digest=outs,
                rule="Same inputs, same thresholds and same code give the same output digest. Reproduce recomputes it.")
