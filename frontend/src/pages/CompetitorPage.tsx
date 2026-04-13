import { ResponsiveContainer, LineChart, CartesianGrid, XAxis, YAxis, Tooltip, Line } from 'recharts'
import type { CompetitorPageProps } from './shared'
import { currency, displayDiffValue } from './shared'

export default function CompetitorPage({
  pageOneTopTen,
  oneByOne,
  comparisonMessage,
  competitors,
  sortKey,
  onSortKeyChange,
  timeline,
  timelineChart,
  comparisonDiff,
}: CompetitorPageProps) {
  return (
    <>
      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Top 10 gigs on Fiverr page one</h2><span>{pageOneTopTen.length}</span></div>
          <div className="table">
            {pageOneTopTen.length ? pageOneTopTen.map((item) => (
              <div className="row row--stacked" key={`${item.url}-${item.rank_position ?? item.title}`}>
                <div className="row-topline">
                  <span className="rank-badge">#{item.rank_position ?? '?'}</span>
                  <strong>{item.title}</strong>
                  <span className={`status status--${item.is_first_page ? 'ok' : 'queued'}`}>
                    {item.is_first_page ? 'page 1' : 'tracked'}
                  </span>
                </div>
                <p className="row-seller">{item.seller_name || 'Unknown seller'} {(item.badges ?? []).join(' · ')}</p>
                <p>{(item.why_on_page_one ?? item.win_reasons ?? []).join(' ') || 'No ranking reasons captured yet.'}</p>
                <div className="row-metrics">
                  <span>{currency(item.starting_price)}</span>
                  <span>{item.rating ?? '--'} ★ ({item.reviews_count ?? 0})</span>
                  <span>{item.delivery_days ? `${item.delivery_days}d delivery` : ''}</span>
                </div>
              </div>
            )) : <p className="inline-note">{comparisonMessage || 'No live Fiverr page-one gigs matched this keyword yet. Try a more specific phrase.'}</p>}
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>How to beat each top-10 gig</h2><span>{oneByOne.length}</span></div>
          <div className="feed-list">
            {oneByOne.length ? oneByOne.map((item) => (
              <div className="feed-item" key={`${item.rank_position}-${item.competitor_title}`}>
                <div className="row-topline">
                  <strong>#{item.rank_position ?? '?'} {item.competitor_title}</strong>
                  <span className={`status status--${item.priority === 'high' ? 'warning' : item.priority === 'medium' ? 'queued' : 'ok'}`}>{item.priority ?? 'next'}</span>
                </div>
                <p>{(item.why_it_ranks ?? []).join(' ') || 'No rank reason was generated.'}</p>
                <p><strong>Do this:</strong> {item.primary_recommendation ?? 'No recommendation generated.'}</p>
                <ul className="bullet-list compact">
                  {(item.what_to_change ?? []).map((change) => <li key={`${item.rank_position}-${change}`}>{change}</li>)}
                </ul>
                <div className="row-metrics">
                  <span>{currency(item.starting_price)}</span>
                  <span>{item.reviews_count ?? '--'} reviews</span>
                  <span>{item.expected_gain ?? '--'}% est. gain</span>
                </div>
              </div>
            )) : <p className="inline-note">{comparisonMessage || 'Run a compare to generate one-by-one recommendations against page-one gigs.'}</p>}
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head">
            <h2>All Competitors</h2>
            <select value={sortKey} onChange={(event) => onSortKeyChange(event.target.value as typeof sortKey)}>
              <option value="rank_position">page rank</option>
              <option value="conversion_proxy_score">conversion</option>
              <option value="reviews_count">reviews</option>
              <option value="starting_price">price</option>
            </select>
          </div>
          <div className="table">
            {competitors.length ? competitors.map((item) => (
              <div className="row row--stacked" key={`${item.url}-${item.title}`}>
                <div className="row-topline">
                  <strong>{item.rank_position ? `#${item.rank_position} ` : ''}{item.title}</strong>
                  <span className={`status status--${item.is_first_page ? 'active' : 'queued'}`}>{item.is_first_page ? 'page one' : 'tracked'}</span>
                </div>
                <p>{item.seller_name || 'Unknown seller'}</p>
                <p>{item.matched_term || '--'}</p>
                <div className="row-metrics">
                  <span>{currency(item.starting_price)}</span>
                  <span>{item.reviews_count ?? '--'} reviews</span>
                  <span>{item.conversion_proxy_score ?? '--'} score</span>
                </div>
              </div>
            )) : <p className="inline-note">{comparisonMessage || 'No competitor gigs are being shown for the active search yet.'}</p>}
          </div>
        </article>

        <div className="split-grid--column">
          <article className="card">
            <div className="card-head"><h2>Comparison timeline</h2><span>{timeline.length} saved runs</span></div>
            <div className="chart-shell">
              {timelineChart.length ? (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={timelineChart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(102,124,153,0.2)" />
                    <XAxis dataKey="label" stroke="#7b91ad" />
                    <YAxis stroke="#7b91ad" />
                    <Tooltip labelFormatter={(label) => String(label ?? '--')} />
                    <Line dataKey="optimization_score" name="Optimization" stroke="#49b3ff" strokeWidth={2.5} dot={false} />
                    <Line dataKey="keyword_score" name="Keyword score" stroke="#ff9966" strokeWidth={2.5} dot={false} />
                    <Line dataKey="competitor_count" name="Competitors" stroke="#5ed1a3" strokeWidth={2.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="inline-note">Comparison runs will appear here once you compare the same gig more than once.</p>
              )}
            </div>
          </article>

          <article className="card">
            <div className="card-head"><h2>Latest comparison diff</h2><span>{comparisonDiff.available ? 'ready' : 'pending'}</span></div>
            <p className="inline-note">{comparisonDiff.summary}</p>
            <div className="table">
              {comparisonDiff.available && comparisonDiff.changes.length ? comparisonDiff.changes.map((change) => (
                <div className="row row--stacked" key={`${change.label}-${String(change.before)}-${String(change.after)}`}>
                  <div className="row-topline">
                    <strong>{change.label}</strong>
                  </div>
                  <div className="diff diff--stacked">
                    <pre>{displayDiffValue(change.before)}</pre>
                    <pre>{displayDiffValue(change.after)}</pre>
                  </div>
                </div>
              )) : <p className="inline-note">Run another comparison to see how the market recommendations changed over time.</p>}
            </div>
          </article>
        </div>
      </section>
    </>
  )
}
