"""Live recovery service: webhooks in, gated actions out, on a clock you can fast-forward.

Real recovery plays out over weeks, so the service runs on its own clock. `advance(hours)` executes
every scheduled action that falls due, through the same engine, gate and ledger as the experiment.
Debit outcomes come from Razorpay test mode when keys and a mandate token are configured, and from
a demo bank (the simulator's customer model) otherwise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from . import codes
from .audit import Ledger
from .calibration import BASE
from .engine import Engine
from .models import IST, Action, ActionType, Case, FailureClass, MESSAGE_TYPES, Rail
from .payday import fit, population_prior
from .policies import Context, Dobaara, Plan, bounce_cost_for
from .razorpay import RazorpayClient
from .replies import baseline
from .simulator import CustomerWorld
from .verify import verify


@dataclass
class Message:
    case_id: str
    at: datetime
    kind: str
    text: str
    link: str | None = None


@dataclass
class Service:
    razorpay: RazorpayClient = field(default_factory=RazorpayClient.from_env)
    ledger_path: Path | None = None
    clock: datetime = field(default_factory=lambda: datetime.now(IST).replace(minute=0, second=0, microsecond=0))
    policy: Dobaara = field(default_factory=Dobaara)

    def __post_init__(self) -> None:
        self.engine = Engine(Ledger(self.ledger_path))
        self.cases: dict[str, Case] = {}
        self.ctx: dict[str, Context] = {}
        self.pending: dict[str, list[Action]] = {}
        self.worlds: dict[str, CustomerWorld] = {}
        self.outbox: list[Message] = []
        self.queue: list[dict[str, Any]] = []
        self.links: dict[str, str] = {}
        self._prior = population_prior([CustomerWorld(999, f"p{i}", BASE).history(True) for i in range(150)])

    # -- opening cases --------------------------------------------------------------------------------

    def open_case(self, *, case_id: str, customer_id: str, rail: Rail, amount: float, mandate_max: float,
                  source_system: str, code: str, description: str = "",
                  history: list[tuple[date, bool]] | None = None, world: CustomerWorld | None = None) -> Case:
        if case_id in self.cases:
            return self.cases[case_id]
        cls = codes.classify(source_system, code, description)
        case = Case(case_id, customer_id, rail, amount, mandate_max, self.clock, code, cls,
                    mandate_active=cls is not FailureClass.MANDATE_INACTIVE)
        self.cases[case_id] = case
        self.pending[case_id] = []
        if world is not None:
            self.worlds[case_id] = world
        curve = fit(history or [], prior=self._prior)
        self.ctx[case_id] = Context(curve=curve, bounce_cost=bounce_cost_for(rail, float(np.mean(BASE.enach_bounce_range))))
        self.engine.open_case(case)
        self._apply(case, self.policy.on_open(case, self.ctx[case_id]), self.clock)
        return case

    def open_demo_cases(self, n: int = 6, seed: int = 4242) -> list[Case]:
        """Customers from the simulator, so the demo bank answers debits consistently with their income."""
        out = []
        worlds = sorted((CustomerWorld(seed, f"demo{i:03d}", BASE) for i in range(n)), key=lambda w: w.failed_at)
        for i, w in enumerate(worlds):
            # Open cases in time order, running everything already due, so the ledger stays chronological.
            if w.failed_at > self.clock:
                self.run_until(w.failed_at)
            out.append(self.open_case(
                case_id=f"case_{seed}_{i:03d}", customer_id=w.customer_id, rail=w.rail, amount=w.amount,
                mandate_max=w.mandate_max, source_system="upi" if w.rail is Rail.UPI_AUTOPAY else "nach",
                code=w.failure_code(), history=w.history(True), world=w,
            ))
        return out

    def handle_webhook(self, event: dict[str, Any]) -> dict[str, Any]:
        kind = event.get("event", "")
        if kind == "payment.failed":
            p = event["payload"]["payment"]["entity"]
            notes = p.get("notes") or {}
            if not (p.get("recurring") or notes.get("subscription_id") or p.get("token_id")):
                return {"ignored": "not a recurring debit"}
            case = self.open_case(
                case_id=f"case_{p['id']}", customer_id=p.get("customer_id") or p.get("contact", "unknown"),
                rail=Rail.ENACH if p.get("method") in ("emandate", "nach") else Rail.UPI_AUTOPAY,
                amount=p["amount"] / 100, mandate_max=float(notes.get("mandate_max", p["amount"] / 100)),
                source_system="razorpay", code=p.get("error_reason") or "", description=p.get("error_description") or "",
            )
            return {"case_id": case.case_id, "failure_class": case.failure_class.value}
        if kind == "payment_link.paid":
            ref = event["payload"]["payment_link"]["entity"].get("reference_id")
            case = self.cases.get(ref or "")
            if case:
                self.engine.payment_received(case, self.clock, "payment_link")
                self.pending[case.case_id] = []
                return {"case_id": case.case_id, "recovered": True}
        return {"ignored": kind}

    # -- customer replies ----------------------------------------------------------------------------

    def reply(self, case_id: str, text: str, parser: str = "baseline") -> dict[str, Any]:
        case = self.cases[case_id]
        if parser == "llm":
            from .replies.llm import LLMParser
            parsed = LLMParser().parse(text, self.clock.date())
        else:
            parsed = baseline.parse(text, self.clock.date())
        self.engine.reply_received(case, self.clock, parsed)
        self._apply(case, self.policy.on_reply(case, self.clock, parsed, self.ctx[case_id]), self.clock)
        return {"intent": parsed.intent.value, "promised_date": parsed.promised_date.isoformat() if parsed.promised_date else None,
                "grounded": parsed.grounded, "parser": parsed.parser}

    def mark_link_paid(self, case_id: str) -> None:
        case = self.cases[case_id]
        self.engine.payment_received(case, self.clock, "payment_link")
        self.pending[case_id] = []

    # -- time ------------------------------------------------------------------------------------------

    def advance(self, hours: int) -> int:
        return self.run_until(self.clock + timedelta(hours=hours))

    def run_until(self, end: datetime) -> int:
        ran = 0
        while True:
            due = sorted(((a.at, cid, a) for cid, acts in self.pending.items() for a in acts if a.at <= end),
                         key=lambda x: x[0])
            if not due:
                break
            at, cid, action = due[0]
            self.pending[cid].remove(action)
            self.clock = max(self.clock, at)
            self._execute(self.cases[cid], action)
            ran += 1
        self.clock = end
        return ran

    # -- internals -------------------------------------------------------------------------------------

    def _apply(self, case: Case, plan: Plan, now: datetime) -> None:
        if plan.replace_pending:
            self.pending[case.case_id] = [a for a in self.pending[case.case_id] if a.at <= now]
        for a in plan.actions:
            if a.at <= now:
                self._execute(case, a)
            else:
                self.pending[case.case_id].append(a)

    def _execute(self, case: Case, a: Action) -> None:
        if case.recovered:
            return
        if not self.engine.propose(case, a):
            return
        if a.type is ActionType.PAYMENT_LINK:
            link = self.razorpay.create_payment_link(
                amount_inr=case.amount, reference_id=case.case_id, description="Your subscription payment",
                customer_name=case.customer_id, contact="+919999999999")
            self.links[case.case_id] = link.get("short_url", "")
            self.outbox.append(Message(case.case_id, a.at, a.type.value, _copy(a, case), self.links[case.case_id]))
        elif a.type in MESSAGE_TYPES:
            self.outbox.append(Message(case.case_id, a.at, a.type.value, _copy(a, case)))
        elif a.type is ActionType.ESCALATE:
            self.queue.append({"case_id": case.case_id, "at": a.at.isoformat(), "reason": a.reason})
        elif a.type is ActionType.DEBIT_ATTEMPT:
            world = self.worlds.get(case.case_id)
            ok = bool(world and case.mandate_active and world.has_funds(a.at.date()))
            self.engine.debit_result(case, a.at, ok, "" if ok else "Z9")
            if ok:
                self.pending[case.case_id] = []
            else:
                self._apply(case, self.policy.on_debit_failed(case, a.at, FailureClass.INSUFFICIENT_FUNDS,
                                                              self.ctx[case.case_id]), a.at)

    # -- views -----------------------------------------------------------------------------------------

    def case_view(self, case_id: str) -> dict[str, Any]:
        c = self.cases[case_id]
        return {
            "case_id": c.case_id, "customer_id": c.customer_id, "rail": c.rail.value, "amount": c.amount,
            "failure_code": c.failure_code, "failure_class": c.failure_class.value, "failed_at": c.failed_at.isoformat(),
            "recovered": c.recovered, "recovered_via": c.recovered_via, "stopped": c.stopped, "escalated": c.escalated,
            "debit_attempts": c.debit_attempts, "outreach_sent": c.outreach_sent,
            "pending": [{"type": a.type.value, "at": a.at.isoformat(), "reason": a.reason, "rule": a.rule_id}
                        for a in sorted(self.pending[case_id], key=lambda a: a.at)],
            "timeline": [r.as_dict() for r in self.engine.ledger.for_case(case_id)],
            "curve": [round(float(x), 3) for x in self.ctx[case_id].curve.p] if self.ctx[case_id].curve else None,
        }

    def summary(self) -> dict[str, Any]:
        cs = list(self.cases.values())
        return {
            "clock": self.clock.isoformat(), "razorpay_mode": self.razorpay.mode, "cases": len(cs),
            "recovered": sum(c.recovered for c in cs), "recovered_inr": sum(c.amount for c in cs if c.recovered),
            "due_inr": sum(c.amount for c in cs), "escalations": len(self.queue), "blocked_by_gate": self.engine.blocked,
            "verifier": verify(self.engine.ledger.dump()).as_dict(),
        }


def _copy(a: Action, c: Case) -> str:
    amt = f"₹{c.amount:,.0f}"
    if a.type is ActionType.PRE_DEBIT_NOTICE:
        return f"Your subscription payment of {amt} will be debited on {a.for_debit_at:%d %b, %I:%M %p}. Reply if you need more time."
    if a.type is ActionType.PAYMENT_LINK:
        return f"Your {amt} subscription payment didn't go through. Pay anytime via UPI with this link — no bank charges."
    if a.type is ActionType.REMANDATE_LINK:
        return f"Your AutoPay for {amt} is paused. Tap to re-authorise so your plan keeps running."
    if a.type is ActionType.REMINDER:
        return f"Gentle reminder about your {amt} payment, as you mentioned. Reply STOP to opt out."
    return a.reason


def dump_json(obj: Any) -> str:
    return json.dumps(obj, default=str)
