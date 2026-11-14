import json
import os

import lab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = json.load(open(os.path.join(ROOT, "site", "data", "fields", "demo.json")))
V = json.load(open(os.path.join(ROOT, "data", "validation.json")))
R = json.load(open(os.path.join(ROOT, "data", "real_injection.json")))
L = lab.laboratory(F, V, R)


def test_releases_refuse_silent_qr2_mixing():
    assert not lab.release_check(["spherex_qr2", "spherex_dr1"])["compatible"]
    assert lab.release_check(["spherex_dr1", "spherex_qr3"])["compatible"]
    assert lab.DEFAULT_COLLECTIONS == "spherex_dr1+spherex_qr3"


def test_channels_and_blank_channels():
    assert lab.channel_of(0.751, 1) == 1 and lab.channel_of(4.99, 6) == 102
    c = L["candidates"][0]["spectral"]
    assert all(s == "no data in DR1 cube" for s in c["state"][50] + c["state"][51])
    assert all(x is None for x in c["flux"][50])  # missing channels are never measurements


def test_forensics_finds_planted_artefacts():
    art = [c for c in L["candidates"] if c["truth"] == "artefact"]
    assert sum(c["forensics"]["instrumental"] for c in art) >= 2
    assert not any(c["forensics"]["instrumental"] for c in L["candidates"] if c["truth"] in ("moving", "variable"))
    assert len(L["candidates"][0]["forensics"]["modules"]) >= 10


def test_information_gain_is_bounded():
    assert abs(lab.eig([0.5, 0.5], [0, 10], [1, 1]) - 1.0) < 0.05
    assert lab.eig([0.5, 0.5], [0, 0], [1, 1]) < 0.05


def test_fdr_and_wilson():
    assert lab.benjamini_hochberg([0.001, 0.2, 0.04, 0.9]) == [True, False, False, False]
    lo, hi = lab.wilson(29, 120)
    assert lo < 29 / 120 < hi
    assert L["validation"]["real_vs_simulated"]["real"]["found"] == 29


def test_passport_seal_and_diff():
    p = L["candidates"][0]["passport"]
    assert lab.verify(p)
    q = json.loads(json.dumps(p))
    q["body"]["science"]["verdict"] = "planet"
    assert not lab.verify(q)
    q["section_sha256"]["science"] = "x"
    assert lab.diff(p, q) == ["science"]


def test_kappas_and_planetx():
    assert lab.cohen_kappa(list("aabb"), list("aabb")) == 1.0
    assert lab.fleiss_kappa([[3, 0], [0, 3], [3, 0]]) == 1.0
    pp = L["planetx"]["published_pair"]
    assert 47 < pp["separation_arcmin"] < 48 and "not a discovery" in pp["status"]
