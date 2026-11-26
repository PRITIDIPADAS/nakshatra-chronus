# CHRONOS source-linked event-yield input contract

**API:** `POST /api/v5/population/yso/source-linked-event-yield`

**Output status:** source-selection-weighted candidate-event yield; not a validated YSO population result.

## Event record

Each accepted event record must contain:

| Field | Requirement |
|---|---|
| `event_id` | Globally unique, non-empty event identifier |
| `field_id` | Exact real field identifier from the coverage manifest |
| `source_id` | Exact source identifier that passed the source-level coverage and selection gates |
| `status` | Exactly `accepted`, under the frozen event rule |
| `preregistration_sha256` | Same immutable protocol digest frozen into every selection trial |
| `event_definition_sha256` | Same digest frozen into every selection trial and bound to this event definition |
| `start_mjd`, `end_mjd` | Finite MJD interval with end later than start |
| `measurement_ids` | At least two unique IDs from the source's verified measurement lineage, spanning at least two distinct MJDs |

A source's measurement lineage is built from valid rows after native science/calibration file verification, CWAVE/CBAND checks, observation-product identity checks and source-position/WCS consistency checks. An event that cites a row outside that exact source series is rejected. The event interval must lie within the MJD span of the cited measurements.

## Field-level event counts and controls

Each real science field still supplies `observed_events` and `null_events`. The `observed_events` integer must equal the number of accepted source-linked event records assigned to that field. An explicit empty event list is allowed only when every field's `observed_events` count is zero; a missing event list or an aggregate count unsupported by source rows is not accepted.

The field also supplies science area and baseline, null-control area and baseline, and the corresponding science/control area-time ratio. The estimator independently recomputes that ratio and rejects inconsistent values.

## Selection correction

Each eligible source receives an inverse-probability weight (1/p_i) from the predeclared multidimensional source-selection function. All event contributions from the same source share one Poisson bootstrap multiplier so repeated events are not treated as independent sources. The resampling universe contains every eligible source in each field, including sources with zero accepted events; conditioning only on event-bearing sources would understate source-sampling uncertainty. Field reports distinguish eligible-source count from event-bearing-source count. The selection-trial set must carry the same `event_definition_sha256` as the submitted event records.

## Scientific limits

This path corrects source-catalogue inclusion only. It does not yet model event-level detection efficiency, the source-level composition of contaminants, cross-field covariance, or the representativeness of the injection distribution. Null-control counts remain aggregate area-time controls rather than a matched source-level contaminant sample. The output must therefore not be described as a fully selection-corrected YSO population rate, a discovery, or a validated CHRONOS scientific result.

The legacy `/api/v5/population/yso/rate` endpoint remains an aggregate field-level exploratory estimator and is explicitly labelled as not source-selection-corrected.



## Selection-probability uncertainty in the source-linked yield

Eligible source records carry the fitted selection-cell 95% interval as well as the point estimate. The source-linked estimator draws one probability per joint cell from a logit-normal approximation calibrated to that interval and shares that draw across all eligible sources in the same cell. Source-level Poisson cluster multipliers preserve repeated-event dependence within a source.

This propagates the reported source-selection uncertainty into the candidate-yield interval. It is an approximation to the supplied field-cluster interval, not a full hierarchical posterior and not a model of calibration covariance. Event-detection completeness and source-level contamination remain separate open gates.
