import type { ReactNode } from 'react'
import { EmptyState as SharedEmptyState } from '../components/ui'

export type TitleOption = { label: string; title: string; rationale: string }
export type DescriptionOption = { label: string; summary: string; text: string; paired_title?: string; notes?: string[] }
export type PersonaFocus = { persona: string; score: number; pain_point: string; emphasis: string[] }
export type RecommendedPackage = { name: string; price: number; delivery_days?: number | null; highlights?: string[] }
export type CompetitorRecommendation = {
  rank_position?: number
  competitor_title: string
  competitor_url?: string
  seller_name?: string
  matched_term?: string
  starting_price?: number | null
  rating?: number | null
  reviews_count?: number | null
  conversion_proxy_score?: number
  why_it_ranks?: string[]
  primary_recommendation?: string
  what_to_change?: string[]
  expected_gain?: number
  priority?: string
}

export function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>
}

export function MetaItem({ label, value }: { label: string; value: string }) {
  return <div className="meta-item"><span>{label}</span><strong>{value}</strong></div>
}

export function Block({
  title,
  body,
  action,
  busy,
}: {
  title: string
  body: string
  action: () => void
  busy: boolean
}) {
  return (
    <div className="block">
      <div>
        <p className="eyebrow">{title}</p>
        <strong>{body}</strong>
      </div>
      <button className="secondary" onClick={action} disabled={busy || isPlaceholderText(body)}>
        Queue
      </button>
    </div>
  )
}

export function shortDate(value?: string) {
  if (!value) return '--'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : `${parsed.getMonth() + 1}/${parsed.getDate()}`
}

export function pretty(value: string) {
  try {
    return JSON.stringify(JSON.parse(value), null, 2)
  } catch {
    return value
  }
}

export function human(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (match) => match.toUpperCase())
}

export function currency(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

export function isPlaceholderText(value: string) {
  const normalized = value.trim().toLowerCase()
  return !normalized || normalized === '--' || normalized.startsWith('no ')
}

export function percent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  return `${Math.round(Number(value) * 100)}%`
}

export function milliseconds(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value) || Number(value) <= 0) return '--'
  const numeric = Number(value)
  if (numeric >= 1000) {
    return `${(numeric / 1000).toFixed(1)}s`
  }
  return `${Math.round(numeric)}ms`
}

export function keywordDifficultyTone(value?: string) {
  const normalized = String(value ?? '').toLowerCase()
  if (normalized === 'low') return 'ok'
  if (normalized === 'medium') return 'queued'
  if (normalized === 'high') return 'warning'
  return 'pending'
}

export function displayDiffValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '--'
  }
  if (typeof value === 'string') {
    return value
  }
  return JSON.stringify(value, null, 2)
}

export function clamp(value: number) {
  return Math.max(12, Math.min(100, Math.round(value)))
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
}: {
  icon: string
  title: string
  hint?: string
  action?: ReactNode
}) {
  return <SharedEmptyState icon={icon} title={title} hint={hint} action={action} />
}
