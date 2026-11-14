#!/usr/bin/env python3
"""Extract the position-specific SPHEREx DR1/QR3 ePSF as a native-pixel stamp.

Follows the official IRSA tutorial: choose the nearest EPSF binary-table zone
using the parent-detector position, evaluate its oversampled ImagePSF model at
the source's sub-pixel phase, and normalize the rendered native-pixel stamp.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def detector_position_from_cutout(x_cutout: float, y_cutout: float, image_header: dict) -> tuple[float, float]:
    """Convert Astropy 0-based cutout coordinates to parent detector coords."""
    n1, n2 = int(image_header.get("NAXIS1", -1)), int(image_header.get("NAXIS2", -1))
    if (n1, n2) == (2040, 2040):
        return float(x_cutout), float(y_cutout)
    if "CRPIX1A" in image_header and "CRPIX2A" in image_header:
        return (1.0 + float(x_cutout) - float(image_header["CRPIX1A"]),
                1.0 + float(y_cutout) - float(image_header["CRPIX2A"]))
    raise ValueError("cutout has no CRPIX1A/CRPIX2A; refusing to guess its parent-detector origin")


def select_epsf_row(table, parent_x: float, parent_y: float) -> tuple[int, dict]:
    required = {"XCENTER", "YCENTER", "EPSF", "BINX", "BINY"}
    names = set(table.colnames)
    missing = required - names
    if missing:
        raise ValueError(f"EPSF table is missing required columns: {sorted(missing)}")
    xx = np.asarray(table["XCENTER"], dtype=float)
    yy = np.asarray(table["YCENTER"], dtype=float)
    valid = np.isfinite(xx) & np.isfinite(yy)
    if not valid.any():
        raise ValueError("EPSF table has no finite detector-zone centres")
    rows = np.flatnonzero(valid)
    row = int(rows[np.argmin((xx[valid] - parent_x) ** 2 + (yy[valid] - parent_y) ** 2)])
    meta = {
        "row": row,
        "binx": int(table["BINX"][row]),
        "biny": int(table["BINY"][row]),
        "xcenter_parent_detector_px": float(xx[row]),
        "ycenter_parent_detector_px": float(yy[row]),
        "cwave_um": float(table["CWAVE"][row]) if "CWAVE" in names else None,
        "cband_um": float(table["CBAND"][row]) if "CBAND" in names else None,
        "neff_mean": float(table["NEFF_MEAN"][row]) if "NEFF_MEAN" in names else None,
    }
    return row, meta


def render_native_stamp(epsf_data: np.ndarray, *, oversampling: tuple[int, int],
                        x0: float, y0: float, stamp_size: int = 11) -> tuple[np.ndarray, int, int]:
    """Evaluate oversampled ePSF at exact subpixel phase on native pixels.

    The operation uses Photutils ImagePSF rather than averaging/cropping the
    33x33 array, because IRSA warns that the sub-pixel phase changes the
    pixel-integrated native-resolution PSF.
    """
    if stamp_size < 3 or stamp_size % 2 == 0:
        raise ValueError("stamp_size must be an odd integer >= 3")
    data = np.asarray(epsf_data, dtype=float)
    if data.ndim != 2 or not np.isfinite(data).all():
        raise ValueError("selected EPSF must be a finite 2D image")
    if data.sum() <= 0:
        raise ValueError("selected EPSF must have positive total sum")
    try:
        from photutils.psf import ImagePSF
    except ImportError as exc:
        raise RuntimeError("Install photutils to render the oversampled ePSF at native-pixel resolution") from exc
    model = ImagePSF(data=data, oversampling=oversampling)
    half = (stamp_size - 1) / 2.0
    x_ll, y_ll = int(np.floor(float(x0) - half)), int(np.floor(float(y0) - half))
    x_centres = x_ll + np.arange(stamp_size, dtype=float)
    y_centres = y_ll + np.arange(stamp_size, dtype=float)
    Y, X = np.meshgrid(y_centres, x_centres, indexing="ij")
    stamp = np.asarray(model.evaluate(X, Y, flux=1.0, x_0=float(x0), y_0=float(y0)), dtype=float)
    if stamp.shape != (stamp_size, stamp_size) or not np.isfinite(stamp).all():
        raise ValueError("Photutils returned an invalid rendered PSF stamp")
    total = float(stamp.sum())
    if total <= 0:
        raise ValueError("rendered native-pixel PSF has nonpositive total")
    stamp /= total
    return stamp, x_ll, y_ll


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def extract(science_mef: Path, *, x: float, y: float, out: Path,
            stamp_size: int = 11, image_hdu: str = "IMAGE", epsf_hdu: str = "EPSF") -> dict:
    try:
        from astropy.io import fits
        from astropy.table import Table
    except ImportError as exc:
        raise RuntimeError("Install astropy to read the SPHEREx MEF") from exc
    with fits.open(science_mef, memmap=True) as hdul:
        image = hdul[image_hdu]
        if image.data is None:
            raise ValueError("IMAGE extension is empty")
        if epsf_hdu not in hdul:
            raise ValueError("EPSF extension is missing; this workflow requires a DR1/QR3 image with EPSF or a separately supplied matching calibration table")
        version = str(hdul[0].header.get("VERSION", ""))
        if version and version.split(".", 1)[0].isdigit() and int(version.split(".", 1)[0]) < 7:
            raise ValueError(f"MEF version {version} predates EPSF support; use a DR1/QR3 MEF with version >= 7.0")
        detector = str(image.header.get("DETECTOR", hdul[epsf_hdu].header.get("DETECTOR", ""))).strip()
        epsf_detector = str(hdul[epsf_hdu].header.get("DETECTOR", detector)).strip()
        if detector and epsf_detector and detector != epsf_detector:
            raise ValueError(f"detector mismatch: IMAGE={detector}, EPSF={epsf_detector}")
        parent_x, parent_y = detector_position_from_cutout(x, y, image.header)
        table = Table(hdul[epsf_hdu].data)
        row, zone_meta = select_epsf_row(table, parent_x, parent_y)
        epsf_header = hdul[epsf_hdu].header
        ovx, ovy = int(epsf_header.get("OVSMPX", 0)), int(epsf_header.get("OVSMPY", 0))
        if ovx < 1 or ovy < 1:
            raise ValueError("EPSF header must provide positive OVSMPX and OVSMPY")
        epsf_data = np.asarray(table["EPSF"][row], dtype=float)
        stamp, x_ll, y_ll = render_native_stamp(epsf_data, oversampling=(ovy, ovx),
            x0=x, y0=y, stamp_size=stamp_size)
        out.parent.mkdir(parents=True, exist_ok=True)
        header = fits.Header()
        header["DETECTOR"] = detector or "UNKNOWN"
        header["SRCX"] = float(x)
        header["SRCY"] = float(y)
        header["XLL"] = int(x_ll)
        header["YLL"] = int(y_ll)
        header["EPSFROW"] = int(row)
        header["OVSMPX"] = int(ovx)
        header["OVSMPY"] = int(ovy)
        header["PSFNORM"] = float(stamp.sum())
        header["BUNIT"] = "fractional flux per native pixel"
        fits.PrimaryHDU(stamp.astype(np.float32), header=header).writeto(out, overwrite=True)
        metadata = {
            "science_mef": str(science_mef), "science_mef_sha256": file_sha256(science_mef),
            "output_stamp": str(out), "output_sha256": file_sha256(out),
            "mef_version": version, "detector": detector, "epsf_detector": epsf_detector,
            "source_position_cutout_pixel_0based": [float(x), float(y)],
            "source_position_parent_detector_pixel_0based": [float(parent_x), float(parent_y)],
            "zone": zone_meta, "epsf_oversampling_xy": [ovx, ovy],
            "stamp_size_native_pixels": stamp_size, "stamp_lower_left_cutout_pixel_0based": [x_ll, y_ll],
            "normalization_sum": float(stamp.sum()),
            "method": "Photutils ImagePSF evaluation at source sub-pixel phase followed by native-pixel evaluation and unit-sum normalization",
            "source_note": "Followed IRSA SPHEREx ePSF tutorial; this stamp is position/phase-specific and should not be reused at other detector positions or subpixel phases."
        }
    out.with_suffix(out.suffix + ".json").write_text(json.dumps(metadata, indent=2))
    return metadata


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("science_mef", type=Path)
    p.add_argument("--x", required=True, type=float, help="Source x pixel in IMAGE extension, Astropy 0-based")
    p.add_argument("--y", required=True, type=float, help="Source y pixel in IMAGE extension, Astropy 0-based")
    p.add_argument("--out", type=Path, default=Path("native_epsf_stamp.fits"))
    p.add_argument("--size", type=int, default=11)
    a = p.parse_args()
    result = extract(a.science_mef, x=a.x, y=a.y, out=a.out, stamp_size=a.size)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
