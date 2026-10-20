"""Weibull accelerated-failure-time (AFT) model for time-to-disposition.

Why survival analysis and not regression
-----------------------------------------
The question P2 asks is "when will this component need attention", over a
fleet where most components have **not yet** needed it. Fitting a regression
on only the ones that already crossed the threshold throws away every
still-healthy component and biases the answer badly short. Survival analysis
handles exactly this: a component still healthy at the end of its observation
window is *right-censored* - it contributes the information "it lasted at
least this long", which is real information, not a missing value.

Why Weibull AFT rather than Cox or a survival forest
-----------------------------------------------------
* It is **parametric**, so S(t|x) is a closed form. The planner needs
  P(event within h) for arbitrary h (3/6/12/24 months) and for horizons
  beyond any observed follow-up; a Cox model's baseline hazard cannot
  extrapolate past the last observed event without extra assumptions.
* The Weibull shape parameter k has a physical reading: k > 1 means hazard
  *increasing* with age, which is what wear-out looks like. A fitted k <= 1
  on this data would be a red flag that something is wrong.
* It is small enough to read. Written out below rather than imported, so a
  reviewer can check the likelihood rather than trust a dependency - and
  ``tests/test_survival.py`` proves the implementation recovers known
  coefficients from simulated data.

Parameterisation
----------------
    log(T) = X·beta + sigma·W,     W ~ Gumbel(minimum)

equivalently a Weibull with scale lambda(x) = exp(X·beta) and shape
k = 1/sigma:

    S(t|x) = exp( -(t / lambda(x))^k )

Right-censored log-likelihood, for observation i with duration t_i and event
indicator d_i:

    d_i = 1 (event) :  log k - log lambda + (k-1)·log(t/lambda) - (t/lambda)^k
    d_i = 0 (censor):  -(t/lambda)^k
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from scipy.optimize import minimize

#: Durations at or below this (in years) are clipped before taking a log.
_MIN_DURATION = 1e-3

#: A fit is treated as converged when the largest absolute gradient component
#: of the MEAN negative log-likelihood is below this. Because the objective is
#: averaged, this threshold means the same thing at any sample size.
_GRADIENT_TOLERANCE = 1e-5


@dataclass
class WeibullAFT:
    """Maximum-likelihood Weibull AFT fitter with right censoring."""

    feature_names: List[str] = field(default_factory=list)
    coefficients: Optional[np.ndarray] = None  # beta, including intercept at index 0
    log_shape: Optional[float] = None  # log(k)
    covariance: Optional[np.ndarray] = None  # asymptotic covariance of [beta, log k]
    converged: bool = False
    max_gradient: Optional[float] = None
    log_likelihood: Optional[float] = None
    n_observations: int = 0
    n_events: int = 0

    # ------------------------------------------------------------------ fit
    @staticmethod
    def _design(x: np.ndarray) -> np.ndarray:
        """Prepend an intercept column."""
        return np.column_stack([np.ones(len(x)), x])

    @staticmethod
    def _mean_negative_log_likelihood(
        params: np.ndarray, design: np.ndarray, durations: np.ndarray, events: np.ndarray
    ) -> float:
        """Negative log-likelihood divided by n.

        The division does not move the optimum, but it makes the gradient
        scale independent of dataset size, so the optimiser's tolerances mean
        the same thing at n=500 and n=50,000. Optimising the raw sum makes
        BFGS report non-convergence on large samples even when it has landed
        exactly on the optimum. The covariance is rescaled by n in ``fit``.
        """
        beta, log_k = params[:-1], params[-1]
        k = np.exp(log_k)
        log_lambda = design @ beta
        # z = log(t) - log(lambda), so (t/lambda)^k = exp(k*z)
        z = np.log(durations) - log_lambda
        kz = np.clip(k * z, -500, 500)  # guard against overflow on wild steps
        log_density = log_k + kz - np.exp(kz)  # hazard-weighted density term
        log_survival = -np.exp(kz)
        total = np.sum(np.where(events == 1, log_density, log_survival))
        if not np.isfinite(total):
            return 1e12
        return -float(total) / len(durations)

    def fit(
        self,
        x: np.ndarray,
        durations: np.ndarray,
        events: np.ndarray,
        feature_names: Optional[Sequence[str]] = None,
    ) -> "WeibullAFT":
        """Fit by maximum likelihood. ``durations`` in years, ``events`` in {0,1}."""
        x = np.asarray(x, dtype=float)
        durations = np.clip(np.asarray(durations, dtype=float), _MIN_DURATION, None)
        events = np.asarray(events, dtype=int)

        if x.ndim != 2:
            raise ValueError("x must be 2-dimensional (n_samples, n_features)")
        if not len(x) == len(durations) == len(events):
            raise ValueError("x, durations and events must have the same length")
        if events.sum() == 0:
            raise ValueError("Cannot fit a survival model with zero observed events")

        design = self._design(x)
        # Sensible start: intercept at log(mean observed duration), slopes 0, k=1.
        start = np.zeros(design.shape[1] + 1)
        start[0] = float(np.log(np.mean(durations)))

        n = len(durations)
        result = minimize(
            self._mean_negative_log_likelihood,
            start,
            args=(design, durations, events),
            method="BFGS",
            options={"maxiter": 2000, "gtol": 1e-8},
        )

        self.coefficients = result.x[:-1]
        self.log_shape = float(result.x[-1])
        # BFGS's inverse-Hessian approximation at the optimum estimates the
        # asymptotic covariance (inverse observed Fisher information). The
        # objective is the MEAN negative log-likelihood, whose Hessian is the
        # summed Hessian divided by n - so the returned inverse is n times too
        # large and has to be divided back. Used only for confidence
        # intervals, never for the point forecast.
        self.covariance = np.asarray(result.hess_inv, dtype=float) / n
        # BFGS reports success=False whenever it cannot reach `gtol`, which on a
        # flat likelihood can happen while sitting exactly on the optimum. Judge
        # convergence on the thing that actually matters - whether the gradient
        # of the mean log-likelihood is negligible - and accept either signal.
        max_gradient = float(np.max(np.abs(result.jac))) if result.jac is not None else np.inf
        self.max_gradient = max_gradient
        self.converged = bool(result.success or max_gradient < _GRADIENT_TOLERANCE)
        self.log_likelihood = -float(result.fun) * n  # report the summed LL
        self.n_observations = int(len(durations))
        self.n_events = int(events.sum())
        self.feature_names = list(feature_names or [f"x{i}" for i in range(x.shape[1])])
        return self

    # -------------------------------------------------------------- predict
    @property
    def shape(self) -> float:
        """Weibull shape k. k > 1 means hazard rises with age (wear-out)."""
        if self.log_shape is None:
            raise ValueError("Model is not fitted")
        return float(np.exp(self.log_shape))

    def _log_scale(self, x: np.ndarray) -> np.ndarray:
        if self.coefficients is None:
            raise ValueError("Model is not fitted")
        return self._design(np.asarray(x, dtype=float)) @ self.coefficients

    def survival_probability(self, x: np.ndarray, horizon_years: float) -> np.ndarray:
        """S(t|x): probability the component is still below threshold at t."""
        kz = self.shape * (np.log(max(horizon_years, _MIN_DURATION)) - self._log_scale(x))
        return np.exp(-np.exp(np.clip(kz, -500, 500)))

    def event_probability_within(self, x: np.ndarray, horizon_years: float) -> np.ndarray:
        """P(no longer suitable for its current application within the horizon) = 1 - S(t|x)."""
        return 1.0 - self.survival_probability(x, horizon_years)

    def event_probability_interval(
        self, x: np.ndarray, horizon_years: float, z: float = 1.96
    ) -> Dict[str, np.ndarray]:
        """Point estimate plus a confidence interval for P(event within h).

        The interval comes from the standard error of the linear predictor,
        Var(x'beta) = x' Sigma x, mapped through the (monotone decreasing in
        lambda) survival function - so a CI on the scale becomes a CI on the
        probability with the bounds swapped.
        """
        if self.covariance is None:
            raise ValueError("Model is not fitted")
        design = self._design(np.asarray(x, dtype=float))
        beta_covariance = self.covariance[:-1, :-1]
        variance = np.einsum("ij,jk,ik->i", design, beta_covariance, design)
        standard_error = np.sqrt(np.clip(variance, 0.0, None))

        log_time = np.log(max(horizon_years, _MIN_DURATION))
        log_scale = design @ self.coefficients

        def probability(shifted_log_scale: np.ndarray) -> np.ndarray:
            kz = self.shape * (log_time - shifted_log_scale)
            return 1.0 - np.exp(-np.exp(np.clip(kz, -500, 500)))

        # A larger scale means a longer life, hence a LOWER event probability.
        return {
            "probability": probability(log_scale),
            "lower": probability(log_scale + z * standard_error),
            "upper": probability(log_scale - z * standard_error),
        }

    def predict_median_years(self, x: np.ndarray) -> np.ndarray:
        """Median remaining time to threshold: lambda · (ln 2)^(1/k)."""
        return np.exp(self._log_scale(x)) * (np.log(2.0) ** (1.0 / self.shape))

    # ----------------------------------------------------------- reporting
    def summary(self) -> Dict[str, Any]:
        """Fitted parameters in a JSON-serialisable shape."""
        if self.coefficients is None:
            raise ValueError("Model is not fitted")
        standard_errors = np.sqrt(np.clip(np.diag(self.covariance), 0.0, None))
        terms = ["intercept", *self.feature_names]
        return {
            "shape_k": round(self.shape, 4),
            "shape_interpretation": (
                "k > 1: hazard increases with age (wear-out), which is what a "
                "degrading mechanical component should look like"
                if self.shape > 1
                else "k <= 1: hazard flat or decreasing with age - unexpected for "
                "wear-out, treat the fit as suspect"
            ),
            "converged": self.converged,
            "max_gradient": (
                round(float(self.max_gradient), 9) if self.max_gradient is not None else None
            ),
            "log_likelihood": round(float(self.log_likelihood), 3),
            "n_observations": self.n_observations,
            "n_events": self.n_events,
            "censoring_rate": round(1.0 - self.n_events / max(self.n_observations, 1), 4),
            "coefficients": {
                name: {
                    "value": round(float(value), 5),
                    "std_error": round(float(error), 5),
                }
                for name, value, error in zip(
                    terms, self.coefficients, standard_errors[:-1], strict=True
                )
            },
            "note": (
                "AFT coefficients act on log(time): a positive coefficient means "
                "a longer time to threshold for a higher feature value."
            ),
        }
