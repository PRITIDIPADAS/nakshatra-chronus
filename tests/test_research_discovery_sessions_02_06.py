from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest


def _manifest_product(uri="https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/test.fits",
                      archive_id="ivo://irsa/test/1", status="discovered_not_downloaded"):
    from research_discovery.spherex.archive_manifest import product_record
    return product_record(
        product_type="level2_mef", native_uri=uri, status=status,
        archive_id=archive_id, release="DR1", detector="D2",
        observation_time={"start_mjd": "60000.0", "end_mjd": "60000.001"},
        pipeline_version="7.1", processing_date="2026-001",
        local_path=None, byte_count=None, sha256=None,
        compatibility_group=None, compatibility_status="unassigned")


def _manifest(products):
    from research_discovery.spherex.archive_manifest import build_manifest
    return build_manifest(archive="IRSA SPHEREx", query={"query_url": "https://irsa.ipac.caltech.edu/SIA"},
        products=products, processing_config={"download": "unit-test"})



def _verified_audit_fixture(tmp_path):
    import json
    from research_discovery.spherex.archive_manifest import build_manifest, product_record
    from research_discovery.spherex.calibration_matrix import build_matrix

    uris = {
        "science": "https://irsa.ipac.caltech.edu/dr1/level2/native_science.fits",
        "spectral": "https://irsa.ipac.caltech.edu/dr1/cal/spectral_wcs/D2.fits",
        "area": "https://irsa.ipac.caltech.edu/dr1/cal/solid_angle/D2.fits",
    }
    files = {}
    for key, payload in (("science", b"native-science-bytes"),
                         ("spectral", b"native-cwave-cband-bytes"),
                         ("area", b"native-solid-angle-bytes")):
        path = tmp_path / (key + ".fits")
        path.write_bytes(payload)
        files[key] = {"path": path, "sha256": hashlib.sha256(payload).hexdigest(),
                      "bytes": len(payload)}
    checks = {name: {"status": "pass"} for name in (
        "required_hdus", "image_2d", "native_full_frame", "image_unit",
        "release_psf_family", "flags_integer_type", "celestial_wcs",
        "alternate_wcs_a", "cutout_parent_origin", "cwave_cband",
        "solid_angle", "variance_alignment", "zodi_alignment")}
    audit = {
        "science_native_uri": uris["science"],
        "science_sha256": files["science"]["sha256"],
        "spectral_wcs_native_uri": uris["spectral"],
        "spectral_wcs_sha256": files["spectral"]["sha256"],
        "release": "DR1",
        "science_detector": "D2",
        "science_pipeline_version": "7.1",
        "science_processing_date": "2026-001",
        "coordinate_frame": "native_detector",
        "spectral_wcs_metadata": {
            "release": "DR1", "detector": "D2", "pipeline_version": "7.1",
            "processing_date": "2026-001", "coordinate_frame": "native_detector"},
        "checks": checks,
        "flags": {"header_flag_dictionary_present": True},
        "wavelength_summary": {
            "cwave_native_shape": [2040, 2040], "cband_native_shape": [2040, 2040]},
        "solid_angle": {
            "status": "pass", "uri": uris["area"], "sha256": files["area"]["sha256"],
            "shape": [2040, 2040], "detector": "D2", "bunit": "arcsec2"},
    }
    audit_path = tmp_path / "native_mef_audit.json"
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")
    audit_sha = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    science_meta = {
        "release": "DR1", "detector": "D2", "pipeline_version": "7.1",
        "processing_date": "2026-001", "coordinate_frame": "native_detector",
        "native_uri": uris["science"], "sha256": files["science"]["sha256"],
        "local_path": str(files["science"]["path"])}
    calibration_meta = {
        "release": "DR1", "detector": "D2", "pipeline_version": "7.1",
        "processing_date": "2026-001", "coordinate_frame": "native_detector",
        "native_uri": uris["spectral"], "sha256": files["spectral"]["sha256"],
        "local_path": str(files["spectral"]["path"]),
        "solid_angle_map_path": str(files["area"]["path"]),
        "wavelength_audit_path": str(audit_path), "wavelength_audit_sha256": audit_sha,
        "solid_angle_map_uri": uris["area"], "solid_angle_map_sha256": files["area"]["sha256"]}
    products = [
        product_record(product_type="level2_mef", native_uri=uris["science"],
            status="downloaded", archive_id="science-archive-id", release="DR1",
            detector="D2", observation_time={"mjd": 60000}, pipeline_version="7.1",
            processing_date="2026-001", local_path=str(files["science"]["path"]),
            byte_count=files["science"]["bytes"], sha256=files["science"]["sha256"]),
        product_record(product_type="spectral_wcs", native_uri=uris["spectral"],
            status="downloaded", archive_id="spectral-archive-id", release="DR1",
            detector="D2", observation_time=None, pipeline_version="7.1",
            processing_date="2026-001", local_path=str(files["spectral"]["path"]),
            byte_count=files["spectral"]["bytes"], sha256=files["spectral"]["sha256"],
            compatibility_status="candidate_only"),
        product_record(product_type="solid_angle_pixel_map", native_uri=uris["area"],
            status="downloaded", archive_id="area-archive-id", release="DR1",
            detector="D2", observation_time=None, pipeline_version="7.1",
            processing_date="2026-001", local_path=str(files["area"]["path"]),
            byte_count=files["area"]["bytes"], sha256=files["area"]["sha256"],
            compatibility_status="candidate_only"),
    ]
    manifest = build_manifest(archive="IRSA", query={}, products=products, processing_config={})
    matrix = build_matrix({
        "science_exposures": [{"id": "science", "uri": uris["science"],
            "sha256": files["science"]["sha256"], "local_path": str(files["science"]["path"]), "metadata": science_meta}],
        "calibration_candidates": [{"id": "D2-spectral", "uri": uris["spectral"],
            "sha256": files["spectral"]["sha256"], "local_path": str(files["spectral"]["path"]), "product_type": "spectral_wcs",
            "metadata": calibration_meta}],
    })
    return manifest, matrix, audit_path, science_meta, calibration_meta



