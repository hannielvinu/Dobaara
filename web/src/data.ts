import { useEffect, useState } from 'react'

export type ArmName = 'do_nothing' | 'naive' | 'calendar' | 'dobaara'

export type ArmMetrics = {
  cases: number
  due_inr: number
  recovered_inr: number
  recovery_rate_count: number
  recovery_rate_value: number
  customer_bounce_charges_inr: number
  outreach_per_case: number
  notices_per_case: number
  debit_retries_per_case: number
  cancel_rate: number
  escalation_rate: number
  median_days_to_recover: number | null
  blocked_by_gate: number
  recovered_via: Record<string, number>
}

export type Uplift = { total: number; ci95: [number, number]; per_1000_cases: number }

export type Experiment = {
  arms: Record<ArmName, ArmMetrics>
  uplift: Record<string, Uplift>
  harm_delta: Record<string, Uplift>
  recovery_rate_by_failure_class: Record<string, Record<ArmName, number>>
  compliance: Record<ArmName, { violations: number; actions_checked: number; chain_ok: boolean }>
  payday_inference: Record<'with_network' | 'merchant_only', { customers: number; mae_days: number; within_1_day: number; within_3_days: number }>
  seeds: number[]
  cases_per_seed: number
  calibration: string
  parser: { name: string; promise_date_exact: number }
}

export type SensitivityCell = {
  value: number
  uplift_per_1000: number
  uplift_ci95_per_1000: [number, number]
  harm_delta_per_1000: number
  dobaara_beats_naive: boolean
}

export type ReplyScore = {
  n: number
  accuracy: number
  macro_f1: number
  promise_date_exact: number | null
  ungrounded_rate: number
  per_intent: Record<string, { precision: number; recall: number; f1: number; support: number }>
  confusion: Record<string, Record<string, number>>
}

export type Results = {
  experiment: { test: Experiment | null; shifted: Experiment | null; dev: Experiment | null }
  sensitivity: Record<string, SensitivityCell[]> | null
  ablations: Record<string, { uplift_vs_naive: Uplift; harm_delta_vs_naive: Uplift; dobaara_recovery_rate_value: number }> | null
  replies: {
    baseline_dev: ReplyScore | null
    baseline_dev_v1: ReplyScore | null
    baseline_heldout: ReplyScore | null
    llm_heldout: ReplyScore | null
    examples: { id: string; text: string; sent: string; gold: string; gold_date: string | null; pred: string; pred_date: string | null }[]
  }
  rules: { id: string; text: string; source: string }[]
  codes: { source_system: string; code: string; description: string; cls: string; source: string; verified: boolean }[]
}

export type LedgerRecord = {
  seq: number
  at: string
  case_id: string
  event: string
  data: Record<string, unknown>
  prev_hash: string
  hash: string
}

export type CaseOutcome = {
  recovered: boolean
  recovered_via: string
  days_to_recover: number | null
  bounce_cost: number
  outreach: number
  notices: number
  debits: number
  cancelled: boolean
  escalated: boolean
  blocked: number
  replies: number
}

export type CaseStory = {
  case_id: string
  story: string
  rail: 'upi_autopay' | 'enach'
  amount: number
  failure_code: string
  failure_class: string
  failed_at: string
  payday_kind: string
  true_payday: number | null
  estimated_payday: number
  bounce_charge: number
  curve: number[]
  arms: Record<'naive' | 'calendar' | 'dobaara', { outcome: CaseOutcome; timeline: LedgerRecord[] }>
}

function useJson<T>(path: string): T | null {
  const [data, setData] = useState<T | null>(null)
  useEffect(() => {
    let alive = true
    fetch(path)
      .then((r) => r.json())
      .then((j) => alive && setData(j as T))
      .catch(() => alive && setData(null))
    return () => {
      alive = false
    }
  }, [path])
  return data
}

export const useResults = () => useJson<Results>('./data/results.json')
export const useCases = () => useJson<CaseStory[]>('./data/cases.json')

export const ARM_LABEL: Record<ArmName, string> = {
  do_nothing: 'Do nothing',
  naive: 'Fixed daily retries',
  calendar: 'Salary-day heuristic',
  dobaara: 'Dobaara',
}

export const CLASS_LABEL: Record<string, string> = {
  insufficient_funds: 'Insufficient funds',
  technical: 'Bank / PSP technical',
  mandate_inactive: 'Mandate revoked / paused',
  limit_exceeded: 'Limit exceeded',
  account_blocked: 'Account blocked / closed',
  risk_decline: 'Issuer risk decline',
  unknown: 'Unrecognised code',
}
