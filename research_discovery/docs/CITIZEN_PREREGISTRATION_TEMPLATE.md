# CHRONOS citizen-science pilot: preregistration template

**Status: blank planning document; no participant study or outcome data are represented.** Complete and time-stamp this document before recruitment or access to held-out truth labels.

## Study identity

- Study title: Human review of two-epoch astronomical image cutouts
- Protocol version: [version]
- Date/time preregistered (UTC): [timestamp]
- Lead / institution: [details]
- Ethics review body and approval reference: [reference]
- Data release and exact input-file hashes: [manifest path]

## Research questions and hypotheses

1. Does independent multi-review consensus improve triage accuracy compared with a single volunteer review on the same blinded cases?
2. Does review confidence discriminate correct from incorrect classifications on independently adjudicated controls?
3. Does human consensus reduce expert review time without increasing the false-negative rate for the predeclared moving-source controls?

Hypotheses and numerical decision thresholds: [pre-register]

## Participants

- Eligibility: adults aged 18+ for the first pilot, unless a separately approved protocol permits others.
- Recruitment method and target: [details]
- Exclusion / withdrawal rules: [details]
- Compensation, if any: [details]
- Consent procedure: [approved form and platform]

## Task cases and truth labels

- Number of cases: [number]
- Number of independent reviews per case: [number]
- Control categories and counts: [moving, stationary, artifact, uncertain]
- Origin of each control label and independent adjudicator: [details]
- Held-out candidate set and concealment rule: [details]
- Image preprocessing and display stretch: [frozen method]
- Randomization seed and assignment policy: [details]

Do not create truth labels by copying the algorithm output that the volunteers are being evaluated against. Use independent expert adjudication and external evidence.

## Analysis plan

- Primary outcome: [e.g., per-case majority label accuracy on blinded controls]
- Secondary outcomes: Fleiss' kappa, confusion matrix, confidence calibration, completion time, missingness and disagreement.
- Consensus / tie rule: [pre-register]
- Statistical intervals and multiplicity handling: [pre-register]
- Comparison against the frozen algorithm: [pre-register]
- Treatment of uncertain votes: [pre-register]
- Exclusion criteria for cases/reviews: [pre-register]

## Data management

- Public and private data separation: [details]
- Access controls: [details]
- Retention and deletion policy: [details]
- De-identified release plan: [details]
- Software version and SHA-256: [details]

## Stop/go criteria

Set numeric criteria before recruitment for minimum agreement, acceptable false-negative rate, candidate-review efficiency and data-quality exclusions. No discovery claim is permitted solely because many classifications were collected.

## Deviations and results

Maintain a dated deviation log. Report the sample size, participant flow, missingness, disagreement, negative results, false alarms and all preregistered outcomes, not only favourable results.
