"""CHRONOS 4D: space x time x wavelength x evidence.

Ten laboratories computed from one investigation (the output of investigate.investigate, the same JSON the
observatory page reads). Everything here is a classical, physics first calculation: no generative AI and no
trained model. Each result says what was measured, what is inferred and what cannot be tested with these data.

Sources for the SPHEREx facts used below: SPHEREx Archive at IRSA, Data Products and Data Access pages
(DR1 released November 12, 2026; QR2 no longer searchable, direct download through February 2027; All-Sky Cube
channels 51 and 52 hold no data and are listed in BLANKCH; WCS-WAVE is display grade, CWAVE and CBAND of the
Spectral WCS product are for science; ePSF supersedes PSF).
"""
import hashlib
import json
import math

import numpy as np

# ---------------------------------------------------------------- 0. Releases and provenance (P0)

RELEASES = {
    "dr1": dict(collections=["spherex_dr1", "spherex_dr1_deep"], cube="spherex_dr1_cube", searchable=True, psf="EPSF",
                note="Reprocessed; forms one uniformly processed set with QR3. Use for new work."),
    "qr3": dict(collections=["spherex_qr3", "spherex_qr3_deep"], searchable=True, psf="EPSF", note="New gain calibration; uniform with DR1."),
    "qr2": dict(collections=["spherex_qr2"], searchable=False, psf="PSF",
                note="Superseded. Not searchable; direct download through February 2027. Previous gain: needs the L3 flux corrections before any comparison with QR3 or DR1."),
}
DEFAULT_COLLECTIONS = "spherex_dr1+spherex_qr3"
BLANK_CHANNELS = (51, 52)  # 1 based, All-Sky Cube
BANDS = {1: (0.75, 1.09), 2: (1.10, 1.62), 3: (1.63, 2.41), 4: (2.42, 3.82), 5: (3.83, 4.41), 6: (4.42, 5.00)}
CALIBRATION_PRODUCTS = {  # directory pattern under https://irsa.ipac.caltech.edu/ibe/data/spherex/<release>/
    "absolute gain": "abs_gain_matrix/cal-agm-v*/<det>/", "ePSF": "epsf/cal-epsf-v*/<det>/", "spectral WCS (CWAVE, CBAND)": "spectral_wcs/cal-wcs-v*/<det>/",
    "nonlinearity": "nonlinear_pars/base-*/<det>/", "read noise": "readnoise_pars/base-*/<det>/", "nonfunctional pixels": "nonfunc_v2/base-*/<det>/",
    "crosstalk": "xtalk_class<type>/base-*/<det>/", "flux corrections": "l3_flux_corrections/cal-flxc-v*/<det>/", "zodi scaling": "zodi_scaling_v*/cal-zodi-v*/<det>/",
    "aurora template (band 1)": "aurora_template/base-*/<det>/", "helium template (bands 1, 2)": "he_template/base-*/<det>/",
    "shuttle glow template (band 5)": "shuttle_glow_template/base-*/<det>/", "solid angle pixel map": "solid_angle_pixel_map/cal-sapm-v*/<det>/",
}


def release_of(name):
    n = str(name).lower()
    for k in ("dr1", "qr3", "qr2"):
        if k in n:
            return k
    return "simulation" if "sim" in n or n == "" else "unknown"


def release_check(names):
    """Refuse silent mixing: QR2 never combines with QR3 or DR1 without flux corrections."""
    rel = sorted({release_of(x) for x in names})
    mixed_qr2 = "qr2" in rel and len(set(rel) - {"qr2"}) > 0
    return dict(releases=rel, compatible=not mixed_qr2, superseded=[r for r in rel if r == "qr2"],
                rule="DR1 and QR3 are one uniformly processed set. QR2 used the previous gain: combine only after the L3 flux corrections.",
                verdict="Do not combine without flux corrections." if mixed_qr2 else "Compatible.")


def channel_of(lam, det):
    """DR1 cube channel (1..102): 17 log spaced channels per detector."""
    lo, hi = BANDS.get(int(det), (0.75, 5.0))
    k = int(np.clip(math.floor(17 * math.log(lam / lo) / math.log(hi / lo)), 0, 16))
    return (int(det) - 1) * 17 + k + 1


def channel_center(ch):
    det, k = (ch - 1) // 17 + 1, (ch - 1) % 17
    lo, hi = BANDS[det]
    return lo * (hi / lo) ** ((k + 0.5) / 17)


# ---------------------------------------------------------------- 1. The 4D spectral record F(lambda, t), sigma(lambda, t)