def test_archive_manifest_retains_identity_and_is_valid():
    from research_discovery.spherex.archive_manifest import validate_manifest
    product = _manifest_product()
    manifest = _manifest([product])
    report = validate_manifest(manifest)
    assert report["valid"]
    assert manifest["products"][0]["archive_id"] == "ivo://irsa/test/1"
    assert manifest["products"][0]["native_uri"].endswith("test.fits")


def test_manifest_duplicate_native_uri_and_archive_id_are_reported():
    from research_discovery.spherex.archive_manifest import validate_manifest
    a = _manifest_product()
    b = _manifest_product()
    report = validate_manifest(_manifest([a, b]))
    codes = {x["code"] for x in report["issues"]}
    assert "duplicate_product_uri" in codes
    assert "duplicate_archive_id" in codes


def test_manifest_missing_product_field_is_reported():
    from research_discovery.spherex.archive_manifest import validate_manifest
    product = _manifest_product()
    del product["detector"]
    report = validate_manifest(_manifest([product]))
    assert any(x["code"] == "missing_product_field" and x["field"] == "detector"
               for x in report["issues"])


def test_manifest_malformed_hash_is_rejected():
    from research_discovery.spherex.archive_manifest import validate_manifest
    product = _manifest_product(status="downloaded")
    product.update({"local_path": "fake.fits", "byte_count": 12, "sha256": "not-a-hash"})
    report = validate_manifest(_manifest([product]))
    assert any(x["code"] in {"malformed_sha256", "download_missing_sha256"}
               for x in report["issues"])


