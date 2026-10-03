import pytest

from dobaara import codes
from dobaara.models import FailureClass as F
from dobaara.models import Rail


@pytest.mark.parametrize("system,code,cls", [
    ("upi", "Z9", F.INSUFFICIENT_FUNDS),
    ("upi", "z9", F.INSUFFICIENT_FUNDS),
    ("upi", "U16", F.RISK_DECLINE),
    ("upi", "YE", F.ACCOUNT_BLOCKED),
    ("upi", "Z8", F.LIMIT_EXCEEDED),
    ("upi", "ZA", F.MANDATE_INACTIVE),
    ("upi", "U30", F.UNKNOWN),
    ("razorpay", "insufficient_funds", F.INSUFFICIENT_FUNDS),
    ("razorpay", "bank_technical_error", F.TECHNICAL),
    ("razorpay", "payment_risk_check_failed", F.RISK_DECLINE),
    ("razorpay", "debit_instrument_blocked", F.ACCOUNT_BLOCKED),
    ("nach", "04", F.INSUFFICIENT_FUNDS),
])
def test_known_codes(system, code, cls):
    assert codes.classify(system, code) is cls


@pytest.mark.parametrize("desc,cls", [
    ("Insufficient balance in account", F.INSUFFICIENT_FUNDS),
    ("Mandate revoked by customer", F.MANDATE_INACTIVE),
    ("Account frozen", F.ACCOUNT_BLOCKED),
    ("Request timed out at issuer", F.TECHNICAL),
    ("something odd happened", F.UNKNOWN),
])
def test_unknown_codes_fall_back_to_keywords_then_unknown(desc, cls):
    assert codes.classify("razorpay", "never_seen_before", desc) is cls


def test_every_code_is_sourced_and_unique():
    keys = [(c.source_system, c.code.lower()) for c in codes.CODES]
    assert len(keys) == len(set(keys))
    assert all(c.source for c in codes.CODES)


def test_unverified_codes_are_flagged():
    assert any(not c.verified for c in codes.CODES)
    assert all(c.verified for c in codes.CODES if c.source_system == "razorpay")


def test_codes_for_rail():
    assert all(c.source_system == "upi" for c in codes.codes_for(F.INSUFFICIENT_FUNDS, Rail.UPI_AUTOPAY))
    assert all(c.source_system == "nach" for c in codes.codes_for(F.INSUFFICIENT_FUNDS, Rail.ENACH))
