"""Recovery policies. A policy only *proposes* actions; the engine and its gate decide what runs.

Three policies share one interface so the experiment can compare them on identical cases:

- DoNothing  — baseline A: no action.
- Naive      — baseline B: the common fixed schedule (retry on each of the next 3 days, one link).
- Dobaara    — the system under test.

Every action carries a `rule_id` naming the policy rule that produced it, so each decision in the
audit log can be traced back to one line of this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .models import IST, Action, ActionType, Case, FailureClass, Intent, ParsedReply, RETRIABLE, Rail, STOP_INTENTS
from .payday import SuccessCurve

NOTICE_HOUR = time(11, 0)
DEBIT_HOUR = time(14, 0)
LINK_HOUR = time(11, 30)
REMINDER_HOUR = time(12, 0)


@dataclass
class Context:
    """What a policy is allowed to know about the customer at decision time."""

    curve: SuccessCurve | None = None
    bounce_cost: float = 0.0  # expected bank charge to the customer for one failed debit on this rail


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)
    replace_pending: bool = False  # drop previously scheduled, not-yet-run actions


def at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=IST)


def next_contact_slot(now: datetime, t: time = LINK_HOUR) -> datetime:
    slot = at(now.date(), t)
    return slot if slot >= now else at(now.date() + timedelta(days=1), t)


def notice_and_debit(case: Case, now: datetime, debit_day: date, rule_id: str, reason: str) -> list[Action]:
    """A debit on `debit_day` plus the pre-debit notice that must precede it by 24h.

    If the notice can no longer be sent 24h ahead, the debit moves to the next day.
    """
    while True:
        debit_at = at(debit_day, DEBIT_HOUR)
        notice_at = at(debit_day - timedelta(days=1), NOTICE_HOUR)
        if notice_at < now:
            notice_at = next_contact_slot(now, NOTICE_HOUR)
        if debit_at - notice_at >= timedelta(hours=24):
            break
        debit_day += timedelta(days=1)
    return [
        Action(ActionType.PRE_DEBIT_NOTICE, notice_at, case.amount, reason, rule_id, for_debit_at=debit_at),
        Action(ActionType.DEBIT_ATTEMPT, debit_at, case.amount, reason, rule_id),
    ]


class Policy:
    name = "policy"

    def on_open(self, case: Case, ctx: Context) -> Plan:
        return Plan()

    def on_debit_failed(self, case: Case, now: datetime, cls: FailureClass, ctx: Context) -> Plan:
        return Plan()

    def on_reply(self, case: Case, now: datetime, reply: ParsedReply, ctx: Context) -> Plan:
        if reply.intent in STOP_INTENTS:
            return Plan([Action(ActionType.STOP, now, reason=f"customer replied {reply.intent}", rule_id="STOP-ON-REPLY")],
                        replace_pending=True)
        return Plan()

    def on_mandate_reactivated(self, case: Case, now: datetime, ctx: Context) -> Plan:
        return Plan()


class DoNothing(Policy):
    name = "do_nothing"

    def on_reply(self, case: Case, now: datetime, reply: ParsedReply, ctx: Context) -> Plan:
        return Plan()


class Naive(Policy):
    """Fixed schedule: payment link now, retry on each of the next three days."""

    name = "naive"

    def on_open(self, case: Case, ctx: Context) -> Plan:
        now = case.failed_at
        actions = [Action(ActionType.PAYMENT_LINK, next_contact_slot(now), case.amount, "standard dunning link", "N-LINK")]
        if case.failure_class in RETRIABLE:
            day = now.date()
            for k in (1, 2, 3):
                actions += notice_and_debit(case, now, day + timedelta(days=k), "N-RETRY-DAILY", f"fixed retry {k}/3")
        return Plan(actions)


class Calendar(Policy):
    """A sensible heuristic a merchant might write: retry around common salary days (1st, 2nd, 7th).

    Not in the original plan; added before any test run to check whether Dobaara's gain over the
    naive schedule is just "wait for the 1st".
    """

    name = "calendar"
    SALARY_DAYS = (1, 2, 7)

    def on_open(self, case: Case, ctx: Context) -> Plan:
        now = case.failed_at
        actions = [Action(ActionType.PAYMENT_LINK, next_contact_slot(now), case.amount, "standard dunning link", "C-LINK")]
        if case.failure_class in RETRIABLE:
            d, picked = now.date() + timedelta(days=1), []
            while len(picked) < 3 and at(d, DEBIT_HOUR) < case.window_end:
                if d.day in self.SALARY_DAYS:
                    picked.append(d)
                d += timedelta(days=1)
            for k, day in enumerate(picked, 1):
                actions += notice_and_debit(case, now, day, "C-RETRY-SALARY-DAY", f"retry on salary day {day.day}")
        return Plan(actions)


class Dobaara(Policy):
    """Failure-aware, payday-timed, harm-aware, reply-aware recovery."""

    name = "dobaara"

    def __init__(self, harm_weight: float = 1.0, p_min: float = 0.35, min_gap_days: int = 2,
                 escalate_amount: float = 5000.0) -> None:
        self.harm_weight = harm_weight
        self.p_min = p_min
        self.min_gap_days = min_gap_days
        self.escalate_amount = escalate_amount

    # -- planning helpers -------------------------------------------------------------------------

    def _retry_days(self, case: Case, start: date, end: date, k: int, ctx: Context) -> list[date]:
        """Pick up to k retry days with the best success odds whose expected value is positive.

        Expected value of one attempt = p * amount - harm_weight * (1 - p) * bounce_cost.
        On eNACH a failed attempt costs the customer a bank charge, so low-odds retries are refused.
        """
        if k <= 0 or ctx.curve is None:
            return []
        scored = []
        d = start
        while d <= end:
            p = ctx.curve.at(d)
            ev = p * case.amount - self.harm_weight * (1 - p) * ctx.bounce_cost
            if p >= self.p_min and ev > 0:
                scored.append((p, d))
            d += timedelta(days=1)
        chosen: list[date] = []
        for p, d in sorted(scored, key=lambda x: (-x[0], x[1])):
            if all(abs((d - c).days) >= self.min_gap_days for c in chosen):
                chosen.append(d)
            if len(chosen) == k:
                break
        return sorted(chosen)

    def _remaining_retries(self, case: Case) -> int:
        return max(0, 4 - case.debit_attempts)

    def _retry_plan(self, case: Case, now: datetime, ctx: Context, k: int, rule: str) -> list[Action]:
        start = now.date() + timedelta(days=1)
        end = (case.window_end - timedelta(days=1)).date()
        actions: list[Action] = []
        for d in self._retry_days(case, start, end, k, ctx):
            p = ctx.curve.at(d) if ctx.curve else 0.0
            actions += notice_and_debit(case, now, d, rule, f"retry when funds likely (p={p:.2f})")
        return actions

    # -- events -----------------------------------------------------------------------------------

    def on_open(self, case: Case, ctx: Context) -> Plan:
        now, cls = case.failed_at, case.failure_class
        link_at = next_contact_slot(now)
        actions: list[Action] = []

        if cls in (FailureClass.ACCOUNT_BLOCKED, FailureClass.RISK_DECLINE, FailureClass.LIMIT_EXCEEDED):
            actions.append(Action(ActionType.PAYMENT_LINK, link_at, case.amount,
                                  f"{cls}: the mandate cannot be debited; offer another way to pay", "D-TERMINAL-LINK"))
            if cls is FailureClass.RISK_DECLINE or case.amount >= self.escalate_amount:
                actions.append(Action(ActionType.ESCALATE, now, reason=f"{cls} on ₹{case.amount:,.0f}", rule_id="D-ESCALATE-TERMINAL"))
        elif cls is FailureClass.MANDATE_INACTIVE:
            # Collect this due now via a link, and ask for a fresh mandate for future dues.
            actions.append(Action(ActionType.PAYMENT_LINK, link_at, case.amount,
                                  "mandate revoked/paused: collect this due by link", "D-INACTIVE-LINK"))
            actions.append(Action(ActionType.REMANDATE_LINK, link_at + timedelta(days=1), case.amount,
                                  "mandate revoked/paused: ask the customer to re-authorise", "D-REMANDATE"))
        elif cls is FailureClass.TECHNICAL:
            # Bank-side fault: money is probably there, retry at the first compliant slot.
            actions += notice_and_debit(case, now, now.date() + timedelta(days=1), "D-TECH-RETRY", "transient bank/PSP fault")
            actions.append(Action(ActionType.PAYMENT_LINK, link_at, case.amount,
                                  "UPI link in case the bank stays down", "D-SOFT-LINK"))
        elif cls is FailureClass.INSUFFICIENT_FUNDS:
            actions += self._retry_plan(case, now, ctx, self._remaining_retries(case), "D-PAYDAY-RETRY")
            actions.append(Action(ActionType.PAYMENT_LINK, link_at, case.amount,
                                  "UPI link: pay whenever money is in, no bounce charge", "D-SOFT-LINK"))
        else:  # UNKNOWN: be conservative
            actions += self._retry_plan(case, now, ctx, 1, "D-UNKNOWN-ONE-RETRY")
            actions.append(Action(ActionType.ESCALATE, now, reason="unrecognised failure code", rule_id="D-ESCALATE-UNKNOWN"))
        return Plan(actions)

    def on_debit_failed(self, case: Case, now: datetime, cls: FailureClass, ctx: Context) -> Plan:
        if cls in (FailureClass.ACCOUNT_BLOCKED, FailureClass.RISK_DECLINE, FailureClass.LIMIT_EXCEEDED,
                   FailureClass.MANDATE_INACTIVE):
            case.failure_class = cls
            return Plan([Action(ActionType.PAYMENT_LINK, next_contact_slot(now), case.amount,
                                f"retry hit {cls}; stop debiting, offer a link", "D-TERMINAL-AFTER-RETRY")],
                        replace_pending=True)
        if case.failure_class is FailureClass.TECHNICAL and cls is FailureClass.TECHNICAL:
            # Fault recurred: try once more after a day's gap, then fall back to payday timing.
            return Plan(notice_and_debit(case, now, now.date() + timedelta(days=2), "D-TECH-RETRY-2", "bank fault recurred"))
        if case.failure_class is FailureClass.TECHNICAL and cls is FailureClass.INSUFFICIENT_FUNDS:
            # It was not a bank fault after all: switch to payday timing.
            case.failure_class = cls
            return Plan(self._retry_plan(case, now, ctx, self._remaining_retries(case), "D-PAYDAY-RETRY"),
                        replace_pending=True)
        return Plan()

    def on_reply(self, case: Case, now: datetime, reply: ParsedReply, ctx: Context) -> Plan:
        intent = reply.intent
        if intent in STOP_INTENTS:
            actions = [Action(ActionType.STOP, now, reason=f"customer replied {intent}", rule_id="D-STOP-ON-REPLY")]
            if intent is Intent.DISPUTE:
                actions.append(Action(ActionType.ESCALATE, now, reason="customer disputes the charge", rule_id="D-ESCALATE-DISPUTE"))
            return Plan(actions, replace_pending=True)
        if intent is Intent.ALREADY_PAID:
            return Plan([Action(ActionType.ESCALATE, now, reason="customer says already paid: reconcile before any debit",
                                rule_id="D-PAID-CLAIM")], replace_pending=True)
        if intent is Intent.HARDSHIP:
            return Plan([Action(ActionType.ESCALATE, now, reason="hardship: offer pause or smaller plan",
                                rule_id="D-HARDSHIP")], replace_pending=True)
        if intent is Intent.PROMISE_TO_PAY and reply.promised_date is not None and reply.grounded:
            promised = reply.promised_date
            debit_day = max(promised + timedelta(days=1), now.date() + timedelta(days=1))
            if at(debit_day, DEBIT_HOUR) >= case.window_end or case.failure_class not in RETRIABLE or not case.mandate_active:
                return Plan()
            actions = notice_and_debit(case, now, debit_day, "D-PROMISE-RETRY", f"customer promised to pay by {promised}")
            if promised > now.date():
                actions.append(Action(ActionType.REMINDER, at(promised, REMINDER_HOUR), case.amount,
                                      "reminder on the promised day", "D-PROMISE-REMINDER"))
            return Plan(actions, replace_pending=True)
        if intent is Intent.OTHER:
            return Plan([Action(ActionType.ESCALATE, now, reason="reply not understood", rule_id="D-ESCALATE-OTHER")])
        return Plan()

    def on_mandate_reactivated(self, case: Case, now: datetime, ctx: Context) -> Plan:
        case.failure_class = FailureClass.INSUFFICIENT_FUNDS if ctx.curve else FailureClass.UNKNOWN
        actions = self._retry_plan(case, now, ctx, 1, "D-AFTER-REMANDATE")
        if not actions:
            actions = notice_and_debit(case, now, now.date() + timedelta(days=2), "D-AFTER-REMANDATE", "mandate re-authorised")
        return Plan(actions, replace_pending=True)


def bounce_cost_for(rail: Rail, enach_charge: float) -> float:
    return enach_charge if rail is Rail.ENACH else 0.0
