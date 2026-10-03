"""Export results and sample case replays as static JSON for the dashboard (web/public/data).

    python -m dobaara.export
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from . import codes, rules
from .calibration import BASE
from .experiment import RESULTS, make_policies, measured_parser, run_seed
from .payday import fit, population_prior
from .replies import baseline
from .replies.dataset import load as load_replies

OUT = Path(__file__).resolve().parents[1] / "web" / "public" / "data"


def _read(name: str) -> dict | None:
    p = RESULTS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _pick_cases(n: int = 800, seed: int = 100) -> list[dict]:
    worlds, out, verdicts, ledgers = run_seed(BASE, seed, n, measured_parser(), make_policies(), keep_ledgers=True)
    prior = population_prior([w.history(True) for w in worlds[:400]])
    by_arm = {arm: {o.case_id: o for o in rows} for arm, rows in out.items()}

    def story(cid: str) -> str | None:
        d, nv, cal = by_arm["dobaara"][cid], by_arm["naive"][cid], by_arm["calendar"][cid]
        if d.replies and d.recovered and not nv.recovered:
            return "reply_driven"
        if d.rail == "enach" and d.bounce_cost < nv.bounce_cost and d.recovered and not nv.recovered:
            return "harm_avoided"
        if d.recovered and not nv.recovered and d.failure_class == "insufficient_funds":
            return "payday_timing"
        if d.failure_class == "mandate_inactive" and d.recovered:
            return "remandate"
        if d.failure_class == "technical" and d.recovered:
            return "technical"
        if d.cancelled or (d.replies and not d.recovered and d.escalated):
            return "stopped_or_escalated"
        if nv.recovered and not d.recovered:
            return "dobaara_lost"
        if cal.recovered and not d.recovered:
            return "dobaara_lost_to_calendar"
        return None

    wanted = {"payday_timing": 4, "harm_avoided": 3, "reply_driven": 3, "remandate": 2, "technical": 2,
              "stopped_or_escalated": 2, "dobaara_lost": 2, "dobaara_lost_to_calendar": 1}
    picked: list[dict] = []
    for w in worlds:
        cid = f"{seed}-{w.customer_id}"
        s = story(cid)
        if s is None or wanted.get(s, 0) == 0:
            continue
        wanted[s] -= 1
        curve = fit(w.history(True), prior=prior)
        picked.append({
            "case_id": cid, "story": s, "rail": w.rail.value, "amount": w.amount,
            "failure_code": w.failure_code(), "failure_class": w.failure_class.value,
            "failed_at": w.failed_at.isoformat(), "payday_kind": w.payday_kind, "true_payday": w.true_payday(),
            "estimated_payday": curve.likely_payday(), "bounce_charge": round(w.bounce_charge, 2),
            "curve": [round(float(x), 3) for x in curve.p],
            "arms": {arm: {"outcome": asdict(by_arm[arm][cid]),
                           "timeline": [r.as_dict() for r in ledgers[arm].for_case(cid)]}
                     for arm in ("naive", "calendar", "dobaara")},
        })
        if not any(wanted.values()):
            break
    return picked


def _reply_examples() -> list[dict]:
    rows = []
    for ex in load_replies("heldout"):
        p = baseline.parse(ex.text, ex.sent)
        rows.append({"id": ex.id, "text": ex.text, "sent": ex.sent.isoformat(), "gold": ex.intent.value,
                     "gold_date": ex.promised_date.isoformat() if ex.promised_date else None,
                     "pred": p.intent.value, "pred_date": p.promised_date.isoformat() if p.promised_date else None})
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bundle = {
        "experiment": {k: _read(f"experiment_{k}.json") for k in ("test", "shifted", "dev")},
        "sensitivity": _read("sensitivity.json"),
        "ablations": _read("ablations.json"),
        "replies": {
            "baseline_dev": _read("replies_baseline_dev.json"),
            "baseline_dev_v1": _read("replies_baseline_dev_v1.json"),
            "baseline_heldout": _read("replies_baseline_heldout.json"),
            "llm_heldout": _read("replies_llm_heldout.json"),
            "examples": _reply_examples(),
        },
        "rules": [asdict(r) for r in rules.RULES.values()],
        "codes": [{**asdict(c), "cls": c.cls.value} for c in codes.CODES],
        "calibration": {k: (v if not isinstance(v, dict) else {str(a): b for a, b in v.items()})
                        for k, v in asdict(BASE).items()},
    }
    (OUT / "results.json").write_text(json.dumps(bundle, default=str, ensure_ascii=False), encoding="utf-8")
    cases = _pick_cases()
    (OUT / "cases.json").write_text(json.dumps(cases, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT / 'results.json'} and {len(cases)} cases")


if __name__ == "__main__":
    main()
