# Dobaara

**Recovering failed UPI AutoPay and eNACH debits: retry when the money is there, understand what the
customer replies, never break the rules, and prove it.**

Razorpay AI Buildathon 2026 · Track 03 — AI Revenue Recovery
Prototype: **https://hannielvinu.github.io/Dobaara/** · Build log: [NOTES.md](NOTES.md) ·
Pre-registered plan: [METRICS_PLAN.md](METRICS_PLAN.md) · Held-out runs: [HELDOUT_LOG.md](HELDOUT_LOG.md)

---

## Results first (held-out test, 50,000 failed debits, run once)

| Policy | Value recovered | Bank charges paid by customers (₹ / 1,000 cases) | Messages / case | Cancellations | Sent to a person | Compliance violations |
|---|---:|---:|---:|---:|---:|---:|
| Do nothing | 16.6% | 0 | 0.00 | 0.0% | 0.0% | 0 |
| Fixed daily retries (common default) | 53.8% | 1,60,016 | 0.97 | 4.7% | 0.0% | 0 |
| Salary-day heuristic (1st, 2nd, 7th) | 72.2% | 61,343 | 1.00 | 4.0% | 0.0% | 0 |
| **Dobaara** | **79.8%** | **23,236** | 1.15 | 3.9% | 14.6% | **0** |

**Incremental ₹ recovered per 1,000 failed debits (paired by customer, 95% bootstrap CI):**

| Comparison | ₹ / 1,000 cases | 95% CI |
|---|---:|---:|
| Dobaara − salary-day heuristic | **₹1,24,735** | ₹1,15,802 – ₹1,34,501 |
| Dobaara − fixed daily retries (pre-registered primary) | ₹4,25,554 | ₹4,12,198 – ₹4,38,710 |
| Dobaara − do nothing | ₹10,35,987 | ₹10,18,455 – ₹10,53,302 |

- **Shifted world** (an income calendar and customer behaviour the policy was never tuned on):
  Dobaara − salary-day = ₹88,723 per 1,000 (CI ₹75,498 – ₹1,01,779); value recovered 80.1% vs 75.7%.
- **Compliance:** 5,45,927 executed actions re-checked by an independent verifier → 0 violations;
  hash chain intact in every arm.
- **Reply understanding** (keyword baseline, frozen on dev, held-out run once): macro-F1 0.932,
  promise-date exact match 93.3% on 64 held-out replies. See the caveat below.

### What does *not* look good, stated plainly

1. **Most of the gain over daily retries is just waiting for money.** The salary-day heuristic gets
   there too. Dobaara's own margin is the ₹1.25 L per 1,000 cases over that heuristic.
2. **Without Razorpay's network view, Dobaara loses.** Inferring a customer's payday from one
   merchant's own history is off by ~3.9 days; with their payments to other merchants, by ~0.8 days.
   In the ablation without network history, Dobaara recovers 49.3% of value, *less* than fixed daily
   retries. This only works inside the payment network.
3. **The harm-aware stopping rule almost never binds.** Removing it changes nothing. The 85% cut in
   bank charges comes from retrying on days the money is there, not from that rule.
4. **A perfect reply parser adds ~₹3,500 per 1,000 cases.** Replies matter for consent (stop,
   dispute, wrong number) and for routing hardship to a person, not for the money. So the parser
   never decides an action.
5. **14.6% of cases go to a person.** Disputes, hardship, "already paid", risk declines, unknown codes.
   That is a staffing cost.
6. **Dobaara sends slightly more messages** (1.15 vs 0.97 per case), mostly re-mandate links and promise-day reminders.
7. **The world is simulated.** Failure codes, retry caps, notice rules and execution windows follow
   NPCI / RBI / Razorpay docs; income calendars, reply behaviour and top-ups are assumptions, each
   tagged in [calibration.py](dobaara/calibration.py) and varied in the sensitivity grid.
