"""Labelled reply set.

Gold labels are written as *rules* ("dom:5", "+1", "wd:mon", "eom", "abs:2026-10-20") so the human
judgement — what day the customer meant — is separate from the calendar arithmetic, which is done
here mechanically and independently of the parser's own date code.

The split is a hash of the id, fixed before any parser was evaluated.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from ..models import Intent

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "replies"
SOURCE = DATA_DIR / "replies_source.jsonl"
_WD = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass(frozen=True)
class Example:
    id: str
    sent: date
    text: str
    intent: Intent
    promised_date: date | None
    split: str


def gold_date(rule: str | None, sent: date) -> date | None:
    if rule is None:
        return None
    kind, _, arg = rule.partition(":")
    if rule.startswith("+"):
        return sent + timedelta(days=int(rule[1:]))
    if kind == "abs":
        return date.fromisoformat(arg)
    if kind == "eom":
        return date(sent.year, sent.month, calendar.monthrange(sent.year, sent.month)[1])
    if kind == "wd":
        ahead = (_WD[arg] - sent.weekday()) % 7 or 7
        return sent + timedelta(days=ahead)
    if kind == "dom":
        dom, y, m = int(arg), sent.year, sent.month
        while True:
            if dom <= calendar.monthrange(y, m)[1] and date(y, m, dom) >= sent:
                return date(y, m, dom)
            m = m % 12 + 1
            y += 1 if m == 1 else 0
    raise ValueError(f"unknown date rule {rule!r}")


def split_of(example_id: str) -> str:
    return "dev" if int(hashlib.sha256(example_id.encode()).hexdigest(), 16) % 10 < 6 else "heldout"


def load(split: str | None = None, path: Path = SOURCE) -> list[Example]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        sent = date.fromisoformat(row["sent"])
        ex = Example(row["id"], sent, row["text"], Intent(row["intent"]), gold_date(row["date_rule"], sent),
                     split_of(row["id"]))
        if split is None or ex.split == split:
            out.append(ex)
    return out
