# Submission kit

Answers for the application form, and a script for the 5-minute video. Numbers are from
`results/` (held-out test unless noted). Edit the voice to your own before submitting.

## Form answers

**Track:** 03 — AI Revenue Recovery

**Project name:** Dobaara

**What it solves (short):**
Failed UPI AutoPay and eNACH debits. Most merchants retry on fixed days, which hits the same empty
account, charges the customer a bank fee, and burns the NPCI retry budget. Dobaara classifies the
failure code, retries on the days this customer's payments usually succeed (learned from their
payments across the Razorpay network), reads Hinglish replies like "5 tarik ko salary aayegi", and
passes every action through a 10-rule compliance gate with a hash-chained audit log. On 50,000
held-out simulated failures it recovers 79.8% of value vs 72.2% for a salary-day heuristic and
53.8% for fixed daily retries, cuts customers' bank charges by 85%, with 0 compliance violations
across 5.46 lakh independently re-checked actions.

**GitHub:** https://github.com/hannielvinu/Dobaara

**Prototype:** https://hannielvinu.github.io/Dobaara/

**What broke, and how you got out:**
The first result was too good: 76% recovered vs 45% for daily retries. I didn't trust it. In my
simulator a low-balance customer stayed broke until payday, which is exactly the assumption my
method exploits. So I made the world harder on myself: customers now top up after a "debit failed"
SMS (which rewards quick retries), and I added a second baseline, retrying on salary days, the
obvious heuristic a merchant would write. Most of my "win" disappeared into that heuristic. What
survived is a smaller, honest margin (₹1.25 L per 1,000 failed debits), written into the plan before
the held-out run.

The held-out ablations then showed two of my features didn't matter. The harm-aware stopping rule
never binds, and the bank-charge savings come from timing. And without network payment history,
Dobaara does *worse* than daily retries. I report both on the dashboard. The second one turned into
the real pitch: this needs to run inside Razorpay, because only the network sees when a customer's
other payments succeed.

Smaller ones: a shell heredoc turned `\b` in a regex into a backspace character, so "wrong no." was
silently never matched. "2-3 din" (two to three days) parsed as 2 March, caught by a unit test.
And the live console logged events out of order across demo cases, which let a stale plan overwrite
a customer's promise to pay. Fixed, with a regression test asserting the audit log stays chronological.

## 5-minute video script

**0:00 – 0:35 · The problem**
"About 20 million UPI AutoPay mandates are revoked every month over low balance. When a debit fails,
most merchants retry tomorrow, the day after, the day after that. If the account is empty, all three
fail. On eNACH each failure costs the customer ₹300–600 in bank charges, and the retry budget is gone."

**0:35 – 1:45 · Demo: case replay** (dashboard → Case replays → a "Waited for payday" case)
"Same customer, same luck, three policies. Daily retries: three failures, three charges. Salary-day
heuristic: better. Dobaara inferred this customer gets paid around the 1st, from their payments to
other merchants, and retried on the 4th. One notice 24 hours ahead, one retry, recovered.
Every line here is a hash-chained audit record with the rule that produced it."

**1:45 – 2:30 · Demo: live console** (API running)
"A failed-debit webhook opens a case. I reply as the customer in Hinglish: 'salary 5 tarik ko
aayegi.' The parser extracts the 5th, and the policy moves the retry to the 6th with a notice and a
reminder. I fast-forward. Recovered. The verifier re-checked every action: zero violations.
I reply 'band karo', and everything stops."

**2:30 – 3:30 · Architecture and AI judgment** (How it works page)
"Failure codes are a lookup table. Compliance is code with veto power, plus a second independent
implementation that re-checks the log. Payday timing is a small explainable model. The LLM only
reads free text, and its answer is grounded: the quoted evidence must be in the reply, the date
must come from a real date expression, and it never decides an action. A keyword baseline gets
0.93 F1 on held-out replies, so the LLM has to beat it to ship."

**3:30 – 4:30 · Results, honestly** (Overview + Experiment)
"Pre-registered plan, first commit. Held-out test, run once: 79.8% recovered vs 72.2% for the
salary-day heuristic, ₹1.25 lakh more per 1,000 failures, 85% lower bank charges, 0 violations. Now the
parts that don't flatter me: most of the gain over daily retries comes from just waiting, which the
heuristic also does. The harm rule never binds. And without network history Dobaara loses, which is
why this belongs inside Razorpay rather than inside each merchant."

**4:30 – 5:00 · What's next**
"Collect real Hinglish replies (protocol in the repo), run on Razorpay test-mode subscriptions
end-to-end, and measure the human-queue cost: 14.6% of cases go to a person, and that's a real
cost."