FEATURES = [  # micron, name, kind
    (1.083, "He I 1.083 (instrumental and atmospheric emission stripes)", "contaminant"), (1.282, "Paschen beta", "emission"),
    (1.4, "H2O (brown dwarfs, cool stars)", "absorption"), (1.9, "H2O (brown dwarfs, Miras)", "absorption"), (2.166, "Brackett gamma (accretion)", "emission"),
    (2.29, "CO bandhead", "absorption"), (3.05, "H2O ice", "absorption"), (3.3, "CH4 / aromatic", "absorption"), (3.53, "CH3OH ice", "absorption"),
    (4.27, "CO2 ice", "absorption"), (4.62, "OCN- (XCN) ice", "absorption"), (4.67, "CO ice", "absorption"),
]


def spectral_record(cand, field):
    rows = [r for r in cand["dossier"]["spectral"]["rows"] if r.get("f") is not None and r.get("e")]
    visits = sorted({r["visit"] for r in rows})
    F = np.full((102, len(visits)), np.nan)
    E = np.full((102, len(visits)), np.nan)
    L = np.full((102, len(visits)), np.nan)
    for r in rows:
        c, v = channel_of(r["lam"], r["det"]) - 1, visits.index(r["visit"])
        F[c, v], E[c, v], L[c, v] = r["f"], r["e"], r["lam"]
    state = np.where(np.isfinite(F), "measured", "not observed").astype(object)
    for b in BLANK_CHANNELS:
        state[b - 1, :] = "no data in DR1 cube"
    # Stability: one shape for all visits, a free gray scale per visit. chi2 against it.
    gray, chi, dof = [], 0.0, 0
    ref = np.nanmedian(F, 1)
    for v in range(len(visits)):
        ok = np.isfinite(F[:, v]) & np.isfinite(ref) & (ref > 0)
        if ok.sum() < 2:
            gray.append(None)
            continue
        w = 1 / E[ok, v] ** 2
        s = float(np.sum(w * F[ok, v] * ref[ok]) / np.sum(w * ref[ok] ** 2))
        gray.append(round(s, 4))
        sys = 0.02 * F[ok, v]  # 2 percent calibration floor
        chi += float(np.sum((F[ok, v] - s * ref[ok]) ** 2 / (E[ok, v] ** 2 + sys ** 2)))
        dof += int(ok.sum()) - 1
    g = [x for x in gray if x]
    gray_change = (max(g) / min(g) - 1) if len(g) >= 2 else 0.0
    red = chi / dof if dof else None
    score = None if red is None else round(float(math.exp(-max(0.0, red - 1) / 3)), 3)
    # Spectral residual court: could the wavelength sampling alone make the change?
    samp = []
    for c in range(102):
        ok = np.isfinite(F[c]) & np.isfinite(L[c])
        if ok.sum() >= 2:
            lam = L[c, ok]
            dlam = float(lam.max() - lam.min())
            slope = local_slope(F, L, c)
            exp = abs(slope * dlam)
            obs = float(np.nanmax(F[c, ok]) - np.nanmin(F[c, ok]))
            samp.append(dict(channel=c + 1, dlam_um=round(dlam, 4), expected_from_sampling=round(exp, 2), observed=round(obs, 2),
                             explained=bool(obs <= 2 * exp + 3 * float(np.nanmax(E[c, ok])))))
    explained = sum(s["explained"] for s in samp)
    warnings = []
    lam_src = {e.get("lam_src") for e in field["field"]["exposures"]}
    if not any("CWAVE" in str(s) for s in lam_src):
        warnings.append("Wavelengths are not from the CWAVE and CBAND calibration product. Treat wavelength shifts below one channel as unverified.")
    rc = release_check([e.get("rel", "") for e in field["field"]["exposures"]])
    if not rc["compatible"]:
        warnings.append("Releases with different gain calibrations are combined. A gray change may be the calibration.")
    if gray_change > 0.05 and red is not None and red < 2:
        warnings.append(f"The change is gray ({100 * gray_change:.0f} percent, same at every wavelength). Check the star ensemble gains before calling it astrophysical.")
    if samp and explained == len(samp):
        warnings.append("Every channel difference is within what the wavelength sampling and noise allow.")
    diff = None
    if len(visits) >= 2:
        a, b = F[:, 0], F[:, -1]
        z = (b - a) / np.sqrt(E[:, 0] ** 2 + E[:, -1] ** 2)
        diff = [None if not np.isfinite(x) else round(float(x), 2) for x in z]
    feats = []
    for lam, name, kind in FEATURES:
        ch = [c for c in range(1, 103) if abs(channel_center(c) - lam) / lam < 0.03]
        feats.append(dict(um=lam, name=name, kind=kind, channels=ch, measured=bool(any(np.isfinite(F[c - 1]).any() for c in ch)),
                          blank=bool(set(ch) & set(BLANK_CHANNELS))))
    by_det = {}
    for r in rows:
        by_det.setdefault(r["det"], []).append(r["f"] / max(np.nanmedian(F[np.isfinite(F)]), 1e-9))
    return dict(visits=visits, flux=_l(F), sigma=_l(E), lam=_l(L, 4), state=state.tolist(), gray_scale=gray, gray_change=round(gray_change, 4),
                stability=dict(reduced_chi2=None if red is None else round(red, 2), dof=dof, score=score,
                               meaning="1 means one spectral shape fits every visit (after a gray scale). Near 0 means the shape changed."),
                difference_z_first_last=diff, sampling_court=dict(rows=samp, explained=explained, tested=len(samp)), features=feats,
                detectors={d: dict(n=len(v), median_rel=round(float(np.median(v)), 3), spread=round(float(np.std(v)), 3)) for d, v in sorted(by_det.items())},
                warnings=warnings, blank_channels=list(BLANK_CHANNELS))


