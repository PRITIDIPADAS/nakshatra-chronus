# Bayesian linear measurement inference in CHRONOS

## Implemented probability model

The module \`backend/chronos_causal/bayesian.py\` implements exact conjugate inference for the restricted model

\[
y \mid \beta \sim \mathcal{N}(X\beta, C), \qquad
\beta \sim \mathcal{N}(m_0,S_0),
\]

where \(C\) is a supplied, known, positive-definite measurement covariance and \(S_0\) is a proper, positive-definite coefficient-prior covariance.

The coefficient posterior is

\[
S_n = (S_0^{-1}+X^T C^{-1}X)^{-1},
\qquad
m_n = S_n(S_0^{-1}m_0+X^TC^{-1}y).
\]

The marginal likelihood is evaluated analytically from

\[
y \sim \mathcal{N}(Xm_0,\ C+XS_0X^T).
\]

For a finite set of candidate design matrices and explicitly supplied model priors, normalized marginal likelihoods give posterior model probabilities.

## Posterior-predictive checks

The endpoint draws coefficient vectors \(\beta^{(s)}\) from the exact Gaussian posterior, then draws replicated data

\[
y_{\mathrm{rep}}^{(s)} \sim \mathcal{N}(X\beta^{(s)},C).
\]

It reports pointwise predictive intervals and posterior-predictive tail areas for global whitened-residual chi-square and maximum absolute whitened residual discrepancies.

## API

- \`POST /api/v5/causal/bayesian/posterior-predictive\`
- \`POST /api/v5/causal/bayesian/model-comparison\`

The posterior-predictive request supplies \`observed\`, \`design_matrix\`, \`covariance\`, \`prior_mean\`, \`prior_covariance\`, \`draws\` and \`seed\`. Model comparison supplies a mapping of model names to design matrices, a proper coefficient prior for every model, and a positive prior model probability for every model.

## Important limits

- BIC remains an information-criterion score. Normalized \(\exp(-\Delta\mathrm{BIC}/2)\) values are approximate relative model weights under restrictive assumptions; they are not posterior model probabilities.
- A conditional parametric bootstrap at fixed predictions remains a frequentist conditional bootstrap. It is not retroactively converted into Bayesian posterior prediction.
- The new posterior-predictive check is exact for the specified linear-Gaussian measurement submodel. It is not posterior sampling of the full CHRONOS sky, detector, spatial ePSF, wavelength-response, calibration, astrometry, selection and population model.
- Measurement covariance is treated as known. Calibration uncertainty must either be represented in a larger explicit probabilistic model or reported as an external systematic.
- Posterior model probabilities depend on the finite model set and all coefficient/model priors. Prior sensitivity and omitted-model checks are required before scientific interpretation.

The Bayesian routes are a research capability, not a claim of empirically validated SPHEREx model probabilities or a demonstrated Sky–Detector Twin performance advantage.
