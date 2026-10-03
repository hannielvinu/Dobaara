"""Score a reply parser on the labelled set.

    python -m dobaara.replies.evaluate --parser baseline --split dev
    python -m dobaara.replies.evaluate --parser llm --split heldout   # needs ANTHROPIC credentials
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Callable

from ..models import Intent, ParsedReply
from . import baseline
from .dataset import Example, load

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"
INTENTS = [i.value for i in Intent]

Parser = Callable[[str, date], ParsedReply]


def score(examples: list[Example], parse: Parser) -> dict:
    tp, fp, fn = Counter(), Counter(), Counter()
    confusion: dict[str, Counter] = defaultdict(Counter)
    date_total = date_ok = ungrounded = 0
    errors = []
    for ex in examples:
        pred = parse(ex.text, ex.sent)
        g, p = ex.intent.value, pred.intent.value
        confusion[g][p] += 1
        if g == p:
            tp[g] += 1
        else:
            fp[p] += 1
            fn[g] += 1
        if not pred.grounded:
            ungrounded += 1
        if ex.intent is Intent.PROMISE_TO_PAY:
            date_total += 1
            got = pred.promised_date if pred.intent is Intent.PROMISE_TO_PAY else None
            if got == ex.promised_date:
                date_ok += 1
        if g != p or (ex.intent is Intent.PROMISE_TO_PAY and pred.promised_date != ex.promised_date):
            errors.append({"id": ex.id, "text": ex.text, "gold": g, "pred": p,
                           "gold_date": str(ex.promised_date) if ex.promised_date else None,
                           "pred_date": str(pred.promised_date) if pred.promised_date else None})

    per_intent = {}
    f1s = []
    for i in INTENTS:
        prec = tp[i] / (tp[i] + fp[i]) if tp[i] + fp[i] else 0.0
        rec = tp[i] / (tp[i] + fn[i]) if tp[i] + fn[i] else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        support = tp[i] + fn[i]
        per_intent[i] = {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3), "support": support}
        if support:
            f1s.append(f1)
    n = len(examples)
    return {
        "n": n,
        "accuracy": round(sum(tp.values()) / n, 3) if n else 0.0,
        "macro_f1": round(sum(f1s) / len(f1s), 3) if f1s else 0.0,
        "promise_date_exact": round(date_ok / date_total, 3) if date_total else None,
        "promise_examples": date_total,
        "ungrounded_rate": round(ungrounded / n, 3) if n else 0.0,
        "per_intent": per_intent,
        "confusion": {g: dict(row) for g, row in confusion.items()},
        "errors": errors,
    }


def confusion_probs(result: dict) -> dict[str, dict[str, float]]:
    """Row-normalised confusion matrix, for injecting parser error into the simulator."""
    out = {}
    for g, row in result["confusion"].items():
        total = sum(row.values())
        out[g] = {p: c / total for p, c in row.items()}
    return out


def get_parser(name: str) -> Parser:
    if name == "baseline":
        return baseline.parse
    if name == "llm":
        from .llm import LLMParser
        return LLMParser().parse
    raise ValueError(name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", default="baseline", choices=["baseline", "llm"])
    ap.add_argument("--split", default="dev", choices=["dev", "heldout", "all"])
    args = ap.parse_args()
    examples = load(None if args.split == "all" else args.split)
    result = score(examples, get_parser(args.parser))
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"replies_{args.parser}_{args.split}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {k: result[k] for k in ("n", "accuracy", "macro_f1", "promise_date_exact", "ungrounded_rate")}
    print(json.dumps(summary, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
