"""The next steps: Rubin cross match, Hugging Face publishing, the citizen study and the sky tiles. No network is used."""
import importlib.util
import os
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app as A
import connectors as cn
import study

C = TestClient(A.app)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSV = ("oid,ra,dec,ndiasources,firstdiasourcemjdtai,lastdiasourcemjdtai,r_psffluxmean,i_psffluxmean\n"
       "170000000000000001,269.4520,4.6930,12,61100.2,61290.4,5321.0,6012.5\n"
       "170000000000000002,269.4480,4.6933,3,61201.0,61210.9,,\n")


def test_rubin_cone_reads_the_broker_answer(monkeypatch):
    seen = {}

    def fake(url, params=None, cache=True):
        seen.update(url=url, q=params["QUERY"], cache=cache)
        return CSV.encode()
    monkeypatch.setattr(cn, "fetch", fake)
    rows = cn.rubin_cone(269.448, 4.6933, 12)
    assert seen["url"] == cn.ALERCE_TAP and "alerce_tap.lsst_dia_object" in seen["q"] and "CIRCLE('ICRS', 269.448" in seen["q"]
    assert seen["cache"] is False  # alerts change every night
    assert [r["oid"] for r in rows] == ["170000000000000002", "170000000000000001"]  # nearest first
    assert rows[0]["sep_arcsec"] < 1 and rows[0]["r_flux_njy"] is None and rows[1]["n"] == 12


def test_crossmatch_keeps_going_when_one_service_fails(monkeypatch):
    def down(*a, **k):
        raise TimeoutError("broker down")
    monkeypatch.setattr(cn, "rubin_cone", down)
    monkeypatch.setattr(cn, "known_movers", lambda ra, dec, mjd, hw=0.05: dict(fields=["Object name"], data=[["(1) Ceres"]], note="n"))
    r = cn.crossmatch(10.0, -5.0, 61000.0)
    assert r["rubin"] is None and "TimeoutError" in r["errors"]["rubin"] and r["known_bodies"]["n"] == 1
    assert "not a confirmation" in r["summary"] and "September 2027" in r["neo_surveyor"]


def test_crossmatch_endpoint_needs_real_coordinates():
    r = C.get("/api/crossmatch", params=dict(ra=10, dec=-5, mode="sim")).json()
    assert r["rubin"] is None and "Live SPHEREx" in r["note"]


def test_publish_to_hugging_face(monkeypatch):
    import huggingface_hub
    calls = []

    class Api:
        def __init__(self, token=None):
            calls.append(("token", token))

        def create_repo(self, repo, repo_type=None, private=False, exist_ok=False):
            calls.append(("create", repo, repo_type, exist_ok))

        def upload_file(self, path_or_fileobj=None, path_in_repo=None, repo_id=None, repo_type=None, commit_message=None):
            calls.append(("upload", repo_id, path_in_repo, len(path_or_fileobj)))
    monkeypatch.setattr(huggingface_hub, "HfApi", Api)
    pkg = dict(record=dict(seal="ab" * 32), investigation=dict(meta=dict(key="demo")))
    r = cn.publish_hf(pkg, "someone/chronos-records", token="t")
    assert r["ok"] and r["path"] == "records/" + "ab" * 8 + ".json" and r["url"].startswith("https://huggingface.co/datasets/someone/chronos-records/")
    assert ("create", "someone/chronos-records", "dataset", True) in calls and calls[-1][0] == "upload"
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert C.post("/api/publish_hf", json=dict(repo="someone/x", package=pkg)).status_code == 400
    with pytest.raises(ValueError):
        cn.publish_hf(dict(record=dict(seal="not a seal")), "someone/x", token="t")


def fake_field(key, kinds, rng):
    img = dict(w=3, h=3, lo=0.0, hi=1.0, b64="AAAAAAAAAAAA")
    cands = []
    for i, k in enumerate(kinds):
        cands.append(dict(id=f"C{i + 1:02d}", methods="PDA", truth=k, truth_sub=None, post=dict(unknown=False, verdict=k if rng.random() < 0.8 else "null"),
                          dossier=dict(cutouts=dict(visits=[dict(visit=str(v + 1), img=img) for v in range(4)]))))
    return (key, key.title(), dict(candidates=cands))


