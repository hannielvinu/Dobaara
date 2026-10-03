import { Alert, Box, Text } from '@razorpay/blade/components'
import { useState } from 'react'
import type { ReplyScore, Results } from '../data'
import { pct } from '../format'
import { Chip, Kpi, Loading, Panel, Stack } from '../ui'

const INTENTS = ['promise_to_pay', 'already_paid', 'hardship', 'cancel', 'dispute', 'wrong_person', 'other']
const label = (s: string) => s.replace(/_/g, ' ')

function Score({ s, title }: { s: ReplyScore | null; title: string }) {
  if (!s) {
    return <Kpi label={title} value="not run" note="needs an Anthropic API key; see README" />
  }
  return (
    <Kpi
      label={title}
      value={`${s.macro_f1.toFixed(3)} F1`}
      note={`accuracy ${pct(s.accuracy)} · promise dates exact ${s.promise_date_exact == null ? '—' : pct(s.promise_date_exact)} · n=${s.n}`}
    />
  )
}

export default function Replies({ results }: { results: Results | null }) {
  const [onlyErrors, setOnlyErrors] = useState(false)
  if (!results) return <Loading />
  const r = results.replies
  const held = r.baseline_heldout
  const rows = r.examples.filter((e) => !onlyErrors || e.gold !== e.pred || e.gold_date !== e.pred_date)

  return (
    <Stack>
      <Text color="surface.text.gray.muted">
        Customers answer dunning messages in Hinglish, Hindi and English: "salary aane pe kar dunga", "5 tarik ko pakka", "बंद कर दो".
        Each reply becomes an intent and, if it names one, a calendar day. The parser only produces data; the action comes from a
        deterministic table, and a date is used only if it is grounded in the text.
      </Text>

      <div className="grid grid-4">
        <Score s={r.baseline_dev_v1} title="Keyword baseline v1 (dev)" />
        <Score s={r.baseline_dev} title="Baseline v2, frozen (dev)" />
        <Score s={held} title="Baseline v2 (held-out, run once)" />
        <Score s={r.llm_heldout} title="Claude parser (held-out)" />
      </div>

      {held ? (
        <Panel title="Per-intent results on held-out replies" subtitle="Precision, recall and F1 of the frozen keyword baseline">
          <table className="tbl">
            <thead>
              <tr>
                <th>Intent</th>
                <th className="num">Precision</th>
                <th className="num">Recall</th>
                <th className="num">F1</th>
                <th className="num">Support</th>
              </tr>
            </thead>
            <tbody>
              {INTENTS.map((i) => {
                const m = held.per_intent[i]
                return m ? (
                  <tr key={i}>
                    <td>{label(i)}</td>
                    <td className="num">{m.precision.toFixed(2)}</td>
                    <td className="num">{m.recall.toFixed(2)}</td>
                    <td className="num">{m.f1.toFixed(2)}</td>
                    <td className="num">{m.support}</td>
                  </tr>
                ) : null
              })}
            </tbody>
          </table>
        </Panel>
      ) : null}

      <Panel
        title="Held-out replies, with what the parser said"
        subtitle="Red rows are mistakes. A wrong date on a promise counts as a mistake."
        right={
          <label style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
            <input type="checkbox" checked={onlyErrors} onChange={(e) => setOnlyErrors(e.target.checked)} /> only mistakes
          </label>
        }
      >
        <div className="scroll-x">
          <table className="tbl">
            <thead>
              <tr>
                <th>Reply</th>
                <th>Sent</th>
                <th>Label</th>
                <th>Parser</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => {
                const ok = e.gold === e.pred && e.gold_date === e.pred_date
                return (
                  <tr key={e.id} style={ok ? undefined : { background: '#fff5f5' }}>
                    <td style={{ maxWidth: 380 }}>{e.text}</td>
                    <td className="mono">{e.sent.slice(5)}</td>
                    <td>
                      {label(e.gold)}
                      {e.gold_date ? <Chip tone="gray">{e.gold_date.slice(5)}</Chip> : null}
                    </td>
                    <td>
                      {label(e.pred)}
                      {e.pred_date ? <Chip tone={e.pred_date === e.gold_date ? 'gray' : 'red'}>{e.pred_date.slice(5)}</Chip> : null}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid grid-2">
        <Panel title="Where an LLM earns its place" subtitle="and where it does not">
          <Stack gap="spacing.3">
            <Text size="small">
              The keyword baseline is free, instant and explainable, and it already scores {held ? held.macro_f1.toFixed(2) : '—'} macro-F1 on
              held-out replies. The Claude parser is wired in with structured output and grounding checks, and ships only if it beats the
              baseline on the same held-out set.
            </Text>
            <Text size="small">Grounding checks run in code on every LLM answer:</Text>
            <Box paddingLeft="spacing.4">
              <Text size="small">• the quoted evidence must appear verbatim in the reply</Text>
              <Text size="small">• a promised date is kept only if the reply contains a date expression</Text>
              <Text size="small">• an amount is kept only if those digits are in the reply</Text>
              <Text size="small">• customer text is wrapped as data; instructions inside it are ignored</Text>
            </Box>
          </Stack>
        </Panel>
        <Panel title="How the labelled set was built" subtitle="and its weakness">
          <Text size="small">
            180 replies with gold labels written as rules ("dom:5", "+1", "wd:mon"), so the human judgement is separate from calendar
            arithmetic. Split by a hash of the id: 116 dev, 64 held-out. The keyword lexicon was written before the set and tuned on dev
            only.
          </Text>
          <Box marginTop="spacing.4">
            <Alert
              color="notice"
              emphasis="subtle"
              isFullWidth
              description="The replies were written by the builder, not collected from customers, so the same person wrote the lexicon and the test. Treat these numbers as a smoke test. The protocol for collecting real replies is in data/replies/README.md."
            />
          </Box>
        </Panel>
      </div>
    </Stack>
  )
}
