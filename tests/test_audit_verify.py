"""The ledger detects tampering, and the independent verifier agrees with the gate."""

import copy
import random
from datetime import timedelta

import pytest

from dobaara.audit import Ledger, verify_chain
from dobaara.engine import Engine
from dobaara.models import IST, Action, ActionType, Case, FailureClass, Intent, ParsedReply, Rail
from dobaara.verify import verify
from tests.conftest import D0, days, ist


def _ledger_with_activity(case):
    eng = Engine()
    eng.open_case(case)
    debit_at = ist(D0 + days(1), 14)
    eng.propose(case, Action(ActionType.PRE_DEBIT_NOTICE, ist(D0, 11), case.amount, for_debit_at=debit_at))
    eng.propose(case, Action(ActionType.DEBIT_ATTEMPT, debit_at, case.amount))
    eng.debit_result(case, debit_at, False, "Z9")
    eng.propose(case, Action(ActionType.PAYMENT_LINK, ist(D0 + days(1), 15), case.amount))
    return eng


def test_clean_chain_verifies(case):
    eng = _ledger_with_activity(case)
    assert verify_chain(eng.ledger.dump()) == (True, None)
    assert verify(eng.ledger.dump()).ok


@pytest.mark.parametrize("mutate", ["edit", "delete", "swap"])
def test_tampering_is_detected(case, mutate):
    recs = _ledger_with_activity(case).ledger.dump()
    bad = copy.deepcopy(recs)
    if mutate == "edit":
        bad[2]["data"]["amount"] = 1.0
    elif mutate == "delete":
        del bad[1]
    else:
        bad[1], bad[2] = bad[2], bad[1]
    ok, seq = verify_chain(bad)
    assert not ok and seq is not None


def test_ledger_persists_and_reloads(tmp_path, case):
    path = tmp_path / "ledger.jsonl"
    eng = Engine(Ledger(path))
    eng.open_case(case)
    eng.propose(case, Action(ActionType.PAYMENT_LINK, ist(D0, 11), case.amount))
    again = Ledger(path)
    assert [r.hash for r in again.records] == [r.hash for r in eng.ledger.records]
    assert verify_chain(again.dump())[0]


def test_verifier_catches_an_action_that_bypassed_the_gate(case):
    eng = Engine()
    eng.open_case(case)
    # Write straight to the ledger, skipping the gate: a debit with no pre-debit notice at 11:00.
    eng.ledger.append(case.case_id, "action_executed", ist(D0 + days(1), 11), type="debit_attempt",
                      amount=case.amount, policy_rule="X", reason="", for_debit_at=None, is_message=False)
    report = verify(eng.ledger.dump())
    rules = {v["rule"] for v in report.violations}
    assert {"R2_PRE_DEBIT_NOTICE", "R3_EXECUTION_WINDOW"} <= rules
    assert not report.ok


ACTION_TYPES = [ActionType.PRE_DEBIT_NOTICE, ActionType.DEBIT_ATTEMPT, ActionType.PAYMENT_LINK,
                ActionType.REMINDER, ActionType.REMANDATE_LINK]


@pytest.mark.parametrize("seed", range(20))
def test_gate_and_verifier_agree_on_random_proposals(seed):
    """Two independent implementations of the rules, fuzzed: every executed action must verify clean."""
    rnd = random.Random(seed)
    eng = Engine()
    for c in range(15):
        cls = rnd.choice(list(FailureClass))
        case = Case(f"f{seed}-{c}", "cx", rnd.choice(list(Rail)), float(rnd.choice([99, 499, 3500])),
                    float(rnd.choice([99, 499, 999, 3500])), ist(D0, 9), "Z9", cls,
                    mandate_active=cls is not FailureClass.MANDATE_INACTIVE)
        eng.open_case(case)
        t = case.failed_at
        for _ in range(40):
            t = t + timedelta(hours=rnd.randint(1, 20))
            kind = rnd.choice(ACTION_TYPES)
            amount = case.amount if rnd.random() < 0.85 else case.amount * 2
            target = t + timedelta(hours=rnd.choice([20, 24, 27, 30]))
            target = target.replace(minute=0)
            a = Action(kind, t.replace(minute=0), amount, for_debit_at=target if kind is ActionType.PRE_DEBIT_NOTICE else None)
            eng.propose(case, a)
            if rnd.random() < 0.05:
                eng.reply_received(case, t, ParsedReply(rnd.choice(list(Intent))))
            if rnd.random() < 0.03:
                eng.payment_received(case, t, "payment_link")
    report = verify(eng.ledger.dump())
    assert report.chain_ok
    assert report.violations == [], report.violations[:5]
    assert eng.blocked > 0  # the fuzz really did propose illegal actions
