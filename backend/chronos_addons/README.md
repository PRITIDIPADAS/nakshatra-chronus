# CHRONOS research add-ons

This optional package extends Nakshatra CHRONOS without replacing its existing pipeline. It is deterministic and measurement-driven; it makes no generative-AI calls and the HTTP endpoints perform no network requests.

- `spectral.py`: All-Sky Cube and Level-2 MEF readers, uncertainty-aware comparison.
- `bridge.py`: connects existing CHRONOS forced PSF/ePSF photometry to time-resolved `F(lambda,t)`; requires official `CWAVE/CBAND` samples.
- `archive.py`: explicit calibration, named-HDU and ECSV readers.
- `forensics.py`: transparent detector-triage rules and candidate-list ablation.
- `planner.py`: expected information gain for supplied Gaussian forecasts.
- `passport.py`: SHA-256 content seal and verification; not identity authentication.
- `validation.py`: one-to-one recovery metrics, Wilson intervals, group splits and calibration metrics.
- `molecular.py`: pre-specified equivalent-width measurement; no molecular identification.
- `catalogs.py`: positional catalogue cross-match; no physical association inference.
- `orbits.py`: low-precision two-body visual sandbox; not a validated ephemeris.
- `selection.py`: null/completeness corrected counts with uncertainty and low-completeness exclusion.
- `citizen.py`: inter-rater and crowd summary statistics.
- `api.py`: optional FastAPI router.

The add-ons do not download SPHEREx data. Supply correctly versioned archive files and calibration products yourself. See `docs/SPHEREX_DR1_ADAPTER_GUIDE.md` before interpreting measurements.

## External observation-feasibility trust

The planner ranks information gain from supplied forecasts; it does not contact an observatory, scheduler or archive. A caller-provided `status: verified` value is not an attestation. Feasibility is promoted only when the detached Ed25519 signature verifies against a deployment-pinned public key.

Configure `CHRONOS_FEASIBILITY_ATTESTATION_KEY_ID` and `CHRONOS_FEASIBILITY_ATTESTATION_PUBLIC_KEY_B64` outside the repository. Without both values, feasibility records remain unverified and the planner returns no externally feasible recommendation. Keep the signing private key with the independent availability service; never commit it or send it to the analysis runner.

See [Observation Feasibility Attestation](../../docs/OBSERVATION_FEASIBILITY_ATTESTATION.md) for the canonical signed payload, key provisioning and limitations.
