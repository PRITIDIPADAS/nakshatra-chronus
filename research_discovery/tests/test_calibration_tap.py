import numpy as np
from astropy.table import Table

from research_discovery.spherex.probe_calibration_tap import normalize_tap_results


def test_normalize_tap_results_accepts_astropy_table_directly():
    expected = Table({"uri": ["https://example.test/a.fits"], "detector": [2]})
    assert normalize_tap_results(expected) is expected


def test_normalize_tap_results_accepts_to_table_method():
    expected = Table({"uri": ["https://example.test/a.fits"]})

    class MethodResult:
        def to_table(self):
            return expected

    assert normalize_tap_results(MethodResult()) is expected


def test_normalize_tap_results_accepts_to_table_property():
    expected = Table({"uri": ["https://example.test/a.fits"]})

    class PropertyResult:
        to_table = expected

    assert normalize_tap_results(PropertyResult()) is expected


def test_normalize_tap_results_uses_pyvo_column_fallback():
    class ColumnResult:
        fieldnames = ["uri", "detector"]

        def getcolumn(self, name):
            return {
                "uri": np.array(["https://example.test/a.fits"]),
                "detector": np.array([2]),
            }[name]

    table = normalize_tap_results(ColumnResult())
    assert table.colnames == ["uri", "detector"]
    assert table["uri"][0] == "https://example.test/a.fits"
    assert int(table["detector"][0]) == 2


def test_normalize_tap_results_rejects_unrecognised_result():
    class BrokenResult:
        pass

    try:
        normalize_tap_results(BrokenResult())
    except TypeError as exc:
        assert "cannot be converted" in str(exc)
    else:
        raise AssertionError("unrecognised TAP result must fail closed")