def local_slope(F, L, c):
    xs, ys = [], []
    for k in range(max(0, c - 3), min(102, c + 4)):
        ok = np.isfinite(F[k]) & np.isfinite(L[k])
        if ok.any():
            xs.append(float(np.mean(L[k, ok])))
            ys.append(float(np.mean(F[k, ok])))
    if len(xs) < 2 or np.ptp(xs) <= 0:
        return 0.0
    return float(np.polyfit(xs, ys, 1)[0])


def _l(a, k=2):
    return [[None if not np.isfinite(x) else round(float(x), k) for x in row] for row in a]


# ---------------------------------------------------------------- 3. Instrument forensics

def forensics(cand, field, rec):
    f, d = cand["features"], cand["dossier"]
    tests = {t["id"]: t for t in d.get("tests", [])}
    arr = d.get("artefact_array")
    one_array = f.get("a5", 0) > 0.8
    det_rows = rec["detectors"]

    def mod(name, question, product, measured, verdict):
        return dict(module=name, question=question, product=product, measured=measured, verdict=verdict)

    out = [
        mod("Crosstalk Atlas", "Is there a bright star one or two readout channels (64 or 128 columns) away?", CALIBRATION_PRODUCTS["crosstalk"],
            tests.get("Q3", {}).get("result", "not run"), "explains" if tests.get("Q3", {}).get("outcome") == "against" or "crosstalk" in str(tests.get("Q3", {}).get("result", "")).lower() and "no bright" not in str(tests.get("Q3", {}).get("result", "")).lower() else "does not explain"),
        mod("Aurora Interference", "Is the signal confined to band 1, where auroral emission lives?", CALIBRATION_PRODUCTS["aurora template (band 1)"],
            f"Array carrying most signal: {arr or 'none dominant'}.", "possible" if one_array and arr == 1 else "does not explain"),
        mod("Helium Emission", "Does the change sit in the channel holding He I 1.083 micron?", CALIBRATION_PRODUCTS["helium template (bands 1, 2)"],
            _he(rec), "possible" if _he(rec).startswith("Largest") else "does not explain"),
        mod("Shuttle Glow", "Is the signal confined to band 5?", CALIBRATION_PRODUCTS["shuttle glow template (band 5)"],
            f"Array {arr or 'none'} dominates." if one_array else "Seen in several arrays.", "possible" if one_array and arr == 5 else "does not explain"),
        mod("Dead Pixel Observatory", "Does it sit on nonfunctional or flagged pixels?", CALIBRATION_PRODUCTS["nonfunctional pixels"],
            f"Flagged in {100 * f.get('flagfrac', 0):.0f} percent of exposures.", "explains" if f.get("flagfrac", 0) > 0.5 else "does not explain"),
        mod("Nonlinearity Court", "Is the source bright enough for detector nonlinearity?", CALIBRATION_PRODUCTS["nonlinearity"],
            f"Deep signal to noise {f.get('deep_snr', 0):.0f}.", "cannot test without Q_nl and Qmax" if f.get("deep_snr", 0) > 300 else "does not explain"),
        mod("Read Noise Laboratory", "Is the noise of these exposures larger than the file says?", CALIBRATION_PRODUCTS["read noise"],
            f"Worst noise scale {max(e['noise_k'] for e in field['field']['exposures']):.2f}.", "does not explain" if (d.get("robustness", {}).get("rows") or [{}])[0].get("survives", True) else "possible"),
        mod("Gain Calibration Monitor", "Do the star ensemble gains move like the candidate?", CALIBRATION_PRODUCTS["absolute gain"],
            f"Gain warnings: {sum(r['warn'] for r in field['field']['guardian']['rows'])}. Candidate gray change {100 * rec['gray_change']:.0f} percent.",
            "possible" if any(r["warn"] for r in field["field"]["guardian"]["rows"]) else "does not explain"),
        mod("Zodiacal Light Auditor", "Would a background scaling error make a point source?", CALIBRATION_PRODUCTS["zodi scaling"],
            "Zodiacal light is smooth on arcminute scales; a point change needs a point cause.", "does not explain" if 0.75 <= f.get("sharp", 1) <= 1.4 else "cannot test"),
        mod("PSF Forensics", "Does its shape follow the instrument ePSF?", CALIBRATION_PRODUCTS["ePSF"],
            f"Width ratio {f.get('sharp', 0):.2f} (1 is the optics).", "explains" if f.get("sharp", 1) < 0.6 else "does not explain"),
    ]
    if f.get("partner") == 0 and f.get("a4", 0) > 0.6:
        out.append(mod("Simultaneous array", "Does the array behind the dichroic see it at the same moment?", "frame partner",
                       "No, and one exposure carries it.", "explains"))
    causes = [m for m in out if m["verdict"] == "explains"]
    possible = [m for m in out if m["verdict"] == "possible"]
    expl = ("Instrumental explanation supported by: " + ", ".join(m["module"] for m in causes) + ".") if causes else \
        ("No instrumental test explains it. Still open: " + ", ".join(m["module"] for m in possible) + ".") if possible else \
        "No instrumental test explains it; it survives instrument forensics."
    return dict(modules=out, explanation=expl, instrumental=bool(causes))


