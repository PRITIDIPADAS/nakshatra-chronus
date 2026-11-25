"""Compare sky-to-detector predictions with independently sourced detector landmarks."""
from __future__ import annotations
import argparse,csv,hashlib,json
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from research_discovery.spherex.coordinate_transform import sky_to_detector,coordinate_residual_report

def sha256(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()
def run(science_mef,landmarks_file,out):
 source=Path(landmarks_file);source_sha=sha256(source);data=json.loads(source.read_text())
 if data.get("sha256") and data["sha256"]!=source_sha:raise ValueError("landmark file SHA-256 does not match its declared checksum")
 if not data.get("source_uri","").startswith("https://"):raise ValueError("landmark file must preserve an HTTPS source URI")
 predicted=[];observed=[];ids=[];cov=[]
 with fits.open(science_mef,memmap=True) as hdul:
  image=hdul["IMAGE"];header=dict(image.header);det=str(header.get("DETECTOR","")).strip()
  w=WCS(image.header)
  if not w.has_celestial:raise ValueError("science IMAGE has no celestial WCS")
  for row in data.get("landmarks",[]):
   result=sky_to_detector(row["ra_deg"],row["dec_deg"],image_wcs=w,image_header=header,
     science_detector=det,requested_detector=row["detector"],positional_covariance_arcsec2=
     (np.eye(2)*float(row["position_sigma_arcsec"])**2 if row.get("position_sigma_arcsec") is not None else None))
   predicted.append([float(np.asarray(result["detector_x"])),float(np.asarray(result["detector_y"]))])
   observed.append([float(row["detector_x"]),float(row["detector_y"])])
   ids.append(row.get("landmark_id"))
   if "positional_covariance_detector_px2" in result:cov.append(result["positional_covariance_detector_px2"].tolist())
 report=coordinate_residual_report(predicted,observed,landmark_source_uri=data["source_uri"],
  landmark_source_sha256=source_sha,detector=det,min_landmarks=3)
 report.update({"science_mef":str(science_mef),"science_mef_sha256":sha256(science_mef),
  "landmark_ids":ids,"propagated_positional_covariances_px2":cov,
  "coordinate_convention":"IMAGE celestial WCS -> cutout pixel -> CRPIX1A/CRPIX2A native detector pixel",
  "status_note":"Coordinate residuals are a check against the supplied external landmarks, not proof of detector persistence."})
 Path(out).write_text(json.dumps(report,indent=2));return report
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("science_mef",type=Path);p.add_argument("landmarks",type=Path)
 p.add_argument("--out",type=Path,default=Path("coordinate_residual_report.json"));a=p.parse_args()
 r=run(a.science_mef,a.landmarks,a.out);print(json.dumps(r,indent=2))
 if r["status"]!="validated_against_external_landmarks":raise SystemExit(2)
if __name__=="__main__":main()
