"""The controlled experiment described in METRICS_PLAN.md.

    python -m dobaara.experiment --split dev          # tuning runs
    python -m dobaara.experiment --split test         # once, after freeze
    python -m dobaara.experiment --split shifted      # once, after freeze
    python -m dobaara.experiment --sensitivity
    python -m dobaara.experiment --ablations

Each split writes results/experiment_<split>.json.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from . import payday
from .audit import Ledger
from .calibration import BASE, SHIFTED, Calibration
from .engine import Engine
from .policies import Calendar, Dobaara, DoNothing, Naive, Policy
from .replies import baseline
from .replies.dataset import load as load_replies
from .replies.evaluate import confusion_probs, score
from .simulator import CustomerWorld, Outcome, ParserModel, PERFECT_PARSER, run_case
from .verify import verify

RESULTS = Path(__file__).resolve().parents[1] / "results"
SPLITS = {
    "dev": (BASE, list(range(0, 5))),
    "test": (BASE, list(range(100, 110))),
    "shifted": (SHIFTED, list(range(200, 205))),
}
ARMS = ("do_nothing", "naive", "calendar", "dobaara")


def make_policies(**dobaara_kw) -> dict[str, Policy]:
    return {"do_nothing": DoNothing(), "naive": Naive(), "calendar": Calendar(), "dobaara": Dobaara(**dobaara_kw)}


def measured_parser() -> ParserModel:
    """Parser error as measured on the dev reply split, injected into the simulator."""
    res = score(load_replies("dev"), baseline.parse)
    return ParserModel(confusion_probs(res), res["promise_date_exact"] or 0.0, "baseline(dev-measured)")


def run_seed(cal: Calibration, seed: int, n: int, parser: ParserModel, policies: dict[str, Policy],
             network: bool = True, keep_ledgers: bool = False):
    worlds = [CustomerWorld(seed, f"c{i:05d}", cal) for i in range(n)]
    prior = payday.population_prior([w.history(network) for w in worlds[: min(400, n)]])
    out: dict[str, list[Outcome]] = {}
    ledgers: dict[str, Ledger] = {}
    for arm, policy in policies.items():
        engine = Engine(Ledger())
        out[arm] = [run_case(w, policy, engine, parser, prior, network)[0] for w in worlds]
        ledgers[arm] = engine.ledger
    verdicts = {arm: verify(led.dump()).as_dict() for arm, led in ledgers.items()}
    return worlds, out, verdicts, (ledgers if keep_ledgers else None)


def _arm_metrics(rows: list[Outcome]) -> dict:
    amt = np.array([r.amount for r in rows])
    rec = np.array([r.recovered for r in rows])
    days = [r.days_to_recover for r in rows if r.days_to_recover is not None]
    return {
        "cases": len(rows),
        "due_inr": float(amt.sum()),
        "recovered_inr": float((amt * rec).sum()),
        "recovery_rate_count": float(rec.mean()),
        "recovery_rate_value": float((amt * rec).sum() / amt.sum()),
        "customer_bounce_charges_inr": float(sum(r.bounce_cost for r in rows)),
        "outreach_per_case": float(np.mean([r.outreach for r in rows])),
        "notices_per_case": float(np.mean([r.notices for r in rows])),
        "debit_retries_per_case": float(np.mean([r.debits for r in rows])),
        "cancel_rate": float(np.mean([r.cancelled for r in rows])),
        "escalation_rate": float(np.mean([r.escalated for r in rows])),
        "median_days_to_recover": float(np.median(days)) if days else None,
        "blocked_by_gate": int(sum(r.blocked for r in rows)),
        "recovered_via": {v: int(sum(1 for r in rows if r.recovered and r.recovered_via == v))
                          for v in sorted({r.recovered_via for r in rows if r.recovered})},
    }


def _paired_ci(a: np.ndarray, b: np.ndarray, resamples: int = 2000, seed: int = 7) -> dict:
    """Total of (a - b) over customers, with a 95% bootstrap CI resampling customers."""
    diff = a - b
    rng = np.random.default_rng(seed)
    n = len(diff)
    totals = np.array([diff[rng.integers(0, n, n)].sum() for _ in range(resamples)])
    lo, hi = np.percentile(totals, [2.5, 97.5])
    return {"total": float(diff.sum()), "ci95": [float(lo), float(hi)], "per_1000_cases": float(diff.mean() * 1000)}


def summarise(outcomes: dict[str, list[Outcome]]) -> dict:
    arms = {arm: _arm_metrics(rows) for arm, rows in outcomes.items()}
    val = {arm: np.array([r.amount * r.recovered for r in rows]) for arm, rows in outcomes.items()}
    harm = {arm: np.array([r.bounce_cost for r in rows]) for arm, rows in outcomes.items()}
    out = {"arms": arms, "uplift": {}, "harm_delta": {}}
    for x, y in (("dobaara", "naive"), ("dobaara", "calendar"), ("dobaara", "do_nothing"), ("naive", "do_nothing"),
                 ("calendar", "naive")):
        if x in val and y in val:
            out["uplift"][f"{x}_vs_{y}"] = _paired_ci(val[x], val[y])
            out["harm_delta"][f"{x}_vs_{y}"] = _paired_ci(harm[x], harm[y])
    by_class: dict[str, dict] = {}
    classes = sorted({r.failure_class for r in next(iter(outcomes.values()))})
    for c in classes:
        by_class[c] = {arm: float(np.mean([r.recovered for r in rows if r.failure_class == c])) for arm, rows in outcomes.items()}
    out["recovery_rate_by_failure_class"] = by_class
    return out


def payday_accuracy(worlds: list[CustomerWorld], network: bool) -> dict:
    prior = payday.population_prior([w.history(network) for w in worlds[:400]])
    errs = []
    for w in worlds:
        true = w.true_payday()
        if true is None:
            continue
        est = payday.fit(w.history(network), prior=prior).likely_payday()
        errs.append(payday.payday_error_days(est, true))
    e = np.array(errs)
    return {"customers": int(len(e)), "mae_days": float(e.mean()), "within_1_day": float((e <= 1).mean()),
            "within_3_days": float((e <= 3).mean())}


def run_split(split: str, n: int, policy_kw: dict | None = None) -> dict:
    cal, seeds = SPLITS[split]
    parser = measured_parser()
    pooled: dict[str, list[Outcome]] = {a: [] for a in ARMS}
    verdicts = {}
    all_worlds: list[CustomerWorld] = []
    t0 = time.time()
    for s in seeds:
        worlds, out, v, _ = run_seed(cal, s, n, parser, make_policies(**(policy_kw or {})))
        all_worlds += worlds
        for a in ARMS:
            pooled[a] += out[a]
        verdicts[s] = v
    res = summarise(pooled)
    res["split"] = split
    res["calibration"] = cal.name
    res["seeds"] = seeds
    res["cases_per_seed"] = n
    res["parser"] = {"name": parser.name, "promise_date_exact": parser.date_accuracy}
    res["compliance"] = {
        arm: {"violations": sum(verdicts[s][arm]["violations"] for s in seeds),
              "actions_checked": sum(verdicts[s][arm]["actions_checked"] for s in seeds),
              "chain_ok": all(verdicts[s][arm]["chain_ok"] for s in seeds)}
        for arm in ARMS
    }
    res["payday_inference"] = {"with_network": payday_accuracy(all_worlds[: 3 * n], True),
                               "merchant_only": payday_accuracy(all_worlds[: 3 * n], False)}
    res["runtime_s"] = round(time.time() - t0, 1)
    return res


def run_ablations(n: int, seeds: list[int]) -> dict:
    """What each component contributes: drop one piece at a time, measure Dobaara − Naive."""
    parser = measured_parser()
    variants = {
        "full": ({}, parser, True),
        "no_network_history": ({}, parser, False),
        "perfect_parser": ({}, PERFECT_PARSER, True),
        "no_harm_awareness": ({"harm_weight": 0.0}, parser, True),
    }
    out = {}
    for name, (kw, prs, network) in variants.items():
        pooled: dict[str, list[Outcome]] = {"naive": [], "dobaara": []}
        for s in seeds:
            pols = make_policies(**kw)
            _, o, _, _ = run_seed(BASE, s, n, prs, {"naive": pols["naive"], "dobaara": pols["dobaara"]}, network)
            for a in pooled:
                pooled[a] += o[a]
        summ = summarise(pooled)
        out[name] = {"uplift_vs_naive": summ["uplift"]["dobaara_vs_naive"],
                     "harm_delta_vs_naive": summ["harm_delta"]["dobaara_vs_naive"],
                     "dobaara_recovery_rate_value": summ["arms"]["dobaara"]["recovery_rate_value"]}
    return out


def _scale_irregular(cal: Calibration, share: float) -> Calibration:
    mix = {k: v for k, v in cal.payday_mix.items() if k != "irregular"}
    total = sum(mix.values())
    mix = {k: v / total * (1 - share) for k, v in mix.items()}
    mix["irregular"] = share
    return replace(cal, payday_mix=mix)


def run_sensitivity(n: int, seeds: list[int]) -> dict:
    grid = {
        "irregular_income_share": [(s, _scale_irregular(BASE, s)) for s in (0.10, 0.18, 0.30, 0.50)],
        "reply_rate_multiplier": [(m, replace(BASE, reply_rate=BASE.reply_rate * m)) for m in (0.25, 0.5, 1.0, 1.5)],
        "enach_bounce_inr": [(b, replace(BASE, enach_bounce_range=(b, b))) for b in (250.0, 354.0, 472.0, 590.0)],
        "annoyance_multiplier": [(m, replace(BASE, annoyance_cancel=BASE.annoyance_cancel * m)) for m in (0.0, 1.0, 2.0, 3.0)],
    }
    parser = measured_parser()
    out: dict[str, list] = {}
    for param, cells in grid.items():
        out[param] = []
        for value, cal in cells:
            pooled: dict[str, list[Outcome]] = {"naive": [], "dobaara": []}
            for s in seeds:
                pols = make_policies()
                _, o, _, _ = run_seed(cal, s, n, parser, {"naive": pols["naive"], "dobaara": pols["dobaara"]})
                for a in pooled:
                    pooled[a] += o[a]
            summ = summarise(pooled)
            up = summ["uplift"]["dobaara_vs_naive"]
            out[param].append({
                "value": value, "uplift_per_1000": up["per_1000_cases"],
                "uplift_ci95_per_1000": [up["ci95"][0] / len(pooled["naive"]) * 1000, up["ci95"][1] / len(pooled["naive"]) * 1000],
                "harm_delta_per_1000": summ["harm_delta"]["dobaara_vs_naive"]["per_1000_cases"],
                "dobaara_beats_naive": up["ci95"][0] > 0,
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=list(SPLITS))
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--sensitivity", action="store_true")
    ap.add_argument("--ablations", action="store_true")
    args = ap.parse_args()
    RESULTS.mkdir(exist_ok=True)

    if args.split:
        res = run_split(args.split, args.n)
        name = f"experiment_{args.split}.json"
    elif args.sensitivity:
        res = run_sensitivity(args.n, [300, 301])
        name = "sensitivity.json"
    elif args.ablations:
        res = run_ablations(args.n, [400, 401])
        name = "ablations.json"
    else:
        ap.error("choose --split, --sensitivity or --ablations")
    (RESULTS / name).write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res.get("uplift", res), indent=2, default=str)[:3000])
    print(f"wrote results/{name}")


if __name__ == "__main__":
    main()