def _he(rec):
    ch = [channel_of(1.083, 1), channel_of(1.083, 2)]
    z = rec.get("difference_z_first_last") or []
    zz = [(i + 1, abs(v)) for i, v in enumerate(z) if v is not None]
    if not zz:
        return "No two visits to compare."
    top = max(zz, key=lambda t: t[1])
    return f"Largest change in channel {top[0]}, the helium channel." if top[0] in ch else f"Largest change in channel {top[0]}, not the helium channel {ch[0]}."


def calibration_impact(field, cands_lab):
    """How the candidate population shrinks as each correction is added."""
    micro = [m for m in field["field"].get("microscope", []) if m.get("fair")]
    stages = []
    if micro:
        keys = [x["key"] for x in micro[0]["layers"]]
        for k in keys:
            stages.append(dict(stage=next(x["label"] for x in micro[0]["layers"] if x["key"] == k), count=sum(next((x["count"] for x in m["layers"] if x["key"] == k), 0) for m in micro)))
    det = field["field"]["detections"]
    stages.append(dict(stage="Detections of three methods (P, D, A)", count=det["P"] + det["D"] + det["A"]))
    stages.append(dict(stage="Linked candidates", count=len(field["candidates"])))
    stages.append(dict(stage="After instrument forensics", count=sum(not c["forensics"]["instrumental"] for c in cands_lab)))
    stages.append(dict(stage="Surviving sky candidates (engine says sky and forensics clean)",
                       count=sum(not c["forensics"]["instrumental"] and c["verdict"] in ("moving", "variable", "transient") for c in cands_lab)))
    return stages


# ---------------------------------------------------------------- 8. Observation optimizer: expected information gain

def _entropy(p):
    p = np.asarray(p, float)
    p = p[p > 1e-12]
    return float(-(p * np.log2(p)).sum())


def eig(prior, means, sigmas, n=2000, seed=1):
    """Monte Carlo expected information gain (bits) of one scalar measurement."""
    rng = np.random.default_rng(seed)
    p = np.asarray(prior, float) / np.sum(prior)
    mu, sd = np.asarray(means, float), np.asarray(sigmas, float)
    h = rng.choice(len(p), n, p=p)
    y = rng.normal(mu[h], sd[h])
    like = np.exp(-0.5 * ((y[:, None] - mu[None]) / sd[None]) ** 2) / sd[None]
    post = like * p[None]
    post /= post.sum(1, keepdims=True)
    return max(0.0, _entropy(p) - float(np.mean([_entropy(q) for q in post])))


