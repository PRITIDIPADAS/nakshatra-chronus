#!/usr/bin/env python3
"""Map a detector-coordinate calibration template into a sky-aligned output grid.

The calibration product itself has no celestial WCS. This code uses the
science MEF's celestial WCS to map output-sky pixels back to detector pixels.
For cutouts, it applies the documented CRPIX1A/CRPIX2A origin relation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np

NATIVE_SHAPE = (2040, 2040)


def _detector_id(header: dict) -> str | None:
    for key in ("DETECTOR", "DETID", "DETECTOR_ID", "DET"):
        if key in header:
            raw = str(header[key]).strip().upper().replace("D", "")
            return raw if raw.isdigit() else str(header[key]).strip()
    return None



def validate_template_coordinate_frame(template_coordinate_frame: str, template_header: dict | None = None) -> None:
    """Require a reviewed native-detector map and reject known alternate frames."""
    if template_coordinate_frame != "detector-native":
        raise ValueError("template coordinate frame is not proven: review the exact product and set template_coordinate_frame='detector-native'")
    declared_frame = str((template_header or {}).get("DETCOORD", "")).strip().lower()
    if declared_frame and declared_frame not in {"detector", "native", "detector-native"}:
        raise ValueError(f"template header DETCOORD={declared_frame!r} is not detector-native; no automatic sky-orientation flip/rotation is assumed")


def detector_origin_offset(exposure_header: dict, native_shape: tuple[int, int] = NATIVE_SHAPE) -> tuple[float, float]:
    """Return cutout-pixel to original detector-pixel offsets; fail closed."""
    n1 = int(exposure_header.get("NAXIS1", -1)); n2 = int(exposure_header.get("NAXIS2", -1))
    # Native full-frame images are already in detector coordinates. CRPIX1A/
    # CRPIX2A are applied only to cutouts, per the IRSA documentation.
    if n1 == native_shape[1] and n2 == native_shape[0]:
        return 0.0, 0.0
    if "CRPIX1A" in exposure_header and "CRPIX2A" in exposure_header:
        return 1.0 - float(exposure_header["CRPIX1A"]), 1.0 - float(exposure_header["CRPIX2A"])
    raise ValueError("cutout origin missing: require CRPIX1A and CRPIX2A in IMAGE header")


def sample_detector_template(template: np.ndarray, detector_x: np.ndarray, detector_y: np.ndarray, *,
                             mask: bool = False, order: int | None = None) -> np.ndarray:
    """Sample a native detector map at floating-point detector coordinates."""
    from scipy.ndimage import map_coordinates
    arr = np.asarray(template)
    if arr.ndim != 2:
        raise ValueError("template must be 2D")
    if order is None: order = 0 if mask else 1
    x, y = np.asarray(detector_x, float), np.asarray(detector_y, float)
    if x.shape != y.shape: raise ValueError("detector coordinate arrays must have equal shape")
    out = np.full(x.shape, np.nan, float)
    good = np.isfinite(x) & np.isfinite(y) & (x >= 0) & (y >= 0) & (x <= arr.shape[1]-1) & (y <= arr.shape[0]-1)
    if np.any(good):
        out[good] = map_coordinates(arr.astype(float, copy=False), [y[good], x[good]],
            order=order, mode="constant", cval=np.nan, prefilter=(order > 1))
    return out


def resolve_celestial_wcs(image_header: dict, primary_header: dict | None = None, key: str = "auto"):
    """Build a celestial WCS from IMAGE, following the official IRSA cutout tutorial."""
    from astropy.wcs import WCS
    candidates = [key] if key != "auto" else [None, "A"]
    headers = [image_header] + ([primary_header] if primary_header is not None else [])
    errors = []
    for header in headers:
        if header is None:
            continue
        for candidate in candidates:
            try:
                w = WCS(header) if candidate is None else WCS(header, key=candidate)
                if w.has_celestial:
                    return w, (candidate or "PRIMARY")
            except Exception as exc:
                errors.append(str(exc))
    raise ValueError("No celestial WCS found in IMAGE/PRIMARY headers. Tried "
                     + repr(candidates) + ". " + "; ".join(errors[-3:]))


def detector_to_sky(template: np.ndarray, *, exposure_wcs, output_wcs,
                     output_shape: tuple[int, int], detector: str,
                     template_detector: str, exposure_header: dict,
                     template_coordinate_frame: str = "unknown",
                     template_header: dict | None = None,
                     mask: bool = False, order: int | None = None,
                     full_detector_shape: tuple[int, int] = NATIVE_SHAPE,
                     chunk_rows: int = 128) -> np.ndarray:
    """Resample native detector map to an arbitrary output celestial WCS.

    `exposure_wcs` is the celestial WCS of the MEF IMAGE HDU (or cutout).
    `output_wcs` is the desired target celestial WCS. The source template is
    expected in native 2040x2040 detector coordinates, not sky coordinates.
    """
    from astropy.wcs import WCS
    arr = np.asarray(template)
    if arr.shape != tuple(full_detector_shape):
        raise ValueError(f"template must be native detector shape {full_detector_shape}; got {arr.shape}")
    validate_template_coordinate_frame(template_coordinate_frame, template_header)
    if str(detector) != str(template_detector):
        raise ValueError(f"detector mismatch: exposure={detector}, template={template_detector}")
    if not isinstance(exposure_wcs, WCS) or not isinstance(output_wcs, WCS):
        raise TypeError("exposure_wcs and output_wcs must be Astropy WCS objects")
    ew = exposure_wcs.celestial
    ow = output_wcs.celestial
    # IRSA's documented cutout mapping: original 0-based pixel =
    # 1 + cutout 0-based pixel - CRPIX_A (FITS CRPIX is 1-based).
    off_x, off_y = detector_origin_offset(exposure_header, full_detector_shape)
    if order is None:
        order = 0 if mask else 1
    out_h, out_w = map(int, output_shape)
    result = np.full((out_h, out_w), np.nan, dtype=float)
    yy_full, xx_full = np.mgrid[0:out_h, 0:out_w]
    for y0 in range(0, out_h, chunk_rows):
        y1 = min(out_h, y0 + chunk_rows)
        yy = yy_full[y0:y1]
        xx = xx_full[y0:y1]
        world = ow.pixel_to_world(xx, yy)
        ex, ey = ew.world_to_pixel(world)
        dx = np.asarray(ex, float) + off_x
        dy = np.asarray(ey, float) + off_y
        block = sample_detector_template(arr, dx, dy, mask=mask, order=order)
        result[y0:y1] = block
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--science-mef", required=True, type=Path)
    p.add_argument("--template", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--template-hdu", default=0)
    p.add_argument("--image-hdu", default="IMAGE")
    p.add_argument("--detector", required=True)
    p.add_argument("--template-detector", required=True)
    p.add_argument("--template-frame", choices=["unknown", "detector-native", "sky-oriented"], default="unknown",
                   help="must be detector-native; declare only after reviewing the exact calibration product documentation/header")
    p.add_argument("--wcs-key", default="auto", help="auto (primary then alternate A), or an explicit FITS WCS key")
    p.add_argument("--mask", action="store_true", help="Use nearest-neighbour interpolation")
    p.add_argument("--output-shape", nargs=2, type=int, metavar=("HEIGHT", "WIDTH"))
    args = p.parse_args()
    try:
        from astropy.io import fits
        from astropy.wcs import WCS
    except ImportError as exc:
        raise SystemExit("Install astropy to read FITS/WCS files") from exc
    hdu_sel = int(args.template_hdu) if str(args.template_hdu).isdigit() else args.template_hdu
    with fits.open(args.science_mef, memmap=True) as sci, fits.open(args.template, memmap=True) as tmp:
        image = sci[args.image_hdu]
        template = tmp[hdu_sel]
        if image.data is None or template.data is None:
            raise ValueError("science IMAGE or template HDU is empty")
        src_wcs, selected_wcs_key = resolve_celestial_wcs(
            image.header, sci[0].header, key=args.wcs_key)
        out_shape = tuple(args.output_shape or image.data.shape[-2:])
        src_det = args.detector
        hdr_det = _detector_id(template.header) or _detector_id(tmp[0].header)
        if hdr_det is not None and hdr_det != str(args.template_detector):
            raise ValueError(f"template FITS header detector={hdr_det} contradicts CLI detector={args.template_detector}")
        image_hdr = dict(image.header)
        result = detector_to_sky(template.data, exposure_wcs=src_wcs,
            output_wcs=src_wcs, output_shape=out_shape, detector=src_det,
            template_detector=args.template_detector, exposure_header=image_hdr,
            template_coordinate_frame=args.template_frame, template_header=dict(template.header),
            mask=args.mask)
        fits.PrimaryHDU(result).writeto(args.output, overwrite=True)
        report = {"science_mef": str(args.science_mef), "template": str(args.template),
          "output": str(args.output), "detector": src_det, "template_detector": args.template_detector,
          "wcs_key_requested": args.wcs_key, "wcs_key_selected": selected_wcs_key,
          "template_coordinate_frame_asserted": args.template_frame,
          "template_detcoord_header": template.header.get("DETCOORD"),
          "interpolation_order": 0 if args.mask else 1,
          "output_shape": list(out_shape), "template_shape": list(template.data.shape),
          "method": "output celestial pixel -> science MEF sky WCS -> native detector pixel -> sample template",
          "status": "reprojected under explicit detector-native coordinate-frame assertion; still requires empirical alignment validation on sources/landmarks"}
        args.output.with_suffix(args.output.suffix + ".json").write_text(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
