"""The observatory: practice sky rules, three detectors, the engine, the investigator, the API and the live path offline."""
import io
import json
import math

import numpy as np
import pytest
from astropy.io import fits
from fastapi.testclient import TestClient

import app as A
import connectors as cn
import core
import engine
import investigate as I
import observatory as O
import pipeline as P
import sky

C = TestClient(A.app)


@pytest.fixture(scope="module")
def demo():
    spec = sky.make_spec(3)
    E, truth, cat = sky.render(spec)
    return I.investigate(E, cat, center=spec["center"], truth=truth, spec=spec, meta=dict(mode="sim", key="demo"))


def test_practice_sky_follows_spherex_rules():
    spec = sky.make_spec(3)
    E, truth, cat = sky.render(spec)
    assert len(E) == 4 * 6 * 2
    for e in E:
        lo, hi, R = core.BANDS[e.det]
        assert lo <= e.lam <= hi and e.label == "SIMULATION"
    by = {}
    for e in E:
        by.setdefault(e.frame, set()).add(e.det)
    assert all(v in ({1, 4}, {2, 5}, {3, 6}) for v in by.values())  # two arrays, one on each side of the dichroic, share a moment
    a = [e for e in E if e.det == 2 and e.id.endswith("s0")]
    shift = [(x.lam - a[0].lam) / x.bw for x in a]
    assert abs(shift[1]) < 0.2 and 0.3 < shift[2] < 0.7  # surveys 3 and 4 sit half a channel away
    kinds = {t["kind"] for t in truth}
    assert kinds == {"moving", "variable", "transient", "artefact"}
    assert any(s["name"].startswith("bright star") for s in cat)  # the crosstalk parent is in the catalog


def test_empty_field_gives_no_candidate():
    spec = sky.make_spec(50001, center=(40.0, -20.0), events="none")
    E, truth, cat = sky.render(spec)
    core.prepare(E)
    S = P.run(E, cat, center=spec["center"])
    assert len(S["cands"]) <= 1 and not truth


def test_every_planted_change_is_found_and_disagreement_is_kept(demo):
    sc = demo["score"]
    assert not sc["missed"], sc["missed"]
    pats = {c["truth_sub"]: c["methods"] for c in demo["candidates"]}
    assert pats["appear"] != "PDA"  # a change between visits with no fair color match escapes the difference method
    assert "D" in pats["flare"] and "A" in pats["glitch"]


def test_engine_probabilities_and_unknown():
    m = engine.model()
    assert m is not None and m["classes"] == list(sky.CLASSES)
    f = {k: 0.0 for k in m["features"]}
    p = engine.posterior(f)
    assert abs(sum(p["probs"].values()) - 1) < 1e-9 and 0 <= p["entropy"] <= 1
    odd = dict(f, a1=40.0, var_z=-30.0, deep_snr=-20.0)
    assert engine.posterior(odd)["unknown"]  # far from training: the engine must say unknown
    pr = engine.posterior(f, prior=dict(moving=50.0))
    assert pr["probs"]["moving"] > p["probs"]["moving"]


def test_investigation_is_complete_and_every_sentence_has_evidence(demo):
    assert demo["candidates"] and demo["record"]["seal"] and demo["field"]["microscope"]
    for c in demo["candidates"]:
        d = c["dossier"]
        ids = {e["id"] for e in d["evidence"]}
        assert d["report"] and all(s["refs"] and set(s["refs"]) <= ids for s in d["report"])
        assert all(t["outcome"] in ("supports", "challenges", "neutral", "not run") for t in d["tests"])
        assert d["robustness"]["total"] == 1 + 5 + demo["visits"] + 1
        assert len(d["debate"]["analysts"]) == 3 and d["chain"] and d["graph"]["nodes"][0]["id"] == "C"
        assert set(c["post"]["probs"]) == set(sky.CLASSES)


def test_microscope_funnel_removes_false_change(demo):
    for L in demo["field"]["microscope"]:
        if L["fair"]:
            n = [x["count"] for x in L["layers"]]
            assert n[-1] <= n[0] and n[-1] <= 4


def test_guardian_catches_the_old_release(demo):
    bad = [r for r in demo["field"]["guardian"]["rows"] if r["release"] == "QR2"]
    assert bad and bad[0]["warn"] and abs(bad[0]["gain"] - 0.95) < 0.02


def test_crosstalk_test_finds_the_parent_star(demo):
    g = next(c for c in demo["candidates"] if c["truth_sub"] == "ghost")
    q = next(t for t in g["dossier"]["tests"] if "crosstalk" in t["question"])
    assert q["outcome"] == "supports"


def test_mover_track_and_motion_stack(demo):
    m = next(c for c in demo["candidates"] if c["truth"] == "moving")
    mo = m["dossier"]["motion"]
    assert mo["n"] == 4 and mo["sig"] > 5
    true_pm = math.hypot(1.4, -0.9)
    assert abs(mo["pm_arcsec_yr"] - true_pm) < 4 * mo["err"] * core.PIX + 0.3
    assert m["dossier"]["cutouts"].get("motion_stack")