def optimizer(cand, field, rec):
    probs = cand["post"].get("probs") or {}
    H = [h for h in ("moving", "variable", "transient", "artefact", "null") if h in probs]
    prior = np.array([max(probs[h], 1e-3) for h in H])
    mo = cand["dossier"]["motion"]
    pm = abs(mo.get("pm_px_yr") or 0.0)
    err = mo.get("err") or 0.05
    amp = max(cand["features"].get("amp", 0.0), 0.05)
    opts = []
    # A. Position after half a year: movers shift, others do not.
    shift = {h: (max(pm, 0.3) * 0.5 if h == "moving" else 0.0) for h in H}
    opts.append(("Next visit, about 182 days later, same array", "position offset (pixels)", shift, {h: math.hypot(err, 0.05) for h in H},
                 "Six months distinguishes slow motion from fixed position variability."))
    # B. Brightness at a new epoch.
    fl = {h: amp if h == "variable" else (1.0 if h == "transient" else 0.0) for h in H}
    opts.append(("Fair pair at a new epoch, same channel", "fractional brightness change", fl, {h: (0.5 * amp if h == "variable" else 0.1) for h in H},
                 "A same color pair removes the wavelength sampling explanation of a brightness change."))
    # C. Partner array at the same moment: sky sources appear in both, artefacts in one.
    pa = {h: 0.0 if h in ("artefact", "null") else 1.0 for h in H}
    opts.append(("Simultaneous partner array behind the dichroic", "detected in partner (0 or 1)", pa, {h: 0.2 for h in H},
                 "An artefact lives in one array; the sky reaches both arrays at the same moment."))
    # D. Repeat exposure within the visit at the same color.
    rp = {h: 0.0 if h == "artefact" else 1.0 for h in H}
    opts.append(("Repeat exposure in the same visit, same color", "present again (0 or 1)", rp, {h: 0.25 for h in H},
                 "A cosmic ray or glitch never repeats; a sky source does."))
    ranked = []
    for name, obs, m, s, why in opts:
        ranked.append(dict(option=name, observable=obs, bits=round(eig(prior, [m[h] for h in H], [s[h] for h in H]), 3), why=why,
                           predictions={h: round(m[h], 3) for h in H}))
    ranked.sort(key=lambda x: -x["bits"])
    return dict(hypotheses=H, prior=[round(float(x), 3) for x in prior / prior.sum()], prior_entropy_bits=round(_entropy(prior / prior.sum()), 3), ranked=ranked,
                recommended=ranked[0], visibility=visibility(cand["ra"], cand["dec"]),
                rule="t* = argmax_t E[H(H|D) - H(H|D, D_t)]. Predictions come from the measured motion, amplitude and the instrument geometry.")


def visibility(ra, dec):
    """SPHEREx scans near 90 degrees from the Sun: a place is observed when the Sun's ecliptic longitude is lambda +/- 90 degrees."""
    try:
        from astropy.coordinates import SkyCoord, GeocentricTrueEcliptic
        import astropy.units as u
        lam = float(SkyCoord(ra * u.deg, dec * u.deg).transform_to(GeocentricTrueEcliptic()).lon.deg)
        beta = float(SkyCoord(ra * u.deg, dec * u.deg).transform_to(GeocentricTrueEcliptic()).lat.deg)
    except Exception:
        return None
    from datetime import date, timedelta
    windows = []
    for s in ((lam + 90) % 360, (lam - 90) % 360):
        day = (s - 280.0) / 0.9856  # solar longitude is about 280 degrees on January 1
        windows.append((date(2027, 1, 1) + timedelta(days=day % 365.25)).isoformat())
    return dict(ecliptic_lon=round(lam, 2), ecliptic_lat=round(beta, 2), next_windows_2027=sorted(windows),
                note="Approximate. Near the ecliptic poles SPHEREx sees the field nearly every orbit.")


# ---------------------------------------------------------------- 9. Validation observatory

def wilson(k, n, z=1.96):
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 3), round(min(1, c + h), 3)]


def benjamini_hochberg(pvals, q=0.05):
    p = np.asarray(pvals, float)
    o = np.argsort(p)
    m = len(p)
    keep = np.zeros(m, bool)
    if m:
        ok = p[o] <= q * (np.arange(1, m + 1) / m)
        if ok.any():
            keep[o[: np.max(np.where(ok)[0]) + 1]] = True
    return keep.tolist()


def validation(field, cands_lab, val, real):
    from scipy.stats import norm
    sig = []
    for c in field["candidates"]:
        rows = c["dossier"]["robustness"].get("rows") or [{}]
        sig.append(float(rows[0].get("value") or 0))
    p = [float(2 * norm.sf(abs(s))) for s in sig]
    keep = benjamini_hochberg(p)
    chance = val["controls"]["null_candidates_mean"] if val else None
    out = dict(fdr=dict(q=0.05, tested=len(p), kept=int(sum(keep)), rows=[dict(id=c["id"], significance=round(s, 1), p=float(f"{pp:.2e}"), kept=k)
                                                                          for c, s, pp, k in zip(field["candidates"], sig, p, keep)]),
               expected_by_chance=chance, chance_note="Mean false candidates per empty simulated field (40 null fields). Compare with the count here.",
               negative_controls=field["field"].get("controls", {}))
    if real:
        planted = real.get("planted_all") or sum(f.get("score", {}).get("planted", 0) for f in real.get("fields", []))
        found = sum(f.get("score", {}).get("found", 0) for f in real.get("fields", []))
        out["real_vs_simulated"] = dict(real=dict(found=found, planted=planted, fraction=round(found / max(planted, 1), 3), interval=wilson(found, planted)),
                                        simulated_test_accuracy=round(val["unknown"]["accuracy_when_decided"], 3) if val else None,
                                        lesson="Simulated performance does not predict real performance. Real QR3 recovery is far lower.")
    if val:
        out["sensitivity"] = {k: {m: dict(n=v["n"], fraction=round(v["fraction"], 3), interval=[round(v["lo"], 3), round(v["hi"], 3)]) for m, v in d.items()}
                              for k, d in val["completeness"].items()}
    out["uncertainty_reports"] = [dict(id=c["id"], **c["uncertainty"]) for c in cands_lab]
    return out


