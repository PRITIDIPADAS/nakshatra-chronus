import hashlib

from research_discovery.spherex.run_provenance_calibration_audit import (
    build_sql,
    calibration_family_from_uri,
    normalize_archive_uri,
    normalize_release,
    verify_archive_checksum,
)


def test_native_archive_paths_are_normalized_to_exact_irsa_https_urls():
    uri = normalize_archive_uri(
        "ibe/data/spherex/dr1/spectral_wcs/cal-swcs-v5-2026-191/2/file.fits"
    )
    assert uri == (
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/"
        "spectral_wcs/cal-swcs-v5-2026-191/2/file.fits"
    )
    assert normalize_release(uri) == "DR1"


def test_provenance_calibration_family_classification_is_specific():
    assert calibration_family_from_uri(
        "ibe/data/spherex/dr1/spectral_wcs/cal-swcs-v5-2026-191/2/file.fits"
    ) == "spectral_wcs"
    assert calibration_family_from_uri(
        "ibe/data/spherex/dr1/abs_gain_matrix/cal-agm-v8-2026-191/2/file.fits"
    ) == "absolute_gain"
    assert calibration_family_from_uri(
        "ibe/data/spherex/dr1/xtalk_class2/base-2026-191/2/file.ecsv"
    ) == "crosstalk_class_2"
    assert calibration_family_from_uri(
        "ibe/data/spherex/dr1/unknown_family/base/2/file.fits"
    ) == "unclassified_calibration"


def test_archive_checksum_verification_supports_tap_md5(tmp_path):
    path = tmp_path / "product.ecsv"
    payload = b"# %ECSV 1.0\nvalue\n1\n"
    path.write_bytes(payload)
    expected = hashlib.md5(payload).hexdigest()
    result = verify_archive_checksum(path, "md5:" + expected)
    assert result["status"] == "pass"
    assert result["algorithm"] == "md5"
    assert verify_archive_checksum(path, "md5:" + "0" * 32)["status"] == "fail"


def test_science_artifact_query_escapes_uri_and_uses_tap_lineage_tables():
    query = build_sql("ibe/data/spherex/dr1/file's name.fits")
    assert "spherex.artifact" in query
    assert "spherex.plane" in query
    assert "spherex.observation" in query
    assert "file''s name.fits" in query