8. **The reply set (180 examples) was written by me**, the same person who wrote the keyword lexicon.
   Treat the reply scores as a smoke test. The protocol for collecting real replies is in
   [data/replies/README.md](data/replies/README.md).

---

## The problem

Recurring payments in India fail a lot. About 20 million UPI AutoPay mandates a month are revoked
over low balance (Business Standard, Sep 2025), and every failed eNACH debit costs the *customer*
a bank charge of ₹250–500 + GST. Most merchants respond with a fixed retry schedule: retry
tomorrow, the day after, the day after that. When the cause is low balance, those retries land in
the same dry week: they fail, they charge the customer, and they burn the mandate's retry budget.

## What Dobaara does

```
Razorpay webhook (payment.failed, recurring)
  1. Failure-code table          DETERMINISTIC  NPCI / Razorpay code -> cause (19 Razorpay + 15 NPCI codes, each sourced)
  2. Payday model                SMALL MODEL    kernel-smoothed success odds by day of month, from network payment history
  3. Recovery policy             DETERMINISTIC  picks the intervention; every action carries the rule id that produced it
  4. Reply parser                LLM / KEYWORDS Hinglish reply -> intent + promised day, grounded in the text
  5. Compliance gate             DETERMINISTIC  10 rules with veto power; blocked proposals are logged
  6. Hash-chained ledger         every proposal, outcome and reply
  7. Independent verifier        re-derives every rule from the ledger alone (separate implementation)
```

