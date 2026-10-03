"""Recovery-world simulator with common random numbers.

Each customer's latent world (income calendar, when their balance runs dry, how they reply) is a
pure function of `(seed, customer_id)`. Every random draw during an episode is keyed by
`(seed, customer_id, event, day)`, so when the three policies are run on the same customer they
face the same luck. Differences between arms are caused by the policies, not by noise.

Nothing in here is visible to a policy except through the engine's `Case` and the payment
history passed in `Context` — exactly what a merchant / Razorpay would see.
"""

from __future__ import annotations

import calendar
import hashlib
import struct
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np

from . import codes
from .calibration import Calibration
from .engine import Engine
from .models import (
    IST, MESSAGE_TYPES, OUTREACH_TYPES, Action, ActionType, Case, FailureClass, Intent, ParsedReply, Rail,
)
from .payday import SuccessCurve, fit
from .policies import Context, Plan, Policy, at, bounce_cost_for

EPISODE_MONTH = (2026, 10)


class Rng:
    """Keyed uniform draws: the same key always gives the same number."""

    def __init__(self, seed: int, customer: str) -> None:
        self.prefix = f"{seed}|{customer}|"

    def u(self, *key: object) -> float:
        h = hashlib.blake2b((self.prefix + "|".join(map(str, key))).encode(), digest_size=8).digest()
        return struct.unpack(">Q", h)[0] / 2**64

    def choice(self, options: list, weights: list[float], *key: object) -> object:
        r, acc = self.u(*key), 0.0
        total = sum(weights)
        for o, w in zip(options, weights):
            acc += w / total
            if r < acc:
                return o
        return options[-1]

    def randint(self, lo: int, hi: int, *key: object) -> int:  # inclusive
        return lo + int(self.u(*key) * (hi - lo + 1))


