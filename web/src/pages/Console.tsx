import { Alert, Badge, Box, Button, Code, Text } from '@razorpay/blade/components'
import { useCallback, useEffect, useState } from 'react'
import type { LedgerRecord } from '../data'
import { inr, time } from '../format'
import { Timeline } from '../timeline'
import { Kpi, Panel, Stack } from '../ui'

type Summary = {
  clock: string
  razorpay_mode: string
  cases: number
  recovered: number
  recovered_inr: number
  due_inr: number
  escalations: number
  blocked_by_gate: number
  verifier: { violations: number; chain_ok: boolean; actions_checked: number }
}
type CaseRow = { case_id: string; amount: number; rail: string; failure_class: string; recovered: boolean; stopped: boolean; escalated: boolean; pending: { type: string; at: string; reason: string; rule: string }[] }
type CaseView = CaseRow & { failed_at: string; timeline: LedgerRecord[] }
type Msg = { case_id: string; at: string; kind: string; text: string; link: string | null }

function initialApi(): string {
  const q = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('api')
  if (q) return q
  try {
    return localStorage.getItem('dobaara.api') ?? 'http://127.0.0.1:8000'
  } catch {
    return 'http://127.0.0.1:8000'
  }
}

export default function Console() {
  const [api, setApi] = useState(initialApi)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [rows, setRows] = useState<CaseRow[]>([])
  const [sel, setSel] = useState<CaseView | null>(null)
  const [outbox, setOutbox] = useState<Msg[]>([])
  const [reply, setReply] = useState('salary 5 tarik ko aayegi, tab kar dunga')
  const [error, setError] = useState<string | null>(null)
  const [last, setLast] = useState<string | null>(null)

  const call = useCallback(
    async <T,>(path: string, body?: unknown): Promise<T> => {
      const r = await fetch(`${api}${path}`, {
        method: body === undefined ? 'GET' : 'POST',
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
      return (await r.json()) as T
    },
    [api],
  )

  const refresh = useCallback(
    async (caseId?: string) => {
      try {
        const [s, c, o] = await Promise.all([call<Summary>('/summary'), call<CaseRow[]>('/cases'), call<Msg[]>('/outbox')])
        setSummary(s)
        setRows(c)
        setOutbox(o.slice(-12).reverse())
        const id = caseId ?? sel?.case_id ?? c[0]?.case_id
        if (id) setSel(await call<CaseView>(`/cases/${id}`))
        setError(null)
        try {
          localStorage.setItem('dobaara.api', api)
        } catch {
          /* storage unavailable: fine */
        }
      } catch (e) {
        setError(`Can't reach the Dobaara API at ${api}. ${(e as Error).message}`)
      }
    },
    [api, call, sel?.case_id],
  )

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api])

  const act = async (fn: () => Promise<unknown>) => {
    try {
      const r = await fn()
      setLast(JSON.stringify(r))
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <Stack>
      <Panel title="Connect to a running Dobaara API" subtitle="The live console drives the real engine: webhooks in, gated actions out, on a clock you can fast-forward.">
        <Box display="flex" gap="spacing.3" flexWrap="wrap" alignItems="center">
          <input className="field" style={{ flex: 1, minWidth: 240 }} value={api} onChange={(e) => setApi(e.target.value)} aria-label="API base URL" />
          <Button variant="secondary" onClick={() => refresh()}>
            Connect
          </Button>
          {summary ? <Badge color="positive">connected · Razorpay {summary.razorpay_mode} mode</Badge> : null}
        </Box>
        {error ? (
          <Box marginTop="spacing.4">
            <Alert
              color="notice"
              isFullWidth
              title="API not reachable"
              description={
                <>
                  {error} Start it locally with <Code size="small">pip install -r requirements.txt && uvicorn dobaara.api:app</Code>, then press
                  Connect. Everything else on this site works without it.
                </>
              }
            />
          </Box>
        ) : null}
      </Panel>

      {summary ? (
        <>
          <div className="grid grid-4">
            <Kpi label="Engine clock" value={time(summary.clock)} />
            <Kpi label="Recovered" value={`${inr(summary.recovered_inr)}`} note={`${summary.recovered}/${summary.cases} cases of ${inr(summary.due_inr)} due`} tone="positive" />
            <Kpi label="Sent to a person" value={String(summary.escalations)} note={`${summary.blocked_by_gate} proposals vetoed by the gate`} />
            <Kpi
              label="Verifier"
              value={summary.verifier.violations === 0 && summary.verifier.chain_ok ? '0 violations' : `${summary.verifier.violations} violations`}
              note={`${summary.verifier.actions_checked} actions · chain ${summary.verifier.chain_ok ? 'intact' : 'broken'}`}
              tone={summary.verifier.violations === 0 ? 'positive' : 'negative'}
            />
          </div>

          <Box display="flex" gap="spacing.3" flexWrap="wrap">
            <Button onClick={() => act(() => call('/demo/cases', { n: 6, seed: Math.floor(Math.random() * 10000) }))}>Open 6 demo failures</Button>
            <Button variant="secondary" onClick={() => act(() => call('/clock/advance', { hours: 24 }))}>
              +1 day
            </Button>
            <Button variant="secondary" onClick={() => act(() => call('/clock/advance', { hours: 24 * 7 }))}>
              +1 week
            </Button>
          </Box>

          <div className="case-layout">
            <Stack gap="spacing.4">
              {rows.map((r) => (
                <button key={r.case_id} className={`case-item${sel?.case_id === r.case_id ? ' active' : ''}`} onClick={() => refresh(r.case_id)}>
                  <Box display="flex" justifyContent="space-between">
                    <Text weight="semibold">{inr(r.amount)}</Text>
                    <Badge size="small" color={r.recovered ? 'positive' : r.stopped ? 'negative' : r.escalated ? 'notice' : 'neutral'}>
                      {r.recovered ? 'recovered' : r.stopped ? 'stopped' : r.escalated ? 'with a person' : `${r.pending.length} scheduled`}
                    </Badge>
                  </Box>
                  <Text size="small" color="surface.text.gray.muted">
                    {r.rail === 'enach' ? 'eNACH' : 'UPI AutoPay'} · {r.failure_class.replace(/_/g, ' ')}
                  </Text>
                </button>
              ))}
            </Stack>
            {sel ? (
              <Stack gap="spacing.5">
                <Panel title={`Case ${sel.case_id}`} subtitle="Reply as the customer; the parser turns it into an intent and the policy re-plans.">
                  <textarea className="reply" value={reply} onChange={(e) => setReply(e.target.value)} />
                  <Box display="flex" gap="spacing.3" marginTop="spacing.3" flexWrap="wrap">
                    <Button size="small" onClick={() => act(() => call(`/cases/${sel.case_id}/reply`, { text: reply }))}>
                      Send reply
                    </Button>
                    <Button size="small" variant="secondary" onClick={() => act(() => call(`/cases/${sel.case_id}/reply`, { text: reply, parser: 'llm' }))}>
                      Send via Claude parser
                    </Button>
                    <Button size="small" variant="tertiary" onClick={() => act(() => call(`/cases/${sel.case_id}/link-paid`, {}))}>
                      Customer pays the link
                    </Button>
                  </Box>
                  {last ? (
                    <Box marginTop="spacing.3">
                      <Code size="small">{last}</Code>
                    </Box>
                  ) : null}
                </Panel>
                <div className="grid grid-2">
                  <Panel title="Audit log">
                    <Timeline records={sel.timeline} start={sel.failed_at} />
                  </Panel>
                  <Panel title="Scheduled next">
                    {sel.pending.length === 0 ? (
                      <Text size="small" color="surface.text.gray.muted">
                        Nothing scheduled.
                      </Text>
                    ) : (
                      sel.pending.map((p, i) => (
                        <div key={i} className="event">
                          <div className="when">{time(p.at)}</div>
                          <div>
                            <span style={{ fontWeight: 500 }}>{p.type.replace(/_/g, ' ')}</span>
                            <div style={{ color: '#6b7a99' }}>
                              {p.reason} · {p.rule}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </Panel>
                </div>
              </Stack>
            ) : null}
          </div>

          <Panel title="Outbox" subtitle="Messages the engine sent (mock SMS; payment links come from Razorpay in test mode)">
            {outbox.map((m, i) => (
              <div key={i} className="event" style={{ gridTemplateColumns: '120px 1fr' }}>
                <div className="when">{time(m.at)}</div>
                <div>
                  <span className="chip gray">{m.kind.replace(/_/g, ' ')}</span> {m.text}
                  {m.link ? <div className="hash">{m.link}</div> : null}
                </div>
              </div>
            ))}
          </Panel>
        </>
      ) : null}
    </Stack>
  )
}