def test_manifest_detects_changed_file_bytes(tmp_path):
    from research_discovery.spherex.archive_manifest import build_manifest, product_record, sha256_file, validate_manifest
    path = tmp_path / "science.fits"
    path.write_bytes(b"SIMPLE  test bytes")
    product = product_record(
        product_type="level2_mef", native_uri="https://irsa.ipac.caltech.edu/test.fits",
        status="downloaded", archive_id="ivo://irsa/test/2", release="DR1",
        detector="D3", observation_time={"mjd": 60001.0}, pipeline_version="7.1",
        processing_date="2026-002", local_path=str(path), byte_count=path.stat().st_size,
        sha256=sha256_file(path), compatibility_group=None, compatibility_status="unassigned")
    manifest = build_manifest(archive="IRSA", query={}, products=[product], processing_config={})
    assert validate_manifest(manifest, verify_local=True)["valid"]
    path.write_bytes(b"SIMPLE  tampered bytes")
    result = validate_manifest(manifest, verify_local=True)
    assert any(x["code"] in {"byte_count_mismatch", "sha256_mismatch"} for x in result["issues"])


def test_manifest_digest_detects_metadata_changes():
    from research_discovery.spherex.archive_manifest import validate_manifest
    manifest = _manifest([_manifest_product()])
    manifest["query"]["query_url"] = "https://example.invalid/changed"
    report = validate_manifest(manifest)
    assert any(x["code"] == "manifest_sha256_invalid_or_mismatch" for x in report["issues"])


def test_manifest_allows_empty_unpopulated_state_without_fake_products():
    from research_discovery.spherex.archive_manifest import build_manifest, validate_manifest
    manifest = build_manifest(archive="IRSA SPHEREx", query={}, products=[], processing_config={})
    assert manifest["status"] == "empty_unpopulated"
    assert manifest["products"] == []
    assert validate_manifest(manifest)["valid"]


def test_calibration_pair_rejects_wrong_spectral_grid_and_bad_values():
    from research_discovery.spherex.calibration_compatibility import compatibility_decision
    science = {"release":"DR1","detector":"D2","pipeline_version":"7.1",
               "processing_date":"2026-001","coordinate_frame":"native_detector"}
    wrong_grid = {"release":"DR1","detector":"D2","pipeline_version":"7.1",
        "processing_date":"2026-001","coordinate_frame":"native_detector",
        "cwave":np.ones((20,20)),"cband":np.ones((20,20))}
    assert compatibility_decision(science,wrong_grid)["status"] == "review_required"
    invalid = {"release":"DR1","detector":"D2","pipeline_version":"7.1",
        "processing_date":"2026-001","coordinate_frame":"native_detector",
        "cwave":np.ones((2040,2040),dtype=np.float32),
        "cband":np.ones((2040,2040),dtype=np.float32)}
    invalid["cwave"][0,0] = np.nan
    assert compatibility_decision(science,invalid)["status"] == "review_required"


def test_calibration_pair_without_native_audit_is_not_compatible():
    from research_discovery.spherex.calibration_compatibility import compatibility_decision
    science = {"release":"DR1","detector":"D2","pipeline_version":"7.1",
               "processing_date":"2026-001","coordinate_frame":"native_detector"}
    cal = {"release":"DR1","detector":"D2","pipeline_version":"7.1",
           "processing_date":"2026-001","coordinate_frame":"native_detector",
           "cwave_shape":[2040,2040],"cband_shape":[2040,2040],
           "valid_fraction":1.0,"wavelength_maps_audit_sha256":"c"*64}
    assert compatibility_decision(science,cal)["status"] == "review_required"


def test_coordinate_cutout_offset_and_round_trip():
    from research_discovery.spherex.coordinate_transform import detector_origin_offset, image_to_detector, detector_to_image
    header = {"NAXIS1": 20, "NAXIS2": 12, "DETECTOR": "D2",
              "CTYPE1A": "LINEAR", "CTYPE2A": "LINEAR", "WCSAXESA": 2,
              "CRPIX1A": -99.0, "CRPIX2A": -49.0,
              "CRVAL1A": 0.0, "CRVAL2A": 0.0,
              "CDELT1A": 1.0, "CDELT2A": 1.0}
    assert detector_origin_offset(header) == (100, 50)
    x, y = image_to_detector(np.array([0.0, 4.5]), np.array([0.0, 6.5]), header,
                             science_detector="D2", requested_detector="2")
    assert np.allclose(x, [100.0, 104.5])
    assert np.allclose(y, [50.0, 56.5])
    ix, iy = detector_to_image(x, y, header, science_detector="2", requested_detector="D2")
    assert np.allclose(ix, [0.0, 4.5])
    assert np.allclose(iy, [0.0, 6.5])


