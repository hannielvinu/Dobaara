"""When is this customer likely to have money? A small, inspectable estimator — not an LLM.

Input is the customer's payment history as (date, succeeded) pairs. On Razorpay this can include
payments to *other* merchants on the network, which a single merchant never sees; the experiment
measures how much that network view adds (`network_history` ablation).

Model: kernel-smoothed success rate by day of month on a 31-day circle, shrunk toward a population
prior when the customer has little history. Cheap, deterministic, and explainable in one sentence:
"payments from this customer usually succeed on the 1st–4th of the month".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

DAYS = 31
_DOM = np.arange(1, DAYS + 1)


def _circ_dist(a: np.ndarray | int, b: np.ndarray | int) -> np.ndarray:
    d = np.abs(np.asarray(a) - np.asarray(b)) % DAYS
    return np.minimum(d, DAYS - d)


@dataclass(frozen=True)
class SuccessCurve:
    p: np.ndarray       # p[dom-1] = estimated probability a debit succeeds on that day of month
    n_obs: int

    def at(self, d: date) -> float:
        return float(self.p[min(d.day, DAYS) - 1])

    def likely_payday(self) -> int:
        """Day of month where the success probability rises most steeply (the 'money arrives' day)."""
        rise = self.p - np.roll(self.p, 2)
        return int(_DOM[int(np.argmax(rise))])


def fit(history: list[tuple[date, bool]], prior: np.ndarray | None = None,
        bandwidth: float = 1.5, prior_strength: float = 2.0) -> SuccessCurve:
    if prior is None:
        prior = np.full(DAYS, 0.5)
    if not history:
        return SuccessCurve(prior.copy(), 0)
    days = np.array([min(d.day, DAYS) for d, _ in history])
    ok = np.array([1.0 if s else 0.0 for _, s in history])
    w = np.exp(-(_circ_dist(_DOM[:, None], days[None, :]) ** 2) / (2 * bandwidth ** 2))
    succ = (w * ok[None, :]).sum(axis=1)
    tot = w.sum(axis=1)
    p = (succ + prior_strength * prior) / (tot + prior_strength)
    return SuccessCurve(np.clip(p, 0.0, 1.0), len(history))


def population_prior(histories: list[list[tuple[date, bool]]]) -> np.ndarray:
    """Pooled curve across many customers; the shrinkage target for thin histories."""
    pooled = [h for hist in histories for h in hist]
    return fit(pooled, prior=np.full(DAYS, 0.5), bandwidth=2.0, prior_strength=10.0).p


def payday_error_days(estimated: int, true_day: int) -> int:
    return int(_circ_dist(estimated, true_day))
