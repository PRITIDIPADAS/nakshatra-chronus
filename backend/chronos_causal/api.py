"""HTTP endpoints for the CHRONOS research workspaces."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .inference import investigate
from .counterfactual import make_counterfactual

router = APIRouter(prefix="/api/v5", tags=["CHRONOS research workspaces"])

class InvestigationRequest(BaseModel):
    observations: list[dict[str, Any]]
    min_relative_support: float = 0.65
    min_delta_bic: float = 6.0
    flux_covariance: list[list[float]] | None = None

class CounterfactualRequest(BaseModel):
    observations: list[dict[str, Any]]
    intervention: str
    flux_covariance: list[list[float]] | None = None
    amplitude: float = 1.0
    template_amplitude: float = 0.0
    motion_x_per_day: float = 0.0
    motion_y_per_day: float = 0.0
    added_noise_sigma: float = 0.0
    event_start_mjd: float | None = None
    event_end_mjd: float | None = None
    seed: int = 1

class SpectroTemporalRequest(BaseModel):
    samples: list[dict[str, Any]]
    wavelength_grid_um: list[float]
    time_grid_mjd: list[float]
    wavelength_bandwidth_um: float
    time_bandwidth_days: float
    min_neighbors: int = 2
    calibration_group: str | None = None
    measurement_covariance: list[list[float]] | None = None
    shared_calibration_fractional_sigma: float = 0.0

class FeatureEvolutionRequest(BaseModel):
    epochs: list[dict[str, Any]]
    feature_interval_um: list[float]
    continuum_intervals_um: list[list[float]]
    potential_blend_intervals_um: list[list[float]] = Field(default_factory=list)

class IdentityRequest(BaseModel):
    candidate: dict[str, Any]
    catalogue_rows: list[dict[str, Any]]
    search_radius_arcsec: float = 10.0
    background_density_per_arcsec2: float = 0.001
    prior_match_probability: float = 0.9

class SourceGraphRequest(BaseModel):
    candidate_id: str
    association_results: list[dict[str, Any]]

class ScenarioRequest(BaseModel):
    scenario: str
    seed: int = 1
    n_observations: int = 12

class DetectorSimulationRequest(BaseModel):
    shape: list[int]
    sources: list[dict[str, Any]] = Field(default_factory=list)
    psf_kernel: list[list[float]]
    background_electrons: Any = 0.0
    dark_current_electrons: Any = 0.0
    read_noise_electrons: Any = 0.0
    flat_field: Any = None
    hot_pixel_electrons: Any = None
    persistence_electrons: Any = None
    bad_pixel_mask: Any = None
    nonlinearity_per_electron: float = 0.0
    crosstalk_fraction: float = 0.0
    crosstalk_axis: int = 1
    seed: int = 1

class ManifestRequest(BaseModel):
    project: str = "Nakshatra CHRONOS"
    calibration_group: str
    files: list[dict[str, Any]]
    software: dict[str, Any]
    processing_choices: dict[str, Any] = Field(default_factory=dict)

class ManifestVerifyRequest(BaseModel):
    manifest: dict[str, Any]

class ObservationPlanRequest(BaseModel):
    candidates: list[dict[str, Any]]
    priors: dict[str, float] | None = None
    measurement_sigma: float = 1.0
    alternative_priors: dict[str, dict[str, float]] = Field(default_factory=dict)

class PopulationRateRequest(BaseModel):
    fields: list[dict[str, Any]]
    minimum_completeness: float = 0.1
    draws: int = 10000
    seed: int = 1

class ResidualRequest(BaseModel):
    observed: list[float]
    predicted: list[float]
    sigma: list[float]

class BenchmarkSummaryRequest(BaseModel):
    decisions: list[dict[str, Any]]

class IdentifiabilityRequest(BaseModel):
    observations: list[dict[str, Any]]
    weak_condition_number: float = 1e3
    severe_condition_number: float = 1e6
    near_collinearity: float = 0.98

class BaselineComparisonRequest(BaseModel):
    truth_positions: list[list[float]]
    methods: dict[str, list[dict[str, float]]]
    score_thresholds: list[float]
    match_radius: float = 2.0
    field_area_deg2: float | None = None
    target_false_candidates_per_field: float | None = None
    target_completeness: float | None = None

class EvidenceGraphRequest(BaseModel):
    candidate_id: str
    observations: list[dict[str, Any]]
    analysis: dict[str, Any]
    manifest: dict[str, Any] | None = None

def guarded(fn):
    try:
        return fn()
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get("/status")
def status():
    return {
        "version": "0.3.0",
        "status": "research preview",
        "category": "Physics",
        "central_question": "Can a measured infrared change be separated into astrophysical, instrumental and sampling effects?",
        "capabilities": [
            "measurement-level sky and detector model competition",
            "transient interval search with a search penalty",
            "design-matrix identifiability audit",
            "coordinate persistence diagnostics",
            "measurement-level counterfactuals",
            "electron-domain detector experiments",
            "sampling-aware spectral reconstruction",
            "predefined spectral-feature evolution",
            "proper-motion-aware counterpart association",
            "expected-information-gain planning",
            "selection-corrected population-rate estimates",
            "archive provenance manifests",
            "claim-to-measurement evidence graphs",
            "legacy four-baseline comparison endpoint",
            "common-input four-baseline package enforcement and matched operating points",
            "encrypted blind truth stores and frozen field-level unblinding",
            "generic pixel-level spectral forward experiments with parameter provenance",
            "forward-model Jacobian identifiability and nuisance-degeneracy analysis",
            "grouped residuals and conditional parametric-bootstrap challenges",
            "predeclared measurement-level sky, detector and mixed interventions",
            "synthetic challenge fixtures",
        ],
        "not_claimed": [
            "calibrated posterior probabilities",
            "calibrated SPHEREx pixel-level detector modelling",
            "validated SPHEREx detector coefficients",
            "full Bayesian posterior-predictive inference",
            "real-data performance improvement",
            "automated telescope scheduling",
        ],
    }

@router.post("/causal/investigate")
def causal_investigate(request: InvestigationRequest):
    return guarded(lambda: investigate(
        request.observations,
        min_relative_support=request.min_relative_support,
        min_delta_bic=request.min_delta_bic,
        flux_covariance=request.flux_covariance,
    ))

@router.post("/causal/counterfactual")
def causal_counterfactual(request: CounterfactualRequest):
    def run():
        altered = make_counterfactual(
            request.observations, request.intervention, amplitude=request.amplitude,
            template_amplitude=request.template_amplitude,
            motion_x_per_day=request.motion_x_per_day, motion_y_per_day=request.motion_y_per_day,
            added_noise_sigma=request.added_noise_sigma,
            event_start_mjd=request.event_start_mjd, event_end_mjd=request.event_end_mjd,
            seed=request.seed,
        )
        altered["analysis"] = investigate(
            altered["observations"], flux_covariance=request.flux_covariance
        )
        return altered
    return guarded(run)

@router.post("/causal/identifiability")
def causal_identifiability(request: IdentifiabilityRequest):
    from .identifiability import audit_identifiability
    return guarded(lambda: audit_identifiability(
        request.observations,
        weak_condition_number=request.weak_condition_number,
        severe_condition_number=request.severe_condition_number,
        near_collinearity=request.near_collinearity,
    ))

@router.post("/detector/simulate")
def detector_simulate(request: DetectorSimulationRequest):
    from .forward_model import simulate_detector_frame
    return guarded(lambda: simulate_detector_frame(
        shape=request.shape,
        sources=request.sources,
        psf_kernel=request.psf_kernel,
        background_electrons=request.background_electrons,
        dark_current_electrons=request.dark_current_electrons,
        read_noise_electrons=request.read_noise_electrons,
        flat_field=request.flat_field,
        hot_pixel_electrons=request.hot_pixel_electrons,
        persistence_electrons=request.persistence_electrons,
        bad_pixel_mask=request.bad_pixel_mask,
        nonlinearity_per_electron=request.nonlinearity_per_electron,
        crosstalk_fraction=request.crosstalk_fraction,
        crosstalk_axis=request.crosstalk_axis,
        seed=request.seed,
    ))

@router.post("/spectrotemporal/reconstruct")
def spectrotemporal_reconstruct(request: SpectroTemporalRequest):
    from chronos_spectrotemporal.reconstruction import reconstruct
    return guarded(lambda: reconstruct(
        request.samples, request.wavelength_grid_um, request.time_grid_mjd,
        wavelength_bandwidth_um=request.wavelength_bandwidth_um,
        time_bandwidth_days=request.time_bandwidth_days,
        min_neighbors=request.min_neighbors,
        calibration_group=request.calibration_group,
        measurement_covariance=request.measurement_covariance,
        shared_calibration_fractional_sigma=request.shared_calibration_fractional_sigma,
    ))

@router.post("/spectrotemporal/feature-evolution")
def spectrotemporal_feature_evolution(request: FeatureEvolutionRequest):
    from chronos_spectrotemporal.feature_evolution import measure_feature_evolution
    return guarded(lambda: measure_feature_evolution(
        request.epochs, request.feature_interval_um, request.continuum_intervals_um,
        potential_blend_intervals_um=request.potential_blend_intervals_um,
    ))

@router.post("/identity/associate")
def identity_associate(request: IdentityRequest):
    from chronos_identity.associations import probabilistic_associations
    return guarded(lambda: probabilistic_associations(
        request.candidate, request.catalogue_rows,
        search_radius_arcsec=request.search_radius_arcsec,
        background_density_per_arcsec2=request.background_density_per_arcsec2,
        prior_match_probability=request.prior_match_probability,
    ))

@router.post("/identity/source-graph")
def identity_source_graph(request: SourceGraphRequest):
    from chronos_identity.source_graph import build_source_graph
    return guarded(lambda: build_source_graph(request.candidate_id, request.association_results))

@router.post("/observations/plan")
def observations_plan(request: ObservationPlanRequest):
    from chronos_addons.planner import plan_observations
    return guarded(lambda: plan_observations(
        request.candidates, request.priors, request.measurement_sigma,
        alternative_priors=request.alternative_priors,
    ))

@router.post("/population/rate")
def population_rate(request: PopulationRateRequest):
    from chronos_population.rates import estimate_event_rate
    return guarded(lambda: estimate_event_rate(
        request.fields, minimum_completeness=request.minimum_completeness,
        draws=request.draws, seed=request.seed,
    ))

@router.post("/evidence/manifest")
def evidence_manifest(request: ManifestRequest):
    from .provenance import create_manifest
    return guarded(lambda: create_manifest(
        project=request.project, calibration_group=request.calibration_group,
        files=request.files, software=request.software,
        processing_choices=request.processing_choices,
    ))

@router.post("/evidence/manifest/verify")
def evidence_manifest_verify(request: ManifestVerifyRequest):
    from .provenance import verify_manifest
    return verify_manifest(request.manifest)

@router.post("/evidence/graph")
def evidence_graph(request: EvidenceGraphRequest):
    from .evidence_graph import build_evidence_graph
    return guarded(lambda: build_evidence_graph(
        candidate_id=request.candidate_id,
        observations=request.observations,
        analysis=request.analysis,
        manifest=request.manifest,
    ))

@router.post("/validation/residuals")
def validation_residuals(request: ResidualRequest):
    from .posterior_predictive import residual_checks
    return guarded(lambda: residual_checks(request.observed, request.predicted, request.sigma))

@router.post("/benchmark/baselines")
def benchmark_baselines(request: BaselineComparisonRequest):
    from chronos_benchmark.baselines import compare_baselines
    return guarded(lambda: compare_baselines(
        request.truth_positions, request.methods, request.score_thresholds,
        match_radius=request.match_radius,
        field_area_deg2=request.field_area_deg2,
        target_false_candidates_per_field=request.target_false_candidates_per_field,
        target_completeness=request.target_completeness,
    ))

@router.post("/benchmark/synthetic-case")
def benchmark_synthetic_case(request: ScenarioRequest):
    from chronos_benchmark.scenarios import generate_scenario
    return guarded(lambda: generate_scenario(
        request.scenario, seed=request.seed, n_observations=request.n_observations,
    ))

@router.post("/benchmark/summary")
def benchmark_summary(request: BenchmarkSummaryRequest):
    from chronos_benchmark.metrics import summarize_decisions
    return guarded(lambda: summarize_decisions(request.decisions))


class BenchmarkPackageRequest(BaseModel):
    package: dict[str, Any]
    bootstrap_draws: int = 2000
    seed: int = 20261125

class JacobianAuditRequest(BaseModel):
    jacobian: list[list[float]]
    parameter_names: list[str]
    covariance: Any = None
    parameter_roles: dict[str, str] | None = None
    measurement_options: list[dict[str, Any]] = Field(default_factory=list)
    weak_condition_number: float = 1e3
    severe_condition_number: float = 1e6
    near_collinearity: float = 0.98
    covariance_verified: bool = False

class SpectralExposureRequest(BaseModel):
    shape: list[int]
    mjd: float
    exposure_time_s: float
    wavelengths_um: list[float]
    bandwidths_um: list[float]
    wavelength_response: list[list[list[float]]]
    sources: list[dict[str, Any]]
    psf_kernel: list[list[float]]
    background_rate_electrons_per_s: Any = 0.0
    dark_current_rate_electrons_per_s: Any = 0.0
    read_noise_electrons: Any = 0.0
    flat_field: Any = None
    detector_fixed_electrons: Any = None
    missing_pixel_mask: Any = None
    flags: Any = None
    bad_flag_bits: int = 0
    wavelength_map_um: Any = None
    calibration_nuisance: dict[str, float] = Field(default_factory=dict)
    parameter_provenance: dict[str, Any] = Field(default_factory=dict)
    seed: int = 1

class FalsificationRequest(BaseModel):
    observations: list[dict[str, Any]]
    challenge_specs: list[dict[str, Any]] | None = None
    flux_covariance: list[list[float]] | None = None
    challenge_plan_sha256: str | None = None
    bootstrap_draws: int = 1000
    transient_draws: int = 500
    seed: int = 20261125
    maximum_predictive_p_value: float = 0.01
    min_relative_support: float = 0.65
    min_delta_bic: float = 6.0

@router.post("/benchmark/compare-package")
def benchmark_compare_package(request: BenchmarkPackageRequest):
    from chronos_benchmark.runner import compare_benchmark_package
    return guarded(lambda: compare_benchmark_package(
        request.package,
        bootstrap_draws=request.bootstrap_draws,
        seed=request.seed,
    ))

@router.post("/causal/identifiability/jacobian")
def causal_identifiability_jacobian(request: JacobianAuditRequest):
    from .identifiability import audit_forward_model_identifiability
    return guarded(lambda: audit_forward_model_identifiability(
        request.jacobian,
        request.parameter_names,
        covariance=request.covariance,
        parameter_roles=request.parameter_roles,
        measurement_options=request.measurement_options,
        weak_condition_number=request.weak_condition_number,
        severe_condition_number=request.severe_condition_number,
        near_collinearity=request.near_collinearity,
        covariance_verified=request.covariance_verified,
    ))

@router.post("/causal/forward-exposure")
def causal_forward_exposure(request: SpectralExposureRequest):
    from .pixel_forward import simulate_spectral_exposure
    return guarded(lambda: simulate_spectral_exposure(
        shape=request.shape,
        mjd=request.mjd,
        exposure_time_s=request.exposure_time_s,
        wavelengths_um=request.wavelengths_um,
        bandwidths_um=request.bandwidths_um,
        wavelength_response=request.wavelength_response,
        sources=request.sources,
        psf_kernel=request.psf_kernel,
        background_rate_electrons_per_s=request.background_rate_electrons_per_s,
        dark_current_rate_electrons_per_s=request.dark_current_rate_electrons_per_s,
        read_noise_electrons=request.read_noise_electrons,
        flat_field=request.flat_field,
        detector_fixed_electrons=request.detector_fixed_electrons,
        missing_pixel_mask=request.missing_pixel_mask,
        flags=request.flags,
        bad_flag_bits=request.bad_flag_bits,
        wavelength_map_um=request.wavelength_map_um,
        calibration_nuisance=request.calibration_nuisance,
        parameter_provenance=request.parameter_provenance,
        seed=request.seed,
    ))

@router.post("/causal/falsify")
def causal_falsify(request: FalsificationRequest):
    from .falsification import run_falsification_suite
    return guarded(lambda: run_falsification_suite(
        request.observations,
        challenge_specs=request.challenge_specs,
        challenge_plan_sha256=request.challenge_plan_sha256,
        flux_covariance=request.flux_covariance,
        bootstrap_draws=request.bootstrap_draws,
        transient_draws=request.transient_draws,
        seed=request.seed,
        maximum_predictive_p_value=request.maximum_predictive_p_value,
        min_relative_support=request.min_relative_support,
        min_delta_bic=request.min_delta_bic,
    ))