def test_coordinate_cutout_rejects_missing_or_fractional_origin():
    from research_discovery.spherex.coordinate_transform import detector_origin_offset
    with pytest.raises(ValueError, match="CRPIX"):
        detector_origin_offset({"NAXIS1": 20, "NAXIS2": 10})
    with pytest.raises(ValueError, match="integer"):
        detector_origin_offset({"NAXIS1": 20, "NAXIS2": 10, "CRPIX1A": -10.5, "CRPIX2A": -9.0})


def test_coordinate_path_rejects_detector_mismatch():
    from research_discovery.spherex.coordinate_transform import image_to_detector
    with pytest.raises(ValueError, match="detector mismatch"):
        image_to_detector(1.0, 2.0, {"NAXIS1": 2040, "NAXIS2": 2040},
                          science_detector="D2", requested_detector="D5")


def test_coordinate_landmark_report_requires_external_provenance():
    from research_discovery.spherex.coordinate_transform import coordinate_residual_report
    p = np.array([[1, 2], [3, 4], [5, 6]], float)
    report = coordinate_residual_report(p, p + 0.1)
    assert report["status"] == "review_required"
    valid = coordinate_residual_report(p, p + 0.1,
        landmark_source_uri="https://catalog.example.org/landmarks.csv",
        landmark_source_sha256="a" * 64, detector="D2")
    assert valid["status"] == "validated_against_external_landmarks"
    assert valid["landmark_count"] == 3


def test_rotated_wcs_conversion_and_uncertainty_propagation():
    astropy = pytest.importorskip("astropy")
    from astropy.wcs import WCS
    from research_discovery.spherex.coordinate_transform import sky_to_detector, detector_to_sky
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [150.0, 2.0]
    w.wcs.crpix = [20.0, 15.0]
    a = np.deg2rad(23.0)
    scale = 1.7 / 3600.0
    w.wcs.cd = np.array([[-scale*np.cos(a), scale*np.sin(a)],
                         [scale*np.sin(a), scale*np.cos(a)]])
    header = {"NAXIS1": 40, "NAXIS2": 30, "DETECTOR": "D2",
              "CTYPE1A": "LINEAR", "CTYPE2A": "LINEAR", "WCSAXESA": 2,
              "CRPIX1A": -99.0, "CRPIX2A": -49.0,
              "CRVAL1A": 0.0, "CRVAL2A": 0.0,
              "CDELT1A": 1.0, "CDELT2A": 1.0}
    sky = w.pixel_to_world(12.25, 10.75)
    result = sky_to_detector(sky.ra.deg, sky.dec.deg, image_wcs=w, image_header=header,
        science_detector="D2", requested_detector="D2", positional_covariance_arcsec2=np.eye(2)*0.04)
    assert result["detector_x"] == pytest.approx(112.25, abs=1e-5)
    assert result["detector_y"] == pytest.approx(60.75, abs=1e-5)
    assert np.linalg.eigvalsh(result["positional_covariance_detector_px2"]).min() > 0
    sky_back = detector_to_sky(result["detector_x"], result["detector_y"], image_wcs=w,
        image_header=header, science_detector="D2", requested_detector="D2")
    assert float(sky_back.separation(sky).arcsec) < 1e-4


def test_calibration_pair_requires_checksum_verified_native_audit(tmp_path):
    from research_discovery.spherex.calibration_compatibility import compatibility_decision
    manifest, matrix, audit_path, science_meta, calibration_meta = _verified_audit_fixture(tmp_path)
    result = compatibility_decision(science_meta, calibration_meta)
    assert result["status"] == "compatible"
    assert result["audit"]["audit_sha256"] == hashlib.sha256(audit_path.read_bytes()).hexdigest()
    calibration_meta["detector"] = "D5"
    assert compatibility_decision(science_meta, calibration_meta)["status"] == "rejected"


