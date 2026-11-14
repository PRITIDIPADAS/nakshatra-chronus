"""Optional FastAPI router. No endpoint here performs a network request."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from .spectral import Spectrum,compare_spectra
from .forensics import diagnose_candidate,calibration_ablation
from .planner import plan_observations
from .passport import create_passport,verify_passport
from .validation import score_recovery,probability_metrics
from .molecular import measure_equivalent_width
from .catalogs import crossmatch_catalog
from .orbits import apparent_track
from .selection import selection_corrected_counts
from .citizen import analyze_reviews
router=APIRouter(prefix="/api/addons",tags=["CHRONOS research extensions"])
def dump(x):return x.model_dump() if hasattr(x,"model_dump") else x.dict()
class SpectralSeries(BaseModel):
    wavelength_um:list[float];flux:list[float];sigma:list[float]|None=None;valid:list[bool]|None=None;flags:list[int]|None=None;hits:list[int]|None=None;metadata:dict[str,Any]=Field(default_factory=dict)
class SpectralCompareRequest(BaseModel):reference:SpectralSeries;comparison:SpectralSeries;min_overlap:int=5
class ForensicsRequest(BaseModel):evidence:dict[str,Any];thresholds:dict[str,float]|None=None
class ObservationPlanRequest(BaseModel):candidates:list[dict[str,Any]];priors:dict[str,float]|None=None;measurement_sigma:float=1.
class PassportRequest(BaseModel):project:str;candidate_id:str;creator:str;inputs:dict[str,Any];measurements:dict[str,Any];methods:dict[str,Any];software:dict[str,Any];source_hashes:dict[str,str]=Field(default_factory=dict);external_references:list[dict[str,str]]=Field(default_factory=list);limitations:list[str]=Field(default_factory=list)
class PassportVerifyRequest(BaseModel):passport:dict[str,Any]
class RecoveryRequest(BaseModel):truth_positions:list[list[float]]=Field(default_factory=list);detection_positions:list[list[float]]=Field(default_factory=list);match_radius:float=2.;field_area_deg2:float|None=None
class ProbabilityRequest(BaseModel):true_labels:list[str];probability_rows:list[dict[str,float]|None];classes:list[str];bins:int=10
class AblationRequest(BaseModel):baseline_positions:list[list[float]]=Field(default_factory=list);variant_positions:dict[str,list[list[float]]];match_radius_pixels:float=2.
class SpectralFeatureRequest(BaseModel):spectrum:SpectralSeries;feature_interval_um:list[float];continuum_intervals_um:list[list[float]]
class CatalogueMatchRequest(BaseModel):candidates:list[dict[str,Any]];catalogue_rows:list[dict[str,Any]];candidate_ra:str="ra";candidate_dec:str="dec";catalogue_ra:str="ra";catalogue_dec:str="dec";radius_arcsec:float=5.;catalogue_name:str="catalogue"
class OrbitTrackRequest(BaseModel):mjds:list[float];elements:dict[str,float]
class SelectionCorrectionRequest(BaseModel):tiles:list[dict[str,Any]];minimum_completeness:float=.05
class CitizenReviewRequest(BaseModel):responses:list[dict[str,Any]];answer_key:dict[str,str];machine_labels:dict[str,str]|None=None

def guarded(fn):
    try:return fn()
    except HTTPException:raise
    except Exception as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc
@router.get("/status")
def status():return {"ok":True,"module":"chronos_addons","version":"0.1.0","network_access":False,"capabilities":["spectral analysis","instrument forensics","follow-up planning","evidence passports","validation","catalogue matching","citizen review"]}
@router.post("/spectral/compare")
def spectral_compare(r:SpectralCompareRequest):return guarded(lambda:compare_spectra(Spectrum(**dump(r.reference)),Spectrum(**dump(r.comparison)),r.min_overlap))
@router.post("/forensics/diagnose")
def forensics(r:ForensicsRequest):return guarded(lambda:diagnose_candidate(r.evidence,r.thresholds))
@router.post("/forensics/calibration-ablation")
def ablation(r:AblationRequest):return guarded(lambda:calibration_ablation(r.baseline_positions,r.variant_positions,r.match_radius_pixels))
@router.post("/observations/plan")
def observations(r:ObservationPlanRequest):return guarded(lambda:plan_observations(r.candidates,r.priors,r.measurement_sigma))
@router.post("/passport/create")
def passport_create(r:PassportRequest):return guarded(lambda:create_passport(**dump(r)))
@router.post("/passport/verify")
def passport_verify(r:PassportVerifyRequest):return verify_passport(r.passport)
@router.post("/validation/recovery")
def recovery(r:RecoveryRequest):return guarded(lambda:score_recovery(r.truth_positions,r.detection_positions,r.match_radius,r.field_area_deg2))
@router.post("/validation/probabilities")
def probabilities(r:ProbabilityRequest):return guarded(lambda:probability_metrics(r.true_labels,r.probability_rows,r.classes,r.bins))
@router.post("/spectral/feature")
def spectral_feature(r:SpectralFeatureRequest):return guarded(lambda:measure_equivalent_width(Spectrum(**dump(r.spectrum)),r.feature_interval_um,r.continuum_intervals_um))
@router.post("/catalog/crossmatch")
def catalogue_crossmatch(r:CatalogueMatchRequest):return guarded(lambda:crossmatch_catalog(r.candidates,r.catalogue_rows,candidate_ra=r.candidate_ra,candidate_dec=r.candidate_dec,catalogue_ra=r.catalogue_ra,catalogue_dec=r.catalogue_dec,radius_arcsec=r.radius_arcsec,catalogue_name=r.catalogue_name))
@router.post("/planet/orbit-track")
def orbit_track(r:OrbitTrackRequest):return guarded(lambda:{"track":apparent_track(r.mjds,r.elements),"warning":"Low-precision two-body scenario only; use JPL Horizons or another validated ephemeris for scientific work."})
@router.post("/validation/selection-correction")
def selection_correction(r:SelectionCorrectionRequest):return guarded(lambda:selection_corrected_counts(r.tiles,r.minimum_completeness))
@router.post("/citizen/aggregate")
def citizen_aggregate(r:CitizenReviewRequest):return guarded(lambda:analyze_reviews(r.responses,r.answer_key,r.machine_labels))
