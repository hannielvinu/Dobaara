"""Core data types shared by the engine, the simulator and the API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


class Rail(StrEnum):
    UPI_AUTOPAY = "upi_autopay"
    ENACH = "enach"


class FailureClass(StrEnum):
    INSUFFICIENT_FUNDS = "insufficient_funds"
    TECHNICAL = "technical"            # transient: bank/PSP down, timeout
    MANDATE_INACTIVE = "mandate_inactive"  # revoked, paused, declined by customer
    LIMIT_EXCEEDED = "limit_exceeded"  # per-txn or frequency limit; retrying the same debit won't help
    ACCOUNT_BLOCKED = "account_blocked"  # closed / frozen / no such account: terminal
    RISK_DECLINE = "risk_decline"      # issuer risk rule: terminal, needs a person
    UNKNOWN = "unknown"


RETRIABLE = {FailureClass.INSUFFICIENT_FUNDS, FailureClass.TECHNICAL, FailureClass.UNKNOWN}
TERMINAL_FOR_DEBIT = {
    FailureClass.MANDATE_INACTIVE,
    FailureClass.LIMIT_EXCEEDED,
    FailureClass.ACCOUNT_BLOCKED,
    FailureClass.RISK_DECLINE,
}


class Intent(StrEnum):
    PROMISE_TO_PAY = "promise_to_pay"
    ALREADY_PAID = "already_paid"
    HARDSHIP = "hardship"
    CANCEL = "cancel"
    DISPUTE = "dispute"
    WRONG_PERSON = "wrong_person"
    OTHER = "other"


# Replies after which the customer must not be contacted or debited again.
STOP_INTENTS = {Intent.CANCEL, Intent.DISPUTE, Intent.WRONG_PERSON}


class ActionType(StrEnum):
    PRE_DEBIT_NOTICE = "pre_debit_notice"
    DEBIT_ATTEMPT = "debit_attempt"
    PAYMENT_LINK = "payment_link"
    REMANDATE_LINK = "remandate_link"
    REMINDER = "reminder"
    ESCALATE = "escalate"
    STOP = "stop"


OUTREACH_TYPES = {ActionType.PAYMENT_LINK, ActionType.REMANDATE_LINK, ActionType.REMINDER}
MESSAGE_TYPES = OUTREACH_TYPES | {ActionType.PRE_DEBIT_NOTICE}


@dataclass(frozen=True)
class ParsedReply:
    intent: Intent
    promised_date: date | None = None
    amount_inr: float | None = None
    grounded: bool = True
    parser: str = "baseline"


@dataclass(frozen=True)
class Action:
    type: ActionType
    at: datetime
    amount: float = 0.0
    reason: str = ""
    rule_id: str = ""          # which policy rule produced this action
    for_debit_at: datetime | None = None  # pre-debit notices: the debit they announce


@dataclass
class Case:
    """One failed recurring debit and everything that happened while recovering it."""

    case_id: str
    customer_id: str
    rail: Rail
    amount: float
    mandate_max: float
    failed_at: datetime
    failure_code: str
    failure_class: FailureClass
    mandate_active: bool = True
    debit_attempts: int = 1  # the original failed debit counts as attempt 1
    outreach_sent: int = 0
    stopped: bool = False
    stop_reason: str = ""
    recovered: bool = False
    recovered_at: datetime | None = None
    recovered_via: str = ""
    escalated: bool = False
    replies: list[ParsedReply] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    notices: list[Action] = field(default_factory=list)

    @property
    def window_end(self) -> datetime:
        return self.failed_at + timedelta(days=30)
