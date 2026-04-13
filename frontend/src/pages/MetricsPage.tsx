import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { MetricHistoryPoint } from '../types'
import { EmptyState, MetaItem, keywordDifficultyTone, milliseconds, percent, shortDate } from './helpers'

interface KeywordScoreData {
  enabled: boolean
  keyword?: string
  score?: number
  difficulty?: string
  summary?: string
  components?: Record<string, number>
}

interface ScraperLogRecord {
  id: number
  keyword?: string
  status?: string
  gigs_found?: number | null
  duration_ms?: number | null
  error_msg?: string
  meta_json?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

interface ScraperSummary {
  total_runs: number
  success_rate: number
  failure_rate: number
  avg_duration_ms: number
  last_success_at?: string
  last_error?: string
}

interface MetricsPageProps {
  metricsHistory: MetricHistoryPoint[]
  keywordScore: KeywordScoreData
  primarySearchTerm: string
  marketAnchorPrice: string
  scraperSummary: ScraperSummary
  scraperLogs: ScraperLogRecord[]
  trendingQueries: string[]
  topSearchTitles: string[]
  connectorHealth: Array<Record<string, string>>
}

export default function MetricsPage({
  metricsHistory,
  keywordScore,
  primarySearchTerm,
  marketAnchorPrice,
  scraperSummary,
  scraperLogs,
  trendingQueries,
  topSearchTitles,
  connectorHealth,
}: MetricsPageProps) {
  return (
    <>
      <section className="charts">
        <article className="card">
          <div className="card-head"><h2>Live metrics</h2><span>{metricsHistory.length} points</span></div>
          <div className="chart-shell">
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={metricsHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(102,124,153,0.2)" />
                <XAxis dataKey="timestamp" tickFormatter={shortDate} stroke="#7b91ad" />
                <YAxis stroke="#7b91ad" />
                <Tooltip labelFormatter={(label) => shortDate(String(label ?? ''))} />
                <Line dataKey="impressions" stroke="#49b3ff" strokeWidth={2.5} dot={false} />
                <Line dataKey="ctr" stroke="#ff9966" strokeWidth={2.5} dot={false} />
                <Line dataKey="conversion_rate" stroke="#5ed1a3" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>Keyword quality</h2><span className={`status status--${keywordDifficultyTone(keywordScore.difficulty)}`}>{keywordScore.difficulty || 'unknown'}</span></div>
          <div className="meta-grid">
            <MetaItem label="Keyword" value={keywordScore.keyword || primarySearchTerm || '--'} />
            <MetaItem label="Score" value={String(keywordScore.score ?? '--')} />
            <MetaItem label="Market anchor" value={marketAnchorPrice} />
            <MetaItem label="Enabled" value={keywordScore.enabled ? 'Yes' : 'No'} />
          </div>
          <p className="inline-note">{keywordScore.summary || 'Run a compare to score the current keyword.'}</p>
          <div className="pill-row">
            {Object.entries(keywordScore.components ?? {}).map(([label, value]) => (
              <span className="pill" key={label}>{label}: {String(value)}</span>
            ))}
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Scraper status</h2><span>{scraperSummary.total_runs ?? 0} tracked runs</span></div>
          <div className="meta-grid">
            <MetaItem label="Success rate" value={percent(scraperSummary.success_rate)} />
            <MetaItem label="Failure rate" value={percent(scraperSummary.failure_rate)} />
            <MetaItem label="Avg duration" value={milliseconds(scraperSummary.avg_duration_ms)} />
            <MetaItem label="Last success" value={scraperSummary.last_success_at ? shortDate(scraperSummary.last_success_at) : '--'} />
          </div>
          {scraperSummary.last_error ? <p className="inline-note">{scraperSummary.last_error}</p> : null}
          <div className="table">
            {scraperLogs.length ? scraperLogs.slice(0, 6).map((item) => (
              <div className="row row--stacked" key={`${item.id}-${item.updated_at ?? item.created_at ?? ''}`}>
                <div className="row-topline">
                  <strong>{item.keyword || 'marketplace scrape'}</strong>
                  <span className={`status status--${item.status || 'queued'}`}>{item.status || 'unknown'}</span>
                </div>
                <p>{String(item.meta_json?.last_message ?? item.error_msg ?? 'No status message captured yet.')}</p>
                <div className="row-metrics">
                  <span>{item.gigs_found ?? 0} gigs</span>
                  <span>{milliseconds(item.duration_ms)}</span>
                  <span>{item.updated_at ? shortDate(item.updated_at) : '--'}</span>
                </div>
              </div>
            )) : (
              <EmptyState icon="🛰️" title="No scraper history yet" hint="Run a live market compare to start building scraper visibility." />
            )}
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>Keyword pulse</h2><span>{trendingQueries.length}</span></div>
          <div className="pill-row">{trendingQueries.map((item) => <span className="pill" key={item}>{item}</span>)}</div>
          <h3>Top live search titles</h3>
          {topSearchTitles.length ? (
            <ul className="bullet-list">
              {topSearchTitles.map((item) => <li key={item}>{item}</li>)}
            </ul>
          ) : (
            <EmptyState icon="📈" title="No live search titles yet" hint="Run a compare to capture the current market phrasing." />
          )}
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Connector health</h2><span>{connectorHealth.length}</span></div>
          <div className="table">
            {connectorHealth.length ? connectorHealth.map((item) => (
              <div className="row" key={item.connector}>
                <div>
                  <strong>{item.connector}</strong>
                  <p>{item.detail}</p>
                </div>
                <span className={`status status--${item.status}`}>{item.status}</span>
              </div>
            )) : (
              <EmptyState icon="⚙️" title="No connector health yet" hint="Connector status will appear here after bootstrap data loads." />
            )}
          </div>
        </article>
      </section>
    </>
  )
}
