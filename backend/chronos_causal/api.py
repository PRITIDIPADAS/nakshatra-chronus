"""HTTP endpoints for the CHRONOS research workspaces."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException, Response
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
    shared_calibration_fractional_sigma: float | None = None
    include_grid_covariance: bool = False

class FeatureEvolutionRequest(BaseModel):
    epochs: list[dict[str, Any]]
    feature_interval_um: list[float]
    continuum_intervals_um: list[list[float]]
    potential_blend_intervals_um: list[list[float]] = Field(default_factory=list)
    continuum_model: str = "linear"
    laboratory_references: list[dict[str, Any]] = Field(default_factory=list)

class IdentityRequest(BaseModel):
    candidate: dict[str, Any]
    catalogue_rows: list[dict[str, Any]]
    search_radius_arcsec: float = 10.0
    background_density_per_arcsec2: float = 0.001
    prior_match_probability: float = 0.9
    minimum_secure_probability: float = 0.8

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
    source_query: dict[str, Any] | str | None = None
    retrieved_at: str | None = None

class ManifestVerifyRequest(BaseModel):
    manifest: dict[str, Any]

class InvestigationPackageRequest(BaseModel):
    candidate_id: str
    analysis: dict[str, Any]
    evidence_graph: dict[str, Any]
    source_files: list[dict[str, Any]]
    reproduction_command: str
    code_commit: str | None = None
    environment: dict[str, Any] = Field(default_factory=dict)
    processing_configuration: dict[str, Any] = Field(default_factory=dict)
    failed_checks: list[dict[str, Any]] = Field(default_factory=list)

class ObservationPlanRequest(BaseModel):
    candidates: list[dict[str, Any]]
    priors: dict[str, float] | None = None
    measurement_sigma: float = 1.0
    alternative_priors: dict[str, dict[str, float]] = Field(default_factory=dict)

class CandidateObservationPlanRequest(BaseModel):
    candidates: list[dict[str, Any]]
    priors: dict[str, float] | None = None
    prior_sets: dict[str, dict[str, float]] = Field(default_factory=dict)
    measurement_sigma: float = 1.0

class PopulationRateRequest(BaseModel):
    fields: list[dict[str, Any]]
    minimum_completeness: float = 0.1
    draws: int = 10000
    seed: int = 1

class PopulationCoverageRequest(BaseModel):
    fields: list[dict[str, Any]]
    target_class: str = "young_stellar_object"
    feature_interval_um: list[float]
    blue_continuum_um: list[float]
    red_continuum_um: list[float]
    minimum_independent_fields: int = 5
    minimum_epochs_per_source: int = 3
    minimum_feature_samples: int = 3
    minimum_continuum_samples: int = 4
    minimum_median_snr: float = 5.0
    minimum_completeness: float = 0.5

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

class WorkspaceCandidatesRequest(BaseModel):
    observations: list[dict[str, Any]]
    query: str = ""
    dataset_class: str | None = None
    calibration_group: str | None = None

class WorkspaceCompareRequest(BaseModel):
    candidate_ids: list[str]
    observations: list[dict[str, Any]]
    min_relative_support: float = 0.65
    min_delta_bic: float = 6.0


class EvidenceGraphRequest(BaseModel):
    candidate_id: str
    observations: list[dict[str, Any]]
    analysis: dict[str, Any]
    manifest: dict[str, Any] | None = None
    model_runs: list[dict[str, Any]] = Field(default_factory=list)
    counterfactuals: list[dict[str, Any]] = Field(default_factory=list)
    failed_tests: list[dict[str, Any]] = Field(default_factory=list)
    environment: dict[str, Any] | None = None
    code_commit: str | None = None

class YSOPopulationRateRequest(PopulationCoverageRequest):
    preregistration_sha256: str
    draws: int = 10000
    seed: int = 1

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
            "exact Gaussian posterior and posterior-predictive checks for explicitly specified linear measurement models",
            "Bayesian model probabilities from proper-prior Gaussian marginal likelihoods (not BIC)",
            "predeclared measurement-level sky, detector and mixed interventions",
            "synthetic challenge fixtures",
        ],
        "not_claimed": [
            "calibrated posterior probabilities",
            "calibrated SPHEREx pixel-level detector modelling",
            "validated SPHEREx detector coefficients",
            "full Bayesian posterior predictive inference for the complete joint sky, detector and calibration model",
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
        include_grid_covariance=request.include_grid_covariance,
    ))

@router.post("/spectrotemporal/feature-evolution")
def spectrotemporal_feature_evolution(request: FeatureEvolutionRequest):
    from chronos_spectrotemporal.feature_evolution import measure_feature_evolution
    return guarded(lambda: measure_feature_evolution(
        request.epochs, request.feature_interval_um, request.continuum_intervals_um,
        potential_blend_intervals_um=request.potential_blend_intervals_um,
        continuum_model=request.continuum_model,
        laboratory_references=request.laboratory_references,
    ))

@router.post("/identity/associate")
def identity_associate(request: IdentityRequest):
    from chronos_identity.associations import probabilistic_associations
    return guarded(lambda: probabilistic_associations(
        request.candidate, request.catalogue_rows,
        search_radius_arcsec=request.search_radius_arcsec,
        background_density_per_arcsec2=request.background_density_per_arcsec2,
        prior_match_probability=request.prior_match_probability,
        minimum_secure_probability=request.minimum_secure_probability,
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

@router.post("/observations/plan-candidate")
def observations_plan_candidate(request: CandidateObservationPlanRequest):
    from chronos_addons.planner import plan_candidate_observations
    return guarded(lambda: plan_candidate_observations(
        request.candidates, priors=request.priors,
        prior_sets=request.prior_sets, measurement_sigma=request.measurement_sigma,
    ))


@router.post("/population/rate")
def population_rate(request: PopulationRateRequest):
    from chronos_population.rates import estimate_event_rate
    return guarded(lambda: estimate_event_rate(
        request.fields, minimum_completeness=request.minimum_completeness,
        draws=request.draws, seed=request.seed,
    ))

@router.post("/population/assess-coverage")
def population_assess_coverage(request: PopulationCoverageRequest):
    from chronos_population.coverage import assess_population_coverage
    return guarded(lambda: assess_population_coverage(
        request.fields, target_class=request.target_class,
        feature_interval_um=request.feature_interval_um,
        blue_continuum_um=request.blue_continuum_um,
        red_continuum_um=request.red_continuum_um,
        minimum_independent_fields=request.minimum_independent_fields,
        minimum_epochs_per_source=request.minimum_epochs_per_source,
        minimum_feature_samples=request.minimum_feature_samples,
        minimum_continuum_samples=request.minimum_continuum_samples,
        minimum_median_snr=request.minimum_median_snr,
        minimum_completeness=request.minimum_completeness,
    ))


@router.post("/population/yso/rate")
def population_yso_rate(request: YSOPopulationRateRequest):
    """Repeat the archive coverage gate on the same real records before population estimation."""
    import re
    from chronos_population.coverage import assess_population_coverage
    from chronos_population.rates import estimate_event_rate
    digest = str(request.preregistration_sha256).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise HTTPException(status_code=422, detail="preregistration_sha256 must be a 64-character SHA-256 digest")

    def run():
        coverage = assess_population_coverage(
            request.fields, target_class=request.target_class,
            feature_interval_um=request.feature_interval_um,
            blue_continuum_um=request.blue_continuum_um,
            red_continuum_um=request.red_continuum_um,
            minimum_independent_fields=request.minimum_independent_fields,
            minimum_epochs_per_source=request.minimum_epochs_per_source,
            minimum_feature_samples=request.minimum_feature_samples,
            minimum_continuum_samples=request.minimum_continuum_samples,
            minimum_median_snr=request.minimum_median_snr,
            minimum_completeness=request.minimum_completeness,
        )
        if not coverage["eligible_for_predeclared_population_protocol"]:
            raise HTTPException(status_code=422, detail={
                "message": "Population analysis blocked: real-data coverage gates were not met.",
                "coverage_audit": coverage,
            })
        rate = estimate_event_rate(
            request.fields, minimum_completeness=request.minimum_completeness,
            draws=request.draws, seed=request.seed,
        )
        return {
            "scientific_status": "coverage_passed_preregistration_digest_supplied",
            "preregistration_sha256": digest,
            "coverage_audit": coverage,
            "population_rate": rate,
            "interpretation": "Conditional on the supplied predeclared selection and null-control assumptions. This is not a discovery claim.",
        }
    return guarded(run)

@router.post("/evidence/manifest")
def evidence_manifest(request: ManifestRequest):
    from .provenance import create_manifest
    return guarded(lambda: create_manifest(
        project=request.project, calibration_group=request.calibration_group,
        files=request.files, software=request.software,
        processing_choices=request.processing_choices,
        source_query=request.source_query,
        retrieved_at=request.retrieved_at,
    ))

@router.post("/evidence/manifest/verify")
def evidence_manifest_verify(request: ManifestVerifyRequest):
    from .provenance import verify_manifest
    return verify_manifest(request.manifest)

@router.post("/evidence/package/export")
def evidence_package_export(request: InvestigationPackageRequest):
    def run():
        import tempfile
        from pathlib import Path
        from chronos_causal.investigation_package import create_investigation_package
        if any("local_path" in row for row in request.source_files):
            raise ValueError(
                "HTTP package export accepts source metadata only; use the local export utility to embed FITS bytes"
            )
        with tempfile.TemporaryDirectory(prefix="chronos-package-") as directory:
            package_path = Path(directory) / "investigation.zip"
            create_investigation_package(
                package_path,
                candidate_id=request.candidate_id,
                analysis=request.analysis,
                evidence_graph=request.evidence_graph,
                source_files=request.source_files,
                reproduction_command=request.reproduction_command,
                code_commit=request.code_commit,
                environment=request.environment or None,
                processing_configuration=request.processing_configuration,
                failed_checks=request.failed_checks,
                include_source_bytes=False,
            )
            payload = package_path.read_bytes()
        safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in request.candidate_id)[:64]
        return Response(
            content=payload,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="chronos_{safe_id or "candidate"}.zip"'},
        )
    return guarded(run)

@router.post("/evidence/graph")
def evidence_graph(request: EvidenceGraphRequest):
    from .evidence_graph import build_evidence_graph
    return guarded(lambda: build_evidence_graph(
        candidate_id=request.candidate_id,
        observations=request.observations,
        analysis=request.analysis,
        manifest=request.manifest,
        model_runs=request.model_runs,
        counterfactuals=request.counterfactuals,
        failed_tests=request.failed_tests,
        environment=request.environment,
        code_commit=request.code_commit,
    ))

@router.post("/workspace/candidates")
def workspace_candidates(request: WorkspaceCandidatesRequest):
    if not request.observations:
        raise HTTPException(status_code=422, detail="observations are required")
    query = request.query.strip().lower()
    grouped = {}
    for index, row in enumerate(request.observations):
        candidate_id = str(row.get("candidate_id") or row.get("source_id") or "").strip()
        if not candidate_id:
            continue
        data_class = str(row.get("dataset_class", row.get("data_class", "synthetic" if row.get("synthetic_fixture") is True else "unverified"))).lower()
        if data_class not in {"real", "synthetic", "illustrative", "unverified"}:
            data_class = "unverified"
        calibration_group = str(row.get("calibration_group") or "")
        if request.dataset_class and data_class != request.dataset_class:
            continue
        if request.calibration_group and calibration_group != request.calibration_group:
            continue
        if query and query not in candidate_id.lower():
            continue
        entry = grouped.setdefault(candidate_id, {
            "classes": set(), "groups": set(), "observation_ids": [],
            "times": [], "wavelengths": [],
        })
        entry["classes"].add(data_class)
        if calibration_group:
            entry["groups"].add(calibration_group)
        entry["observation_ids"].append(str(row.get("observation_id", row.get("measurement_id", index))))
        try:
            entry["times"].append(float(row["mjd"]))
            entry["wavelengths"].append(float(row["wavelength_um"]))
        except (KeyError, TypeError, ValueError):
            pass
    output = []
    for candidate_id, entry in grouped.items():
        classes = sorted(entry["classes"])
        times, waves = entry["times"], entry["wavelengths"]
        output.append({
            "candidate_id": candidate_id,
            "data_class": classes[0] if len(classes) == 1 else "mixed",
            "dataset_classes": classes,
            "calibration_groups": sorted(entry["groups"]),
            "observation_count": len(entry["observation_ids"]),
            "observation_ids": entry["observation_ids"],
            "time_span_days": max(times) - min(times) if len(times) > 1 else 0.0,
            "wavelength_count": len(set(waves)),
        })
    output.sort(key=lambda row: row["candidate_id"])
    return {"candidates": output, "count": len(output),
            "data_class_policy": "Labels are inherited from input rows; missing labels are unverified."}


@router.post("/workspace/compare")
def workspace_compare(request: WorkspaceCompareRequest):
    if len(request.candidate_ids) != 2 or request.candidate_ids[0] == request.candidate_ids[1]:
        raise HTTPException(status_code=422, detail="select exactly two distinct candidate IDs")
    comparisons = []
    for candidate_id in request.candidate_ids:
        rows = [row for row in request.observations
                if str(row.get("candidate_id") or row.get("source_id") or "") == candidate_id]
        if not rows:
            raise HTTPException(status_code=422, detail=f"no observations found for candidate {candidate_id}")
        result = guarded(lambda rows=rows: investigate(
            rows, min_relative_support=request.min_relative_support,
            min_delta_bic=request.min_delta_bic))
        classes = sorted({str(row.get("dataset_class", row.get("data_class", "synthetic" if row.get("synthetic_fixture") is True else "unverified")))
                          for row in rows})
        comparisons.append({
            "candidate_id": candidate_id,
            "data_class": classes[0] if len(classes) == 1 else "mixed",
            "observation_count": len(rows),
            "analysis": result,
        })
    return {"comparisons": comparisons,
            "warning": "The two investigations are independent. Relative support is descriptive and is not a ranking of astrophysical importance."}


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
    motion_integration_substeps: int = 1
    seed: int = 1

class FalsificationRequest(BaseModel):
    observations: list[dict[str, Any]]
    challenge_specs: list[dict[str, Any]] | None = None
    candidate_family: list[dict[str, Any]] | None = None
    candidate_family_complete: bool = False
    flux_covariance: list[list[float]] | None = None
    challenge_plan_sha256: str | None = None
    bootstrap_draws: int = 1000
    transient_draws: int = 500
    seed: int = 20261125
    maximum_predictive_p_value: float = 0.01
    min_relative_support: float = 0.65
    min_delta_bic: float = 6.0

class BayesianPosteriorPredictiveRequest(BaseModel):
    observed: list[float]
    design_matrix: list[list[float]]
    covariance: list[list[float]]
    prior_mean: list[float]
    prior_covariance: list[list[float]]
    draws: int = 4000
    seed: int = 1

class BayesianModelComparisonRequest(BaseModel):
    observed: list[float]
    covariance: list[list[float]]
    models: dict[str, list[list[float]]]
    coefficient_priors: dict[str, dict[str, Any]]
    model_priors: dict[str, float]

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
        motion_integration_substeps=request.motion_integration_substeps,
        seed=request.seed,
    ))

@router.post("/causal/falsify")
def causal_falsify(request: FalsificationRequest):
    from .falsification import run_falsification_suite
    return guarded(lambda: run_falsification_suite(
        request.observations,
        challenge_specs=request.challenge_specs,
        candidate_family=request.candidate_family,
        candidate_family_complete=request.candidate_family_complete,
        challenge_plan_sha256=request.challenge_plan_sha256,
        flux_covariance=request.flux_covariance,
        bootstrap_draws=request.bootstrap_draws,
        transient_draws=request.transient_draws,
        seed=request.seed,
        maximum_predictive_p_value=request.maximum_predictive_p_value,
        min_relative_support=request.min_relative_support,
        min_delta_bic=request.min_delta_bic,
    ))

@router.post("/causal/bayesian/posterior-predictive")
def causal_bayesian_posterior_predictive(request: BayesianPosteriorPredictiveRequest):
    from .bayesian import gaussian_linear_posterior_predictive
    return guarded(lambda: gaussian_linear_posterior_predictive(
        request.observed,
        request.design_matrix,
        request.covariance,
        request.prior_mean,
        request.prior_covariance,
        draws=request.draws,
        seed=request.seed,
    ))

@router.post("/causal/bayesian/model-comparison")
def causal_bayesian_model_comparison(request: BayesianModelComparisonRequest):
    from .bayesian import bayesian_linear_model_comparison
    return guarded(lambda: bayesian_linear_model_comparison(
        request.observed,
        request.covariance,
        request.models,
        request.coefficient_priors,
        request.model_priors,
    ))
