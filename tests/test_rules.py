from datetime import time

import pytest

from dobaara import rules
from dobaara.engine import Engine
from dobaara.models import Action, ActionType, FailureClass, Intent, ParsedReply
from tests.conftest import D0, days, ist


def notice_for(case, debit_at, lead_hours=27):
    from datetime import timedelta
    return Action(ActionType.PRE_DEBIT_NOTICE, debit_at - timedelta(hours=lead_hours), case.amount,
                  for_debit_at=debit_at)


def debit(case, d, h=14, amount=None):
    return Action(ActionType.DEBIT_ATTEMPT, ist(d, h), case.amount if amount is None else amount)


def test_debit_without_notice_is_blocked(case):
    assert "R2_PRE_DEBIT_NOTICE" in rules.check(case, debit(case, D0 + days(1)))


def test_debit_with_27h_notice_is_allowed(case):
    eng = Engine()
    d = debit(case, D0 + days(1))
    assert eng.propose(case, notice_for(case, d.at))
    assert rules.check(case, d) == []


def test_notice_23h_ahead_is_not_enough(case):
    eng = Engine()
    d = debit(case, D0 + days(1))
    assert eng.propose(case, Action(ActionType.PRE_DEBIT_NOTICE, ist(D0, 15), case.amount, for_debit_at=d.at))
    assert "R2_PRE_DEBIT_NOTICE" in rules.check(case, d)


def test_notice_for_a_different_amount_does_not_count(case):
    eng = Engine()
    d = debit(case, D0 + days(1))
    eng.propose(case, Action(ActionType.PRE_DEBIT_NOTICE, ist(D0, 11), 1.0, for_debit_at=d.at))
    assert "R2_PRE_DEBIT_NOTICE" in rules.check(case, d)


@pytest.mark.parametrize("hour,minute,ok", [
    (9, 59, True), (10, 0, False), (12, 59, False), (13, 0, True), (16, 59, True), (17, 0, False),
    (21, 29, False), (21, 30, True), (23, 0, True), (7, 0, True),
])
def test_execution_windows(hour, minute, ok):
    assert rules.in_execution_window(ist(D0, hour, minute)) is ok


@pytest.mark.parametrize("hour,ok", [(7, False), (8, True), (12, True), (18, True), (19, False), (22, False)])
def test_contact_hours(hour, ok):
    assert rules.in_contact_hours(ist(D0, hour)) is ok


def test_message_outside_contact_hours_blocked(case):
    a = Action(ActionType.PAYMENT_LINK, ist(D0, 21), case.amount)
    assert "R4_CONTACT_HOURS" in rules.check(case, a)


def test_outreach_cap(case):
    eng = Engine()
    for k in range(3):
        assert eng.propose(case, Action(ActionType.REMINDER, ist(D0 + days(k + 1), 11), case.amount))
    assert "R5_OUTREACH_CAP" in rules.check(case, Action(ActionType.REMINDER, ist(D0 + days(5), 11), case.amount))


def test_pre_debit_notices_do_not_count_toward_outreach_cap(case):
    eng = Engine()
    for k in range(5):
        d = ist(D0 + days(k + 2), 14)
        assert eng.propose(case, Action(ActionType.PRE_DEBIT_NOTICE, ist(D0 + days(k + 1), 11), case.amount, for_debit_at=d))
    assert case.outreach_sent == 0


@pytest.mark.parametrize("intent", [Intent.CANCEL, Intent.DISPUTE, Intent.WRONG_PERSON])
def test_stop_intents_block_messages_and_debits(case, intent):
    eng = Engine()
    d = debit(case, D0 + days(2))
    eng.propose(case, notice_for(case, d.at))
    eng.reply_received(case, ist(D0 + days(1), 9), ParsedReply(intent))
    assert "R6_STOP_RESPECTED" in rules.check(case, d)
    assert "R6_STOP_RESPECTED" in rules.check(case, Action(ActionType.REMINDER, ist(D0 + days(1), 12), case.amount))


@pytest.mark.parametrize("cls", [FailureClass.ACCOUNT_BLOCKED, FailureClass.RISK_DECLINE, FailureClass.LIMIT_EXCEEDED])
def test_no_debit_on_terminal_classes(case, cls):
    case.failure_class = cls
    assert "R7_NO_DEBIT_WHEN_TERMINAL" in rules.check(case, debit(case, D0 + days(1)))


def test_no_debit_when_mandate_inactive(case):
    case.mandate_active = False
    assert "R7_NO_DEBIT_WHEN_TERMINAL" in rules.check(case, debit(case, D0 + days(1)))


def test_amount_bound(case):
    assert "R8_AMOUNT_BOUND" in rules.check(case, debit(case, D0 + days(1), amount=case.amount + 1))


def test_amount_bound_respects_mandate_max(case):
    case.amount, case.mandate_max = 1500.0, 999.0
    assert "R8_AMOUNT_BOUND" in rules.check(case, debit(case, D0 + days(1)))


def test_max_four_attempts(case):
    case.debit_attempts = 4
    assert "R1_MAX_ATTEMPTS" in rules.check(case, debit(case, D0 + days(1)))


def test_recovery_window(case):
    a = Action(ActionType.REMINDER, ist(D0 + days(31), 11), case.amount)
    assert "R9_RECOVERY_WINDOW" in rules.check(case, a)


def test_no_debit_after_recovery(case):
    case.recovered = True
    assert "R10_NO_DOUBLE_DEBIT" in rules.check(case, debit(case, D0 + days(1)))


def test_no_debit_after_already_paid_claim(case):
    Engine().reply_received(case, ist(D0, 12), ParsedReply(Intent.ALREADY_PAID))
    assert "R10_NO_DOUBLE_DEBIT" in rules.check(case, debit(case, D0 + days(1)))


def test_blocked_action_is_logged_with_rules(case):
    eng = Engine()
    assert not eng.propose(case, debit(case, D0 + days(1)))
    rec = eng.ledger.records[-1]
    assert rec.event == "action_blocked" and "R2_PRE_DEBIT_NOTICE" in rec.data["violated"]


def test_every_rule_has_a_source():
    assert all(r.source for r in rules.RULES.values())
    assert len(rules.RULES) == 10


def test_stop_window_end_constant(case):
    assert case.window_end - case.failed_at == days(30)
    assert time(8, 0) == rules.CONTACT_START
