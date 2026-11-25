"""Derive a per-pixel electrons-per-image-unit map from SPHEREx absolute gain."""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import numpy as np

NATIVE_SHAPE=(2040,2040)

def sha256_file(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()

def _detector(value):
    if value is None:return None
    s=str(value).strip().upper()
    if s.startswith("DETECTOR"):s=s[len("DETECTOR"):]
    if s.startswith("D"):s=s[1:]
    return "D"+s if s in {"1","2","3","4","5","6"} else None

def _is_absolute_gain_unit(value):
    compact=re.sub(r"[\s(){}]", "", str(value or "")).lower()
    return ("mjy" in compact and "sr" in compact and
            ("electron" in compact or "e-" in compact) and "s" in compact)

def derive_electrons_per_image_unit(*,calibration_path,expected_sha256,detector,
                                    calibration_bunit,exposure_time_s,
                                    origin_xy,image_shape,science_image_unit="MJy/sr"):
    """Return e-/IMAGE-unit/pixel for this exposure's exact science footprint.

    SPHEREx absolute-gain maps encode (MJy/sr)/(e-/s) pixel by pixel.
    Therefore expected source electrons = source IMAGE signal * exposure_time_s / G_abs.
    No gain is invented, interpolated, spatially averaged, or silently filled.
    """
    try:
        from astropy.io import fits
    except ImportError as exc:
        raise RuntimeError("Astropy is required to read the SPHEREx absolute-gain calibration") from exc
    path=Path(calibration_path)
    if not path.is_file():raise FileNotFoundError(f"absolute-gain calibration is unavailable: {path}")
    actual_sha=sha256_file(path)
    if actual_sha.lower()!=str(expected_sha256).lower():
        raise ValueError("absolute-gain calibration SHA-256 does not match the verified record")
    detector_id=_detector(detector)
    if detector_id is None:raise ValueError(f"invalid science detector: {detector!r}")
    exptime=float(exposure_time_s)
    if not np.isfinite(exptime) or exptime<=0:raise ValueError("exposure_time_s must be finite and positive")
    if str(science_image_unit).strip()!="MJy/sr":
        raise ValueError("SPHEREx IMAGE units must be MJy/sr for this conversion path")
    with fits.open(path,memmap=True,checksum=True) as hdul:
        candidates=[hdu for hdu in hdul if hdu.data is not None and np.asarray(hdu.data).ndim==2]
        if not candidates:raise ValueError("absolute-gain FITS has no 2D image")
        hdu=next((h for h in candidates if str(h.name).upper()=="IMAGE"),candidates[0])
        values=np.asarray(hdu.data,dtype=float)
        header_detector=hdu.header.get("DETECTOR",hdul[0].header.get("DETECTOR"))
        if _detector(header_detector)!=detector_id:
            raise ValueError(f"absolute-gain detector mismatch: science={detector_id}, calibration={header_detector!r}")
        bunit=str(hdu.header.get("BUNIT", ""))
        if not bunit or bunit!=str(calibration_bunit):
            raise ValueError(f"absolute-gain BUNIT mismatch: record={calibration_bunit!r}, file={bunit!r}")
        if not _is_absolute_gain_unit(bunit):
            raise ValueError(f"absolute-gain BUNIT is not the documented surface-brightness per electron-rate unit: {bunit!r}")
        if values.shape!=NATIVE_SHAPE:
            raise ValueError(f"absolute-gain map must be native 2040x2040; got {values.shape}")
    origin_x,origin_y=map(int,origin_xy)
    height,width=map(int,image_shape)
    if min(origin_x,origin_y)<0 or min(height,width)<=0 or origin_x+width>NATIVE_SHAPE[1] or origin_y+height>NATIVE_SHAPE[0]:
        raise ValueError("science footprint is outside the absolute-gain map")
    gain_patch=values[origin_y:origin_y+height,origin_x:origin_x+width].copy()
    valid=np.isfinite(gain_patch)&(gain_patch>0)
    conversion=np.full(gain_patch.shape,np.nan,dtype=np.float64)
    conversion[valid]=exptime/gain_patch[valid]
    return conversion