def test_study_has_fixed_cases_training_and_spaced_repeats():
    rng = np.random.default_rng(3)
    kinds = ["moving", "variable", "transient", "artefact"] * 3
    S = study.make([fake_field(f"f{j}", kinds, rng) for j in range(3)])
    assert len(S["training"]) == 3 and len(S["cases"]) == sum(study.TARGET.values())
    seq = S["sequence"]
    assert len(seq) == len(S["cases"]) + 4 and sum(s["repeat"] for s in seq) == 4
    for k, s in enumerate(seq):
        if s["repeat"]:
            first = next(j for j, q in enumerate(seq) if q["case"] == s["case"])
            assert k - first > 4
    rng2 = np.random.default_rng(3)
    assert S == study.make([fake_field(f"f{j}", kinds, rng2) for j in range(3)])  # same for every participant
    ids = {c["id"] for c in S["cases"]}
    assert not ids & {c["id"] for c in S["training"]}


def test_study_analysis_pools_participants():
    rng = np.random.default_rng(4)
    S = study.make([fake_field(f"f{j}", ["moving", "variable", "transient", "artefact"] * 3, rng) for j in range(3)])

    def export(pid, wrong=()):
        ans = [dict(training=True, answer="moving", confidence="sure")] * 3
        for s in S["sequence"]:
            t = S["cases"][s["case"]]["truth"]
            ans.append(dict(case=s["case"], repeat=s["repeat"], training=False, answer="null" if s["case"] in wrong else t, confidence="sure"))
        return dict(protocol=S["protocol"], participant=pid, answers=ans)
    res = study.analyse(S, [export("a"), export("b"), export("c", wrong=(0, 1))])
    assert res["participants"] == 3 and res["retest_consistency"] == 1.0
    assert 0.5 < res["fleiss_kappa"] <= 1.0 and res["crowd_majority_right"] == 1.0
    assert res["per_participant"][2]["right"] < 1.0
    assert study.fleiss([[3, 0], [0, 3]]) == 1.0


def test_sky_tiles_are_equal_area_and_follow_the_scan():
    pytest.importorskip("astropy_healpix")
    spec = importlib.util.spec_from_file_location("make_sky_tiles", os.path.join(ROOT, "scripts", "make_sky_tiles.py"))
    M = importlib.util.module_from_spec(spec)
    sys.modules["make_sky_tiles"] = M
    spec.loader.exec_module(M)
    T = M.tiles()
    assert len(T) == 48 and all(len(t["outline"]) == 16 for t in T)
    pole = [t for t in T if abs(t["elat"]) > 60]
    plane = min(T, key=lambda t: abs(t["glat"]))
    assert pole and all(M.plan(t)[0] == 6 for t in pole) and M.plan(plane)[1] > M.plan(max(T, key=lambda t: abs(t["glat"])))[1]
    fake = [dict(t, planted=4, called=3, null_called=0, inject_planted=4, inject_called_true=3, true_rate=4 / M.AREA, raw_rate=3 / M.AREA,
                 epochs=M.plan(t)[0]) for t in T[:6]]
    cls = M.correct(fake)
    assert all(abs(q["completeness"] - 0.75) < 1e-9 for q in cls.values())
    s = M.summary(fake, cls)
    assert abs(s["corrected_over_true"] - 1) < 1e-9 and abs(s["raw_over_true"] - 0.75) < 1e-9 and s["within_two_errors"] == 1.0


def test_plain_words_come_only_from_the_numbers():
    card = dict(label="SIMULATION", pair=dict(fair=True, score=91, false_change=dict(predicted=0.012, measured=0.013, excess_sigma=0.4)))
    for lang in ("en", "bn"):
        r = cn.explain(card, lang)
        assert r == dict(text=cn.template(card, lang), source="template")
