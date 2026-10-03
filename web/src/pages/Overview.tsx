import {
  Alert,
  Box,
  ChartBar,
  ChartBarWrapper,
  ChartCartesianGrid,
  ChartTooltip,
  ChartXAxis,
  ChartYAxis,
  Display,
  Link,
  Text,
} from '@razorpay/blade/components'
import { ARM_LABEL, CLASS_LABEL, type ArmName, type Results } from '../data'
import { inrShort, num, pct } from '../format'
import { Kpi, Loading, Panel, Stack } from '../ui'

const ARMS: ArmName[] = ['do_nothing', 'naive', 'calendar', 'dobaara']

export default function Overview({ results }: { results: Results | null }) {
  const t = results?.experiment.test
  if (!results || !t) return <Loading />

  const d = t.arms.dobaara
  const cal = t.arms.calendar
  const nv = t.arms.naive
  const upCal = t.uplift.dobaara_vs_calendar
  const upNaive = t.uplift.dobaara_vs_naive
  const harmCut = 1 - d.customer_bounce_charges_inr / nv.customer_bounce_charges_inr
  const harmCutCal = 1 - d.customer_bounce_charges_inr / cal.customer_bounce_charges_inr
  const checked = Object.values(t.compliance).reduce((s, c) => s + c.actions_checked, 0)
  const violations = Object.values(t.compliance).reduce((s, c) => s + c.violations, 0)
  const n = t.cases_per_seed * t.seeds.length
  const net = t.payday_inference.with_network
  const own = t.payday_inference.merchant_only

  const recoveryData = ARMS.map((a) => ({ policy: ARM_LABEL[a], recovered: Math.round(t.arms[a].recovery_rate_value * 1000) / 10 }))
  const harmData = ARMS.filter((a) => a !== 'do_nothing').map((a) => ({
    policy: ARM_LABEL[a],
    charges: Math.round((t.arms[a].customer_bounce_charges_inr / n) * 1000),
  }))

  return (
    <Stack>
      <div style={{ borderRadius: 16, padding: 32, background: 'linear-gradient(120deg, #0b1530 0%, #14286b 55%, #305eff 120%)' }}>
        <Text size="small" weight="semibold" color="surface.text.staticWhite.normal">
          HELD-OUT TEST · {num(n)} FAILED DEBITS · 10 SEEDS
        </Text>
        <Box marginTop="spacing.4" maxWidth="900px">
          <Display size="medium" color="surface.text.staticWhite.normal">
            {inrShort(upCal.per_1000_cases)} more recovered per 1,000 failed debits
          </Display>
        </Box>
        <Box marginTop="spacing.4" maxWidth="820px">
          <Text size="large" color="surface.text.staticWhite.subtle">
            compared with retrying on salary days, and {inrShort(upNaive.per_1000_cases)} more than fixed daily retries, while charging
            customers {pct(harmCut, 0)} less in bank bounce fees. {num(checked)} actions checked by an independent verifier:{' '}
            {violations} compliance violations.
          </Text>
        </Box>
      </div>

      <div className="grid grid-4">
        <Kpi
          label="Value recovered"
          value={pct(d.recovery_rate_value)}
          tone="positive"
          note={`vs ${pct(cal.recovery_rate_value)} salary-day · ${pct(nv.recovery_rate_value)} daily retries`}
        />
        <Kpi
          label="Uplift vs salary-day heuristic"
          value={inrShort(upCal.total)}
          note={`95% CI ${inrShort(upCal.ci95[0])} – ${inrShort(upCal.ci95[1])} on ${num(n)} cases`}
          tone="positive"
        />
        <Kpi
          label="Bounce charges to customers"
          value={`−${pct(harmCut, 0)}`}
          note={`vs daily retries; −${pct(harmCutCal, 0)} vs salary-day`}
          tone="positive"
        />
        <Kpi label="Compliance violations" value={String(violations)} note={`${num(checked)} actions re-checked from the audit log`} />
      </div>

      <div className="grid grid-2">
        <Panel title="Share of money due that was recovered" subtitle="30-day window, same customers in every arm">
          <ChartBarWrapper data={recoveryData} height="280px">
            <ChartCartesianGrid />
            <ChartXAxis dataKey="policy" />
            <ChartYAxis />
            <ChartTooltip />
            <ChartBar dataKey="recovered" name="Recovered (%)" color="data.background.categorical.blue.moderate" />
          </ChartBarWrapper>
        </Panel>
        <Panel title="Bank bounce charges paid by customers" subtitle="₹ per 1,000 failed debits (failed eNACH retries cost ₹295–590 each)">
          <ChartBarWrapper data={harmData} height="280px">
            <ChartCartesianGrid />
            <ChartXAxis dataKey="policy" />
            <ChartYAxis />
            <ChartTooltip />
            <ChartBar dataKey="charges" name="₹ per 1,000 cases" color="data.background.categorical.red.moderate" />
          </ChartBarWrapper>
        </Panel>
      </div>

      <div className="grid grid-3">
        <Panel title="Why this belongs inside Razorpay" subtitle="Estimating each customer's payday">
          <Stack gap="spacing.4">
            <Box>
              <Text size="small" color="surface.text.gray.muted">
                One merchant's own debit history
              </Text>
              <Text size="large" weight="semibold">
                ±{own.mae_days.toFixed(1)} days · {pct(own.within_1_day, 0)} within a day
              </Text>
            </Box>
            <Box>
              <Text size="small" color="surface.text.gray.muted">
                Plus the customer's payments across the network
              </Text>
              <Text size="large" weight="semibold" color="feedback.text.positive.intense">
                ±{net.mae_days.toFixed(1)} days · {pct(net.within_1_day, 0)} within a day
              </Text>
            </Box>
            <Text size="small" color="surface.text.gray.subtle">
              A single merchant can't see when a customer's other payments succeed. Razorpay can.
            </Text>
          </Stack>
        </Panel>
        <Panel title="Human in the loop" subtitle="What goes to a person instead of an automated action">
          <Stack gap="spacing.3">
            <Text size="large" weight="semibold">
              {pct(d.escalation_rate)} of cases
            </Text>
            <Text size="small" color="surface.text.gray.subtle">
              Disputes, hardship, "I already paid", risk declines and unrecognised codes are routed to a person. That load is a cost,
              and it is counted, not hidden.
            </Text>
            <Text size="small" color="surface.text.gray.subtle">
              Messages per case: {d.outreach_per_case.toFixed(2)} vs {nv.outreach_per_case.toFixed(2)} for daily retries. Cancellations:{' '}
              {pct(d.cancel_rate)} vs {pct(nv.cancel_rate)}.
            </Text>
          </Stack>
        </Panel>
        <Panel title="Recovery by failure type" subtitle="Dobaara vs salary-day heuristic">
          <table className="tbl">
            <tbody>
              {Object.entries(t.recovery_rate_by_failure_class).map(([cls, r]) => (
                <tr key={cls}>
                  <td>{CLASS_LABEL[cls] ?? cls}</td>
                  <td className="num">{pct(r.dobaara, 0)}</td>
                  <td className="num" style={{ color: '#6b7a99' }}>
                    {pct(r.calendar, 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>

      <Alert
        color="information"
        title="What these numbers are, and are not"
        isFullWidth
        description={
          <>
            They come from a simulator with common random numbers, calibrated where public figures exist and tagged "assumption" where
            they don't. The arms, metrics and splits were fixed in a pre-registered plan before any experiment code was written, and the
            test split was run once. The sensitivity grid shows where Dobaara stops winning.{' '}
            <Link href="https://github.com/hannielvinu/Dobaara/blob/main/METRICS_PLAN.md" target="_blank">
              Read the metrics plan
            </Link>
          </>
        }
      />
    </Stack>
  )
}
