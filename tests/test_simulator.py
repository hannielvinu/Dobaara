from dataclasses import replace

import numpy as np

from dobaara.audit import Ledger
from dobaara.calibration import BASE
from dobaara.engine import Engine
from dobaara.experiment import _paired_ci, make_policies, run_seed, summarise
from dobaara.models import FailureClass
from dobaara.payday import population_prior
from dobaara.simulator import PERFECT_PARSER, CustomerWorld, Rng, run_case


def test_keyed_rng_is_deterministic():
    a, b = Rng(1, "c1"), Rng(1, "c1")
    assert a.u("x", 3) == b.u("x", 3)
    assert a.u("x", 3) != Rng(2, "c1").u("x", 3)


def test_world_is_a_pure_function_of_seed_and_id():
    w1, w2 = CustomerWorld(5, "c00042", BASE), CustomerWorld(5, "c00042", BASE)
    assert (w1.amount, w1.rail, w1.failed_at, w1.payday_kind) == (w2.amount, w2.rail, w2.failed_at, w2.payday_kind)
    assert w1.history(True) == w2.history(True)


def test_insufficient_funds_failures_happen_on_dry_days():
    for i in range(200):
        w = CustomerWorld(9, f"c{i}", BASE)
        if w.failure_class is FailureClass.INSUFFICIENT_FUNDS and w.topup is None:
            # the failure day is dry unless the noise flip made the whole month look funded
            assert not w.has_funds(w.failed_at.date()) or all(w.has_funds(w.failed_at.date().replace(day=d)) for d in range(1, 29))


def test_runs_are_reproducible():
    pol = make_policies()["dobaara"]
    worlds = [CustomerWorld(3, f"c{i}", BASE) for i in range(50)]
    prior = population_prior([w.history(True) for w in worlds])
    a = [run_case(w, pol, Engine(Ledger()), PERFECT_PARSER, prior)[0] for w in worlds]
    b = [run_case(w, pol, Engine(Ledger()), PERFECT_PARSER, prior)[0] for w in worlds]
    assert a == b


def test_no_debit_after_recovery_in_any_arm():
    _, out, verdicts, ledgers = run_seed(BASE, 11, 300, PERFECT_PARSER, make_policies(), keep_ledgers=True)
    for arm, led in ledgers.items():
        recovered = set()
        for r in led.records:
            if r.event == "case_recovered":
                recovered.add(r.case_id)
            if r.event == "action_executed" and r.data["type"] == "debit_attempt":
                assert r.case_id not in recovered, arm
        assert verdicts[arm]["violations"] == 0 and verdicts[arm]["chain_ok"]


def test_arms_see_identical_customers():
    _, out, _, _ = run_seed(BASE, 12, 200, PERFECT_PARSER, make_policies())
    ids = [[o.case_id for o in rows] for rows in out.values()]
    amounts = [[o.amount for o in rows] for rows in out.values()]
    assert all(x == ids[0] for x in ids) and all(x == amounts[0] for x in amounts)


def test_do_nothing_sends_nothing_and_charges_nothing():
    _, out, _, _ = run_seed(BASE, 13, 200, PERFECT_PARSER, make_policies())
    rows = out["do_nothing"]
    assert sum(r.outreach + r.notices + r.debits for r in rows) == 0
    assert sum(r.bounce_cost for r in rows) == 0


def test_upi_failures_cost_the_customer_nothing():
    cal = replace(BASE, share_enach=0.0)
    _, out, _, _ = run_seed(cal, 14, 200, PERFECT_PARSER, make_policies())
    assert all(r.bounce_cost == 0 for rows in out.values() for r in rows)


def test_paired_ci_brackets_the_total():
    rng = np.random.default_rng(0)
    a, b = rng.normal(10, 3, 500), rng.normal(9, 3, 500)
    ci = _paired_ci(a, b)
    assert ci["ci95"][0] <= ci["total"] <= ci["ci95"][1]


def test_summary_has_all_pairs():
    _, out, _, _ = run_seed(BASE, 15, 100, PERFECT_PARSER, make_policies())
    s = summarise(out)
    assert {"dobaara_vs_naive", "dobaara_vs_calendar", "dobaara_vs_do_nothing"} <= set(s["uplift"])
