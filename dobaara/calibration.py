"""Simulator parameters. Every value is tagged `sourced` (with where it comes from) or `assumption`.

Assumptions are exactly what the sensitivity grid in `experiment.py` varies, so a reader can see
how much each conclusion depends on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .models import FailureClass

SOURCES = {
    "autopay_revocations": "Business Standard, Sep 2025: ~20M UPI AutoPay mandates revoked per month on low balance",
    "enach_bounce": "Bank NACH return charges commonly ₹250–500 + 18% GST (varies by bank; see aadesh README)",
    "retry_rules": "NPCI 2025: 1 original + 3 retries for a failed AutoPay debit",
}


@dataclass(frozen=True)
class Calibration:
    name: str = "base"

    # Population ----------------------------------------------------------------------------------
    share_enach: float = 0.30                       # assumption
    upi_amounts: tuple[int, ...] = (99, 149, 199, 299, 499, 799, 999, 1499, 2999)
    upi_amount_weights: tuple[float, ...] = (0.12, 0.14, 0.16, 0.16, 0.14, 0.10, 0.08, 0.06, 0.04)  # assumption
    enach_amount_median: float = 3500.0             # assumption (EMIs, insurance, SIPs)
    enach_amount_cap: float = 15000.0

    # Why the first debit failed, by class. Low balance dominates (sourced: autopay_revocations);
    # the exact split is an assumption.
    failure_mix: dict[FailureClass, float] = field(default_factory=lambda: {
        FailureClass.INSUFFICIENT_FUNDS: 0.62,
        FailureClass.TECHNICAL: 0.14,
        FailureClass.MANDATE_INACTIVE: 0.10,
        FailureClass.LIMIT_EXCEEDED: 0.04,
        FailureClass.ACCOUNT_BLOCKED: 0.04,
        FailureClass.RISK_DECLINE: 0.02,
        FailureClass.UNKNOWN: 0.04,
    })

    # Income: which day salary/income lands. Indian salaried pay is concentrated at month start /
    # month end; the split is an assumption. "irregular" = gig / daily-wage style income.
    payday_mix: dict[str, float] = field(default_factory=lambda: {
        "1": 0.32, "last": 0.22, "7": 0.12, "10": 0.10, "15": 0.06, "irregular": 0.18,
    })
    dry_after_days: tuple[int, int] = (8, 24)       # assumption: days after payday until balance < due amount
    irregular_incomes_per_month: tuple[int, int] = (2, 4)   # assumption
    irregular_funds_days: tuple[int, int] = (2, 7)          # assumption
    funds_noise: float = 0.05                       # assumption: chance funds state flips on a given day

    technical_repeat_fail: float = 0.20             # assumption: a technical fault recurs on the next try
    # After a failed debit the bank texts the customer; some move money in within days. This favours
    # quick retries (the naive policy), so it is in the world to keep the comparison honest.
    topup_after_failure: float = 0.25               # assumption
    topup_lag_days: tuple[int, int] = (1, 3)        # assumption
    topup_lasts_days: tuple[int, int] = (2, 5)      # assumption

    # Behaviour -------------------------------------------------------------------------------------
    reply_rate: float = 0.30                        # assumption: chance a message gets a text reply
    states_date_given_promise: float = 0.65         # assumption
    link_pay_first_day: float = 0.30                # assumption: pays a link on a day they have funds
    link_decay: float = 0.6
    link_active_days: int = 7
    remandate_rate: float = 0.25                    # assumption
    organic_daily: float = 0.01                     # assumption: pays on their own (notices service paused)
    annoyance_cancel: float = 0.02                  # assumption: cancel chance per outreach after the first
    intent_cancel: float = 0.08                     # assumption: already wants to cancel
    intent_hardship: float = 0.05
    intent_dispute: float = 0.02
    wrong_person: float = 0.02
    paid_elsewhere: float = 0.03

    # Customer harm -------------------------------------------------------------------------------
    enach_bounce_range: tuple[float, float] = (295.0, 590.0)  # sourced: enach_bounce (₹250–500 + 18% GST)
    upi_bounce: float = 0.0                         # assumption: failed UPI debits are not charged

    # Data available to the policy ----------------------------------------------------------------
    history_months: int = 6
    network_payments_per_month: int = 6             # assumption: other-merchant payments Razorpay sees


BASE = Calibration()

# A world the policy was not tuned on: different income calendar, quieter customers, pricier bounces.
SHIFTED = replace(
    BASE,
    name="shifted",
    payday_mix={"1": 0.18, "last": 0.14, "5": 0.16, "20": 0.12, "25": 0.10, "irregular": 0.30},
    reply_rate=0.18,
    states_date_given_promise=0.50,
    enach_bounce_range=(400.0, 700.0),
    share_enach=0.40,
)