def uncertainty(cand, rec):
    """Six separate confidences. Never one number."""
    m, f = cand["dossier"]["motion"], cand["features"]
    rows = cand["dossier"]["robustness"].get("rows") or [{}]
    track = m.get("track") or [{}]
    return dict(detection=f"{rows[0].get('value', 0):.1f} sigma, survives {sum(r.get('survives', False) for r in rows)} of {len(rows)} reanalyses",
                position=f"{max((t.get('ex') or 0) for t in track):.3f} px worst track error" if m.get("n", 0) else "single detection",
                motion=f"{m.get('pm_arcsec_yr') or 0:.3f} arcsec/yr at {m.get('sig') or 0:.1f} sigma" if m.get("n", 0) >= 2 else "not measurable",
                brightness=f"variability z {f.get('var_z', 0):.1f}, gray change {100 * rec['gray_change']:.0f} percent",
                spectral=f"stability score {rec['stability']['score']}" if rec["stability"]["score"] is not None else "not enough channels",
                interpretation=f"{cand['post'].get('verdict') or 'unknown'} (engine trained on the simulated sky only)")


# ---------------------------------------------------------------- 6. Planet X laboratory

def planetx(iras=(35.74075, -48.5125), akari=(35.18379, -49.2135), years=23.0):
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    sep = SkyCoord(*iras, unit="deg").separation(SkyCoord(*akari, unit="deg")).deg
    rate = sep / years
    d_circ = (360.0 / rate) ** (2 / 3)  # circular orbit: n = 360 / d^1.5 degrees per year
    sens = [dict(d_au=d, parallax_arcsec_6mo=round(2 * 206265 / d, 1), orbit_arcsec_per_yr=round(360 / d ** 1.5 * 3600, 2),
                 spherex_pixels_6mo=round(2 * 206265 / d / 6.15, 1)) for d in (100, 300, 500, 700, 1000)]
    rng = np.random.default_rng(9)
    n = 20000
    a = rng.uniform(380, 800, n)
    e = rng.uniform(0.1, 0.45, n)
    M = rng.uniform(0, 2 * np.pi, n)
    E = M.copy()
    for _ in range(30):
        E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
    r = a * (1 - e * np.cos(E))
    def for_v(d, mass, alb):  # reflected V magnitude at opposition: Vsun + 5 log(r delta) - 2.5 log(p R^2), radius 6371 km x M^0.55
        rad_au = 6371.0 * mass ** 0.55 / 1.496e8
        return -26.74 + 5 * math.log10(d * (d - 1)) - 2.5 * math.log10(alb * rad_au ** 2)
    v = np.array([for_v(x, 6.0, 0.4) for x in r[:4000]])
    sel = dict(model="a 380 to 800 au, e 0.1 to 0.45, uniform mean anomaly, mass 6 Earth, albedo 0.4 (all assumptions)",
               fraction_brighter_than_V21=round(float(np.mean(v < 21)), 3), fraction_brighter_than_V24=round(float(np.mean(v < 24)), 3),
               median_distance_au=round(float(np.median(r)), 0),
               meaning="Most of a distant orbit is near aphelion, where the planet is faintest: a survey that saw nothing has not searched most of the orbit.")
    return dict(published_pair=dict(iras=iras, akari=akari, separation_arcmin=round(sep * 60, 2), baseline_years=years, rate_deg_per_yr=round(rate, 4),
                                     circular_orbit_distance_au=round(d_circ, 0),
                                     falsification="Two positions fit infinitely many orbits. Predict the position for a new epoch; a non detection there, at a depth that should see it, rejects that orbit.",
                                     status="candidate pair from the literature, not a discovery"),
                motion_sensitivity=sens, selection=sel,
                ladder=["prediction", "candidate", "statistically supported detection", "independent recovery", "confirmed discovery"])


