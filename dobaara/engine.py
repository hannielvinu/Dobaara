"""Engine: the only path by which an action reaches the outside world.

Policies propose; the engine runs each proposal through the compliance gate, executes what is
allowed, and writes everything (executed, blocked, observed) to the audit ledger.
"""

from __future__ import annotations

from datetime import datetime

from . import rules
from .audit import Ledger
from .models import Action, ActionType, Case, MESSAGE_TYPES, OUTREACH_TYPES, ParsedReply


class Engine:
    def __init__(self, ledger: Ledger | None = None) -> None:
        self.ledger = ledger if ledger is not None else Ledger()
        self.blocked = 0

    def open_case(self, case: Case) -> None:
        self.ledger.append(
            case.case_id, "case_opened", case.failed_at,
            customer_id=case.customer_id, rail=case.rail, amount=case.amount, mandate_max=case.mandate_max,
            failure_code=case.failure_code, failure_class=case.failure_class,
            mandate_active=case.mandate_active,
        )

    def propose(self, case: Case, action: Action) -> bool:
        violated = rules.check(case, action)
        if violated:
            self.blocked += 1
            self.ledger.append(
                case.case_id, "action_blocked", action.at,
                type=action.type, amount=action.amount, policy_rule=action.rule_id, violated=violated,
            )
            return False

        if action.type is ActionType.DEBIT_ATTEMPT:
            case.debit_attempts += 1
        elif action.type is ActionType.PRE_DEBIT_NOTICE:
            case.notices.append(action)
        if action.type in OUTREACH_TYPES:
            case.outreach_sent += 1
        if action.type is ActionType.ESCALATE:
            case.escalated = True
        if action.type is ActionType.STOP:
            case.stopped = True
            case.stop_reason = action.reason
        case.actions.append(action)

        self.ledger.append(
            case.case_id, "action_executed", action.at,
            type=action.type, amount=action.amount, policy_rule=action.rule_id, reason=action.reason,
            for_debit_at=action.for_debit_at, is_message=action.type in MESSAGE_TYPES,
        )
        return True

    def debit_result(self, case: Case, at: datetime, success: bool, code: str = "") -> None:
        self.ledger.append(case.case_id, "debit_result", at, success=success, code=code)
        if success:
            self._recovered(case, at, "retry")

    def payment_received(self, case: Case, at: datetime, via: str) -> None:
        self.ledger.append(case.case_id, "payment_received", at, via=via, amount=case.amount)
        self._recovered(case, at, via)

    def reply_received(self, case: Case, at: datetime, parsed: ParsedReply) -> None:
        case.replies.append(parsed)
        self.ledger.append(
            case.case_id, "reply_received", at, intent=parsed.intent, promised_date=parsed.promised_date,
            amount_inr=parsed.amount_inr, grounded=parsed.grounded, parser=parsed.parser,
        )

    def mandate_reactivated(self, case: Case, at: datetime) -> None:
        case.mandate_active = True
        self.ledger.append(case.case_id, "mandate_reactivated", at)

    def customer_cancelled(self, case: Case, at: datetime) -> None:
        case.stopped = True
        case.stop_reason = "customer_cancelled_subscription"
        self.ledger.append(case.case_id, "subscription_cancelled", at)

    def _recovered(self, case: Case, at: datetime, via: str) -> None:
        if not case.recovered:
            case.recovered, case.recovered_at, case.recovered_via = True, at, via
            self.ledger.append(case.case_id, "case_recovered", at, via=via, amount=case.amount)
