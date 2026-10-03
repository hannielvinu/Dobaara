"""Append-only, hash-chained audit ledger.

Each record stores the hash of the previous record, so editing, deleting or reordering any past
record breaks every hash after it. `verify_chain` detects that. The ledger is the only input the
independent verifier (`verify.py`) reads.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

GENESIS = "0" * 64


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default)


def _ints(o: Any) -> Any:
    """Store whole-number floats as ints so any JSON tool (e.g. a browser) re-hashes identically."""
    if isinstance(o, float) and o.is_integer():
        return int(o)
    if isinstance(o, dict):
        return {k: _ints(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_ints(v) for v in o]
    return o


def _default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "value"):
        return o.value
    raise TypeError(f"not serialisable: {type(o).__name__}")


@dataclass(frozen=True)
class Record:
    seq: int
    at: str
    case_id: str
    event: str
    data: dict[str, Any]
    prev_hash: str
    hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq, "at": self.at, "case_id": self.case_id, "event": self.event,
            "data": self.data, "prev_hash": self.prev_hash, "hash": self.hash,
        }


def _digest(seq: int, at: str, case_id: str, event: str, data: dict[str, Any], prev_hash: str) -> str:
    body = _canonical({"seq": seq, "at": at, "case_id": case_id, "event": event, "data": data, "prev": prev_hash})
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class Ledger:
    def __init__(self, path: Path | None = None) -> None:
        self.records: list[Record] = []
        self.path = path
        if path is not None and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.records.append(Record(**json.loads(line)))

    @property
    def head(self) -> str:
        return self.records[-1].hash if self.records else GENESIS

    def append(self, case_id: str, event: str, at: datetime, **data: Any) -> Record:
        clean = _ints(json.loads(_canonical(data)))
        seq = len(self.records)
        at_s = at.isoformat()
        rec = Record(seq, at_s, case_id, event, clean, self.head, _digest(seq, at_s, case_id, event, clean, self.head))
        self.records.append(rec)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(_canonical(rec.as_dict()) + "\n")
        return rec

    def for_case(self, case_id: str) -> list[Record]:
        return [r for r in self.records if r.case_id == case_id]

    def dump(self) -> list[dict[str, Any]]:
        return [r.as_dict() for r in self.records]


def verify_chain(records: Iterable[dict[str, Any]]) -> tuple[bool, int | None]:
    """Return (ok, first_bad_seq). Works on plain dicts so it can check an exported file."""
    prev = GENESIS
    for i, r in enumerate(records):
        if r["seq"] != i or r["prev_hash"] != prev:
            return False, i
        if _digest(r["seq"], r["at"], r["case_id"], r["event"], r["data"], r["prev_hash"]) != r["hash"]:
            return False, i
        prev = r["hash"]
    return True, None
