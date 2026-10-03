import {
  Alert,
  Box,
  ChartCartesianGrid,
  ChartLine,
  ChartLineWrapper,
  ChartReferenceLine,
  ChartTooltip,
  ChartXAxis,
  ChartYAxis,
  Text,
} from '@razorpay/blade/components'
import { ARM_LABEL, type ArmName, type Experiment as Exp, type Results } from '../data'
import { inrShort, num, pct } from '../format'
import { Chip, Loading, Panel, Stack } from '../ui'

const ARMS: ArmName[] = ['do_nothing', 'naive', 'calendar', 'dobaara']

const PARAM: Record<string, { title: string; unit: (v: number) => string; note: string }> = {
  irregular_income_share: { title: 'Share of customers with irregular income', unit: (v) => pct(v, 0), note: 'Payday timing helps less when there is no payday.' },
  reply_rate_multiplier: { title: 'How often customers reply', unit: (v) => `${v}×`, note: 'Fewer replies means fewer promises to act on.' },
  enach_bounce_inr: { title: 'eNACH bounce charge', unit: (v) => `₹${v}`, note: 'Higher charges make more retries not worth it.' },
  annoyance_multiplier: { title: 'Cancellations caused by extra messages', unit: (v) => `${v}×`, note: 'Tests whether extra outreach backfires.' },
}