# ---------------------------------------------------------------- 7. Ice and molecule laboratory

ICES = [(3.05, 0.25, "H2O ice"), (4.27, 0.06, "CO2 ice"), (4.67, 0.05, "CO ice"), (3.53, 0.05, "CH3OH ice"), (4.62, 0.06, "OCN- ice")]


def ice_lab(rec):
    """Band depth tau = -ln(F / Fc) with a linear continuum from the channels beside the band."""
    out = []
    F = np.array([[np.nan if x is None else x for x in r] for r in rec["flux"]])
    E = np.array([[np.nan if x is None else x for x in r] for r in rec["sigma"]])
    lam = np.array([channel_center(c) for c in range(1, 103)])
    f, e = np.nanmean(F, 1), np.sqrt(np.nanmean(E ** 2, 1))
    for c0, w, name in ICES:
        inn = np.where((np.abs(lam - c0) < max(w / 2, c0 / 120)) & np.isfinite(f))[0]
        side = np.where((np.abs(lam - c0) > w) & (np.abs(lam - c0) < 3 * w + 0.1) & np.isfinite(f))[0]
        res = c0 / (35 if c0 < 3.82 else 112 if c0 < 4.42 else 128)
        blend = [n for c, _, n in ICES if n != name and abs(c - c0) < 2 * res]
        if len(inn) == 0 or len(side) < 2:
            out.append(dict(feature=name, um=c0, tau=None, note="Not sampled in these exposures.", blended_with=blend))
            continue
        k = np.polyfit(lam[side], f[side], 1)
        fc = np.polyval(k, lam[inn])
        tau = -np.log(np.clip(f[inn] / fc, 1e-6, None))
        te = e[inn] / np.abs(f[inn])
        out.append(dict(feature=name, um=c0, tau=round(float(np.mean(tau)), 3), tau_err=round(float(np.sqrt(np.mean(te ** 2)) / math.sqrt(len(inn))), 3),
                        channels=(inn + 1).tolist(), blended_with=blend, note="Schematic continuum. Compare with laboratory ice spectra before any claim."))
    return out


# ---------------------------------------------------------------- 10. Evidence passport

def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str).encode()


def passport(field, cand, lab):
    rec = field["record"]
    body = dict(schema="chronos-evidence-passport/1.0", candidate=cand["id"], field=field["meta"].get("key"),
                data=dict(exposures=rec["inputs"]["exposures"], releases=rec["inputs"]["releases"], label=field["meta"].get("label"),
                          release_check=release_check(rec["inputs"]["releases"])),
                processing=dict(thresholds=rec["thresholds"], code=rec["code"], versions=rec["versions"]),
                science=dict(verdict=cand["post"].get("verdict"), probs=cand["post"].get("probs"), stability=lab["spectral"]["stability"],
                             forensics=lab["forensics"]["explanation"], uncertainty=lab["uncertainty"], next_observation=lab["optimizer"]["recommended"]["option"]),
                validation=dict(robustness=cand["dossier"]["robustness"], controls=field["field"].get("controls")),
                limits="Simulated sky unless data.label says REAL SPHEREx. SHA-256 detects changes; it does not prove authorship or truth.")
    body = json.loads(canonical(body))
    sections = {k: hashlib.sha256(canonical(v)).hexdigest() for k, v in body.items()}
    return dict(body=body, section_sha256=sections, seal=hashlib.sha256(canonical(body)).hexdigest(),
                verify="sha256 of the canonical JSON of body (sorted keys, no spaces) equals seal.")


def verify(p):
    return hashlib.sha256(canonical(p["body"])).hexdigest() == p.get("seal")


def diff(p1, p2):
    a, b = p1["section_sha256"], p2["section_sha256"]
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


# ---------------------------------------------------------------- 9b. Human observatory

def fleiss_kappa(table):
    """table[i][j] = raters who put case i in class j."""
    t = np.asarray(table, float)
    n = t.sum(1)[0]
    if len(t) == 0 or n < 2:
        return None
    p = t.sum(0) / t.sum()
    P = ((t * t).sum(1) - n) / (n * (n - 1))
    pe = float((p * p).sum())
    return None if pe == 1 else round(float((P.mean() - pe) / (1 - pe)), 3)


def cohen_kappa(a, b):
    labs = sorted(set(a) | set(b))
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(k) / n) * (b.count(k) / n) for k in labs)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