def test_calibration_audit_hash_tampering_is_rejected(tmp_path):
    from research_discovery.spherex.calibration_compatibility import compatibility_decision
    manifest, matrix, audit_path, science_meta, calibration_meta = _verified_audit_fixture(tmp_path)
    audit_path.write_text(audit_path.read_text() + " ", encoding="utf-8")
    result = compatibility_decision(science_meta, calibration_meta)
    assert result["status"] == "rejected"
    assert result["audit"]["reason"] == "Native-MEF audit JSON SHA-256 mismatch."


def test_calibration_pair_missing_metadata_is_review_required():
    from research_discovery.spherex.calibration_compatibility import compatibility_decision
    report=compatibility_decision({"release":"DR1","detector":"D2"},{"release":"DR1","detector":"D2"})
    assert report["status"] == "review_required"


def test_calibration_pair_without_solid_angle_remains_unresolved():
    from research_discovery.spherex.calibration_compatibility import compatibility_decision
    science={"release":"DR1","detector":"D2","pipeline_version":"7.1",
             "processing_date":"2026-001","coordinate_frame":"native_detector"}
    cal={"release":"DR1","detector":"D2","pipeline_version":"7.1",
         "processing_date":"2026-001","coordinate_frame":"native_detector",
         "cwave":np.ones((2040,2040),dtype=np.float32),
         "cband":np.ones((2040,2040),dtype=np.float32)}
    result=compatibility_decision(science,cal)
    assert result["status"]=="review_required"
    assert result["checks"]["native_mef_audit"]["status"]=="review_required"


def test_cwave_cband_cutout_slices_without_interpolation_and_masks_invalid_values():
    from research_discovery.spherex.native_mef_audit import science_wavelength_cutout
    cw = np.full((2040,2040),2.1,dtype=np.float32)
    cb = np.full((2040,2040),0.05,dtype=np.float32)
    cw[51,101] = np.nan
    header = {"NAXIS1":2,"NAXIS2":3,"CRPIX1A":-99.0,"CRPIX2A":-49.0}
    result=science_wavelength_cutout(cw,cb,header,(3,2))
    assert result["native_origin_xy"] == [100,50]
    assert result["invalid_pixels"] == 1
    assert np.isnan(result["cwave_um"][1,1])
    assert result["cwave_um"][0,0] == pytest.approx(2.1)


def test_compatibility_matrix_applies_group_to_science_and_both_calibrations(tmp_path):
    from research_discovery.spherex.apply_compatibility_matrix import apply_matrix
    manifest, matrix, audit_path, science_meta, calibration_meta = _verified_audit_fixture(tmp_path)
    assert len(matrix["compatible_pairs"]) == 1
    updated, report = apply_matrix(manifest, matrix)
    assert len(report["applied_pairs"]) == 1
    assert len(report["unresolved"]) == 0
    assert {p["compatibility_group"] for p in updated["products"]} == {"DR1:D2:7.1:2026-001"}
    assert {p["compatibility_status"] for p in updated["products"]} == {"compatible"}


def test_compatibility_matrix_refuses_missing_solid_angle_product():
    from research_discovery.spherex.archive_manifest import build_manifest,product_record
    from research_discovery.spherex.apply_compatibility_matrix import apply_matrix
    science_uri="https://irsa.ipac.caltech.edu/dr1/level2/science.fits"
    cal_uri="https://irsa.ipac.caltech.edu/dr1/cal/spectral_wcs/D2.fits"
    products=[
      product_record(product_type="level2_mef",native_uri=science_uri,status="discovered_not_downloaded",
        archive_id="science-1",release="DR1",detector="D2",observation_time={},pipeline_version="7.1",processing_date="2026-001"),
      product_record(product_type="spectral_wcs",native_uri=cal_uri,status="discovered_not_downloaded",
        release="DR1",detector="D2",observation_time=None,pipeline_version="7.1",processing_date="2026-001")]
    manifest=build_manifest(archive="IRSA",query={},products=products,processing_config={})
    matrix={"compatible_pairs":[{"science_uri":science_uri,"calibration_uri":cal_uri,
      "solid_angle_uri":"https://irsa.ipac.caltech.edu/dr1/cal/solid_angle/D2.fits"}]}
    updated,report=apply_matrix(manifest,matrix)
    assert not report["applied_pairs"]
    assert report["unresolved"]
    assert all(p["compatibility_group"] is None for p in updated["products"])


