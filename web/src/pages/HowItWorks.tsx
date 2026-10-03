import { Box, Heading, Link, Text } from '@razorpay/blade/components'
import { Panel, Stack } from '../ui'

function Node({ x, y, w, title, sub, kind }: { x: number; y: number; w: number; title: string; sub: string; kind: 'rule' | 'model' | 'ai' | 'io' }) {
  const fill = { rule: '#eef2ff', model: '#e7f6ee', ai: '#fff4e0', io: '#f2f4f8' }[kind]
  const stroke = { rule: '#305eff', model: '#12a15e', ai: '#e08700', io: '#98a2b3' }[kind]
  return (
    <g>
      <rect x={x} y={y} width={w} height={58} rx={10} fill={fill} stroke={stroke} strokeWidth={1.5} />
      <text x={x + w / 2} y={y + 25} textAnchor="middle" fontSize={13} fontWeight={600} fill="#1b2640" fontFamily="Inter">
        {title}
      </text>
      <text x={x + w / 2} y={y + 43} textAnchor="middle" fontSize={11} fill="#51607a" fontFamily="Inter">
        {sub}
      </text>
    </g>
  )
}

const Arrow = ({ d }: { d: string }) => <path d={d} stroke="#98a2b3" strokeWidth={1.5} fill="none" markerEnd="url(#arr)" />

export default function HowItWorks() {
  return (
    <Stack>
      <Panel title="Architecture" subtitle="Blue: deterministic rules. Green: small statistical model. Amber: LLM, only for free text, and never with the last word.">
        <div className="scroll-x">
          <svg viewBox="0 0 1060 360" style={{ width: '100%', minWidth: 860 }} role="img" aria-label="Dobaara architecture diagram">
            <defs>
              <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 0L10 5L0 10z" fill="#98a2b3" />
              </marker>
            </defs>
            <Node x={10} y={30} w={190} title="Razorpay webhook" sub="payment.failed (recurring)" kind="io" />
            <Node x={240} y={30} w={190} title="Failure-code table" sub="NPCI / Razorpay code → class" kind="rule" />
            <Node x={470} y={30} w={210} title="Recovery policy" sub="proposes actions + rule ids" kind="rule" />
            <Node x={720} y={30} w={170} title="Compliance gate" sub="10 rules, veto power" kind="rule" />
            <Node x={920} y={30} w={130} title="Execute" sub="link / notice / debit" kind="io" />

            <Node x={470} y={150} w={210} title="Payday model" sub="kernel-smoothed success by day" kind="model" />
            <Node x={240} y={150} w={190} title="Network history" sub="payments across merchants" kind="io" />
            <Node x={470} y={270} w={210} title="Reply parser" sub="keyword baseline · Claude" kind="ai" />
            <Node x={240} y={270} w={190} title="Customer reply" sub="Hinglish / Hindi / English" kind="io" />
            <Node x={720} y={150} w={170} title="Hash-chained ledger" sub="every proposal & outcome" kind="rule" />
            <Node x={720} y={270} w={170} title="Independent verifier" sub="re-derives every rule" kind="rule" />
            <Node x={920} y={150} w={130} title="Human queue" sub="dispute · hardship" kind="io" />

            <Arrow d="M200 59H236" />
            <Arrow d="M430 59H466" />
            <Arrow d="M680 59H716" />
            <Arrow d="M890 59H916" />
            <Arrow d="M430 179H466" />
            <Arrow d="M575 150V92" />
            <Arrow d="M430 299H466" />
            <Arrow d="M575 270C575 230 575 120 575 92" />
            <Arrow d="M805 88V146" />
            <Arrow d="M805 208V266" />
            <Arrow d="M890 179H916" />
          </svg>
        </div>
      </Panel>

      <div className="grid grid-3">
        <Panel title="Where AI is used" subtitle="and where it deliberately isn't">
          <table className="tbl">
            <tbody>
              <tr>
                <td>Failure code → cause</td>
                <td>lookup table</td>
              </tr>
              <tr>
                <td>Compliance</td>
                <td>coded rules + verifier</td>
              </tr>
              <tr>
                <td>When to retry</td>
                <td>small explainable model</td>
              </tr>
              <tr>
                <td>Retry or not (eNACH)</td>
                <td>expected value vs bank charge (rarely binds; see ablations)</td>
              </tr>
              <tr>
                <td>What the customer said</td>
                <td>
                  <b>LLM</b> (or keywords if they're as good)
                </td>
              </tr>
              <tr>
                <td>What to do about it</td>
                <td>deterministic table</td>
              </tr>
            </tbody>
          </table>
        </Panel>
        <Panel title="Every money action is bounded" subtitle="What the system can never do">
          <Stack gap="spacing.3">
            <Text size="small">• Debit more than the amount due or the mandate's maximum</Text>
            <Text size="small">• Debit without a pre-debit notice 24 hours ahead</Text>
            <Text size="small">• Retry more than 3 times, or outside NPCI execution windows</Text>
            <Text size="small">• Contact a customer after cancel, dispute or "wrong number"</Text>
            <Text size="small">• Debit after "I already paid" until a person reconciles</Text>
            <Text size="small">• Run against live keys: rzp_live_ is refused at start-up</Text>
          </Stack>
        </Panel>
        <Panel title="Why Razorpay" subtitle="What only a payment network can do">
          <Stack gap="spacing.3">
            <Text size="small">
              Payday inference from one merchant's history is off by ~4 days. With the customer's payments across merchants it is off by under
              a day. That signal exists only at the network level.
            </Text>
            <Text size="small">
              Built on Razorpay rails: payment.failed webhooks, Payment Links for no-bounce UPI collection, and recurring charges on existing
              tokens, all in test mode.
            </Text>
          </Stack>
        </Panel>
      </div>

      <Box>
        <Heading size="small">Source, data and reproduction</Heading>
        <Box marginTop="spacing.2">
          <Text size="small" color="surface.text.gray.muted">
            Every number on this site is produced by <code>make eval</code> from the repository.{' '}
            <Link href="https://github.com/hannielvinu/Dobaara" target="_blank">
              github.com/hannielvinu/Dobaara
            </Link>
          </Text>
        </Box>
      </Box>
    </Stack>
  )
}