| Failure cause | What Dobaara does |
|---|---|
| Insufficient funds | Up to 3 retries on the days this customer's payments usually succeed (odds ≥ 35%), each announced 24h ahead; a UPI payment link so they can pay whenever money arrives, with no bounce charge |
| Bank / PSP technical | Retry at the next compliant slot; once more after a day if it recurs; then payday timing |
| Mandate revoked / paused | Payment link for this due, re-authorisation link for future dues; never debits an inactive mandate |
| Limit exceeded, account blocked, risk decline | No debit (it can't succeed); payment link; risk declines and large dues go to a person |
| Unrecognised code | At most one retry, plus a person |

| Customer reply | What Dobaara does |
|---|---|
| "5 tarik ko salary aayegi" (promise with a day) | Moves the retry to the day after, with a reminder on the day |
| "kar diya" (already paid) | Stops all debits until a person reconciles (double-debit guard) |
| "job chali gayi" (hardship) | Stops debits; a person offers a pause or a smaller plan |
| "band karo" / "fraud hai" / "wrong number" | Stops all contact; disputes go to a person |

### The rules (every action, every policy)

| Rule | Basis |
|---|---|
| At most 1 original + 3 retries | NPCI UPI AutoPay retry rules, 2025 |
| Pre-debit notice ≥ 24h before **each** debit, for the exact amount (stricter reading) | RBI e-mandate framework |
| Debits only before 10:00, 13:00–17:00, or after 21:30 | NPCI 2025 off-peak windows |
| Messages only 08:00–19:00 | RBI recovery-contact guidance, adopted voluntarily |
| ≤ 3 outreach messages per case; nothing after cancel / dispute / wrong number | anti-harassment, consent |
| Never debit above the amount due or the mandate's maximum | RBI e-mandate framework |
| No debit after "already paid" until reconciled; nothing after 30 days | double-debit guard, stopping rule |

## Where AI is used, and where it deliberately isn't

| Decision | Method | Why |
|---|---|---|
| What a failure code means | lookup table | a code is a fact, not a judgement |
| Is this action allowed | coded rules + independent verifier | compliance must be exact and auditable |
| When to retry | small kernel-smoothed model | explainable in one sentence, checkable against ground truth (payday error) |
| What the customer said | keyword baseline; Claude (`claude-opus-5-5`, structured output) when it beats the baseline on held-out data | free text in three scripts is where language models are useful |
| What to do about the reply | deterministic table | the model never has the last word on money |

LLM guardrails, enforced in code ([llm.py](dobaara/replies/llm.py)): the quoted evidence must
appear verbatim in the reply; a promised date is kept only if the reply contains a date expression;
an amount only if those digits are in the reply; customer text is wrapped as data and the prompt
says to ignore instructions inside it; ungrounded answers lose their date; refusals fall back to
`other` and a person. Responses are cached on disk, so evaluations reproduce at no cost.

## How it was evaluated

- **Pre-registered.** [METRICS_PLAN.md](METRICS_PLAN.md) was the first commit, before any experiment
  code. One change since (adding the salary-day baseline and customer top-ups, both of which make
  the comparison harder) is in its changelog, dated before any test run.
- **Common random numbers.** Every customer's world (income, balance, replies) is a pure function of
  `(seed, customer_id)`, and every random draw is keyed by event and day, so all arms face identical luck.
- **Splits.** Dev seeds 0–4 for tuning; test seeds 100–109 and shifted-world seeds 200–204 run once
  after freeze ([HELDOUT_LOG.md](HELDOUT_LOG.md)). Replies split by a hash of the id.
- **Parser error is in the loop.** The simulator injects the reply parser's measured confusion
  matrix, so parser mistakes cost money in the results instead of being assumed away.
- **Sensitivity and ablations.** Irregular income (10–50%), reply rate (0.25–1.5×), bounce charge
  (₹250–590), annoyance (0–3×); network history, parser quality, harm rule removed one at a time.

## Razorpay integration

- `POST /webhooks/razorpay`: HMAC-SHA256 signature check over the raw body; `payment.failed` on a
  recurring payment opens a case (idempotent); `payment_link.paid` closes it.
- Payment Links API for no-bounce UPI collection (Dobaara sends its own messages, so Razorpay's
  notifications are off and the contact-hour and outreach-cap rules hold).
- Recurring retries: an order, then `payments/create/recurring` on the existing token.
- **Test mode only.** An `rzp_live_` key is refused at start-up. Without keys it runs in mock mode
  with the same response shapes.

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q                     # 169 tests
make eval-dev                           # dev split (tuning)
make eval                               # held-out runs + dashboard export (≈15 min)
uvicorn dobaara.api:app                 # live API on :8000
cd web && npm ci && npm run dev         # dashboard; Live console connects to the API
```

Optional: `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` (test keys), `RAZORPAY_WEBHOOK_SECRET`,
`ANTHROPIC_API_KEY` (enables `make replies-llm` and the Claude parser in the console).

## Repository map

| Path | What |
|---|---|
| [dobaara/codes.py](dobaara/codes.py) | failure-code table with sources and `verified` flags |
| [dobaara/rules.py](dobaara/rules.py) | the compliance gate |
| [dobaara/verify.py](dobaara/verify.py) | independent verifier (does not import the gate) |
| [dobaara/audit.py](dobaara/audit.py) | hash-chained, append-only ledger |
| [dobaara/policies.py](dobaara/policies.py) | Do-nothing, Naive, Calendar, Dobaara |
| [dobaara/payday.py](dobaara/payday.py) | payday / success-odds model |
| [dobaara/replies/](dobaara/replies) | date resolver, keyword baseline, Claude parser, dataset, evaluation |
| [dobaara/simulator.py](dobaara/simulator.py), [calibration.py](dobaara/calibration.py) | world model with keyed randomness; every parameter sourced or tagged |
| [dobaara/experiment.py](dobaara/experiment.py) | controlled experiment, bootstrap CIs, sensitivity, ablations |
| [dobaara/service.py](dobaara/service.py), [api.py](dobaara/api.py), [razorpay.py](dobaara/razorpay.py) | live service, HTTP API, Razorpay adapter |
| [web/](web) | dashboard built with Razorpay's Blade design system |
| [results/](results) | every number in this README |

Built by Hanniel Vinu; Blade is Razorpay's open-source (MIT) design system.
