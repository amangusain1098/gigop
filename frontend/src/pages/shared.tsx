import type { ReactNode } from 'react'

import type {
  ComparisonDiffPayload,
  ComparisonTimelinePoint,
  CompetitorRecord,
  DatasetRecord,
  FailedLoginAttemptRecord,
  JobRun,
  KeywordScore,
  MetricHistoryPoint,
  QueueRecord,
  ScraperLogRecord,
  ScraperSummary,
} from '../types'

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

export interface DashboardHeroMetric {
  label: string
  value: string
}

export interface ExtensionInstallView {
  apiBaseUrl: string
  tokenConfigured: boolean
  apiToken: string
  downloadUrl: string
  guideUrl: string
}

export interface HostingerView {
  status?: string
  configured?: boolean
  projectName?: string
  domain?: string
  selectedVm?: string
  lastCheckedAt?: string
  errorMessage?: string
  metrics: string
  projectLogs: Array<{ id: string; message: string; timestamp: string }>
}

export interface DashboardPageProps {
  heroMetrics: DashboardHeroMetric[]
  scraperStatus: string
  competitorCount: number
  pageOneCount: number
  lastRunMessage: string
  dataLoaded: boolean
  shouldShowExtensionPrompt: boolean
  extensionInstall: ExtensionInstallView
  onCopyExtensionToken: (token: string) => Promise<void>
  onDismissExtensionPrompt: () => void
  comparisonStatus: string
  topRankedGig: {
    title: string
    sellerName: string
    rank: string
    price?: number | null
    reviews: string
    term: string
  }
  topRankedReasons: string[]
  whyCompetitorsWin: string[]
  myGigTitle: string
  myGigPrice?: number | null
  myGigReviews: string
  marketAnchorPrice?: number | null
  detectedTerms: string[]
  titlePatterns: string[]
  whatToImplement: string[]
  doThisFirst: string[]
  failedLoginAttempts: FailedLoginAttemptRecord[]
  onReviewSecurityAttempt: (attemptId: string, action: 'save' | 'discard') => Promise<void>
  busy: string
  currentGigUrl: string
  currentTerms: string
  topTrackedGigTitle: string
}

export interface GigOptimizerPageProps {
  liveMode: boolean
  onSetLiveMode: (value: boolean) => void
  gigUrl: string
  onGigUrlChange: (value: string) => void
  terms: string
  onTermsChange: (value: string) => void
  manualInput: string
  onManualInputChange: (value: string) => void
  busy: string
  onRunJob: (jobType: string, payload?: Record<string, unknown>) => Promise<void>
  maxResults: number
  onMaxResultsChange: (value: number) => void
  autoCompareEnabled: boolean
  onToggleAutoCompare: () => void
  autoCompareMinutes: number
  onAutoCompareMinutesChange: (value: number) => void
  onSaveMarketplaceSettings: () => Promise<void>
  onRunNotificationTest: (channel: 'slack') => Promise<void>
  slackConfigured: boolean
  recommendedTitle: string
  recommendedTags: string[]
  titleOptions: TitleOption[]
  descriptionBlueprint: string[]
  descriptionFull?: string
  descriptionOptions: DescriptionOption[]
  pricingStrategy: string[]
  recommendedPackages: RecommendedPackage[]
  trustBoosters: string[]
  faqRecommendations: string[]
  personaFocus: PersonaFocus[]
  onQueueRecommendation: (actionType: string, proposedValue: unknown) => Promise<void>
  onOpenAIBrain: () => void
}

export interface CompetitorPageProps {
  pageOneTopTen: CompetitorRecord[]
  oneByOne: CompetitorRecommendation[]
  comparisonMessage: string
  competitors: CompetitorRecord[]
  sortKey: 'rank_position' | 'conversion_proxy_score' | 'reviews_count' | 'starting_price'
  onSortKeyChange: (value: 'rank_position' | 'conversion_proxy_score' | 'reviews_count' | 'starting_price') => void
  timeline: ComparisonTimelinePoint[]
  timelineChart: Array<ComparisonTimelinePoint & { label: string }>
  comparisonDiff: ComparisonDiffPayload
}

export interface MetricsPageProps {
  metricsHistory: MetricHistoryPoint[]
  radar: Array<{ name: string; value: number }>
  competitorCount: number
  keywordScore: KeywordScore
  primarySearchTerm: string
  marketAnchorPrice?: number | null
  scraperSummary: ScraperSummary
  scraperLogs: ScraperLogRecord[]
  trendingQueries: string[]
  topSearchTitles: string[]
  connectorHealth: Array<Record<string, string>>
}

export interface SettingsPageProps {
  knowledgeFile: File | null
  onKnowledgeFileChange: (file: File | null) => void
  onUploadDataset: () => Promise<void>
  datasets: DatasetRecord[]
  busy: string
  onDeleteDataset: (documentId: string) => Promise<void>
  onAskCopilotAboutDataset: (filename: string) => Promise<void>
  memoryDocuments: Array<{ id: string; filename: string; preview: string }>
  copilotTraining: {
    status: string
    trainExamples: number
    holdoutExamples: number
    preferenceExamples: number
    positiveFeedback: number
    recentTopics: string[]
  }
  onRunCopilotTrainingExport: () => Promise<void>
  onAskCopilotLearned: () => Promise<void>
  n8nProvider: string
  n8nWebhookUrl: string
  latestAssistantTimestamp: string
  queue: QueueRecord[]
  selectedQueue: QueueRecord | null
  onReviewQueue: (recordId: string, action: 'approve' | 'reject') => Promise<void>
  activeJob: JobRun | null
  jobRuns: JobRun[]
  hostinger: HostingerView
  onRefreshHostinger: () => Promise<void>
}

export interface CopilotPageProps {
  sessionId: string | null
  messages: Array<{
    id?: number
    role: 'user' | 'assistant'
    text: string
    suggestions?: string[]
    feedbackRating?: number | null
    createdAt?: string
  }>
  busy: boolean
  waitingForFirstChunk: boolean
  input: string
  onInputChange: (value: string) => void
  onSendMessage: (prefill?: string) => Promise<void>
  onExportChat: () => void
  onSendFeedback: (messageId: number, rating: 1 | -1) => Promise<void>
  quickPrompts: string[]
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
  return (
    <div className="empty-state">
      <div className="empty-state__icon" aria-hidden="true">{icon}</div>
      <strong className="empty-state__title">{title}</strong>
      {hint ? <p className="empty-state__hint">{hint}</p> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  )
}

export function clamp(value: number) {
  return Math.max(12, Math.min(100, Math.round(value)))
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

export function isPlaceholderText(value: string) {
  const normalized = value.trim().toLowerCase()
  return !normalized || normalized === '--' || normalized.startsWith('no ')
}
