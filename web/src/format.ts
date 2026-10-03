const inrFmt = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export const inr = (v: number) => `₹${inrFmt.format(Math.round(v))}`

/** ₹ in lakh / crore, the way Indian finance teams read large numbers. */
export function inrShort(v: number): string {
  const a = Math.abs(v)
  const sign = v < 0 ? '−' : ''
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(2)} Cr`
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(2)} L`
  return `${sign}₹${inrFmt.format(Math.round(a))}`
}

export const pct = (v: number, digits = 1) => `${(v * 100).toFixed(digits)}%`
export const num = (v: number) => inrFmt.format(Math.round(v))

export function time(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' })
}

export function dayOffset(fromIso: string, toIso: string): string {
  const days = (new Date(toIso).getTime() - new Date(fromIso).getTime()) / 86400000
  return `D+${Math.floor(days + 1e-6)}`
}
