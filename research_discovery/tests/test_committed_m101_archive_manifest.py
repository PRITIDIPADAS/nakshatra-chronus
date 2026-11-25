import json
import re
from pathlib import Path


MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "spherex_archive_manifest.M101_DR1_D2.json"
)


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_m101_manifest_contains_one_science_and_three_calibration_products():
    products = load_manifest()["products"]
    assert len(products) == 4
    assert sum(item["role"] == "science" for item in products) == 1
    assert sum(item["role"] == "calibration" for item in products) == 2
    assert sum(item["role"] == "supplemental_calibration" for item in products) == 1
    assert len({item["product_key"] for item in products}) == len(products)
    assert len({item["archive_plane_id"] for item in products}) == len(products)


def test_every_product_has_traceable_identity_and_integrity_fields():
    for product in load_manifest()["products"]:
        assert product["native_uri"].startswith("https://")
        assert product["archive_plane_id"]
        assert product["byte_count"] > 0
        assert re.fullmatch(r"[0-9a-f]{64}", product["sha256"])
        assert product["release"] == "DR1"
        assert product["detector"] == "D2"
        if product["role"] != "science":
            assert re.fullmatch(r"[0-9a-f]{32}", product["archive_md5"])
            assert product["archive_md5_status"] == "pass"


def test_exact_provenance_links_are_not_invented_for_solid_angle_map():
    products = load_manifest()["products"]
    direct = {item["product_type"] for item in products if item.get("provenance_link")}
    assert direct == {"spectral_wcs_cwave_cband", "absolute_gain_matrix"}
    area = next(item for item in products if item["product_type"] == "solid_angle_pixel_map")
    assert area["provenance_link"] is None
    assert "no exact provenance_input" in area["provenance_relation"].lower()


def test_gain_conversion_remains_pending_independent_review():
    gain = next(
        item for item in load_manifest()["products"]
        if item["product_type"] == "absolute_gain_matrix"
    )
    assert gain["gain_to_electron_conversion_review_status"] == "derived_pending_independent_review"
    assert gain["independent_human_reviewed"] is False
    assert gain["invalid_nonpositive_pixels"] == 175


def test_manifest_preserves_single_exposure_claim_boundary():
    manifest = load_manifest()
    assert manifest["scope"]["field"] == "M101"
    assert manifest["scope"]["observation_id"] == "2025W19_2B_0346_1"
    assert manifest["scope"]["exposure_time_s"] == 113.5826
    assert manifest["status"] == "populated"
    assert "not a validated science sample" in manifest["claim_boundary"].lower()
