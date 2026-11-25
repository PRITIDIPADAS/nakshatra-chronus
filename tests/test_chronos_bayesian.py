import numpy as np
import pytest


def test_exact_gaussian_posterior_and_posterior_predictive_are_seeded_and_finite():
    from chronos_causal.bayesian import gaussian_linear_posterior_predictive

    x = np.column_stack([np.ones(8), np.linspace(-1.0, 1.0, 8)])
    y = 2.0 + 0.7 * x[:, 1] + np.array([0.03, -0.02, 0.01, 0.0, -0.01, 0.02, -0.03, 0.01])
    covariance = np.eye(8) * 0.04
    prior_mean = [0.0, 0.0]
    prior_covariance = [[4.0, 0.0], [0.0, 4.0]]

    first = gaussian_linear_posterior_predictive(
        y, x, covariance, prior_mean, prior_covariance, draws=600, seed=91
    )
    second = gaussian_linear_posterior_predictive(
        y, x, covariance, prior_mean, prior_covariance, draws=600, seed=91
    )

    assert first["model"] == "linear_gaussian_known_covariance"
    assert np.allclose(first["posterior"]["mean"], second["posterior"]["mean"])
    assert np.allclose(first["posterior"]["covariance"], second["posterior"]["covariance"])
    assert np.allclose(first["posterior"]["covariance"], np.asarray(first["posterior"]["covariance"]).T)
    assert np.isfinite(first["log_marginal_likelihood"])
    checks = first["posterior_predictive"]
    assert 0.0 <= checks["global_whitened_residual_chi_square"]["posterior_predictive_p_value"] <= 1.0
    assert 0.0 <= checks["maximum_absolute_whitened_residual"]["posterior_predictive_p_value"] <= 1.0
    assert len(checks["pointwise_95_percent_interval"]) == len(y)
    assert len(checks["replicated_values"]) == 600


def test_bayesian_model_probabilities_use_prior_and_marginal_likelihood_not_bic():
    from chronos_causal.bayesian import bayesian_linear_model_comparison

    t = np.linspace(-1.0, 1.0, 10)
    y = 1.5 + 0.6 * t + np.array([0.01, -0.02, 0.02, -0.01, 0.0, 0.01, -0.01, 0.02, -0.02, 0.0])
    covariance = np.eye(10) * 0.01
    models = {
        "constant": np.ones((10, 1)).tolist(),
        "linear": np.column_stack([np.ones(10), t]).tolist(),
    }
    priors = {
        "constant": {"mean": [0.0], "covariance": [[10.0]]},
        "linear": {"mean": [0.0, 0.0], "covariance": [[10.0, 0.0], [0.0, 10.0]]},
    }
    result = bayesian_linear_model_comparison(
        y, covariance, models, priors, {"constant": 0.5, "linear": 0.5}
    )

    probabilities = [row["posterior_model_probability"] for row in result["models"]]
    assert sum(probabilities) == pytest.approx(1.0)
    assert all(0.0 <= p <= 1.0 for p in probabilities)
    assert result["method"] == "exact_gaussian_marginal_likelihood"
    assert "not BIC" in result["interpretation"]
    assert result["model_set_conditional"] is True


def test_bayesian_linear_model_rejects_improper_covariance_and_unmatched_priors():
    from chronos_causal.bayesian import (
        gaussian_linear_posterior_predictive,
        bayesian_linear_model_comparison,
    )

    y = [1.0, 1.2, 1.4]
    x = [[1.0], [1.0], [1.0]]
    with pytest.raises(ValueError, match="positive definite"):
        gaussian_linear_posterior_predictive(
            y, x, np.zeros((3, 3)), [0.0], [[1.0]], draws=500
        )
    with pytest.raises(ValueError, match="same >=2 model names"):
        bayesian_linear_model_comparison(
            y, np.eye(3), {"a": x, "b": x},
            {"a": {"mean": [0.0], "covariance": [[1.0]]}},
            {"a": 0.5, "b": 0.5},
        )


def test_bayesian_endpoints_are_exposed_by_the_research_api():
    from chronos_causal.api import router

    paths = {route.path for route in router.routes}
    assert "/api/v5/causal/bayesian/posterior-predictive" in paths
    assert "/api/v5/causal/bayesian/model-comparison" in paths
