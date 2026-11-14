"""The real data path, offline. Files are built in the layout that the IRSA documents describe. The archive is not called."""
import io

import numpy as np
import pytest
from astropy.io import fits
from fastapi.testclient import TestClient

import app as A
import connectors as cn
import core

T = A.TARGETS["barnard"]
HOT = 13  # not the default bit, to prove that the table of the file is used


def mef(e, with_psf=True, version="6.5.6"):
    """One cutout file: IMAGE, FLAGS, VARIANCE, ZODI, PSF. No W table, so the color at the target is not known."""
    hd = e.wcs.to_header()
    hd["DETECTOR"], hd["OBSID"], hd["BUNIT"], hd["VERSION"], hd["FINAST"] = e.det, "0000W00_1A_0516_1", "MJy / sr", version, 0
    hd["WCSNAMEA"], hd["CRPIX1A"], hd["CRPIX2A"], hd["CRVAL1A"], hd["CRVAL2A"] = "0-based active pixel coordinates", -999.0, -799.0, 0.0, 0.0
    fl = np.where((e.flags >> core.FLAG_BITS["HOT"]) & 1, 1 << HOT, 0).astype(np.int32)
    fh = fits.Header()
    for name, bit in dict(core.FLAG_BITS, HOT=HOT).items():
        fh["MP_" + name[:5]] = bit if name != "HOT" else HOT
    fh["MP_HOT"] = HOT
    hdus = [fits.PrimaryHDU(), fits.ImageHDU(e.img.astype(np.float32), hd, name="IMAGE"), fits.ImageHDU(fl, fh, name="FLAGS"),
            fits.ImageHDU(e.var.astype(np.float32), name="VARIANCE"), fits.ImageHDU(np.full(e.img.shape, e.zodi, np.float32), name="ZODI")]
    if with_psf:
        y, x = np.indices((101, 101))
        plane = np.exp(-(((x - 50) / 10) ** 2 + ((y - 50) / 10) ** 2) / (2 * core.PSF_SIGMA ** 2))
        ph = fits.Header()
        for i in range(121):
            ph[f"XCTR_{i + 1}"], ph[f"YCTR_{i + 1}"] = 92.0 + 185.5 * (i % 11), 92.0 + 185.5 * (i // 11)
        hdus.append(fits.ImageHDU(np.repeat(plane[None], 121, 0).astype(np.float32), ph, name="PSF"))
    b = io.BytesIO()
    fits.HDUList(hdus).writeto(b)
    return b.getvalue()


@pytest.fixture()
def archive(monkeypatch, tmp_path):
    E, cat = core.sim_field(T, seed=7, dets=(2,), steps=6, catalog=True)
    files = {f"https://example.invalid/level2_0000W00_1A_{i:04d}_1D2_spx_l2b.fits": e for i, e in enumerate(E)}
    rows = [dict(access_url=u, t_min=e.mjd, obs_id=f"0000W00_1A_{i:04d}_1", energy_bandpassname="SPHEREx-D2") for i, (u, e) in enumerate(files.items())]
    calls = []

    def fake_fetch(url, params=None):
        calls.append(url)
        if url == cn.SIA:
            raise AssertionError("search is patched")
        base = url.split("?")[0]
        if "d&size" not in url and len(calls) < 3:
            raise RuntimeError("first form refused")  # the loader must try the second form
        return mef(files[base])

    monkeypatch.setattr(cn, "fetch", fake_fetch)
    monkeypatch.setattr(cn, "search", lambda ra, dec, rad=0.1, coll="x", maxrec=0: rows if coll == "spherex_qr2" else [])
    monkeypatch.setattr(cn, "gaia_cone", lambda ra, dec, rad=0.1, gmax=17.0: cat)
    return E


def test_live_path_reads_files_and_refuses_unknown_color(archive):
    E = core.prepare(cn.live_exposures(T, "spherex_qr3+spherex_qr2", 48, det=2))
    assert len(E) == len(archive) and cn.REPORT["found"] == len(archive) and not cn.REPORT["failed"]
    e = E[0]
    assert e.label == "REAL SPHEREx" and e.det == 2 and e.id.startswith("0000W00_1A_0516_1") and e.psf is not None
    assert e.bits["HOT"] == HOT and not e.lam_ok and e.lam_src == "band center only"
    assert all(x.nanchor >= 5 for x in E)
    assert not any(core.pair_score(a, b)[1] for a in E[:6] for b in E[6:12])


def test_live_path_full_story_when_color_is_known(archive, monkeypatch):
    lam = {round(e.mjd, 4): (e.lam, e.bw) for e in archive}
    state = {}
    real_load = cn.load

    def load(row, ra, dec, size, coll):
        state["mjd"] = round(float(row["t_min"]), 4)
        return real_load(row, ra, dec, size, coll)

    monkeypatch.setattr(cn, "load", load)
    monkeypatch.setattr(cn, "wavelength", lambda h, hd, x, y: lam[state["mjd"]])
    C = TestClient(A.app)
    j = C.get("/api/load?t=barnard&mode=live&coll=spherex_qr2&det=2").json()
    assert j["label"] == "REAL SPHEREx" and len(j["exposures"]) == len(archive) and j["fair_pairs"] > 5
    assert all(e["lam_src"].startswith("W lookup") for e in j["exposures"])
    m = C.get("/api/motion").json()
    assert m["fit"]["verdict"] == "Motion model preferred" and abs(m["pull"]) < 4
    b = C.get("/api/bestpair").json()
    assert C.get(f"/api/pair?a={b['a']}&b={b['b']}").json()["fair"]
    assert C.get("/api/recovery").json()["label"] == "INJECTED INTO REAL SPHEREx"


def test_old_qr2_file_gets_a_warning(archive, monkeypatch):
    e = archive[0]
    monkeypatch.setattr(cn, "fetch", lambda url, params=None: mef(e, version="6.5.2"))
    x = cn.load(dict(access_url="https://example.invalid/a_1D2_spx.fits", t_min=e.mjd), *core.catalog_at(T, e.mjd), 0.08, "spherex_qr2")
    assert any("Old QR2 file" in n for n in x.notes)


def test_missing_psf_falls_back_with_a_note(archive, monkeypatch):
    e = archive[0]
    monkeypatch.setattr(cn, "fetch", lambda url, params=None: mef(e, with_psf=False))
    x = cn.load(dict(access_url="https://example.invalid/a_1D2_spx.fits", t_min=e.mjd), *core.catalog_at(T, e.mjd), 0.08, "spherex_qr3")
    assert x.psf is None and any("Gaussian" in n for n in x.notes)


def test_no_coverage_is_reported_as_a_result(monkeypatch):
    monkeypatch.setattr(cn, "search", lambda *a, **k: [])
    monkeypatch.setattr(cn, "gaia_cone", lambda *a, **k: [])
    r = TestClient(A.app).get("/api/load?t=rdra&mode=live")
    assert r.status_code == 404 and "valid result" in r.json()["detail"]


def test_archive_down_gives_a_clear_message(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("no route")
    monkeypatch.setattr(cn, "search", boom)
    r = TestClient(A.app).get("/api/load?t=rdra&mode=live")
    assert r.status_code == 502 and "archive did not answer" in r.json()["detail"]


def test_detector_from_file_name():
    assert cn.row_detector(dict(access_url="https://x/level2_0000W00_1A_0516_1D2_spx_l2b-v20-0000-000.fits")) == 2
    assert cn.row_detector(dict(access_url="", energy_bandpassname="SPHEREx-D6")) == 6


def test_known_mover_field_format(monkeypatch):
    seen = {}

    class R:
        def json(self):
            return dict(fields=["a"], data_first_pass=[["x"]])

    def fake(url, params=None, timeout=0):
        seen.update(params)
        return R()
    monkeypatch.setattr(cn.requests, "get", fake)
    r = cn.known_movers(133.764625, -7.2426306, core.SIM_T0)
    assert seen["fov-dec-center"].startswith("M07-14-") and seen["fov-ra-center"].startswith("08-55-") and "mpc-code" not in seen
    assert r["data"] == [["x"]]


def test_real_archive_answer_layout():
    """Rows in the layout of a real IRSA SIA2 answer (spherex_qr3, Barnard's Star). Dates in the names are replaced by zeros.
    In the real answer, arrays 3 and 6 share one obs_id and one start time, and arrays 2 and 5 do too."""
    import sky
    rows = [dict(access_url=f"https://x/level2_0000W00_2A_0594_4D{d}_spx_l2b-v27-0000-000.fits", obs_id="0000W00_2A_0594_4",
                 t_min=61000.25, energy_bandpassname=f"SPHEREx-D{d}") for d in (3, 6)]
    rows += [dict(access_url=f"https://x/level2_0000W00_2A_0601_2D{d}_spx_l2b-v27-0000-000.fits", obs_id="0000W00_2A_0601_2",
                  t_min=61000.75, energy_bandpassname=f"SPHEREx-D{d}") for d in (2, 5)]
    dets = [cn.row_detector(r) for r in rows]
    assert dets == [3, 6, 2, 5]
    assert sky.PAIRS[dets[0]] == dets[1] and sky.PAIRS[dets[2]] == dets[3]
    frames = [f"{float(r['t_min']):.5f}" for r in rows]  # the rule in connectors.load
    assert frames[0] == frames[1] and frames[2] == frames[3] and frames[0] != frames[2]


def test_injection_into_archive_files_scores_and_retrains(archive, tmp_path):
    """The real data injection tool, on files in the IRSA layout: planted sources are found and labelled, and the engine retrains."""
    import importlib.util
    import inject
    exps = cn.live_exposures(T, "spherex_qr2", 48, det=0)
    cat = cn.gaia_catalog(cn.REPORT["gaia"])
    res = inject.trials(exps, cat, core.catalog_at(T, core.SIM_T0), 49, n_trials=1, per=3, seed=5)
    sc = inject.score(res)
    assert sc["planted"] == 3 and 1 <= sc["found"] <= 3 and set(sc["by_kind"]) <= set(inject.SKY_KINDS)
    assert all(r["y"] in inject.SKY_KINDS and r["engine"] for r in res["rows"])
    spec = importlib.util.spec_from_file_location("inject_real", "scripts/inject_real.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    out = M.main(["--targets", "barnard", "--coll", "spherex_qr2", "--trials", "1", "--per", "3", "--retrain", "--practice", "2", "--out", str(tmp_path)])
    assert out["status"] == "done" and out["real_rows"] >= 1 and "after" in out and (tmp_path / "engine_real.json").exists()
    assert out["fields"][0]["labels"] == ["REAL SPHEREx"]


def test_search_reports_an_archive_error(monkeypatch):
    err = b'<?xml version="1.0"?><VOTABLE><RESOURCE type="results"><INFO name="QUERY_STATUS" value="ERROR">Query timed out</INFO></RESOURCE></VOTABLE>'
    monkeypatch.setattr(cn, "fetch", lambda url, params=None, cache=True: err)
    with pytest.raises(RuntimeError, match="Query timed out"):
        cn.search(269.446, 4.771)
    assert cn.SEARCH_RADIUS <= 0.01


def test_search_reads_the_results_table_after_the_self_description(monkeypatch):
    """IRSA answers with a self description resource first and the results second."""
    raw = (b'<?xml version="1.0"?><VOTABLE version="1.3" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">'
           b'<RESOURCE type="meta" utype="adhoc:this"><GROUP name="inputParams"><PARAM name="BAND" datatype="double" arraysize="2" value=""/></GROUP>'
           b'<TABLE><FIELD name="dummy" datatype="char" arraysize="*"/><DATA><TABLEDATA></TABLEDATA></DATA></TABLE></RESOURCE>'
           b'<RESOURCE type="results"><INFO name="QUERY_STATUS" value="OVERFLOW"/><TABLE>'
           b'<FIELD name="access_url" datatype="char" arraysize="*" ID="col_0"/><FIELD name="obs_id" datatype="char" arraysize="*" ID="col_1"/>'
           b'<FIELD name="t_min" datatype="double" ID="col_2"/><FIELD name="energy_bandpassname" datatype="char" arraysize="*" ID="col_3"/>'
           b'<DATA><TABLEDATA><TR><TD>https://x/level2_0000W00_2A_0594_3D6_spx_l2b-v27-0000-000.fits</TD><TD>0000W00_2A_0594_3</TD><TD>61000.5</TD><TD>SPHEREx-D6</TD></TR>'
           b'<TR><TD>https://x/level2_0000W00_2A_0594_3D3_spx_l2b-v27-0000-000.fits</TD><TD>0000W00_2A_0594_3</TD><TD>61000.5</TD><TD>SPHEREx-D3</TD></TR>'
           b'</TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>')
    monkeypatch.setattr(cn, "fetch", lambda url, params=None, cache=True: raw)
    rows = cn.search(269.446, 4.771, coll="spherex_qr3")
    assert len(rows) == 2 and [cn.row_detector(r) for r in rows] == [6, 3] and float(rows[0]["t_min"]) == 61000.5


def test_qr3_epsf_table_is_read():
    """QR3 files hold an EPSF binary table: one 33 by 33 ePSF per zone with its detector center. The nearest zone is used."""
    from astropy.io import fits
    y, x = np.indices((33, 33))
    os_ = 3
    g = np.exp(-(((x - 16) / os_) ** 2 + ((y - 16) / os_) ** 2) / (2 * core.PSF_SIGMA ** 2))
    neff = 4 * np.pi * core.PSF_SIGMA ** 2
    cols = [fits.Column(name="XCENTER", format="E", array=np.array([48.0, 1000.0])), fits.Column(name="YCENTER", format="E", array=np.array([48.0, 1000.0])),
            fits.Column(name="NEFF_MEAN", format="E", array=np.array([neff, neff])),
            fits.Column(name="EPSF", format="1089D", dim="(33,33)", array=np.stack([g * 0, g]))]
    h = fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(cols, name="EPSF")])
    hd = fits.Header()
    hd["CRPIX1A"], hd["CRPIX2A"], hd["CRVAL1A"], hd["CRVAL2A"] = -975.0, -975.0, 0.0, 0.0
    psf, note = cn.pick_psf(h, hd, 23.0, 23.0)  # detector pixel near 999: the second zone
    assert psf is not None and "zone 1" in note and "oversampling 3" in note
