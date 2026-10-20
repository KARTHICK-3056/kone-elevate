"""Weibull AFT correctness tests.

These matter more than usual: the AFT is hand-written rather than imported
(see `app/ml/survival.py` for why), so the implementation has to earn trust
by recovering parameters it was never told, from data whose truth we control.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.survival import WeibullAFT


def _simulate(
    n: int,
    beta: np.ndarray,
    intercept: float,
    shape: float,
    censor_at: float | None,
    seed: int,
):
    """Draw exact Weibull AFT data, optionally right-censored at a fixed time."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 1.0, size=(n, len(beta)))
    scale = np.exp(intercept + x @ beta)
    # Inverse-CDF sampling: T = lambda * (-ln U)^(1/k)
    true_time = scale * (-np.log(rng.uniform(0, 1, n))) ** (1.0 / shape)

    if censor_at is None:
        return x, true_time, np.ones(n, dtype=int)
    duration = np.minimum(true_time, censor_at)
    event = (true_time <= censor_at).astype(int)
    return x, duration, event


def test_recovers_known_coefficients_without_censoring():
    beta = np.array([0.8, -0.5])
    x, duration, event = _simulate(6000, beta, intercept=2.0, shape=1.8, censor_at=None, seed=1)

    model = WeibullAFT().fit(x, duration, event, feature_names=["a", "b"])

    assert model.converged
    assert model.coefficients[0] == pytest.approx(2.0, abs=0.06)  # intercept
    assert model.coefficients[1] == pytest.approx(beta[0], abs=0.06)
    assert model.coefficients[2] == pytest.approx(beta[1], abs=0.06)
    assert model.shape == pytest.approx(1.8, rel=0.06)


def test_recovers_known_coefficients_under_heavy_censoring():
    """Censoring is the whole reason for using survival analysis - it must work."""
    beta = np.array([0.7, -0.4])
    x, duration, event = _simulate(8000, beta, intercept=2.0, shape=1.6, censor_at=6.0, seed=2)

    censoring_rate = 1.0 - event.mean()
    assert 0.25 < censoring_rate < 0.85, f"test setup should censor meaningfully, got {censoring_rate}"

    model = WeibullAFT().fit(x, duration, event, feature_names=["a", "b"])

    assert model.converged
    assert model.coefficients[1] == pytest.approx(beta[0], abs=0.08)
    assert model.coefficients[2] == pytest.approx(beta[1], abs=0.08)
    assert model.shape == pytest.approx(1.6, rel=0.08)


def test_ignoring_censoring_biases_the_estimate_downwards():
    """Guards the design decision, not just the code.

    If we had naively regressed on observed durations treating censored rows
    as events, median life would be badly understated. This asserts the AFT
    actually buys us something over that naive alternative.
    """
    beta = np.array([0.5])
    x, duration, event = _simulate(6000, beta, intercept=2.0, shape=1.7, censor_at=5.0, seed=3)

    correct = WeibullAFT().fit(x, duration, event)
    naive = WeibullAFT().fit(x, duration, np.ones_like(event))  # pretend nothing was censored

    true_median = np.exp(2.0) * (np.log(2.0) ** (1.0 / 1.7))
    correct_median = float(np.median(correct.predict_median_years(x)))
    naive_median = float(np.median(naive.predict_median_years(x)))

    assert naive_median < correct_median
    assert abs(correct_median - true_median) < abs(naive_median - true_median)


def test_survival_probability_is_monotone_and_bounded():
    beta = np.array([0.6])
    x, duration, event = _simulate(2000, beta, intercept=1.5, shape=1.5, censor_at=8.0, seed=4)
    model = WeibullAFT().fit(x, duration, event)

    probabilities = [float(np.mean(model.event_probability_within(x, h))) for h in (0.25, 0.5, 1, 2, 5)]

    assert all(0.0 <= p <= 1.0 for p in probabilities)
    assert probabilities == sorted(probabilities), "P(event within h) must increase with h"


def test_confidence_interval_brackets_the_point_estimate():
    beta = np.array([0.6, -0.3])
    x, duration, event = _simulate(3000, beta, intercept=1.8, shape=1.6, censor_at=6.0, seed=5)
    model = WeibullAFT().fit(x, duration, event)

    interval = model.event_probability_interval(x[:50], horizon_years=2.0)

    assert np.all(interval["lower"] <= interval["probability"] + 1e-9)
    assert np.all(interval["probability"] <= interval["upper"] + 1e-9)
    assert np.all(interval["lower"] >= 0.0) and np.all(interval["upper"] <= 1.0)


@pytest.mark.parametrize("n", [1500, 4000, 10000])
def test_converges_across_sample_sizes(n):
    """Convergence must not depend on dataset size.

    The objective is the *mean* negative log-likelihood precisely so the
    optimiser's tolerances mean the same thing at any n. This guards that:
    optimising the summed likelihood instead made BFGS report failure on
    larger samples while sitting exactly on the optimum.
    """
    beta = np.array([0.6, -0.35])
    x, duration, event = _simulate(n, beta, intercept=1.9, shape=1.5, censor_at=6.0, seed=n)

    model = WeibullAFT().fit(x, duration, event)

    assert model.converged, f"n={n} failed to converge (max gradient {model.max_gradient})"
    assert model.max_gradient < 1e-4
    assert model.shape == pytest.approx(1.5, rel=0.12)


def test_refuses_to_fit_with_no_observed_events():
    x = np.random.default_rng(6).normal(size=(100, 2))
    with pytest.raises(ValueError, match="zero observed events"):
        WeibullAFT().fit(x, np.full(100, 3.0), np.zeros(100, dtype=int))