def test_psf_normalization_and_phase_preservation():
    from research_discovery.validation.injection_recovery import normalize_psf
    psf=np.arange(1,10,dtype=float).reshape(3,3)
    normalized=normalize_psf(psf)
    assert normalized.sum() == pytest.approx(1.0)
    assert np.unravel_index(np.argmax(normalized),normalized.shape)==(2,2)


def test_injection_photon_noise_is_seeded_and_updates_variance():
    from research_discovery.validation.injection_recovery import inject_source_patch
    signal=np.arange(1,10,dtype=float).reshape(3,3)/10.0
    outputs=[]
    for _ in range(2):
        image=np.zeros((20,20),float);var=np.ones_like(image);flags=np.zeros_like(image,dtype=np.uint16)
        before_flags=flags.copy()
        result=inject_source_patch(image,var,flags,signal,8.25,9.75,rng=np.random.default_rng(44),
                                   electrons_per_image_unit=100.0)
        outputs.append((image,var))
        assert np.array_equal(flags,before_flags)
        assert result["mode"]=="source_poisson"
        assert (var-1.0).sum() == pytest.approx(signal.sum()/100.0)
    assert np.array_equal(outputs[0][0],outputs[1][0])
    assert np.array_equal(outputs[0][1],outputs[1][1])


def test_pixel_dependent_poisson_variance_uses_local_conversion():
    from research_discovery.validation.injection_recovery import inject_source_patch
    image=np.zeros((12,12));variance=np.ones_like(image);flags=np.zeros_like(image,dtype=np.uint16)
    signal=np.array([[0.1,0.2,0.1],[0.2,0.8,0.2],[0.1,0.2,0.1]])
    conversion=np.full((12,12),0.02)
    conversion[4:7,4:7]=np.array([[0.01,0.02,0.03],[0.01,0.02,0.03],[0.01,0.02,0.03]])
    result=inject_source_patch(image,variance,flags,signal,5,5,rng=np.random.default_rng(9),electrons_per_image_unit=conversion)
    expected_variance=signal/conversion[4:7,4:7]
    assert result["mode"]=="source_poisson"
    assert np.allclose(variance[4:7,4:7]-1.0,expected_variance)


def test_electron_conversion_reads_native_gain_map_and_exposure_time(tmp_path):
    fits=pytest.importorskip('astropy.io.fits')
    from research_discovery.spherex.electron_conversion import derive_electrons_per_image_unit,sha256_file
    path=tmp_path/'abs_gain_D2.fits'
    gain=np.full((2040,2040),4.0,dtype=np.float32)
    gain[21,11]=np.nan
    image=fits.ImageHDU(gain,name='IMAGE')
    image.header['DETECTOR']='D2';image.header['BUNIT']='(MJy/sr)/(e-/s)'
    fits.HDUList([fits.PrimaryHDU(),image]).writeto(path)
    result=derive_electrons_per_image_unit(calibration_path=path,expected_sha256=sha256_file(path),
        detector='D2',calibration_bunit='(MJy/sr)/(e-/s)',exposure_time_s=2.0,
        origin_xy=(10,20),image_shape=(3,2))
    assert result.shape==(3,2)
    assert result[0,0]==pytest.approx(0.5)
    assert np.isnan(result[1,1])


def test_electron_conversion_rejects_tampered_absolute_gain_bytes(tmp_path):
    fits=pytest.importorskip('astropy.io.fits')
    from research_discovery.spherex.electron_conversion import derive_electrons_per_image_unit,sha256_file
    path=tmp_path/'gain.fits'
    h=fits.ImageHDU(np.ones((2040,2040),dtype=np.float32),name='IMAGE')
    h.header['DETECTOR']='D2';h.header['BUNIT']='(MJy/sr)/(e-/s)'
    fits.HDUList([fits.PrimaryHDU(),h]).writeto(path)
    original=sha256_file(path)
    with path.open('ab') as stream:stream.write(b'tampered')
    with pytest.raises(ValueError,match='SHA-256'):
        derive_electrons_per_image_unit(calibration_path=path,expected_sha256=original,detector='D2',
            calibration_bunit='(MJy/sr)/(e-/s)',exposure_time_s=10,origin_xy=(0,0),image_shape=(2,2))



