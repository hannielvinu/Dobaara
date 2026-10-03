# Build log — what broke, and how I got out

Newest entries at the bottom. Each entry says what I saw, why it happened, and what changed. Numbers
are from the dev splits only; test splits are recorded in [HELDOUT_LOG.md](HELDOUT_LOG.md).

## 1. The reply baseline v1 missed a third of replies

First run of the keyword parser on the dev replies: accuracy 0.638, macro-F1 0.689, promise-date
exact match 0.642 (`results/replies_baseline_dev_v1.json`).

What was wrong, from the error list:
- Bare dates were classed `other`. "6 ko sure", "thursday", "Bhai 14 ko pakka" are answers to a
  payment reminder; a day on its own *is* the promise.
- Common phrasings missing: "bhar diya" (paid), "ho gaya payment", "wrong no.", "unemployed".
- Priority order put `cancel` above `hardship`, so "please stop deducting, I am unemployed" became a
  cancel. Someone who has lost their job should go to a person, not be dropped.

Fix (dev split only): a bare resolvable date with no question mark means `promise_to_pay`;
lexicon additions; hardship ranked above cancel. Dev: accuracy 0.948, macro-F1 0.943, date 0.925.
The baseline was frozen here.

## 2. A heredoc ate my regex

"wrong no." was still classed `other` after adding `wrong no\b` to the lexicon. Printing the
compiled patterns showed `wrong no\x08`: the script I used to patch the lexicon was a normal
Python string, so `\b` became a backspace character. The regex compiled fine and silently never
matched. Fixed the file, and the lesson went into how I edit regexes (raw strings or the editor,
never string-replace through a shell).

## 3. "2-3 din" was parsed as 2 March

A unit test (`test_date_resolution[2-3 din me]`) caught it: the d/m date pattern ran before the
"N days" pattern, so a span of two to three days resolved to 2027-03-02. A customer saying "give me
2-3 days" would have been retried five months later. Day spans are now checked before d/m dates.

## 4. The first dev result was too good to trust

Dobaara recovered 75.7% of value vs 44.7% for the naive schedule on the first smoke test. Two
reasons to distrust it:

1. In the world model, a low-balance customer stayed dry until their next income. Real customers
   often get a "debit failed" SMS and top up within days — which is exactly when the naive schedule
   retries. **Added top-ups** (25% of failures, 1–3 days later, assumption) so quick retries can win.
2. The gap might just be "wait for the 1st of the month". **Added a third baseline, `calendar`**,
   that retries on the 1st, 2nd and 7th — the obvious heuristic a merchant would write.

With both in place (dev, 25,000 cases): calendar recovers 72.4% of value and captures most of the
gain over naive. That changed the pitch: the honest claim is the *margin over a sensible heuristic*,
plus far less customer harm, not the margin over a strawman.

## 5. Dobaara lost on two failure classes

Per-class recovery on dev showed Dobaara *below* the baselines on:
- **Inactive mandates** (31.9% vs 39.9%): it sent only a re-mandate link. The baselines send a
  payment link, which collects the current due immediately. Now it sends the payment link first and
  the re-mandate link a day later.
- **Technical failures** (76.5% vs calendar 80.3%): if the bank fault recurred on the retry, the
  policy had no next step and went silent. Now it retries once more after a day's gap, and sends a
  UPI link in case the bank stays down.

After the fix (dev): inactive 50.1%, technical 88.3%. The policy was frozen here, before any test run.

## 6. Payday inference without the Razorpay network view is weak

Estimating a customer's payday from one merchant's debit history alone: mean error 4.0 days, within
one day for 53% of customers. Adding the customer's payments to other merchants (which only the
payment network sees): mean error 0.78 days, within one day for 88%. This is the clearest argument
for this living inside Razorpay rather than inside each merchant.