def _last_day(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def _payday_in_month(kind: str, y: int, m: int) -> date:
    if kind == "last":
        return date(y, m, _last_day(y, m))
    return date(y, m, min(int(kind), _last_day(y, m)))


def _months_back(d: date, k: int) -> tuple[int, int]:
    idx = d.year * 12 + (d.month - 1) - k
    return idx // 12, idx % 12 + 1


@dataclass
class CustomerWorld:
    seed: int
    customer_id: str
    cal: Calibration
    rng: Rng = field(init=False)

    def __post_init__(self) -> None:
        r = self.rng = Rng(self.seed, self.customer_id)
        cal = self.cal
        self.rail = Rail.ENACH if r.u("rail") < cal.share_enach else Rail.UPI_AUTOPAY
        if self.rail is Rail.UPI_AUTOPAY:
            self.amount = float(r.choice(list(cal.upi_amounts), list(cal.upi_amount_weights), "amount"))
        else:
            z = np.sqrt(2) * _erfinv(2 * r.u("amount") - 1)
            self.amount = float(min(cal.enach_amount_cap, max(500.0, round(cal.enach_amount_median * np.exp(0.6 * z), -1))))
        self.mandate_max = self.amount * (1.0 if r.u("mmax") < 0.5 else 2.0)
        kinds = list(cal.payday_mix)
        self.payday_kind = str(r.choice(kinds, [cal.payday_mix[k] for k in kinds], "payday"))
        self.dry_after = r.randint(*cal.dry_after_days, "dry")
        self.bounce_charge = cal.enach_bounce_range[0] + r.u("bounce") * (cal.enach_bounce_range[1] - cal.enach_bounce_range[0]) \
            if self.rail is Rail.ENACH else cal.upi_bounce
        classes = list(cal.failure_mix)
        self.failure_class = FailureClass(r.choice(classes, [cal.failure_mix[c] for c in classes], "fclass"))
        self.wrong_person = r.u("wp") < cal.wrong_person
        self.paid_elsewhere = r.u("pe") < cal.paid_elsewhere
        self.wants_dispute = r.u("disp") < cal.intent_dispute
        self.wants_cancel = r.u("cancel") < cal.intent_cancel
        self.hardship = r.u("hard") < cal.intent_hardship
        self.failed_at = self._pick_failure_time()
        self.topup: tuple[date, date] | None = None
        if r.u("topup") < cal.topup_after_failure:
            start = self.failed_at.date() + timedelta(days=r.randint(*cal.topup_lag_days, "topup_lag"))
            self.topup = (start, start + timedelta(days=r.randint(*cal.topup_lasts_days, "topup_len")))

    # -- money --------------------------------------------------------------------------------------

    def _incomes(self, y: int, m: int) -> list[tuple[date, int]]:
        """Income events in a month as (day, days the money lasts)."""
        if self.payday_kind != "irregular":
            return [(_payday_in_month(self.payday_kind, y, m), self.dry_after)]
        cal, r = self.cal, self.rng
        n = r.randint(*cal.irregular_incomes_per_month, "inc_n", y, m)
        last = _last_day(y, m)
        return [(date(y, m, r.randint(1, last, "inc_d", y, m, i)), r.randint(*cal.irregular_funds_days, "inc_l", y, m, i))
                for i in range(n)]

    def has_funds(self, d: date) -> bool:
        topup = getattr(self, "topup", None)
        if topup is not None and topup[0] <= d < topup[1]:
            return True
        funded = False
        for k in (0, 1):
            y, m = _months_back(d, k)
            for start, lasts in self._incomes(y, m):
                if start <= d < start + timedelta(days=lasts):
                    funded = True
        if self.rng.u("noise", d) < self.cal.funds_noise:
            funded = not funded
        return funded

    def _pick_failure_time(self) -> datetime:
        y, m = EPISODE_MONTH
        start = self.rng.randint(1, 28, "bill")
        for off in range(28):
            d = date(y, m, (start - 1 + off) % 28 + 1)
            if self.failure_class is not FailureClass.INSUFFICIENT_FUNDS or not self.has_funds(d):
                return datetime.combine(d, time(9, 0), tzinfo=IST)
        return datetime.combine(date(y, m, start), time(9, 0), tzinfo=IST)

    # -- what the policy may see ----------------------------------------------------------------------

    def history(self, network: bool) -> list[tuple[date, bool]]:
        out: list[tuple[date, bool]] = []
        bill_dom = self.failed_at.day
        for k in range(1, self.cal.history_months + 1):
            y, m = _months_back(self.failed_at.date(), k)
            bill = date(y, m, min(bill_dom, _last_day(y, m)))
            ok = self.has_funds(bill)
            out.append((bill, ok))
            if not ok:  # past fixed-schedule retries, as most merchants run them today
                for j in (1, 2, 3):
                    rd = bill + timedelta(days=j)
                    s = self.has_funds(rd)
                    out.append((rd, s))
                    if s:
                        break
            if network:
                for i in range(self.cal.network_payments_per_month):
                    nd = date(y, m, self.rng.randint(1, _last_day(y, m), "net", y, m, i))
                    out.append((nd, self.has_funds(nd)))
        return out

    def true_payday(self) -> int | None:
        if self.payday_kind == "irregular":
            return None
        return 31 if self.payday_kind == "last" else int(self.payday_kind)

    def failure_code(self) -> str:
        options = codes.codes_for(self.failure_class, self.rail) or [
            c for c in codes.CODES if c.cls is self.failure_class and c.source_system == "razorpay"]
        if not options:
            return "U30"
        return options[int(self.rng.u("code") * len(options))].code

    # -- replies ---------------------------------------------------------------------------------------

    def next_income_after(self, d: date) -> date | None:
        for k in (0, -1):
            y, m = _months_back(d, k)
            future = sorted(s for s, _ in self._incomes(y, m) if s > d)
            if future:
                return future[0]
        return None

    def true_reply(self, d: date) -> tuple[Intent, date | None]:
        r = self.rng
        if self.wrong_person:
            return Intent.WRONG_PERSON, None
        if self.paid_elsewhere:
            return Intent.ALREADY_PAID, None
        if self.wants_dispute:
            return Intent.DISPUTE, None
        if self.wants_cancel:
            return Intent.CANCEL, None
        if self.hardship:
            return Intent.HARDSHIP, None
        if r.u("other", d) < 0.05:
            return Intent.OTHER, None
        if r.u("states_date", d) >= self.cal.states_date_given_promise:
            return Intent.PROMISE_TO_PAY, None
        if self.has_funds(d):
            return Intent.PROMISE_TO_PAY, d
        return Intent.PROMISE_TO_PAY, self.next_income_after(d)


def _erfinv(y: float) -> float:
    # Winitzki approximation; adequate for sampling a log-normal amount.
    a = 0.147
    ln = np.log(1 - y * y + 1e-12)
    t = 2 / (np.pi * a) + ln / 2
    return float(np.sign(y) * np.sqrt(np.sqrt(t * t - ln / a) - t))


@dataclass
class ParserModel:
    """Turns a customer's true intent into what the reply parser would output.

    `confusion[true][pred]` and `date_accuracy` come from the measured reply-parser evaluation, so
    parser mistakes flow into recovery outcomes instead of being assumed away.
    """

    confusion: dict[str, dict[str, float]]
    date_accuracy: float
    name: str = "baseline"

    def observe(self, rng: Rng, key: object, truth: Intent, true_date: date | None) -> ParsedReply:
        row = self.confusion.get(truth.value) or {truth.value: 1.0}
        intents = list(row)
        pred = Intent(rng.choice(intents, [row[i] for i in intents], "parse", key))
        promised = None
        if pred is Intent.PROMISE_TO_PAY and true_date is not None:
            if rng.u("date_ok", key) < self.date_accuracy:
                promised = true_date
            else:
                promised = true_date + timedelta(days=rng.randint(-3, 3, "date_err", key) or 1)
        return ParsedReply(pred, promised, None, True, self.name)


PERFECT_PARSER = ParserModel(confusion={}, date_accuracy=1.0, name="perfect")


@dataclass
class Outcome:
    case_id: str
    arm: str
    rail: str
    amount: float
    failure_class: str
    recovered: bool
    recovered_via: str
    days_to_recover: float | None
    bounce_cost: float
    outreach: int
    notices: int
    debits: int
    cancelled: bool
    escalated: bool
    blocked: int
    replies: int


def run_case(world: CustomerWorld, policy: Policy, engine: Engine, parser: ParserModel,
             prior: np.ndarray | None, network: bool = True) -> tuple[Outcome, Case]:
    r, cal = world.rng, world.cal
    case = Case(
        case_id=f"{world.seed}-{world.customer_id}", customer_id=world.customer_id, rail=world.rail,
        amount=world.amount, mandate_max=world.mandate_max, failed_at=world.failed_at,
        failure_code=world.failure_code(), failure_class=world.failure_class,
        mandate_active=world.failure_class is not FailureClass.MANDATE_INACTIVE,
    )
    engine.open_case(case)
    curve: SuccessCurve = fit(world.history(network), prior=prior)
    ctx = Context(curve=curve, bounce_cost=bounce_cost_for(world.rail, float(np.mean(cal.enach_bounce_range))))
    blocked_before = engine.blocked

    pending: list[Action] = []

    def apply(plan: Plan, now: datetime) -> None:
        nonlocal pending
        if plan.replace_pending:
            pending = [a for a in pending if a.at <= now]
        immediate = [a for a in plan.actions if a.at <= now]
        pending.extend(a for a in plan.actions if a.at > now)
        pending.sort(key=lambda a: a.at)
        for a in immediate:
            engine.propose(case, a)

    apply(policy.on_open(case, ctx), case.failed_at)

    bounce = 0.0
    link_day: date | None = None
    remandate_day: date | None = None
    cancelled = False
    replies = 0
    msg_index = 0
    start = case.failed_at.date()

    for day in range(0, 31):
        d = start + timedelta(days=day)
        if day == 1 and world.paid_elsewhere and not case.recovered:
            # Customer already paid through another channel; the merchant learns of it via reconciliation.
            engine.payment_received(case, at(d, time(10, 0)), "other_channel")
            break
        while pending and pending[0].at.date() == d and not case.recovered and not cancelled:
            a = pending.pop(0)
            if not engine.propose(case, a):
                continue
            if a.type is ActionType.DEBIT_ATTEMPT:
                tech_fault = case.failure_class is FailureClass.TECHNICAL and r.u("tech", d) < cal.technical_repeat_fail
                ok = case.mandate_active and world.has_funds(d) and not tech_fault
                if ok:
                    engine.debit_result(case, a.at, True)
                else:
                    cls = FailureClass.TECHNICAL if tech_fault else FailureClass.INSUFFICIENT_FUNDS
                    engine.debit_result(case, a.at, False, code=("U68" if tech_fault else "Z9"))
                    bounce += world.bounce_charge
                    apply(policy.on_debit_failed(case, a.at, cls, ctx), a.at)
            if a.type in MESSAGE_TYPES:
                msg_index += 1
                if a.type in OUTREACH_TYPES:
                    if a.type in (ActionType.PAYMENT_LINK, ActionType.REMINDER):
                        link_day = d
                    if a.type is ActionType.REMANDATE_LINK and r.u("remandate", d) < cal.remandate_rate:
                        remandate_day = d + timedelta(days=1 + int(r.u("remandate_lag", d) * 2))
                    if case.outreach_sent >= 2 and r.u("annoy", msg_index) < cal.annoyance_cancel:
                        engine.customer_cancelled(case, a.at + timedelta(hours=1))
                        cancelled = True
                        break
                if replies < 2 and r.u("reply", msg_index) < cal.reply_rate:
                    replies += 1
                    truth, tdate = world.true_reply(d)
                    reply_at = a.at + timedelta(hours=2)
                    parsed = parser.observe(r, msg_index, truth, tdate)
                    engine.reply_received(case, reply_at, parsed)
                    if truth is Intent.CANCEL:
                        engine.customer_cancelled(case, reply_at)
                        cancelled = True
                    apply(policy.on_reply(case, reply_at, parsed, ctx), reply_at)

        if case.recovered or cancelled:
            break
        eod = at(d, time(20, 0))
        if remandate_day == d and not case.mandate_active:
            engine.mandate_reactivated(case, eod)
            apply(policy.on_mandate_reactivated(case, eod, ctx), eod)
        funded = world.has_funds(d)
        stop_contact = world.wrong_person or world.wants_dispute
        if link_day is not None and funded and not stop_contact and 0 <= (d - link_day).days < cal.link_active_days:
            p = cal.link_pay_first_day * cal.link_decay ** (d - link_day).days
            if r.u("linkpay", d) < p:
                engine.payment_received(case, eod, "payment_link")
                break
        if funded and not stop_contact and r.u("organic", d) < cal.organic_daily:
            engine.payment_received(case, eod, "organic")
            break

    days = (case.recovered_at - case.failed_at).total_seconds() / 86400 if case.recovered_at else None
    outcome = Outcome(
        case_id=case.case_id, arm=policy.name, rail=world.rail.value, amount=world.amount,
        failure_class=world.failure_class.value, recovered=case.recovered, recovered_via=case.recovered_via,
        days_to_recover=days, bounce_cost=bounce, outreach=case.outreach_sent, notices=len(case.notices),
        debits=case.debit_attempts - 1, cancelled=cancelled, escalated=case.escalated,
        blocked=engine.blocked - blocked_before, replies=replies,
    )
    return outcome, case
