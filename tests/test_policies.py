from datetime import date, timedelta

import numpy as np
import pytest

from dobaara import rules
from dobaara.models import ActionType, FailureClass, Intent, ParsedReply
from dobaara.payday import DAYS, SuccessCurve, fit, payday_error_days
from dobaara.policies import Calendar, Context, Dobaara, Naive
from tests.conftest import D0, days, ist


def curve_peaking_on(dom_from: int, dom_to: int, hi=0.9, lo=0.05) -> SuccessCurve:
    p = np.full(DAYS, lo)
    p[dom_from - 1:dom_to] = hi
    return SuccessCurve(p, 100)


def debits(plan):
    return [a for a in plan.actions if a.type is ActionType.DEBIT_ATTEMPT]


def test_every_planned_debit_has_a_24h_notice(case):
    plan = Dobaara().on_open(case, Context(curve_peaking_on(1, 5)))
    notices = {a.for_debit_at: a for a in plan.actions if a.type is ActionType.PRE_DEBIT_NOTICE}
    assert debits(plan)
    for d in debits(plan):
        assert d.at in notices and d.at - notices[d.at].at >= timedelta(hours=24)
        assert rules.in_execution_window(d.at)
        assert rules.in_contact_hours(notices[d.at].at)


def test_retries_land_on_payday_window(case):
    plan = Dobaara().on_open(case, Context(curve_peaking_on(1, 5)))
    assert all(1 <= d.at.day <= 5 for d in debits(plan))
    assert len(debits(plan)) <= 3


def test_retries_are_spaced(case):
    plan = Dobaara().on_open(case, Context(curve_peaking_on(1, 9)))
    ds = sorted(d.at.date() for d in debits(plan))
    assert all((b - a).days >= 2 for a, b in zip(ds, ds[1:]))


def test_harm_aware_refuses_low_odds_enach_retries(enach_case):
    flat = SuccessCurve(np.full(DAYS, 0.40), 100)
    # EV = 0.4*3500 - 0.6*354 > 0, so with a big amount it still retries...
    assert debits(Dobaara().on_open(enach_case, Context(flat, bounce_cost=354)))
    # ...but for a small due the expected bank charge outweighs the expected recovery.
    enach_case.amount = enach_case.mandate_max = 199.0
    assert not debits(Dobaara().on_open(enach_case, Context(flat, bounce_cost=354)))
    # The naive schedule retries anyway.
    assert len(debits(Naive().on_open(enach_case, Context(flat, bounce_cost=354)))) == 3


def test_no_retry_when_odds_below_floor(case):
    plan = Dobaara().on_open(case, Context(SuccessCurve(np.full(DAYS, 0.2), 100)))
    assert not debits(plan)
    assert any(a.type is ActionType.PAYMENT_LINK for a in plan.actions)


@pytest.mark.parametrize("cls", [FailureClass.ACCOUNT_BLOCKED, FailureClass.RISK_DECLINE, FailureClass.LIMIT_EXCEEDED])
def test_terminal_classes_get_a_link_not_a_debit(case, cls):
    case.failure_class = cls
    plan = Dobaara().on_open(case, Context(curve_peaking_on(1, 5)))
    assert not debits(plan)
    assert any(a.type is ActionType.PAYMENT_LINK for a in plan.actions)


def test_inactive_mandate_gets_link_and_remandate(case):
    case.failure_class, case.mandate_active = FailureClass.MANDATE_INACTIVE, False
    kinds = {a.type for a in Dobaara().on_open(case, Context(curve_peaking_on(1, 5))).actions}
    assert {ActionType.PAYMENT_LINK, ActionType.REMANDATE_LINK} <= kinds and ActionType.DEBIT_ATTEMPT not in kinds


def test_unknown_code_is_conservative(case):
    case.failure_class = FailureClass.UNKNOWN
    plan = Dobaara().on_open(case, Context(curve_peaking_on(1, 9)))
    assert len(debits(plan)) <= 1
    assert any(a.type is ActionType.ESCALATE for a in plan.actions)


def test_promise_reschedules_to_day_after_promise(case):
    now = ist(D0, 13)
    reply = ParsedReply(Intent.PROMISE_TO_PAY, promised_date=D0 + days(4))
    plan = Dobaara().on_reply(case, now, reply, Context(curve_peaking_on(1, 5)))
    assert plan.replace_pending
    assert [d.at.date() for d in debits(plan)] == [D0 + days(5)]
    assert any(a.type is ActionType.REMINDER and a.at.date() == D0 + days(4) for a in plan.actions)


def test_ungrounded_promise_date_is_ignored(case):
    reply = ParsedReply(Intent.PROMISE_TO_PAY, promised_date=D0 + days(4), grounded=False)
    plan = Dobaara().on_reply(case, ist(D0, 13), reply, Context(curve_peaking_on(1, 5)))
    assert not plan.actions and not plan.replace_pending


@pytest.mark.parametrize("intent", [Intent.CANCEL, Intent.DISPUTE, Intent.WRONG_PERSON])
def test_stop_intents_stop_everything(case, intent):
    plan = Dobaara().on_reply(case, ist(D0, 13), ParsedReply(intent), Context())
    assert plan.replace_pending and plan.actions[0].type is ActionType.STOP
    assert not debits(plan)


@pytest.mark.parametrize("intent", [Intent.ALREADY_PAID, Intent.HARDSHIP])
def test_paid_claims_and_hardship_go_to_a_person(case, intent):
    plan = Dobaara().on_reply(case, ist(D0, 13), ParsedReply(intent), Context())
    assert plan.replace_pending and [a.type for a in plan.actions] == [ActionType.ESCALATE]


def test_calendar_baseline_uses_salary_days(case):
    plan = Calendar().on_open(case, Context())
    assert {d.at.day for d in debits(plan)} <= set(Calendar.SALARY_DAYS)


def test_payday_fit_recovers_payday():
    hist = []
    for m in range(4, 10):
        for dom in range(1, 29):
            hist.append((date(2026, m, dom), 1 <= dom <= 12))
    curve = fit(hist)
    assert payday_error_days(curve.likely_payday(), 1) <= 1
    assert curve.at(date(2026, 10, 3)) > 0.8 and curve.at(date(2026, 10, 20)) < 0.2


def test_payday_fit_without_history_returns_prior():
    prior = np.linspace(0.1, 0.9, DAYS)
    assert np.allclose(fit([], prior=prior).p, prior)
