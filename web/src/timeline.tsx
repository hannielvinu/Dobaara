import type { LedgerRecord } from './data'
import { dayOffset, inr, time } from './format'

type Tone = 'blue' | 'green' | 'red' | 'amber' | 'gray'
const COLOR: Record<Tone, string> = { blue: '#305eff', green: '#12a15e', red: '#d92d20', amber: '#e08700', gray: '#98a2b3' }

const ACTION: Record<string, string> = {
  pre_debit_notice: 'Pre-debit notice sent',
  debit_attempt: 'Debit retried',
  payment_link: 'UPI payment link sent',
  remandate_link: 'Re-authorise mandate link sent',
  reminder: 'Reminder sent',
  escalate: 'Sent to a person',
  stop: 'Stopped all contact',
}

export function describe(r: LedgerRecord): { text: string; detail?: string; tone: Tone } | null {
  const d = r.data as Record<string, string | number | boolean | string[] | null>
  switch (r.event) {
    case 'case_opened':
      return { text: `Debit of ${inr(Number(d.amount))} failed`, detail: `${d.failure_code} → ${String(d.failure_class).replace(/_/g, ' ')} · ${d.rail === 'enach' ? 'eNACH' : 'UPI AutoPay'}`, tone: 'red' }
    case 'action_executed':
      return {
        text: ACTION[String(d.type)] ?? String(d.type),
        detail: [d.reason, d.policy_rule].filter(Boolean).join(' · '),
        tone: d.type === 'escalate' || d.type === 'stop' ? 'amber' : 'blue',
      }
    case 'action_blocked':
      return { text: `Gate blocked ${String(d.type).replace(/_/g, ' ')}`, detail: (d.violated as string[]).join(', '), tone: 'amber' }
    case 'debit_result':
      return d.success ? { text: 'Debit succeeded', tone: 'green' } : { text: `Debit failed (${d.code})`, tone: 'red' }
    case 'reply_received':
      return {
        text: `Customer replied: ${String(d.intent).replace(/_/g, ' ')}`,
        detail: d.promised_date ? `promised ${d.promised_date}` : undefined,
        tone: 'gray',
      }
    case 'payment_received':
      return { text: `Paid via ${String(d.via).replace(/_/g, ' ')}`, tone: 'green' }
    case 'mandate_reactivated':
      return { text: 'Mandate re-authorised', tone: 'green' }
    case 'subscription_cancelled':
      return { text: 'Customer cancelled the subscription', tone: 'red' }
    case 'case_recovered':
      return { text: `Recovered ${inr(Number(d.amount))}`, tone: 'green' }
    default:
      return null
  }
}

export function Timeline({ records, start }: { records: LedgerRecord[]; start: string }) {
  return (
    <div>
      {records.map((r) => {
        const e = describe(r)
        if (!e) return null
        return (
          <div className="event" key={r.seq}>
            <div className="when">
              <div style={{ fontWeight: 600, color: '#1b2640' }}>{dayOffset(start, r.at)}</div>
              <div>{time(r.at).split(', ')[1] ?? ''}</div>
            </div>
            <div>
              <span className="dot" style={{ background: COLOR[e.tone] }} />
              <span style={{ fontWeight: 500 }}>{e.text}</span>
              {e.detail ? <div style={{ color: '#6b7a99', marginTop: 2, marginLeft: 14 }}>{e.detail}</div> : null}
            </div>
          </div>
        )
      })}
    </div>
  )
}
