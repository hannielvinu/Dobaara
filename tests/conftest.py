from datetime import date, datetime, time, timedelta

import pytest

from dobaara.models import IST, Case, FailureClass, Rail


def ist(d: date, h: int, m: int = 0) -> datetime:
    return datetime.combine(d, time(h, m), tzinfo=IST)


D0 = date(2026, 10, 6)


@pytest.fixture
def case() -> Case:
    return Case(
        case_id="t-1", customer_id="c1", rail=Rail.UPI_AUTOPAY, amount=499.0, mandate_max=999.0,
        failed_at=ist(D0, 9), failure_code="Z9", failure_class=FailureClass.INSUFFICIENT_FUNDS,
    )


@pytest.fixture
def enach_case() -> Case:
    return Case(
        case_id="t-2", customer_id="c2", rail=Rail.ENACH, amount=3500.0, mandate_max=3500.0,
        failed_at=ist(D0, 9), failure_code="04", failure_class=FailureClass.INSUFFICIENT_FUNDS,
    )


def days(n: int) -> timedelta:
    return timedelta(days=n)
