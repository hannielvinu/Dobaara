import { Box, Card, CardBody, Heading, Skeleton, Text } from '@razorpay/blade/components'
import type { ReactNode } from 'react'

export function Panel({ title, subtitle, children, right }: { title: string; subtitle?: string; children: ReactNode; right?: ReactNode }) {
  return (
    <Card padding="spacing.5" elevation="lowRaised" borderRadius="large">
      <CardBody>
        <Box display="flex" justifyContent="space-between" alignItems="flex-start" gap="spacing.4" marginBottom="spacing.5" flexWrap="wrap">
          <Box>
            <Heading size="small">{title}</Heading>
            {subtitle ? (
              <Box marginTop="spacing.2">
                <Text size="small" color="surface.text.gray.muted">
                  {subtitle}
                </Text>
              </Box>
            ) : null}
          </Box>
          {right}
        </Box>
        {children}
      </CardBody>
    </Card>
  )
}

export function Kpi({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: 'positive' | 'negative' | 'neutral' }) {
  const color = tone === 'positive' ? 'feedback.text.positive.intense' : tone === 'negative' ? 'feedback.text.negative.intense' : 'surface.text.gray.normal'
  return (
    <Card padding="spacing.5" elevation="lowRaised" borderRadius="large">
      <CardBody>
        <Text size="small" color="surface.text.gray.muted" weight="medium">
          {label}
        </Text>
        <Box marginTop="spacing.3">
          <Heading size="large" color={color}>
            {value}
          </Heading>
        </Box>
        {note ? (
          <Box marginTop="spacing.2">
            <Text size="small" color="surface.text.gray.subtle">
              {note}
            </Text>
          </Box>
        ) : null}
      </CardBody>
    </Card>
  )
}

export function Loading() {
  return (
    <Box display="flex" flexDirection="column" gap="spacing.4">
      <Skeleton height="120px" borderRadius="medium" />
      <Skeleton height="320px" borderRadius="medium" />
    </Box>
  )
}

export function Stack({ children, gap = 'spacing.6' }: { children: ReactNode; gap?: 'spacing.3' | 'spacing.4' | 'spacing.5' | 'spacing.6' | 'spacing.7' }) {
  return (
    <Box display="flex" flexDirection="column" gap={gap}>
      {children}
    </Box>
  )
}

export function Muted({ children }: { children: ReactNode }) {
  return (
    <Text size="small" color="surface.text.gray.muted">
      {children}
    </Text>
  )
}

export function Chip({ children, tone }: { children: ReactNode; tone?: 'red' | 'green' | 'amber' | 'gray' }) {
  return <span className={`chip${tone ? ` ${tone}` : ''}`}>{children}</span>
}
