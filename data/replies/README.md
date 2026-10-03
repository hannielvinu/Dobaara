# Customer replies

`replies_source.jsonl`: 180 replies to payment reminders, in Hinglish, Hindi (Devanagari) and English.

| field | meaning |
|---|---|
| `id` | stable id; the dev / held-out split is a hash of it (`dataset.split_of`) |
| `sent` | date the reply was sent; relative dates resolve against it |
| `text` | the reply, verbatim |
| `intent` | `promise_to_pay`, `already_paid`, `hardship`, `cancel`, `dispute`, `wrong_person`, `other` |
| `date_rule` | gold promised date as a rule, or `null` |

## Labelling rules

- **promise_to_pay**: will pay, or asks to retry (now or later). A bare day ("6 ko", "thursday") in answer
  to a reminder is a promise.
- **already_paid**: says it is already paid, through any channel.
- **hardship**: cannot pay because of job loss, illness or business trouble, or asks to pause or
  downgrade, *without* a commitment to pay. With a commitment, it is a promise.
- **cancel**: does not want the service, asks to stop messages or debits, or refuses to pay without
  disputing the charge.
- **dispute**: the charge is wrong, unauthorised, duplicated or fraudulent, or a refund is demanded first.
- **wrong_person**: not their number or account.
- **other**: questions, acknowledgements, anything unclear.

Date rules: `+N` (N days after sent), `dom:D` (next day-of-month D on or after sent), `wd:mon`
(next Monday strictly after sent), `eom` (last day of the sent month), `abs:YYYY-MM-DD`. Vague timing
("next week", "salary aane pe", "1 week") is `null`. "2-3 din" takes the later bound.

## Known weakness

These replies were written by the builder, who also wrote the keyword lexicon. The lexicon was
written first and tuned on the dev split only, but the same person knew the held-out texts. Treat
the scores as a smoke test, not an unbiased benchmark.

## Collecting real replies (protocol)

1. Google Form shown to 30+ people, ideally across several states: "You missed a ₹499 subscription
   payment. You get this SMS: *'Your payment didn't go through. Pay via this link, or reply if you
   need more time.'* What would you text back? Write it exactly as you would."
   Ask for 3 replies each, in three situations: you'll pay soon / you don't want it / something's wrong.
2. No names, numbers or account details collected.
3. Two people label each reply independently with the rules above; report agreement (Cohen's κ).
4. Disagreements resolved by discussion; the resolved label is gold.
5. New rows get new ids (`h001`…), so the hash split assigns them without anyone choosing.
6. Score once with `python -m dobaara.replies.evaluate --parser baseline --split heldout` and
   `--parser llm`, and record the run in `HELDOUT_LOG.md`.
