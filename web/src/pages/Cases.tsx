import {
  Badge,
  Box,
  ChartLine,
  ChartLineWrapper,
  ChartReferenceLine,
  ChartTooltip,
  ChartXAxis,
  ChartYAxis,
  ChartCartesianGrid,
  Heading,
  Text,
} from '@razorpay/blade/components'
import { useState } from 'react'
import { CLASS_LABEL, type CaseStory } from '../data'
import { inr } from '../format'
import { Timeline } from '../timeline'
import { Chip, Loading, Panel, Stack } from '../ui'

const STORY: Record<string, { title: string; tone: 'positive' | 'notice' | 'negative' | 'information' | 'neutral' }> = {
  payday_timing: { title: 'Waited for payday', tone: 'positive' },
  harm_avoided: { title: 'Fewer bank charges', tone: 'positive' },
  reply_driven: { title: 'Acted on the reply', tone: 'information' },
  remandate: { title: 'Mandate re-authorised', tone: 'information' },
  technical: { title: 'Bank fault', tone: 'neutral' },
  stopped_or_escalated: { title: 'Stopped / to a person', tone: 'notice' },
  dobaara_lost: { title: 'Dobaara lost this one', tone: 'negative' },
  dobaara_lost_to_calendar: { title: 'Heuristic did better', tone: 'negative' },
}

const ARM_TITLE = { naive: 'Fixed daily retries', calendar: 'Salary-day heuristic', dobaara: 'Dobaara' } as const

export default function Cases({ cases }: { cases: CaseStory[] | null }) {
  const [sel, setSel] = useState(0)
  if (!cases) return <Loading />
  const c = cases[Math.min(sel, cases.length - 1)]
  const failed = new Date(c.failed_at)
  const debitDays = new Set(
    c.arms.dobaara.timeline
      .filter((r) => r.event === 'action_executed' && (r.data as { type: string }).type === 'debit_attempt')
      .map((r) => new Date(r.at).getDate()),
  )
  const curve = c.curve.map((p, i) => ({ day: String(i + 1), odds: Math.round(p * 100) }))

  return (
    <div className="case-layout">
      <Stack gap="spacing.4">
        <Text size="small" color="surface.text.gray.muted">
          {cases.length} real runs from the held-out test seed, chosen by outcome, including the ones Dobaara lost.
        </Text>
        {cases.map((k, i) => (
          <button key={k.case_id} className={`case-item${i === sel ? ' active' : ''}`} onClick={() => setSel(i)}>
            <Box display="flex" justifyContent="space-between" alignItems="center" gap="spacing.3">
              <Text weight="semibold">{inr(k.amount)}</Text>
              <Badge size="small" color={STORY[k.story]?.tone ?? 'neutral'}>
                {STORY[k.story]?.title ?? k.story}
              </Badge>
            </Box>
            <Box marginTop="spacing.2">
              <Text size="small" color="surface.text.gray.muted">
                {k.rail === 'enach' ? 'eNACH' : 'UPI AutoPay'} · {CLASS_LABEL[k.failure_class]} · {k.failure_code}
              </Text>
            </Box>
          </button>
        ))}
      </Stack>

      <Stack>
        <Panel
          title={`${inr(c.amount)} ${c.rail === 'enach' ? 'eNACH' : 'UPI AutoPay'} debit failed on ${failed.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}`}
          subtitle={`${CLASS_LABEL[c.failure_class]} (${c.failure_code}). Same customer, same luck, three policies.`}
          right={<Badge color={STORY[c.story]?.tone ?? 'neutral'}>{STORY[c.story]?.title ?? c.story}</Badge>}
        >
          <div className="grid grid-3" style={{ marginBottom: 16 }}>
            <Box>
              <Text size="small" color="surface.text.gray.muted">
                Income pattern (hidden from the policy)
              </Text>
              <Text weight="semibold">
                {c.payday_kind === 'irregular' ? 'Irregular income' : c.true_payday === 31 ? 'Paid on the last day' : `Paid on day ${c.true_payday}`}
              </Text>
            </Box>
            <Box>
              <Text size="small" color="surface.text.gray.muted">
                Payday Dobaara inferred
              </Text>
              <Text weight="semibold">Around day {c.estimated_payday}</Text>
            </Box>
            <Box>
              <Text size="small" color="surface.text.gray.muted">
                Bank charge per failed debit
              </Text>
              <Text weight="semibold">{c.rail === 'enach' ? inr(c.bounce_charge) : '₹0 on UPI'}</Text>
            </Box>
          </div>
          <Text size="small" weight="semibold">
            Estimated chance a debit succeeds, by day of month
          </Text>
          <ChartLineWrapper data={curve} height="200px">
            <ChartCartesianGrid />
            <ChartXAxis dataKey="day" />
            <ChartYAxis />
            <ChartTooltip />
            <ChartLine dataKey="odds" name="Success odds (%)" type="monotone" color="data.background.categorical.blue.moderate" />
            <ChartReferenceLine y={35} label="retry floor" />
            {[...debitDays].map((d) => (
              <ChartReferenceLine key={d} x={String(d)} label="retry" />
            ))}
          </ChartLineWrapper>
        </Panel>

        <div className="arms-3">
          {(['naive', 'calendar', 'dobaara'] as const).map((arm) => {
            const a = c.arms[arm]
            const o = a.outcome
            return (
              <Panel
                key={arm}
                title={ARM_TITLE[arm]}
                right={
                  <Badge color={o.recovered ? 'positive' : 'negative'} emphasis="subtle">
                    {o.recovered ? 'Recovered' : 'Not recovered'}
                  </Badge>
                }
              >
                <Box marginBottom="spacing.3">
                  <Text size="small" color="surface.text.gray.muted">
                    {o.debits} retries · {o.outreach} messages
                    {o.bounce_cost > 0 ? (
                      <Chip tone="red">{inr(o.bounce_cost)} bank charges</Chip>
                    ) : (
                      <Chip tone="green">no bank charges</Chip>
                    )}
                  </Text>
                </Box>
                <Timeline records={a.timeline} start={c.failed_at} />
              </Panel>
            )
          })}
        </div>
        <Box>
          <Heading size="small">Reading the timelines</Heading>
          <Box marginTop="spacing.2">
            <Text size="small" color="surface.text.gray.muted">
              Every line is a record from the hash-chained audit log. Rule ids (D-…, N-…, C-…) name the line of policy code that proposed
              the action; "Gate blocked" means the compliance gate vetoed it.
            </Text>
          </Box>
        </Box>
      </Stack>
    </div>
  )
}
