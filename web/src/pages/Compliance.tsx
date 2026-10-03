import { Badge, Box, Text } from '@razorpay/blade/components'
import { useMemo, useState } from 'react'
import { ARM_LABEL, CLASS_LABEL, type ArmName, type CaseStory, type Results } from '../data'
import { num, time } from '../format'
import { describe } from '../timeline'
import { Chip, Kpi, Loading, Panel, Stack } from '../ui'

async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s))
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** Python's json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False). */
function canonical(v: unknown): string {
  if (v === null || typeof v !== 'object') return JSON.stringify(v)
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`
  const o = v as Record<string, unknown>
  return `{${Object.keys(o)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${canonical(o[k])}`)
    .join(',')}}`
}

export default function Compliance({ results, cases }: { results: Results | null; cases: CaseStory[] | null }) {
  const [check, setCheck] = useState<string | null>(null)
  const t = results?.experiment.test
  const ledger = useMemo(() => cases?.[0]?.arms.dobaara.timeline ?? [], [cases])
  if (!results || !t) return <Loading />

  const arms: ArmName[] = ['naive', 'calendar', 'dobaara']
  const total = arms.reduce((s, a) => s + t.compliance[a].actions_checked, 0)

  async function recheck() {
    // Re-derive each hash in the browser. Per-case excerpts are not a contiguous chain, so this
    // checks each record's own hash; the full chain is verified by `python -m dobaara.verify`.
    let ok = 0
    for (const r of ledger) {
      const body = canonical({ seq: r.seq, at: r.at, case_id: r.case_id, event: r.event, data: r.data, prev: r.prev_hash })
      if ((await sha256(body)) === r.hash) ok++
    }
    setCheck(`${ok} of ${ledger.length} record hashes re-computed in your browser match`)
  }

  return (
    <Stack>
      <div className="grid grid-3">
        <Kpi label="Actions re-checked by the verifier" value={num(total)} note="held-out test, all arms" />
        <Kpi label="Violations found" value={String(arms.reduce((s, a) => s + t.compliance[a].violations, 0))} tone="positive" note="independent re-implementation of every rule" />
        <Kpi label="Proposals vetoed by the gate" value={num(arms.reduce((s, a) => s + t.arms[a].blocked_by_gate, 0))} note="blocked before execution, logged with the rule ids" />
      </div>

      <Panel title="The rules" subtitle="Every action from every policy passes this gate. Where a rule allows two readings, the stricter one is implemented.">
        <table className="tbl">
          <thead>
            <tr>
              <th>Rule</th>
              <th>What it enforces</th>
              <th>Basis</th>
            </tr>
          </thead>
          <tbody>
            {results.rules.map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.id}</td>
                <td>{r.text}</td>
                <td style={{ color: '#6b7a99' }}>{r.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <div className="grid grid-2">
        <Panel title="Two implementations, one answer" subtitle="The gate (rules.py) decides; the verifier (verify.py) re-derives every rule from the audit log alone.">
          <table className="tbl">
            <thead>
              <tr>
                <th>Arm</th>
                <th className="num">Actions checked</th>
                <th className="num">Violations</th>
                <th>Hash chain</th>
              </tr>
            </thead>
            <tbody>
              {arms.map((a) => (
                <tr key={a}>
                  <td>{ARM_LABEL[a]}</td>
                  <td className="num">{num(t.compliance[a].actions_checked)}</td>
                  <td className="num">{t.compliance[a].violations}</td>
                  <td>{t.compliance[a].chain_ok ? <Chip tone="green">intact</Chip> : <Chip tone="red">broken</Chip>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Box marginTop="spacing.4">
            <Text size="small" color="surface.text.gray.muted">
              A fuzz test feeds thousands of random, often illegal, proposals through the gate and asserts the verifier finds zero violations in
              what got through. Another writes a debit straight to the ledger, skipping the gate, and asserts the verifier catches it.
            </Text>
          </Box>
        </Panel>

        <Panel
          title="Hash-chained audit log"
          subtitle="Each record stores the hash of the one before it; editing, deleting or reordering any record breaks every hash after it."
          right={
            <button onClick={recheck} style={{ border: '1px solid #305eff', color: '#305eff', background: '#fff', borderRadius: 8, padding: '6px 12px', cursor: 'pointer', fontWeight: 600 }}>
              Re-hash in browser
            </button>
          }
        >
          {check ? (
            <Box marginBottom="spacing.3">
              <Badge color="positive">{check}</Badge>
            </Box>
          ) : null}
          <div style={{ maxHeight: 360, overflow: 'auto' }}>
            {ledger.map((r) => (
              <div key={r.seq} className="event" style={{ gridTemplateColumns: '120px 1fr' }}>
                <div className="when">{time(r.at)}</div>
                <div>
                  <div style={{ fontWeight: 500 }}>{describe(r)?.text ?? r.event}</div>
                  <div className="hash">prev {r.prev_hash.slice(0, 16)}… → {r.hash.slice(0, 16)}…</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="Failure-code table" subtitle="A failure code is a lookup, not a judgement call: no model is used here. Unverified rows should be confirmed against the current NPCI circular.">
        <div className="scroll-x">
          <table className="tbl">
            <thead>
              <tr>
                <th>Source</th>
                <th>Code</th>
                <th>Meaning</th>
                <th>Class</th>
                <th>Verified</th>
              </tr>
            </thead>
            <tbody>
              {results.codes.map((c) => (
                <tr key={c.source_system + c.code}>
                  <td>{c.source_system}</td>
                  <td className="mono">{c.code}</td>
                  <td>{c.description}</td>
                  <td>{CLASS_LABEL[c.cls] ?? c.cls}</td>
                  <td>{c.verified ? <Chip tone="green">yes</Chip> : <Chip tone="amber">confirm</Chip>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </Stack>
  )
}
