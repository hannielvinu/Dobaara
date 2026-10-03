"""Compliance gate. Every action from every policy passes through `check` before it executes.

The gate is deterministic and has a veto: a policy can propose anything, but only actions with no
violated rule are executed. Blocked proposals are written to the audit log with the rule ids.

Where a regulation allows two readings, the stricter one is implemented and the choice is noted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .models import (
    MESSAGE_TYPES,
    OUTREACH_TYPES,
    Action,
    ActionType,
    Case,
    FailureClass,
    Intent,
    STOP_INTENTS,
)

MAX_DEBIT_ATTEMPTS = 4  # 1 original + 3 retries
OUTREACH_CAP = 3
NOTICE_LEAD = timedelta(hours=24)
CONTACT_START, CONTACT_END = time(8, 0), time(19, 0)
TERMINAL_DEBIT_CLASSES = {
    FailureClass.ACCOUNT_BLOCKED,
    FailureClass.RISK_DECLINE,
    FailureClass.LIMIT_EXCEEDED,
}


@dataclass(frozen=True)
class Rule:
    id: str
    text: str
    source: str


RULES: dict[str, Rule] = {r.id: r for r in [
    Rule("R1_MAX_ATTEMPTS", "At most 4 debit attempts per due amount (1 original + 3 retries).",
         "NPCI UPI AutoPay retry rules, 2025"),
    Rule("R2_PRE_DEBIT_NOTICE", "Every debit attempt is announced by a pre-debit notice sent at least "
         "24 hours earlier for that exact amount. (Stricter reading: one notice per attempt, not per cycle.)",
         "RBI e-mandate framework; NPCI UPI AutoPay"),
    Rule("R3_EXECUTION_WINDOW", "Debits run only before 10:00, between 13:00 and 17:00, or after 21:30 IST.",
         "NPCI 2025 off-peak execution windows for recurring UPI"),
    Rule("R4_CONTACT_HOURS", "Customer messages are sent only between 08:00 and 19:00 IST.",
         "RBI guidance on recovery contact hours, adopted voluntarily"),
    Rule("R5_OUTREACH_CAP", "At most 3 outreach messages (links and reminders) per case.",
         "Dobaara policy (anti-harassment)"),
    Rule("R6_STOP_RESPECTED", "After a cancel, dispute or wrong-person reply: no further messages or debits.",
         "Dobaara policy; consent"),
    Rule("R7_NO_DEBIT_WHEN_TERMINAL", "No debit when the failure is terminal for debits or the mandate is inactive.",
         "Failure-code semantics"),
    Rule("R8_AMOUNT_BOUND", "A debit never exceeds the amount due or the mandate's maximum.",
         "RBI e-mandate framework"),
    Rule("R9_RECOVERY_WINDOW", "No action more than 30 days after the original failure.",
         "Dobaara policy (stopping rule)"),
    Rule("R10_NO_DOUBLE_DEBIT", "No debit once the case is recovered, or after the customer says they already "
         "paid (until a person reconciles).", "Dobaara policy (double-debit guard)"),
]}


def in_execution_window(at: datetime) -> bool:
    t = at.timetz().replace(tzinfo=None)
    return t < time(10, 0) or time(13, 0) <= t < time(17, 0) or t >= time(21, 30)


def in_contact_hours(at: datetime) -> bool:
    t = at.timetz().replace(tzinfo=None)
    return CONTACT_START <= t < CONTACT_END


def _stopped_by_reply(case: Case) -> bool:
    return any(r.intent in STOP_INTENTS for r in case.replies)


def _claims_paid(case: Case) -> bool:
    return any(r.intent is Intent.ALREADY_PAID for r in case.replies)


def check(case: Case, action: Action) -> list[str]:
    """Return the ids of every rule `action` would violate. Empty list means allowed."""
    violated: list[str] = []
    at = action.at

    if at > case.window_end:
        violated.append("R9_RECOVERY_WINDOW")

    if action.type in MESSAGE_TYPES:
        if not in_contact_hours(at):
            violated.append("R4_CONTACT_HOURS")
        if _stopped_by_reply(case) or case.stopped:
            violated.append("R6_STOP_RESPECTED")

    if action.type in OUTREACH_TYPES and case.outreach_sent >= OUTREACH_CAP:
        violated.append("R5_OUTREACH_CAP")

    if action.type is ActionType.DEBIT_ATTEMPT:
        if case.debit_attempts >= MAX_DEBIT_ATTEMPTS:
            violated.append("R1_MAX_ATTEMPTS")
        if not _has_valid_notice(case, action):
            violated.append("R2_PRE_DEBIT_NOTICE")
        if not in_execution_window(at):
            violated.append("R3_EXECUTION_WINDOW")
        if _stopped_by_reply(case) or case.stopped:
            violated.append("R6_STOP_RESPECTED")
        if case.failure_class in TERMINAL_DEBIT_CLASSES or not case.mandate_active:
            violated.append("R7_NO_DEBIT_WHEN_TERMINAL")
        if action.amount > case.amount + 1e-9 or action.amount > case.mandate_max + 1e-9:
            violated.append("R8_AMOUNT_BOUND")
        if case.recovered or _claims_paid(case):
            violated.append("R10_NO_DOUBLE_DEBIT")

    return violated


def _has_valid_notice(case: Case, debit: Action) -> bool:
    return any(
        n.for_debit_at == debit.at
        and abs(n.amount - debit.amount) < 1e-9
        and debit.at - n.at >= NOTICE_LEAD
        for n in case.notices
    )
