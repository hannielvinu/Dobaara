"""Failure-code table: raw rail / gateway codes -> FailureClass.

Deterministic on purpose. A failure code is a lookup, not a judgement call, so no model is used here.

Every row carries its source and a `verified` flag. `verified=True` means the code and meaning were
checked against the cited public document; `False` means it is commonly reported but should be
confirmed against the current NPCI circular before production use. Unrecognised codes map to
UNKNOWN, which the policy treats conservatively (one retry at most, plus a human).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import FailureClass, Rail

RZP_ERRORS_DOC = "https://razorpay.com/docs/errors/payments/"
NPCI_UPI_CODES = "NPCI UPI error and response codes (public list)"
NPCI_NACH = "NPCI NACH return reason codes (confirm against NACH-006-FY-24-25)"


@dataclass(frozen=True)
class FailureCode:
    source_system: str  # "razorpay" | "upi" | "nach"
    code: str
    description: str
    cls: FailureClass
    source: str
    verified: bool


_F = FailureClass

CODES: list[FailureCode] = [
    # Razorpay `error_reason` values (payment.failed webhook payload).
    FailureCode("razorpay", "insufficient_funds", "Insufficient funds", _F.INSUFFICIENT_FUNDS, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "bank_technical_error", "Bank technical error", _F.TECHNICAL, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "issuer_technical_error", "Issuer technical error", _F.TECHNICAL, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "gateway_technical_error", "Gateway technical error", _F.TECHNICAL, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "payment_timed_out", "Payment timed out", _F.TECHNICAL, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "request_timed_out", "Request timed out", _F.TECHNICAL, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "funds_blocked_by_mandate", "Funds blocked by another mandate", _F.INSUFFICIENT_FUNDS, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "mandate_creation_declined", "Mandate declined", _F.MANDATE_INACTIVE, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "mandate_creation_expired", "Mandate expired", _F.MANDATE_INACTIVE, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "reqauth_mandate_not_acknowledged", "Mandate not acknowledged", _F.MANDATE_INACTIVE, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "debit_instrument_blocked", "Debit instrument blocked", _F.ACCOUNT_BLOCKED, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "bank_account_invalid", "Bank account invalid", _F.ACCOUNT_BLOCKED, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "transaction_on_vpa_restricted", "Transactions on VPA restricted", _F.ACCOUNT_BLOCKED, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "transaction_limit_exceeded", "Transaction limit exceeded", _F.LIMIT_EXCEEDED, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "transaction_daily_limit_exceeded", "Daily limit exceeded", _F.LIMIT_EXCEEDED, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "transaction_frequency_limit_exceeded", "Frequency limit exceeded", _F.LIMIT_EXCEEDED, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "transaction_daily_count_exceeded", "Daily count exceeded", _F.LIMIT_EXCEEDED, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "payment_risk_check_failed", "Risk check failed", _F.RISK_DECLINE, RZP_ERRORS_DOC, True),
    FailureCode("razorpay", "compliance_violation", "Compliance violation", _F.RISK_DECLINE, RZP_ERRORS_DOC, True),
    # NPCI UPI response codes.
    FailureCode("upi", "Z9", "Insufficient funds in customer account", _F.INSUFFICIENT_FUNDS, NPCI_UPI_CODES, True),
    FailureCode("upi", "U30", "Debit has failed (generic)", _F.UNKNOWN, NPCI_UPI_CODES, True),
    FailureCode("upi", "U68", "Debit timeout", _F.TECHNICAL, NPCI_UPI_CODES, False),
    FailureCode("upi", "BT", "Acquirer / beneficiary unavailable (timeout)", _F.TECHNICAL, NPCI_UPI_CODES, False),
    FailureCode("upi", "U28", "PSP not available", _F.TECHNICAL, NPCI_UPI_CODES, False),
    FailureCode("upi", "Z8", "Per-transaction limit exceeded", _F.LIMIT_EXCEEDED, NPCI_UPI_CODES, True),
    FailureCode("upi", "Z7", "Transaction frequency limit exceeded", _F.LIMIT_EXCEEDED, NPCI_UPI_CODES, True),
    FailureCode("upi", "U16", "Risk threshold exceeded", _F.RISK_DECLINE, NPCI_UPI_CODES, True),
    FailureCode("upi", "YE", "Remitting account blocked / frozen", _F.ACCOUNT_BLOCKED, NPCI_UPI_CODES, True),
    FailureCode("upi", "ZA", "Transaction declined by customer", _F.MANDATE_INACTIVE, NPCI_UPI_CODES, True),
    # NACH return reasons. Numbers vary across circular revisions: unverified until checked.
    FailureCode("nach", "04", "Balance insufficient", _F.INSUFFICIENT_FUNDS, NPCI_NACH, False),
    FailureCode("nach", "01", "Account closed or transferred", _F.ACCOUNT_BLOCKED, NPCI_NACH, False),
    FailureCode("nach", "02", "No such account", _F.ACCOUNT_BLOCKED, NPCI_NACH, False),
    FailureCode("nach", "36", "Mandate cancelled", _F.MANDATE_INACTIVE, NPCI_NACH, False),
    FailureCode("nach", "68", "Account blocked or frozen", _F.ACCOUNT_BLOCKED, NPCI_NACH, False),
]

_INDEX: dict[tuple[str, str], FailureCode] = {(c.source_system, c.code.lower()): c for c in CODES}

# Last-resort keyword matching on free-text descriptions, applied only when the code is unknown.
_KEYWORDS: list[tuple[tuple[str, ...], FailureClass]] = [
    (("insufficient", "balance", "funds"), _F.INSUFFICIENT_FUNDS),
    (("revoked", "cancelled", "canceled", "paused", "mandate"), _F.MANDATE_INACTIVE),
    (("frozen", "blocked", "closed", "invalid account"), _F.ACCOUNT_BLOCKED),
    (("limit",), _F.LIMIT_EXCEEDED),
    (("timeout", "timed out", "technical", "unavailable"), _F.TECHNICAL),
    (("risk", "fraud"), _F.RISK_DECLINE),
]


def lookup(source_system: str, code: str) -> FailureCode | None:
    return _INDEX.get((source_system, code.strip().lower()))


def classify(source_system: str, code: str, description: str = "") -> FailureClass:
    """Map a raw failure to a FailureClass. Unknown codes fall back to keywords, then UNKNOWN."""
    hit = lookup(source_system, code)
    if hit is not None:
        return hit.cls
    text = description.lower()
    for words, cls in _KEYWORDS:
        if any(w in text for w in words):
            return cls
    return FailureClass.UNKNOWN


def codes_for(cls: FailureClass, rail: Rail) -> list[FailureCode]:
    """Rail-native codes of a class; used by the simulator to emit realistic failures."""
    system = "upi" if rail is Rail.UPI_AUTOPAY else "nach"
    return [c for c in CODES if c.cls is cls and c.source_system == system]
