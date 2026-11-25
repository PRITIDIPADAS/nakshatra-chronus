"""One fail-closed coordinate path between sky, cutout and native detector pixels."""
from __future__ import annotations
from typing import Any, Sequence
import hashlib, json
import numpy as np

NATIVE_SHAPE=(2040,2040)

def _header_value(header,key):
    value=header.get(key)
    if value is None: raise ValueError(f"required coordinate header {key} is missing")
    return float(value)

def detector_origin_offset(image_header, native_shape=NATIVE_SHAPE):
    """Return (x,y) parent-detector coordinate of cutout pixel (0,0), in 0-based pixels."""
    n1=int(image_header.get("NAXIS1",-1)); n2=int(image_header.get("NAXIS2",-1))
    if (n1,n2)==(int(native_shape[1]),int(native_shape[0])):
        return (0,0)
    x0=1.0-_header_value(image_header,"CRPIX1A")
    y0=1.0-_header_value(image_header,"CRPIX2A")
    rounded=(int(round(x0)),int(round(y0)))
    if abs(x0-rounded[0])>1e-6 or abs(y0-rounded[1])>1e-6:
        raise ValueError("alternate-WCS cutout origin is not an integer parent-detector pixel; refusing interpolation or guess")
    if rounded[0]<0 or rounded[1]<0 or rounded[0]+n1>native_shape[1] or rounded[1]+n2>native_shape[0]:
        raise ValueError("cutout bounds fall outside the native detector grid")
    return rounded

def _assert_detector(science_detector, requested_detector):
    a=str(science_detector or "").strip().upper().replace("DETECTOR","").replace("D","")
    b=str(requested_detector or "").strip().upper().replace("D","")
    if not a or not b or a!=b: raise ValueError(f"detector mismatch or missing detector identity: science={science_detector!r}, requested={requested_detector!r}")

def image_to_detector(x,y,image_header,*,science_detector,requested_detector):
    _assert_detector(science_detector,requested_detector)
    ox,oy=detector_origin_offset(image_header)
    xx,yy=np.asarray(x,float),np.asarray(y,float)
    if xx.shape!=yy.shape: raise ValueError("x and y arrays must have equal shape")
    return xx+ox,yy+oy

def detector_to_image(x,y,image_header,*,science_detector,requested_detector):
    _assert_detector(science_detector,requested_detector)
    ox,oy=detector_origin_offset(image_header)
    xx,yy=np.asarray(x,float),np.asarray(y,float)
    if xx.shape!=yy.shape: raise ValueError("x and y arrays must have equal shape")
    return xx-ox,yy-oy

def _skycoord(ra_deg,dec_deg):
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    return SkyCoord(ra=np.asarray(ra_deg)*u.deg,dec=np.asarray(dec_deg)*u.deg,frame="icrs")

def sky_to_detector(ra_deg,dec_deg,*,image_wcs,image_header,science_detector,requested_detector,
                    positional_covariance_arcsec2=None,step_arcsec=0.01):
    """Transform ICRS positions through the science IMAGE celestial WCS to native detector pixels.

    Optional covariance is in local east/north tangent-plane arcsec squared and is propagated
    with a finite-difference Jacobian. It is not a detector-calibration uncertainty estimate.
    """
    from astropy.wcs import WCS
    if not isinstance(image_wcs,WCS) or not image_wcs.has_celestial: raise TypeError("image_wcs must be an Astropy celestial WCS")
    sky=_skycoord(ra_deg,dec_deg)
    x,y=image_wcs.celestial.world_to_pixel(sky)
    dx,dy=image_to_detector(x,y,image_header,science_detector=science_detector,requested_detector=requested_detector)
    result={"detector_x":np.asarray(dx),"detector_y":np.asarray(dy),"frame":"native_detector_pixel_0based","detector":str(science_detector)}
    if positional_covariance_arcsec2 is not None:
        cov=np.asarray(positional_covariance_arcsec2,float)
        if cov.shape!=(2,2) or not np.isfinite(cov).all() or not np.allclose(cov,cov.T,atol=1e-10):
            raise ValueError("positional_covariance_arcsec2 must be a finite symmetric 2x2 covariance")
        if np.linalg.eigvalsh(cov).min() < -1e-10: raise ValueError("positional covariance must be positive semidefinite")
        import astropy.units as u
        east=sky.spherical_offsets_by(step_arcsec*u.arcsec,0*u.arcsec)
        north=sky.spherical_offsets_by(0*u.arcsec,step_arcsec*u.arcsec)
        xe,ye=image_wcs.celestial.world_to_pixel(east); xn,yn=image_wcs.celestial.world_to_pixel(north)
        j=np.array([[(np.asarray(xe)-x)/step_arcsec,(np.asarray(xn)-x)/step_arcsec],
                    [(np.asarray(ye)-y)/step_arcsec,(np.asarray(yn)-y)/step_arcsec]],dtype=float)
        detector_cov=j@cov@j.T
        result["positional_covariance_detector_px2"]=detector_cov
        result["jacobian_detector_px_per_tangent_arcsec"]=j
    return result

def detector_to_sky(detector_x,detector_y,*,image_wcs,image_header,science_detector,requested_detector):
    from astropy.wcs import WCS
    if not isinstance(image_wcs,WCS) or not image_wcs.has_celestial: raise TypeError("image_wcs must be an Astropy celestial WCS")
    x,y=detector_to_image(detector_x,detector_y,image_header,science_detector=science_detector,requested_detector=requested_detector)
    return image_wcs.celestial.pixel_to_world(x,y)

def coordinate_residual_report(predicted_xy,measured_xy,*,landmark_source_uri=None,landmark_source_sha256=None,
                                detector=None,min_landmarks=3):
    pred=np.asarray(predicted_xy,float); obs=np.asarray(measured_xy,float)
    if pred.ndim!=2 or pred.shape[1]!=2 or pred.shape!=obs.shape or not np.isfinite(pred).all() or not np.isfinite(obs).all():
        raise ValueError("predicted_xy and measured_xy must be equal finite Nx2 arrays")
    residual=pred-obs
    radial=np.hypot(residual[:,0],residual[:,1])
    source_ok=bool(landmark_source_uri and str(landmark_source_uri).startswith("https://") and
                   landmark_source_sha256 and len(str(landmark_source_sha256))==64 and
                   all(c in "0123456789abcdef" for c in str(landmark_source_sha256).lower()))
    validated=len(radial)>=min_landmarks and source_ok
    return {"detector":detector,"landmark_count":int(len(radial)),"residuals_detector_px":residual.tolist(),
      "rms_radial_px":float(np.sqrt(np.mean(radial**2))) if len(radial) else None,
      "median_radial_px":float(np.median(radial)) if len(radial) else None,
      "p95_radial_px":float(np.percentile(radial,95)) if len(radial) else None,
      "max_radial_px":float(np.max(radial)) if len(radial) else None,
      "landmark_source_uri":landmark_source_uri,"landmark_source_sha256":landmark_source_sha256,
      "status":"validated_against_external_landmarks" if validated else "review_required",
      "warning":"Residuals describe the supplied landmark sample only; no detector-persistence claim follows from coordinate alignment alone."}

