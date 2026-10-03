# Metrics plan (pre-registered)

This file is committed **before** any experiment code exists. Its git timestamp is the proof that
the metrics, arms, splits and success criteria below were fixed in advance and not chosen after
seeing results. Any later change to this file is listed in the changelog at the bottom with a reason.

## Question

When a recurring UPI AutoPay / eNACH debit fails, does a policy that
(a) classifies the failure code deterministically,
(b) times retries to when the customer is likely to have funds,
(c) understands the customer's free-text (Hinglish) reply, and
(d) refuses retries whose expected cost to the customer exceeds their expected value,

recover **more money, with less customer harm, and zero compliance violations**, than doing
nothing or than the common fixed-schedule retry policy?

## Arms

| Arm | Name | Behaviour |
|-----|------|-----------|
| A | `do_nothing` | No retries, no outreach. Measures organic recovery (customer pays on their own). |
| B | `naive` | Industry-default: retry on each of the next 3 days (one per day), one generic payment-link message on day 0. Same compliance gate as C. |
| C | `dobaara` | The system under test. |

All three arms see the **same failed-debit population with common random numbers**: a customer's
latent state (payday, balance path, reply behaviour) is generated from `(seed, customer_id)` only,
so differences between arms come from the policy, not from luck.

## Primary metric

**Incremental ₹ recovered by C over B**, summed over the batch, within a 30-day recovery window,
reported with a 95% bootstrap confidence interval (resampling customers, 2,000 resamples).

## Secondary metrics (all reported for every arm, none dropped)

1. Recovery rate by count and by value.
2. Incremental ₹ recovered C − A.
3. Customer harm: total bank bounce charges (₹) incurred by customers from failed debit attempts.
4. Contact load: messages sent per case.
5. Induced cancellations (customers who cancel the subscription after outreach).
6. Days-to-recover (median).
7. Human-queue load: share of cases escalated to a person.
8. **Compliance violations — must be exactly 0**, counted by an independent verifier (`verify.py`)
   that re-derives every rule from the append-only audit log, not from the engine's own claims.
9. LLM / API cost per ₹ recovered.

## Reply-understanding sub-study

Separate labelled set of customer replies (intent + promised date + amount).

- Intents: `promise_to_pay`, `already_paid`, `hardship`, `cancel`, `dispute`, `wrong_person`, `other`.
- Metrics: per-intent precision / recall / F1, macro-F1, exact-match accuracy of the resolved
  promise date, and **rate of ungrounded outputs** (a date or amount that does not appear in the reply).
- Two parsers compared on the same split: a keyword/regex baseline and the LLM parser.
  If the LLM is not clearly better than the baseline, that is reported and the baseline is used.
- The LLM can never change the action on its own: its output is one input to a deterministic
  decision table. A test enforces this.

## Splits

- **Simulation dev:** seeds 0–4 on the base calibration. Policy parameters may be tuned here only.
- **Simulation test:** seeds 100–109 on the base calibration. Run once, after code freeze.
- **Shifted-world test:** seeds 200–204 on a calibration with a different payday mix and lower reply
  rates (`calibration_shifted`). Run once, after code freeze. Tests whether gains survive a world
  the policy was not tuned on.
- **Replies:** `dev` and `heldout` files. Prompt / lexicon iteration uses `dev` only. `heldout` is
  scored once after freeze; the run is recorded in `HELDOUT_LOG.md` with a timestamp.

## Sensitivity analysis (reported whether or not it flatters the policy)

Grid over the assumptions we are least sure of:
- share of customers with irregular income (10% → 50%)
- reply rate to outreach (×0.25 → ×1.5)
- eNACH bounce charge (₹250 → ₹590)
- annoyance from extra messages (cancel-probability per extra message, 0 → 3×)

For each cell: C − B uplift with CI. **The cells where C does not beat B are published.**

## Success criteria (decided now)

- C − B ₹ uplift 95% CI lower bound > 0 on the simulation test split.
- C causes **less** customer bounce-charge harm than B.
- 0 compliance violations in every arm, as counted by the verifier.
- Reply parser chosen for production = the one with higher macro-F1 on `heldout`,
  with ungrounded-output rate reported.

If a criterion is not met, the README says so in its first table.

## Known limitations, stated in advance

- The recovery world is a simulator. Its structural assumptions (payday-driven balances, reply
  behaviour) are documented in `dobaara/calibration.py` with a source or an explicit "assumption"
  tag for every parameter. The sensitivity grid exists because those assumptions can be wrong.
- No real customer payment data is used.

## Changelog

- v1 — initial plan.
- v2 — **added** arm B2 `calendar` (retry on the 1st, 2nd and 7th) and a customer top-up behaviour in
  the simulator, after the first dev smoke test showed a gap over B that looked too large to trust
  (NOTES.md §4). Both changes make the comparison harder for Dobaara. Made before any test-split run.
  Nothing was removed; the primary metric (C − B) is unchanged, and C − B2 is reported next to it.
