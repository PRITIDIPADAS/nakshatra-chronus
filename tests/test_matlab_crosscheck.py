"""The MATLAB/Octave re-implementation in matlab/ must give the same answers as the Python code."""
import json
import math
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import core  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("octave") is None, reason="GNU Octave is not installed")


def motion_case(seed, pm):
    rng = np.random.default_rng(seed)
    n = 10
    mjd = 60800 + np.sort(rng.uniform(0, 400, n))
    t = core.year(mjd)
    tc = t - t.mean()
    e = np.full(n, 0.4)
    X = pm[0] * tc + rng.normal(0, 0.4, n)
    Y = pm[1] * tc + rng.normal(0, 0.4, n)
    fx, fy = core.plx_factors(mjd, 120.0, 30.0)
    d = dict(t=t, X=X, Y=Y, eX=e, eY=e, mjd=mjd, ra=120.0, dec=30.0, idx=list(range(n)))
    return d, dict(t=t.tolist(), X=X.tolist(), Y=Y.tolist(), eX=e.tolist(), eY=e.tolist(), fx=fx.tolist(), fy=fy.tolist())


def exposure(det, lam, bw, rel, zodi):
    return SimpleNamespace(det=det, lam=lam, bw=bw, rel=rel, zodi=zodi, mjd=60800.0, lam_ok=True, id="x",
                           flags=np.zeros((5, 5), int), core=0, img=np.zeros((5, 5)))


def test_octave_matches_python(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "flag_names", lambda e, sl: [])
    monkeypatch.setattr(core, "box", lambda e, r=2: None)
    motions, py_motion = [], []
    for seed, pm in ((1, (0.0, 0.0)), (2, (3.0, -2.0)), (3, (0.8, 0.5))):
        d, case = motion_case(seed, pm)
        motions.append(case)
        py_motion.append(core.motion_fit(d))
    pairs = [(1, 1, 1.60, 1.61, 0.04, 0.04, "dr1", "dr1", 1.0, 1.05),
             (1, 1, 1.60, 1.63, 0.04, 0.04, "dr1", "dr1", 1.0, 1.0),
             (2, 2, 2.40, 2.40, 0.06, 0.06, "dr1", "qr3", 1.0, 1.4),
             (3, 4, 3.00, 3.00, 0.08, 0.08, "dr1", "dr1", 1.0, 1.0)]
    py_pairs = [core.pair_score(exposure(a, la, ba, ra, za), exposure(b, lb, bb, rb, zb))
                for a, b, la, lb, ba, bb, ra, rb, za, zb in pairs]
    rng = np.random.default_rng(7)
    i1, i2 = rng.normal(10, 2, 6), rng.normal(11, 2, 6)
    v1, v2, s = rng.uniform(0.5, 1.5, 6), rng.uniform(0.5, 1.5, 6), rng.uniform(1, 9, 6)
    k, f = 1.07, 0.12
    py_z = (i2 - k * i1) / np.sqrt(v2 + k * k * v1 + (f * s) ** 2)
    wil = [[29, 120], [0, 20], [17, 20], [5, 20]]
    cases = dict(motion=motions,
                 pairs=[dict(det_a=a, det_b=b, lam_a=la, lam_b=lb, bw_a=ba, bw_b=bb, rel_a=ra, rel_b=rb, zodi_a=za, zodi_b=zb, nflag=0)
                        for a, b, la, lb, ba, bb, ra, rb, za, zb in pairs],
                 z=dict(i1=i1.tolist(), i2=i2.tolist(), v1=v1.tolist(), v2=v2.tolist(), k=k, f=f, s=s.tolist()),
                 wilson=wil)
    inp, out = tmp_path / "in.json", tmp_path / "out.json"
    inp.write_text(json.dumps(cases))
    cmd = f"addpath('{os.path.join(ROOT, 'matlab')}'); run_crosscheck('{inp}', '{out}')"
    subprocess.run(["octave", "--no-gui", "-q", "--eval", cmd], check=True, capture_output=True, timeout=300)
    got = json.loads(out.read_text())

    for py, m in zip(py_motion, got["motion"]):
        assert m["model"] == py["model"] and m["verdict"] == py["verdict"]
        assert math.isclose(m["dbic"], py["dbic"], rel_tol=1e-6, abs_tol=1e-6)
        assert math.isclose(m["pm"], py["pm"], rel_tol=1e-6, abs_tol=1e-9)
    for py, m in zip(py_pairs, got["pairs"]):
        assert m["score"] == py[0] and bool(m["fair"]) == py[1]
    assert np.allclose(got["z"], py_z, rtol=1e-12)
    for (h, n), (lo, hi) in zip(wil, got["wilson"]):
        plo, phi = core.wilson(h, n)
        assert math.isclose(lo, plo, abs_tol=1e-12) and math.isclose(hi, phi, abs_tol=1e-12)