def test_injection_deterministic_option_does_not_change_variance():
    from research_discovery.validation.injection_recovery import inject_source_patch
    image=np.zeros((20,20));var=np.ones_like(image);flags=np.zeros_like(image,dtype=np.uint16)
    signal=np.ones((3,3))/9
    before=var.copy()
    report=inject_source_patch(image,var,flags,signal,8,8,rng=np.random.default_rng(1))
    assert report["mode"]=="deterministic"
    assert np.array_equal(before,var)
    assert image.sum()==pytest.approx(1.0)


def test_injection_refuses_bad_pixel_footprint_and_edge_clipping():
    from research_discovery.validation.injection_recovery import inject_source_patch
    signal=np.ones((3,3))
    image=np.zeros((12,12));var=np.ones_like(image);flags=np.zeros_like(image,dtype=np.uint16)
    flags[5,5]=1
    with pytest.raises(ValueError,match="flag pixel"):
        inject_source_patch(image,var,flags,signal,5,5,rng=np.random.default_rng(1),excluded_flag_bits=1)
    flags[:]=0
    with pytest.raises(ValueError,match="edge"):
        inject_source_patch(image,var,flags,signal,0.2,5,rng=np.random.default_rng(1))


def test_injection_requires_exposure_bound_calibration_record():
    from research_discovery.validation.injection_recovery import validate_electron_calibration_record
    with pytest.raises(ValueError,match="requires an electron calibration record"):
        validate_electron_calibration_record(None)
    bad={"verification_status":"candidate_only"}
    with pytest.raises(ValueError):
        validate_electron_calibration_record(bad)


def test_injection_rejects_nonfinite_gain():
    from research_discovery.validation.injection_recovery import inject_source_patch
    with pytest.raises(ValueError,match="absolute-gain conversion is invalid"):
        inject_source_patch(np.zeros((10,10)),np.ones((10,10)),np.zeros((10,10),dtype=np.uint16),
            np.ones((3,3)),5,5,rng=np.random.default_rng(1),electrons_per_image_unit=float("nan"))



def test_alternate_wcs_a_is_a_detector_frame_mapping_not_a_celestial_wcs():
    pytest.importorskip("astropy")
    from astropy.io import fits
    from research_discovery.spherex.native_mef_audit import audit_alternate_wcs_a
    header = fits.Header()
    header["CTYPE1A"] = "LINEAR"
    header["CTYPE2A"] = "LINEAR"
    header["CRPIX1A"] = 1.0
    header["CRPIX2A"] = 1.0
    header["CRVAL1A"] = 500.0
    header["CRVAL2A"] = 800.0
    header["CDELT1A"] = 1.0
    header["CDELT2A"] = -1.0
    header["WCSAXESA"] = 2
    result = audit_alternate_wcs_a(header, (12, 20))
    assert result["pixel_n_dim"] == 2
    assert result["world_n_dim"] == 2
    assert result["world_at_cutout_origin"] == pytest.approx([500.0, 800.0])
    assert "not a celestial WCS" in result["mapping"]


