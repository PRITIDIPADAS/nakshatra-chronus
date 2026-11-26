import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("evaluate_holdout", ROOT / "scripts" / "evaluate_holdout.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_holdout_log_scores_as_committed():
    ev = _load()
    res = ev.evaluate(ev.parse((ROOT / "data" / "holdout_run_45835103107.log").read_text()))
    assert [r["field"] for r in res["incomplete"]] == ["Corona_Australis"]
    assert len(res["rows"]) == 5
    assert res["P1"]["rho"] == -0.7 and res["P4"]["rho"] == 1.0
    assert res["P2"]["holds"] and res["P3"]["holds"] and res["adopted"]


def test_decision_does_not_fire_when_the_variant_loses():
    ev = _load()
    fields = {"A": {"status": "completed_calibrated_jy_pilot", "primary": [0, 5, 15], "variant": [0, 3, 10], "ratio": 2.5, "excess": 3.0},
              "B": {"status": "completed_calibrated_jy_pilot", "primary": [2, 8, 16], "variant": [1, 6, 17], "ratio": 1.1, "excess": 1.2}}
    res = ev.evaluate(fields)
    assert not res["P2"]["holds"] and not res["adopted"]
