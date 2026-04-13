import type { BootstrapPayload, JobRun } from '../types'

export type AssistantMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  suggestions?: string[]
  pending?: boolean
  provider?: string
}

export type TimelineRecord = {
  id?: number
  created_at?: string
  keyword?: string
  optimization_score?: number
  keyword_score?: number
  competitor_count?: number
  keyword_difficulty?: string
  top_action?: string
  top_ranked_title?: string
  label: string
}

export type ComparisonDiff = {
  available: boolean
  summary: string
  left?: Record<string, unknown>
  right?: Record<string, unknown>
  changes: Array<{ label: string; before: unknown; after: unknown }>
}

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

export function splitTerms(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

export function textValue(value: unknown) {
  return typeof value === 'string' ? value : ''
}

export function numberValue(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

export function stringArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

export function recordValue(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

export function recordArray(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
    : []
}

export function shortDate(value?: string) {
  if (!value) return '--'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : `${parsed.getMonth() + 1}/${parsed.getDate()}`
}

export function currencyValue(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

export function clamp(value: number) {
  return Math.max(12, Math.min(100, Math.round(value)))
}

export function buildAssistantMessages(payload: BootstrapPayload) {
  const history = mapAssistantHistory(payload.assistant_history ?? recordArray(payload.memory?.assistant_history), payload)
  if (history.length) return history
  return [
    {
      id: 'assistant-seed',
      role: 'assistant' as const,
      text: 'Ask me anything about your live Fiverr market position. I answer from the current page-one leaderboard, your gig comparison, and your recent scraper feed.',
      suggestions: buildAssistantQuickPrompts(recordValue(payload.state.gig_comparison), recordValue(recordValue(payload.state.gig_comparison).implementation_blueprint), recordValue(payload.state.scraper_run)),
    },
  ]
}

export function mapAssistantHistory(items: Array<Record<string, unknown>>, payload: BootstrapPayload | null) {
  const quickPrompts = payload
    ? buildAssistantQuickPrompts(recordValue(payload.state.gig_comparison), recordValue(recordValue(payload.state.gig_comparison).implementation_blueprint), recordValue(payload.state.scraper_run))
    : []
  const mapped = [...items]
    .sort((left, right) => {
      const leftTime = Date.parse(textValue(left.created_at))
      const rightTime = Date.parse(textValue(right.created_at))
      if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime) && leftTime !== rightTime) {
        return leftTime - rightTime
      }
      return Number(left.id ?? 0) - Number(right.id ?? 0)
    })
    .map((item) => {
      const metadata = recordValue(item.metadata)
      return {
        id: textValue(item.id) || `${textValue(item.role) || 'assistant'}-${textValue(item.created_at) || Math.random().toString(36).slice(2, 8)}`,
        role: item.role === 'user' ? 'user' as const : 'assistant' as const,
        text: textValue(item.content).trim(),
        suggestions: item.role === 'assistant' ? stringArray(metadata.suggestions) : undefined,
        provider: item.role === 'assistant' ? textValue(metadata.provider) || undefined : undefined,
      }
    })
    .filter((item) => item.text)
  if (!mapped.length) return []
  const last = mapped[mapped.length - 1]
  if (last.role === 'assistant' && !last.suggestions?.length) {
    last.suggestions = quickPrompts
  }
  return mapped
}

export function buildAssistantQuickPrompts(
  comparison: Record<string, unknown>,
  blueprint: Record<string, unknown>,
  scraperRun: Record<string, unknown>,
) {
  const primaryTerm = textValue(comparison.primary_search_term).trim()
  const topGig = recordValue(comparison.top_ranked_gig)
  const topAction = recordValue(blueprint.top_action)
  const prompts = [
    primaryTerm ? `Why is #1 ranking for ${primaryTerm}?` : '',
    textValue(topGig.title) ? `How do I beat #1 ${textValue(topGig.seller_name) || 'competitor'}?` : '',
    textValue(blueprint.recommended_title) ? 'Rewrite my title using the current market demand.' : 'What title should I use now?',
    textValue(topAction.action_text) ? 'What should I do first and why?' : '',
    textValue(scraperRun.last_status_message) ? 'What is the live Fiverr feed showing right now?' : '',
    'How should I price my packages now?',
  ]
  return Array.from(new Set(prompts.filter(Boolean))).slice(0, 5)
}

export function buildComparisonTimeline(history: Array<Record<string, unknown>>): TimelineRecord[] {
  return history.map((item, index) => {
    const record = recordValue(item.result_json)
    const keyword = textValue(item.keyword) || textValue(record.primary_search_term)
    const createdAt = textValue(item.created_at)
    return {
      id: numberValue(item.id),
      created_at: createdAt,
      keyword,
      optimization_score: numberValue(item.score_after) ?? numberValue(record.optimization_score) ?? numberValue(item.optimization_score),
      keyword_score: numberValue(record.keyword_score) ?? numberValue(record.coverage_score),
      competitor_count: numberValue(record.competitor_count),
      keyword_difficulty: textValue(record.keyword_difficulty),
      top_action: textValue(record.top_action) || textValue(record.recommended_title),
      top_ranked_title: textValue(record.top_ranked_title),
      label: createdAt ? shortDate(createdAt) : `${index + 1}`,
    }
  })
}

export function buildComparisonDiff(history: Array<Record<string, unknown>>): ComparisonDiff {
  if (history.length < 2) {
    return { available: false, summary: 'Run another comparison to see what changed.', changes: [] }
  }
  const left = history[history.length - 2]
  const right = history[history.length - 1]
  const leftRecord = recordValue(left.result_json)
  const rightRecord = recordValue(right.result_json)
  const changes = [
    { label: 'Optimization score', before: left.score_after ?? leftRecord.optimization_score, after: right.score_after ?? rightRecord.optimization_score },
    { label: 'Competitor count', before: leftRecord.competitor_count, after: rightRecord.competitor_count },
    { label: 'Primary term', before: leftRecord.primary_search_term, after: rightRecord.primary_search_term },
    { label: 'Recommended title', before: leftRecord.recommended_title, after: rightRecord.recommended_title },
    { label: 'Top action', before: leftRecord.top_action, after: rightRecord.top_action },
  ].filter((item) => JSON.stringify(item.before) !== JSON.stringify(item.after))
  return {
    available: true,
    summary: changes.length ? 'The latest compare changed the items below.' : 'The last two compares were functionally similar.',
    left,
    right,
    changes,
  }
}

export function activeJob(jobRuns: JobRun[]) {
  return jobRuns.find((job) => ['queued', 'running'].includes(job.status)) ?? jobRuns[0]
}

export function buildKeywordScore(comparison: Record<string, unknown>, report: Record<string, unknown>) {
  const keywordQuality = recordValue(comparison.keyword_quality)
  const components = recordValue(keywordQuality.components)
  const numericComponents = Object.fromEntries(
    Object.entries(components).filter(([, value]) => typeof value === 'number'),
  ) as Record<string, number>
  return {
    enabled: Boolean(keywordQuality.enabled ?? textValue(comparison.primary_search_term)),
    keyword: textValue(keywordQuality.keyword) || textValue(comparison.primary_search_term),
    score: numberValue(keywordQuality.score) ?? numberValue(report.keyword_score),
    difficulty: textValue(keywordQuality.difficulty),
    summary: textValue(keywordQuality.summary),
    components: numericComponents,
  }
}

export function buildScraperSummary(comparison: Record<string, unknown>, scraperRun: Record<string, unknown>) {
  const summary = recordValue(comparison.scraper_summary)
  return {
    total_runs: numberValue(summary.total_runs) ?? (textValue(scraperRun.status) ? 1 : 0),
    success_rate: numberValue(summary.success_rate) ?? (textValue(scraperRun.status) === 'completed' ? 1 : 0),
    failure_rate: numberValue(summary.failure_rate) ?? (textValue(scraperRun.status) === 'failed' ? 1 : 0),
    avg_duration_ms: numberValue(summary.avg_duration_ms) ?? numberValue(scraperRun.duration_ms) ?? 0,
    last_success_at: textValue(summary.last_success_at) || textValue(scraperRun.completed_at),
    last_error: textValue(summary.last_error) || textValue(scraperRun.last_error),
  }
}

export function buildScraperLogs(comparison: Record<string, unknown>, scraperRun: Record<string, unknown>) {
  const source = recordArray(comparison.scraper_logs).length
    ? recordArray(comparison.scraper_logs)
    : recordArray(scraperRun.recent_events)

  return source.map((item, index) => ({
    id: numberValue(item.id) ?? index,
    keyword: textValue(item.keyword) || textValue(item.term),
    status: textValue(item.status) || textValue(item.level) || textValue(scraperRun.status),
    gigs_found: numberValue(item.gigs_found) ?? numberValue(scraperRun.total_results),
    duration_ms: numberValue(item.duration_ms),
    error_msg: textValue(item.error_msg) || textValue(item.message),
    meta_json: recordValue(item.meta_json),
    created_at: textValue(item.created_at) || textValue(item.timestamp),
    updated_at: textValue(item.updated_at) || textValue(item.timestamp),
  }))
}

export function buildConnectorHealth(connectors: unknown, fallback: unknown) {
  const source = recordArray(connectors).length ? recordArray(connectors) : recordArray(fallback)
  return source.map((item) => ({
    connector: textValue(item.connector) || textValue(item.name) || 'connector',
    detail: textValue(item.detail) || textValue(item.message) || '--',
    status: textValue(item.status) || 'queued',
  }))
}

export function fileToBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result ?? '')
      const commaIndex = result.indexOf(',')
      resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result)
    }
    reader.onerror = () => reject(reader.error ?? new Error('Unable to read file.'))
    reader.readAsDataURL(file)
  })
}