def test_alternate_wcs_a_rotation_and_axis_flip_are_used_in_both_directions():
    pytest.importorskip("astropy")
    from research_discovery.spherex.coordinate_transform import image_to_detector, detector_to_image
    header = {
        "NAXIS1": 40, "NAXIS2": 30, "DETECTOR": "D2",
        "CTYPE1A": "LINEAR", "CTYPE2A": "LINEAR", "WCSAXESA": 2,
        "CRPIX1A": 1.0, "CRPIX2A": 1.0,
        "CRVAL1A": 100.0, "CRVAL2A": 200.0,
        "CDELT1A": 1.0, "CDELT2A": 1.0,
        "PC1_1A": 0.0, "PC1_2A": -1.0,
        "PC2_1A": 1.0, "PC2_2A": 0.0,
    }
    detector_x, detector_y = image_to_detector(
        3.0, 4.0, header, science_detector="D2", requested_detector="2")
    assert detector_x == pytest.approx(96.0)
    assert detector_y == pytest.approx(203.0)
    image_x, image_y = detector_to_image(
        detector_x, detector_y, header, science_detector="2", requested_detector="D2")
    assert image_x == pytest.approx(3.0)
    assert image_y == pytest.approx(4.0)


def test_injection_rejects_invalid_image_and_variance_inside_full_psf_patch():
    from research_discovery.validation.injection_recovery import inject_source_patch
    image = np.zeros((12, 12), dtype=float)
    variance = np.ones_like(image)
    flags = np.zeros_like(image, dtype=np.uint16)
    signal = np.ones((3, 3), dtype=float)
    variance[5, 5] = 0.0
    with pytest.raises(ValueError, match="invalid IMAGE or VARIANCE"):
        inject_source_patch(image, variance, flags, signal, 5.0, 5.0,
                            rng=np.random.default_rng(1), electrons_per_image_unit=10.0)
    variance[:] = 1.0
    image[5, 5] = np.nan
    with pytest.raises(ValueError, match="invalid IMAGE or VARIANCE"):
        inject_source_patch(image, variance, flags, signal, 5.0, 5.0,
                            rng=np.random.default_rng(1))


def test_electron_calibration_record_rehashes_file_and_requires_timezone(tmp_path):
    from research_discovery.validation.injection_recovery import validate_electron_calibration_record
    calibration = tmp_path / "abs_gain_fixture.fits"
    calibration.write_bytes(b"fixture abs_gain bytes")
    import hashlib
    record = {
        "verification_status": "verified",
        "science_file_sha256": "a" * 64,
        "science_observation_id": "OBS-FIXTURE",
        "science_source_uri": "https://irsa.ipac.caltech.edu/fixture/science.fits",
        "detector": "D2",
        "image_unit": "MJy/sr",
        "exposure_time_s": 10.0,
        "calibration_product": "abs_gain_matrix",
        "calibration_uri": "https://irsa.ipac.caltech.edu/fixture/abs_gain.fits",
        "calibration_file_path": str(calibration),
        "calibration_sha256": hashlib.sha256(calibration.read_bytes()).hexdigest(),
        "calibration_bunit": "(MJy/sr)/(e-/s)",
        "conversion_method": "exposure_time_s divided by the matching absolute-gain map",
        "verified_by": "independent unit-test fixture",
        "verified_utc": "2026-11-25T00:00:00Z",
    }
    assert validate_electron_calibration_record(record)["verification_status"] == "verified"
    tampered = dict(record)
    calibration.write_bytes(b"changed calibration bytes")
    with pytest.raises(ValueError, match="SHA-256"):
        validate_electron_calibration_record(tampered)
    calibration.write_bytes(b"fixture abs_gain bytes")
    no_zone = dict(record, verified_utc="2026-11-25T00:00:00")
    with pytest.raises(ValueError, match="timezone"):
        validate_electron_calibration_record(no_zone)


def test_native_map_crop_refuses_rotated_or_flipped_wcs_a():
    from research_discovery.spherex.coordinate_transform import detector_origin_offset
    header = {
        "NAXIS1": 40, "NAXIS2": 30,
        "CRPIX1A": -99.0, "CRPIX2A": -49.0,
        "CTYPE1A": "LINEAR", "CTYPE2A": "LINEAR", "WCSAXESA": 2,
        "CRVAL1A": 100.0, "CRVAL2A": 200.0,
        "CDELT1A": 1.0, "CDELT2A": 1.0,
        "PC1_1A": 0.0, "PC1_2A": -1.0,
        "PC2_1A": 1.0, "PC2_2A": 0.0,
    }
    with pytest.raises(ValueError, match="identity-aligned"):
        detector_origin_offset(header)
