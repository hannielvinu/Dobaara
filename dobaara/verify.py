"""Independent compliance verifier.

Reads only the exported audit ledger (plain dicts) and re-derives every compliance claim from
scratch. It deliberately does not import `rules.py` or the engine: if the gate has a bug, this is
a second implementation that has to agree with it, not the same code checking itself.

    python -m dobaara.verify path/to/ledger.jsonl
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .audit import verify_chain

MESSAGE = {"pre_debit_notice", "payment_link", "remandate_link", "reminder"}
OUTREACH = {"payment_link", "remandate_link", "reminder"}
STOP = {"cancel", "dispute", "wrong_person"}
DEBIT_TERMINAL = {"account_blocked", "risk_decline", "limit_exceeded"}


@dataclass
class _State:
    opened: dict[str, Any] | None = None
    opened_at: datetime = datetime.min
    attempts: int = 1
    outreach: int = 0
    notices: list[tuple[datetime, float, str]] = field(default_factory=list)
    stop: bool = False
    paid_claim: bool = False
    recovered: bool = False
    mandate_active: bool = True


@dataclass
class Report:
    chain_ok: bool
    first_bad_seq: int | None
    cases: int
    actions_checked: int
    violations: list[dict[str, Any]]

    @property
    def ok(self) -> bool:
        return self.chain_ok and not self.violations

    def as_dict(self) -> dict[str, Any]:
        by_rule: dict[str, int] = defaultdict(int)
        for v in self.violations:
            by_rule[v["rule"]] += 1
        return {
            "chain_ok": self.chain_ok, "first_bad_seq": self.first_bad_seq, "cases": self.cases,
            "actions_checked": self.actions_checked, "violations": len(self.violations),
            "violations_by_rule": dict(by_rule), "ok": self.ok,
        }


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _minutes(at: datetime) -> int:
    return at.hour * 60 + at.minute


def verify(records: Iterable[dict[str, Any]]) -> Report:
    records = list(records)
    chain_ok, bad = verify_chain(records)
    states: dict[str, _State] = defaultdict(_State)
    violations: list[dict[str, Any]] = []
    checked = 0

    def flag(rec: dict[str, Any], rule: str) -> None:
        violations.append({"seq": rec["seq"], "case_id": rec["case_id"], "rule": rule})

    for rec in records:
        st, d, ev = states[rec["case_id"]], rec["data"], rec["event"]
        at = _t(rec["at"])
        if ev == "case_opened":
            st.opened, st.opened_at = d, at
            st.mandate_active = bool(d.get("mandate_active", True)) and d["failure_class"] != "mandate_inactive"
        elif ev == "reply_received":
            if d["intent"] in STOP:
                st.stop = True
            if d["intent"] == "already_paid":
                st.paid_claim = True
        elif ev in ("case_recovered",):
            st.recovered = True
        elif ev == "mandate_reactivated":
            st.mandate_active = True
        elif ev == "subscription_cancelled":
            st.stop = True
        elif ev == "action_executed":
            checked += 1
            kind = d["type"]
            if st.opened is None:
                flag(rec, "NO_CASE")
                continue
            if at > st.opened_at + timedelta(days=30):
                flag(rec, "R9_RECOVERY_WINDOW")
            if kind in MESSAGE:
                if not (8 * 60 <= _minutes(at) < 19 * 60):
                    flag(rec, "R4_CONTACT_HOURS")
                if st.stop:
                    flag(rec, "R6_STOP_RESPECTED")
            if kind in OUTREACH:
                if st.outreach >= 3:
                    flag(rec, "R5_OUTREACH_CAP")
                st.outreach += 1
            if kind == "pre_debit_notice":
                st.notices.append((at, float(d["amount"]), d["for_debit_at"]))
            if kind == "debit_attempt":
                amt = float(d["amount"])
                if st.attempts >= 4:
                    flag(rec, "R1_MAX_ATTEMPTS")
                if not any(fd == rec["at"] and abs(a - amt) < 1e-9 and at - nt >= timedelta(hours=24)
                           for nt, a, fd in st.notices):
                    flag(rec, "R2_PRE_DEBIT_NOTICE")
                m = _minutes(at)
                if not (m < 10 * 60 or 13 * 60 <= m < 17 * 60 or m >= 21 * 60 + 30):
                    flag(rec, "R3_EXECUTION_WINDOW")
                if st.stop:
                    flag(rec, "R6_STOP_RESPECTED")
                if st.opened["failure_class"] in DEBIT_TERMINAL or not st.mandate_active:
                    flag(rec, "R7_NO_DEBIT_WHEN_TERMINAL")
                if amt > float(st.opened["amount"]) + 1e-9 or amt > float(st.opened["mandate_max"]) + 1e-9:
                    flag(rec, "R8_AMOUNT_BOUND")
                if st.recovered or st.paid_claim:
                    flag(rec, "R10_NO_DOUBLE_DEBIT")
                st.attempts += 1
            if kind == "stop":
                st.stop = True

    cases = sum(1 for s in states.values() if s.opened is not None)
    return Report(chain_ok, bad, cases, checked, violations)


def main(argv: list[str]) -> int:
    path = Path(argv[1])
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = verify(records)
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