def test_api_fields_resolve_planet_and_validation():
    assert {f["key"] for f in C.get("/api/fields").json()} >= {"demo", "quiet", "barnard"}
    r = C.get("/api/resolve", params=dict(q="17h57m48.5s +04d44m36s")).json()
    assert abs(r["ra"] - 269.452) < 0.01 and abs(r["dec"] - 4.7433) < 0.01
    assert C.get("/api/resolve", params=dict(q="barnard")).json()["key"] == "barnard"
    p = C.get("/api/planetlab", params=dict(d=500, mass=6, albedo=0.4, temp=40)).json()
    assert p["thermal_ab_4p5"] > 60 and "not been discovered" in p["status"] and len(p["ladder"]) == 4
    assert C.get("/api/validation").json()["confusion"]


def test_api_investigate_fast_mode():
    j = C.get("/api/investigate", params=dict(key="quiet", deep=0)).json()
    assert j["meta"]["label"] == "SIMULATION" and len(j["candidates"]) <= 1 and j["field"]["exposures"]
    assert C.get("/api/investigate", params=dict(key="nowhere")).status_code == 404


def test_reproduce_gives_the_same_digest():
    j = C.get("/api/investigate", params=dict(key="quiet")).json()
    r = C.post("/api/reproduce", json=j["record"]).json()
    assert r["ok"] is True


# ---------------------------------------------------------------- live path, offline

def mef(e):
    hd = e.wcs.to_header()
    hd["DETECTOR"], hd["OBSID"], hd["VERSION"], hd["FINAST"] = e.det, e.id, "6.5.6", 0
    hd["CRPIX1A"], hd["CRPIX2A"], hd["CRVAL1A"], hd["CRVAL2A"], hd["CTYPE1A"], hd["CTYPE2A"] = 1.0, 1.0, e.dxy[0], e.dxy[1], "", ""
    fh = fits.Header()
    for name, bit in core.FLAG_BITS.items():
        fh["MP_" + name[:5]] = bit
    hdus = [fits.PrimaryHDU(), fits.ImageHDU(e.img.astype(np.float32), hd, name="IMAGE"), fits.ImageHDU(e.flags.astype(np.int32), fh, name="FLAGS"),
            fits.ImageHDU(e.var.astype(np.float32), name="VARIANCE"), fits.ImageHDU(np.full(e.img.shape, e.zodi, np.float32), name="ZODI")]
    b = io.BytesIO()
    fits.HDUList(hdus).writeto(b)
    return b.getvalue()


def test_live_observatory_offline(monkeypatch):
    T = A.TARGETS["barnard"]
    spec = sky.make_spec(11, target=T, events="demo")
    E, truth, cat = sky.render(spec)
    files = {f"https://example.invalid/f{i:03d}.fits": e for i, e in enumerate(E)}
    rows = [dict(access_url=u, t_min=e.mjd, obs_id=e.id, energy_bandpassname=f"SPHEREx-D{e.det}") for u, e in files.items()]
    lam = {round(e.mjd, 5): {} for e in E}
    for e in E:
        lam[round(e.mjd, 5)][e.det] = (e.lam, e.bw)
    monkeypatch.setattr(cn, "fetch", lambda url, params=None: mef(files[url.split("?")[0]]))
    monkeypatch.setattr(cn, "search", lambda ra, dec, rad=0.1, coll="x", maxrec=0: rows if coll == "spherex_qr3" else [])
    dy = float(core.year(core.SIM_T0)) - 2016.0
    gaia = [dict(ra=s["ra"] - s["pm_ra"] / 3600 / math.cos(math.radians(s["dec"])) * dy, dec=s["dec"] - s["pm_dec"] / 3600 * dy, pmra=1000 * s["pm_ra"],
                 pmdec=1000 * s["pm_dec"], parallax=1000 * s["plx"], phot_g_mean_mag=s["mag"]) for s in cat]
    monkeypatch.setattr(cn, "gaia_cone", lambda ra, dec, rad=0.1, gmax=17.0: gaia)

    def nowise(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(cn, "wise_cone", nowise)
    real_load = cn.load

    def load(row, ra, dec, size, coll):
        e = real_load(row, ra, dec, size, coll)
        hd = files[row["access_url"]]
        e.lam, e.bw, e.lam_ok = hd.lam, hd.bw, True
        return e

    monkeypatch.setattr(cn, "load", load)
    out = json.loads(json.dumps(O.run_field("barnard", "live", deep=False), default=O.I_json))
    assert out["meta"]["label"] == "REAL SPHEREx" and len(out["field"]["exposures"]) == len(E)
    assert all(x["frame"] for x in out["field"]["exposures"])
    mover = [c for c in out["candidates"] if c["dossier"]["motion"]["n"] >= 3 and (c["dossier"]["motion"]["sig"] or 0) > 10]
    assert mover, "Barnard's Star must be found moving from the archive files"


def test_output_is_strict_json_and_southern_coordinates(demo):
    json.dumps(json.loads(json.dumps(demo, default=O.I_json)), allow_nan=False)
    ra, dec, key = O.parse_coords("22h04m10s -56d47m00s")
    assert abs(ra - 331.0417) < 0.01 and abs(dec + 56.7833) < 0.01 and key is None