function ArmsTable({ e }: { e: Exp }) {
  const rows: [string, (a: ArmName) => string][] = [
    ['Value recovered', (a) => pct(e.arms[a].recovery_rate_value)],
    ['Cases recovered', (a) => pct(e.arms[a].recovery_rate_count)],
    ['₹ recovered', (a) => inrShort(e.arms[a].recovered_inr)],
    ['Bank charges to customers', (a) => inrShort(e.arms[a].customer_bounce_charges_inr)],
    ['Debit retries / case', (a) => e.arms[a].debit_retries_per_case.toFixed(2)],
    ['Messages / case', (a) => e.arms[a].outreach_per_case.toFixed(2)],
    ['Pre-debit notices / case', (a) => e.arms[a].notices_per_case.toFixed(2)],
    ['Cancellations', (a) => pct(e.arms[a].cancel_rate)],
    ['Sent to a person', (a) => pct(e.arms[a].escalation_rate)],
    ['Median days to recover', (a) => (e.arms[a].median_days_to_recover ?? 0).toFixed(1)],
    ['Actions blocked by the gate', (a) => num(e.arms[a].blocked_by_gate)],
    ['Compliance violations (verifier)', (a) => String(e.compliance[a].violations)],
  ]
  return (
    <div className="scroll-x">
      <table className="tbl">
        <thead>
          <tr>
            <th>Metric</th>
            {ARMS.map((a) => (
              <th key={a} className="num">
                {ARM_LABEL[a]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, f]) => (
            <tr key={label}>
              <td>{label}</td>
              {ARMS.map((a) => (
                <td key={a} className="num" style={a === 'dobaara' ? { fontWeight: 600 } : undefined}>
                  {f(a)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function UpliftTable({ e }: { e: Exp }) {
  const pairs: [string, string][] = [
    ['dobaara_vs_calendar', 'Dobaara − salary-day heuristic'],
    ['dobaara_vs_naive', 'Dobaara − fixed daily retries (primary)'],
    ['dobaara_vs_do_nothing', 'Dobaara − do nothing'],
    ['calendar_vs_naive', 'Salary-day − fixed daily retries'],
  ]
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>Comparison</th>
          <th className="num">₹ per 1,000 cases</th>
          <th className="num">Total</th>
          <th className="num">95% CI</th>
          <th className="num">Bank charges Δ / 1,000</th>
        </tr>
      </thead>
      <tbody>
        {pairs.map(([k, label]) => {
          const u = e.uplift[k]
          const h = e.harm_delta[k]
          if (!u) return null
          return (
            <tr key={k} className={k === 'dobaara_vs_calendar' ? 'hl' : undefined}>
              <td>{label}</td>
              <td className="num">{inrShort(u.per_1000_cases)}</td>
              <td className="num">{inrShort(u.total)}</td>
              <td className="num">
                {inrShort(u.ci95[0])} – {inrShort(u.ci95[1])}
              </td>
              <td className="num">{inrShort(h.per_1000_cases)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default function Experiment({ results }: { results: Results | null }) {
  if (!results?.experiment.test) return <Loading />
  const { test, shifted } = results.experiment
  const sens = results.sensitivity
  const abl = results.ablations

  return (
    <Stack>
      <Panel
        title="Held-out test: base calibration"
        subtitle={`${num(test.cases_per_seed * test.seeds.length)} failed debits across seeds ${test.seeds[0]}–${test.seeds[test.seeds.length - 1]}, run once after the policy was frozen. Each customer appears in every arm with identical randomness.`}
      >
        <ArmsTable e={test} />
      </Panel>

      <Panel title="Incremental money recovered" subtitle="Paired by customer, 2,000 bootstrap resamples. Bank-charge deltas below zero mean less harm.">
        <UpliftTable e={test} />
      </Panel>

      {shifted ? (
        <Panel
          title="Shifted world: a calibration the policy was never tuned on"
          subtitle="Different income calendar (5th / 20th / 25th paydays, 30% irregular), quieter customers, pricier bounces, more eNACH."
        >
          <Stack gap="spacing.5">
            <UpliftTable e={shifted} />
            <ArmsTable e={shifted} />
          </Stack>
        </Panel>
      ) : null}

      {sens ? (
        <Panel title="Sensitivity: where does Dobaara stop winning?" subtitle="One assumption varied at a time; Dobaara − fixed daily retries, ₹ per 1,000 cases with 95% CI.">
          <div className="grid grid-2">
            {Object.entries(sens).map(([param, cells]) => {
              const meta = PARAM[param]
              const data = cells.map((c) => ({
                x: meta?.unit(c.value) ?? String(c.value),
                uplift: Math.round(c.uplift_per_1000),
                low: Math.round(c.uplift_ci95_per_1000[0]),
                harm: Math.round(c.harm_delta_per_1000),
              }))
              const losing = cells.filter((c) => !c.dobaara_beats_naive)
              return (
                <Box key={param} padding="spacing.4" borderRadius="medium" borderWidth="thin" borderColor="surface.border.gray.muted">
                  <Text weight="semibold">{meta?.title ?? param}</Text>
                  <Text size="small" color="surface.text.gray.muted">
                    {meta?.note}
                  </Text>
                  <ChartLineWrapper data={data} height="200px">
                    <ChartCartesianGrid />
                    <ChartXAxis dataKey="x" />
                    <ChartYAxis />
                    <ChartTooltip />
                    <ChartLine dataKey="uplift" name="₹ uplift / 1,000" color="data.background.categorical.blue.moderate" />
                    <ChartLine dataKey="low" name="CI lower bound" type="linear" color="data.background.categorical.blue.subtle" />
                    <ChartLine dataKey="harm" name="Bank charges Δ" color="data.background.categorical.red.moderate" />
                    <ChartReferenceLine y={0} label="0" />
                  </ChartLineWrapper>
                  <Box marginTop="spacing.2">
                    {losing.length ? (
                      <Chip tone="red">Does not beat daily retries at: {losing.map((c) => meta?.unit(c.value) ?? c.value).join(', ')}</Chip>
                    ) : (
                      <Chip tone="green">CI above zero in every cell</Chip>
                    )}
                  </Box>
                </Box>
              )
            })}
          </div>
        </Panel>
      ) : null}

      {abl ? (
        <Panel title="Ablations: what each part contributes" subtitle="Remove one component at a time; Dobaara − fixed daily retries.">
          <table className="tbl">
            <thead>
              <tr>
                <th>Variant</th>
                <th className="num">Value recovered</th>
                <th className="num">₹ uplift / 1,000</th>
                <th className="num">Bank charges Δ / 1,000</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(abl).map(([k, v]) => (
                <tr key={k} className={k === 'full' ? 'hl' : undefined}>
                  <td>
                    {{
                      full: 'Full Dobaara',
                      no_network_history: 'Without network payment history',
                      perfect_parser: 'With a perfect reply parser (upper bound)',
                      no_harm_awareness: 'Without harm-aware stopping',
                    }[k] ?? k}
                  </td>
                  <td className="num">{pct(v.dobaara_recovery_rate_value)}</td>
                  <td className="num">{inrShort(v.uplift_vs_naive.per_1000_cases)}</td>
                  <td className="num">{inrShort(v.harm_delta_vs_naive.per_1000_cases)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Box marginTop="spacing.4" display="flex" flexDirection="column" gap="spacing.3">
            <Alert
              color="negative"
              emphasis="subtle"
              isFullWidth
              title="Without Razorpay's network view, Dobaara loses"
              description="With only one merchant's own debit history, payday estimates are off by about 4 days and Dobaara recovers less than fixed daily retries. The method only works where the customer's payments to other merchants are visible, which is to say inside the payment network."
            />
            <Alert
              color="notice"
              emphasis="subtle"
              isFullWidth
              title="The harm-aware stopping rule almost never binds"
              description="Removing it changes nothing: with a 35% odds floor, the expected-value check only bites for very small eNACH dues. The large cut in bank charges comes from retrying on days the money is there, not from this rule. It stays in as a guard for small dues."
            />
            <Alert
              color="information"
              emphasis="subtle"
              isFullWidth
              title="A perfect reply parser adds little money"
              description="Replies matter for consent (stop, dispute, wrong number) and for routing hardship to a person, more than for the amount recovered. That is why the parser never decides an action on its own."
            />
          </Box>
        </Panel>
      ) : null}

      <Alert
        color="notice"
        isFullWidth
        title="Limits"
        description="The world is simulated. Income calendars, reply behaviour and top-ups are assumptions (tagged in calibration.py); failure codes, retry caps, notice rules and execution windows follow NPCI/RBI. Most of the gain over fixed daily retries comes from simply waiting for funds, which the salary-day heuristic also captures. Dobaara's own margin is the difference to that heuristic."
      />
    </Stack>
  )
}
