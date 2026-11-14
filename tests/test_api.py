"""Every endpoint, for all five targets, on the practice sky."""
import pytest
from fastapi.testclient import TestClient

import app as A

C = TestClient(A.app)


def get(u):
    r = C.get(u)
    assert r.status_code == 200, (u, r.status_code, r.text[:300])
    return r


def story(key):
    j = get(f"/api/load?t={key}&mode=sim").json()
    assert j["label"] == "SIMULATION" and len(j["exposures"]) == 72 and j["fair_pairs"] > 10
    assert all("mjd" in e and "day" in e and e["forecast"] for e in j["exposures"])
    b = get("/api/bestpair").json()
    p = get(f"/api/pair?a={b['a']}&b={b['b']}").json()
    assert p["fair"] and p["score"] >= 70 and len(p["chips"]) == 6
    assert get(f"/api/partners?ref={b['a']}").json()
    for u in (f"/api/frame/{b['a']}.png", f"/api/frame/{b['a']}.png?to={b['b']}", f"/api/frame/{b['b']}.png?flags=1", f"/api/z/{b['a']}/{b['b']}.png"):
        assert get(u).headers["content-type"] == "image/png"
    w = get(f"/api/witness?i={b['b']}&x={p['at'][0]}&y={p['at'][1]}").json()
    assert w["kind"] in ("sky", "single", "mixed")
    m = get("/api/motion").json()
    s = get("/api/spectrum").json()
    assert len(s["rows"]) == 72
    assert get("/api/noise").json()["rows"]
    r = get("/api/recovery").json()
    assert r["curve"][-1]["completeness"] > 0.8 and r["control"]["rate"] < 0.05
    bh = get("/api/behavior").json()
    card = dict(label=j["label"], pair=p, motion=m, behavior=bh)
    for lang in ("en", "bn"):
        t = C.post("/api/explain", json=dict(card=card, lang=lang)).json()
        assert len(t["text"]) > 40 and t["source"] == "template"
    assert get(f"/api/lapse?ref={b['a']}").json()
    assert get("/api/path").json()["points"]
    assert get("/api/movers?i=0").json()["data"] == []
    return m, bh


@pytest.mark.parametrize("key", list(A.TARGETS))
def test_full_story_runs(key):
    story(key)


def test_each_target_gets_the_right_label():
    want = dict(barnard="Motion candidate", epsindib="Motion candidate", wise0855="Motion candidate",
                rwaur="Variable source candidate", rdra="Variable source candidate")
    for key, label in want.items():
        m, bh = story(key)
        assert bh["label"] == label, (key, bh)
        if key in ("barnard", "epsindib", "wise0855"):
            assert abs(m["pull"]) < 4, (key, m["pull"])
        if key == "barnard":
            assert abs(m["pull_parallax"]) < 4
        if key == "rwaur":
            assert bh["color_dependent"]


def test_wise0855_is_forecast_as_not_visible_at_short_colors():
    j = get("/api/load?t=wise0855&mode=sim").json()
    tags = {(e["det"], e["forecast"]) for e in j["exposures"]}
    assert all((d, "not visible") in tags for d in (1, 2, 3)) and any(t in tags for t in ((6, "visible"), (6, "marginal")))


def test_static_and_lab_endpoints():
    get("/api/load?t=barnard&mode=sim")
    assert "CHRONOS" in get("/").text
    assert get("/extras.js").status_code == 200
    assert set(get("/api/targets").json()) == set(A.TARGETS)
    assert get("/api/planetx?d=500&radius=3&albedo=0.3").json()["H"]
    assert get("/api/blind/3/0.png").headers["content-type"] == "image/png"
    assert "moved" in get("/api/blind/3/answer").json()
    assert get("/api/protocol").json()["seal"]
    assert C.get("/api/load?t=nothing").status_code == 404
    assert C.get("/api/frame/999.png").status_code == 404