GLOSSARY = [("change", "পরিবর্তন"), ("evidence", "প্রমাণ"), ("measurement", "পরিমাপ"), ("uncertainty", "অনিশ্চয়তা"), ("wavelength", "তরঙ্গদৈর্ঘ্য"),
            ("spectrum", "বর্ণালী"), ("infrared", "অবলোহিত"), ("detector", "শনাক্তকারী যন্ত্র"), ("artefact", "যান্ত্রিক ত্রুটি"), ("candidate", "প্রার্থী"),
            ("discovery", "আবিষ্কার"), ("hypothesis", "অনুমান"), ("falsification", "ভুল প্রমাণের পরীক্ষা"), ("orbit", "কক্ষপথ"), ("brightness", "উজ্জ্বলতা"),
            ("motion", "গতি"), ("calibration", "মাপাঙ্ক নির্ধারণ"), ("ice", "বরফ"), ("star", "তারা"), ("planet", "গ্রহ")]


# ---------------------------------------------------------------- 5. Real astronomical case studies (need live archive access)

CASES = [
    dict(key="3i_atlas", name="3I/ATLAS, interstellar comet", kind="moving object", data="SPHEREx spectral images at JPL Horizons predicted positions (target '3I', also designated C/2025 N1)",
         tests=["motion along the predicted track", "coma growth between epochs", "spectral features with low signal to noise flagged per channel"],
         status="Adapter ready: run live mode or the Kaggle notebook with internet; not run in this build."),
    dict(key="splices", name="SPLICES ice targets in a SPHEREx field", kind="ice and molecules", data="SPLICES catalogue at IRSA (doi:10.26131/IRSA554), table found by TAP_SCHEMA search",
         tests=["H2O, CO2, CO band depths", "epoch to epoch band depth change", "variability against spectral signature"], status="Query function splices_query(); needs internet."),
    dict(key="rwaur", name="RW Aurigae, young star", kind="young stellar object", data="SPHEREx DR1 + QR3 spectral images", tests=["accretion brightening versus extinction (colour of the change)", "Br gamma"], status="Simulated analogue in the observatory; live mode available."),
    dict(key="wise0855", name="WISE 0855 and Epsilon Indi B, brown dwarfs", kind="brown dwarf laboratory", data="SPHEREx DR1 + QR3", tests=["H2O and CH4 band depths", "variability"], status="Simulated analogue; live mode available."),
    dict(key="rdra", name="R Draconis, Mira variable", kind="variable star observatory", data="SPHEREx DR1 + QR3; compare with an optical light curve", tests=["phase-dependent H2O bands"], status="Simulated analogue; real injection run in QR3."),
]


def splices_query(ra, dec, radius_deg=0.1):
    """SPLICES sources near a position. The table name is discovered, never guessed."""
    from connectors import fetch
    tap = "https://irsa.ipac.caltech.edu/TAP/sync"
    names = fetch(tap, dict(QUERY="SELECT table_name FROM TAP_SCHEMA.tables WHERE LOWER(table_name) LIKE '%splices%'", FORMAT="csv")).decode().split()[1:]
    if not names:
        raise RuntimeError("No SPLICES table is listed in the IRSA TAP schema.")
    q = f"SELECT * FROM {names[0].strip(chr(34))} WHERE CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra},{dec},{radius_deg}))=1"
    return dict(table=names[0], csv=fetch(tap, dict(QUERY=q, FORMAT="csv")).decode())


def read_allsky_cube(path):
    """DR1 All-Sky Cube (Npix*_cube.fits): IMAGE, NHITS, FLAGS, SPECTRAL_CHANNELS. NHITS is a contributor count, not an error."""
    from chronos_addons.spectral import load_allsky_cube
    return load_allsky_cube(path)


# ---------------------------------------------------------------- all ten

def laboratory(field, val=None, real=None):
    np.seterr(all="ignore")
    import warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    cands = []
    for c in field["candidates"]:
        rec = spectral_record(c, field)
        lab = dict(id=c["id"], verdict=c["post"].get("verdict"), truth=c.get("truth"), spectral=rec)
        lab["forensics"] = forensics(c, field, rec)
        lab["optimizer"] = optimizer(c, field, rec)
        lab["uncertainty"] = uncertainty(c, rec)
        lab["ice"] = ice_lab(rec)
        lab["passport"] = passport(field, c, lab)
        cands.append(lab)
    return dict(meta=field["meta"], label=field["meta"].get("label"), releases=release_check(field["record"]["inputs"]["releases"]),
                release_table=RELEASES, default_collections=DEFAULT_COLLECTIONS, calibration_products=CALIBRATION_PRODUCTS,
                candidates=cands, calibration_impact=calibration_impact(field, cands), validation=validation(field, cands, val, real),
                planetx=planetx(), glossary=GLOSSARY, cases=CASES,
                identity="CHRONOS does not merely search for changes. It investigates whether they are real, explains how they could have occurred, and names the evidence that would prove it wrong.")
