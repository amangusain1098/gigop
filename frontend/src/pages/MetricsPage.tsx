import { ResponsiveContainer, LineChart, CartesianGrid, XAxis, YAxis, Tooltip, Line, RadarChart, PolarGrid, PolarAngleAxis, Radar } from 'recharts'
import type { MetricsPageProps } from './shared'
import { MetaItem, currency, human, keywordDifficultyTone, milliseconds, percent, shortDate } from './shared'

export default function MetricsPage({
  metricsHistory,
  radar,
  competitorCount,
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
          <div className="card-head"><h2>Market score radar</h2><span>{competitorCount} competitors</span></div>
          <div className="chart-shell">
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={radar}>
                <PolarGrid stroke="rgba(102,124,153,0.22)" />
                <PolarAngleAxis dataKey="name" stroke="#7b91ad" />
                <Radar dataKey="value" stroke="#49b3ff" fill="#49b3ff" fillOpacity={0.3} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Keyword quality</h2><span className={`status status--${keywordDifficultyTone(keywordScore.difficulty)}`}>{keywordScore.difficulty || 'unknown'}</span></div>
          <div className="meta-grid">
            <MetaItem label="Keyword" value={keywordScore.keyword || primarySearchTerm || '--'} />
            <MetaItem label="Score" value={String(keywordScore.score ?? '--')} />
            <MetaItem label="Competitors found" value={String(competitorCount)} />
            <MetaItem label="Market anchor" value={currency(marketAnchorPrice)} />
          </div>
          <p className="inline-note">{keywordScore.summary || 'Run a compare to score the current keyword.'}</p>
          <div className="pill-row">
            {Object.entries(keywordScore.components ?? {}).map(([label, value]) => (
              <span className="pill" key={label}>{human(label)}: {String(value)}</span>
            ))}
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>Scraper visibility</h2><span>{scraperSummary.total_runs ?? 0} tracked runs</span></div>
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
            )) : <p className="inline-note">No scraper log rows yet. Run a live market compare to start building visibility history.</p>}
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Keyword pulse</h2><span>{trendingQueries.length}</span></div>
          <div className="pill-row">{trendingQueries.map((item) => <span className="pill" key={item}>{item}</span>)}</div>
          <h3>Top live search titles</h3>
          <ul className="bullet-list">{topSearchTitles.map((item) => <li key={item}>{item}</li>)}</ul>
        </article>
        <article className="card">
          <div className="card-head"><h2>System health</h2></div>
          <div className="table">{connectorHealth.map((item) => <div className="row" key={item.connector}><div><strong>{item.connector}</strong><p>{item.detail}</p></div><span className={`status status--${item.status}`}>{item.status}</span></div>)}</div>
        </article>
      </section>
    </>
  )
}
