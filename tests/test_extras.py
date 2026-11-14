import core
import extras


def test_planet_x_reach_grows_with_depth():
    r = extras.planetx(500, 3, 0.3, 19.0)
    assert r["four_visit_reach_au"] > r["single_visit_reach_au"] > 100


def test_blind_pair_truth_and_level():
    a, b, moved, q, xy = extras.blind_pair(0)
    assert moved is True and q == 4


def test_blind_algorithm_is_right_on_bright_pairs():
    ok = sum(extras.blind_answer(k)["algo"] == extras.blind_answer(k)["moved"] for k in range(20) if k % 5 >= 2)
    assert ok >= 11


def test_clean_replaces_nan():
    assert extras.clean({"a": float("nan"), "b": [1.0]}) == {"a": None, "b": [1.0]}


def test_lapse_lists_fair_partners_in_date_order():
    extras.S.update(exps=core.prepare(core.sim_field(seed=1)), mode="sim")
    r = extras.lapse(extras.bestpair()["a"])
    assert len(r) >= 2 and [x["mjd"] for x in r] == sorted(x["mjd"] for x in r)


def test_best_pair_is_fair_and_long():
    extras.S.update(exps=core.prepare(core.sim_field(seed=1)), mode="sim")
    b = extras.bestpair()
    E = extras.S["exps"]
    assert core.pair_score(E[b["a"]], E[b["b"]])[1] and b["days"] > 150


def test_star_gain_between_epochs_is_near_one():
    E = core.prepare(core.sim_field(seed=1))
    g, n = core.star_gain(E[0], E[18])
    assert n >= 3 and abs(g - 1) < 0.05


def test_protocol_seal_is_stable_and_has_no_clock():
    a, b = extras.protocol(), extras.protocol()
    assert a["seal"] == b["seal"] and not any("time" in k or "date" in k or "created" in k for k in a)


def test_parallax_search_finds_injected_distance():
    r = extras.planetsearch(1, 800.0, 2.0, 0)
    assert abs(r["top"][0]["d"] - 800) <= 200 and r["top"][0]["snr"] > 6
    assert r["top"][0]["expected_false_alarms"] < 0.01
