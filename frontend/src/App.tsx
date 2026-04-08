import { startTransition, useEffect, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { createDashboardSocket, fetchJson, loadBootstrap } from './api'
import type { BootstrapPayload, DashboardEvent, JobRun, LegacyState } from './types'
import './App.css'

function App() {
  const [data, setData] = useState<BootstrapPayload | null>(null)
  const [gigUrl, setGigUrl] = useState('')
  const [terms, setTerms] = useState('')
  const [manualInput, setManualInput] = useState('')
  const [liveMode, setLiveMode] = useState(false)
  const [sortKey, setSortKey] = useState<'conversion_proxy_score' | 'reviews_count' | 'starting_price'>('conversion_proxy_score')
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true

    async function init() {
      try {
        const payload = await loadBootstrap()
        if (!active) return
        startTransition(() => applyBootstrap(payload))
      } catch (reason) {
        if (!active) return
        setError(reason instanceof Error ? reason.message : 'Unable to load dashboard.')
      }
    }

    init()
    const socket = createDashboardSocket((event) => {
      if (!active) return
      startTransition(() => applyEvent(event))
    })

    return () => {
      active = false
      socket.close()
    }
  }, [])

  function applyBootstrap(payload: BootstrapPayload) {
    setData(payload)
    const marketplace = payload.state.notifications?.marketplace ?? {}
    setGigUrl(String(marketplace.my_gig_url ?? payload.state.gig_comparison?.gig_url ?? ''))
    setTerms((marketplace.search_terms ?? payload.state.gig_comparison?.detected_search_terms ?? []).join(', '))
  }

  function applyEvent(event: DashboardEvent) {
    if (!data) return
    if (event.type === 'state') {
      setData({
        ...data,
        state: { ...data.state, ...(event.payload as LegacyState) },
      })
      return
    }
    if (event.type === 'scraper_activity') {
      setData({
        ...data,
        state: { ...data.state, scraper_run: event.payload },
      })
      return
    }
    if (['job_queued', 'job_progress', 'job_completed', 'job_failed'].includes(event.type)) {
      const incoming = event.payload as JobRun
      setData({
        ...data,
        job_runs: [incoming, ...data.job_runs.filter((item) => item.run_id !== incoming.run_id)].slice(0, 25),
      })
      if (event.type === 'job_completed') {
        void refresh()
      }
    }
  }

  async function refresh() {
    try {
      applyBootstrap(await loadBootstrap())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Refresh failed.')
    }
  }

  async function postJob(jobType: string, payload: Record<string, unknown> = {}) {
    if (!data) return
    setBusy(jobType)
    setError('')
    setMessage('')
    try {
      const response = await fetchJson<BootstrapPayload>(
        '/api/v2/jobs',
        {
          method: 'POST',
          body: JSON.stringify({ job_type: jobType, ...payload }),
        },
        data.state.auth.csrf_token,
      )
      applyBootstrap(response)
      setMessage(`Queued ${jobType.replaceAll('_', ' ')} job.`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Job request failed.')
    } finally {
      setBusy('')
    }
  }

  async function queueRecommendation(actionType: string, proposedValue: unknown) {
    if (!data) return
    setBusy(actionType)
    try {
      const nextState = await fetchJson<LegacyState>(
        '/api/marketplace/recommendations/apply',
        {
          method: 'POST',
          body: JSON.stringify({ action_type: actionType, proposed_value: proposedValue }),
        },
        data.state.auth.csrf_token,
      )
      setData({ ...data, state: { ...data.state, ...nextState }, queue: nextState.queue ?? data.queue })
      setMessage('Recommendation added to the HITL queue.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to queue the recommendation.')
    } finally {
      setBusy('')
    }
  }

  async function reviewQueue(recordId: string, action: 'approve' | 'reject') {
    if (!data) return
    setBusy(`${action}-${recordId}`)
    try {
      const nextState = await fetchJson<LegacyState>(
        `/api/queue/${recordId}/${action}`,
        { method: 'POST', body: JSON.stringify({ reviewer_notes: '' }) },
        data.state.auth.csrf_token,
      )
      setData({ ...data, state: { ...data.state, ...nextState }, queue: nextState.queue ?? data.queue })
      setMessage(`Queue item ${action}d.`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Queue action failed.')
    } finally {
      setBusy('')
    }
  }

  if (!data) {
    return <main className="shell loading">Preparing the blueprint dashboard…</main>
  }

  const report = data.state.latest_report ?? {}
  const comparison = data.state.gig_comparison ?? {}
  const blueprint = comparison.implementation_blueprint ?? {}
  const activeJob = data.job_runs.find((job) => ['queued', 'running'].includes(job.status)) ?? data.job_runs[0]
  const competitors = [...data.competitors].sort((a, b) => {
    const left = Number(a[sortKey] ?? 0)
    const right = Number(b[sortKey] ?? 0)
    return sortKey === 'starting_price' ? left - right : right - left
  })
  const queue = data.queue.length ? data.queue : data.state.queue
  const selectedQueue = queue[0]
  const radar = [
    { name: 'Discovery', value: clamp((data.state.metrics_history.at(-1)?.ctr ?? 0) * 12) },
    { name: 'Conversion', value: clamp((data.state.metrics_history.at(-1)?.conversion_rate ?? 0) * 10) },
    { name: 'Keywords', value: clamp((report.niche_pulse?.trending_queries?.length ?? 0) * 16) },
    { name: 'Actions', value: clamp((blueprint.weekly_actions?.length ?? 0) * 18) },
    { name: 'Trust', value: clamp(report.optimization_score ?? 0) },
  ]

  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">GigOptimizer Pro Blueprint</p>
          <h1>React dashboard, live jobs, database-backed state, and market-driven gig guidance.</h1>
          <p className="lede">This view runs on the new bootstrap/job APIs and streams updates over WebSocket instead of polling.</p>
        </div>
        <div className="hero-grid">
          <Metric label="Optimization score" value={String(report.optimization_score ?? '--')} />
          <Metric label="Recommended title" value={blueprint.recommended_title ?? 'Run a market compare'} />
          <Metric label="Queue items" value={String(queue.length)} />
          <Metric label="Worker mode" value={`${data.workers.backend}/${data.workers.mode}`} />
        </div>
      </section>

      {(message || error) && <section className={`flash ${error ? 'flash--error' : ''}`}>{error || message}</section>}

      <section className="commands card">
        <div className="card-head"><h2>Run jobs</h2><label><input checked={liveMode} onChange={(event) => setLiveMode(event.target.checked)} type="checkbox" /> live connectors</label></div>
        <div className="form-grid">
          <input value={gigUrl} onChange={(event) => setGigUrl(event.target.value)} placeholder="My Fiverr gig URL" />
          <input value={terms} onChange={(event) => setTerms(event.target.value)} placeholder="wordpress speed, core web vitals" />
        </div>
        <textarea rows={4} value={manualInput} onChange={(event) => setManualInput(event.target.value)} placeholder="Title | price | rating | reviews | delivery | url" />
        <div className="button-row">
          <button onClick={() => postJob('pipeline', { use_live_connectors: liveMode })} disabled={busy === 'pipeline'}>{busy === 'pipeline' ? 'Queueing…' : 'Run pipeline'}</button>
          <button onClick={() => postJob('marketplace_compare', { gig_url: gigUrl, search_terms: splitTerms(terms) })} disabled={busy === 'marketplace_compare'}>{busy === 'marketplace_compare' ? 'Queueing…' : 'Compare gig'}</button>
          <button onClick={() => postJob('marketplace_scrape', { search_terms: splitTerms(terms) })} disabled={busy === 'marketplace_scrape'}>{busy === 'marketplace_scrape' ? 'Queueing…' : 'Scan market'}</button>
          <button onClick={() => postJob('manual_compare', { gig_url: gigUrl, search_terms: splitTerms(terms), competitor_input: manualInput })} disabled={busy === 'manual_compare' || !manualInput.trim()}>{busy === 'manual_compare' ? 'Queueing…' : 'Analyze manual input'}</button>
        </div>
      </section>

      <section className="charts">
        <article className="card">
          <div className="card-head"><h2>Live metrics</h2><span>{data.state.metrics_history.length} points</span></div>
          <div className="chart-shell">
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={data.state.metrics_history}>
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
          <div className="card-head"><h2>Score radar</h2><span>{comparison.competitor_count ?? 0} competitors</span></div>
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
          <div className="card-head"><h2>What to implement</h2><a href="/dashboard-legacy">legacy view</a></div>
          <div className="stack">
            <Block title="Recommended title" body={blueprint.recommended_title ?? 'No title yet.'} action={() => queueRecommendation('title_update', blueprint.recommended_title)} busy={busy === 'title_update'} />
            <Block title="Recommended tags" body={(blueprint.recommended_tags ?? []).join(', ') || 'No tags yet.'} action={() => queueRecommendation('keyword_tag_update', blueprint.recommended_tags ?? [])} busy={busy === 'keyword_tag_update'} />
            <Block title="Description blueprint" body={(blueprint.description_blueprint ?? []).join(' • ') || 'No description guidance yet.'} action={() => queueRecommendation('description_update', blueprint.description_full)} busy={busy === 'description_update'} />
          </div>
          <ul className="bullet-list">{(blueprint.weekly_actions ?? comparison.what_to_implement ?? []).map((item: string) => <li key={item}>{item}</li>)}</ul>
        </article>

        <article className="card">
          <div className="card-head"><h2>HITL queue</h2><span>{queue.length}</span></div>
          {selectedQueue ? (
            <>
              <div className="progress"><div style={{ width: `${selectedQueue.confidence_score}%` }} /></div>
              <div className="diff"><pre>{pretty(selectedQueue.current_value)}</pre><pre>{pretty(selectedQueue.proposed_value)}</pre></div>
              <div className="pill-row">{(selectedQueue.validator_issues ?? []).map((issue) => <span className="pill" key={issue.code}>{issue.code}: {issue.message}</span>)}</div>
              <div className="button-row">
                <button onClick={() => reviewQueue(selectedQueue.id, 'approve')} disabled={busy === `approve-${selectedQueue.id}`}>Approve</button>
                <button className="secondary" onClick={() => reviewQueue(selectedQueue.id, 'reject')} disabled={busy === `reject-${selectedQueue.id}`}>Reject</button>
              </div>
            </>
          ) : <p>No queue items yet.</p>}
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Competitors</h2><select value={sortKey} onChange={(event) => setSortKey(event.target.value as typeof sortKey)}><option value="conversion_proxy_score">conversion</option><option value="reviews_count">reviews</option><option value="starting_price">price</option></select></div>
          <div className="table">
            {competitors.map((item) => (
              <div className="row" key={`${item.url}-${item.title}`}>
                <div><strong>{item.title}</strong><p>{item.seller_name || 'Unknown seller'}</p></div>
                <div className="row-metrics"><span>{currency(item.starting_price)}</span><span>{item.reviews_count ?? '--'} reviews</span></div>
              </div>
            ))}
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>Job progress</h2><a href="/rq">queue overview</a></div>
          {activeJob ? <div className="job"><div className="progress"><div style={{ width: `${Math.max(5, Math.round((activeJob.progress || 0) * 100))}%` }} /></div><strong>{human(activeJob.run_type)}</strong><p>{activeJob.current_stage || activeJob.output_summary || 'Queued'}</p></div> : <p>No jobs yet.</p>}
          <div className="table">{data.job_runs.map((job) => <div className="row" key={job.run_id}><div><strong>{human(job.run_type)}</strong><p>{job.output_summary || job.current_stage || 'Queued'}</p></div><span className={`status status--${job.status}`}>{job.status}</span></div>)}</div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Keyword pulse</h2><span>{(report.niche_pulse?.trending_queries ?? []).length}</span></div>
          <div className="pill-row">{(report.niche_pulse?.trending_queries ?? []).map((item: string) => <span className="pill" key={item}>{item}</span>)}</div>
          <h3>Why competitors win</h3>
          <ul className="bullet-list">{(comparison.why_competitors_win ?? report.competitive_gap_analysis?.why_competitors_win ?? []).map((item: string) => <li key={item}>{item}</li>)}</ul>
        </article>
        <article className="card">
          <div className="card-head"><h2>System health</h2><span className={`status status--${data.health.status}`}>{data.health.status}</span></div>
          <div className="table">{(data.state.setup_health?.connectors ?? []).map((item: Record<string, string>) => <div className="row" key={item.connector}><div><strong>{item.connector}</strong><p>{item.detail}</p></div><span className={`status status--${item.status}`}>{item.status}</span></div>)}</div>
        </article>
      </section>
    </main>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>
}

function Block({ title, body, action, busy }: { title: string; body: string; action: () => void; busy: boolean }) {
  return <div className="block"><div><p className="eyebrow">{title}</p><strong>{body}</strong></div><button className="secondary" onClick={action} disabled={busy || body.includes('No ')}>Queue</button></div>
}

function splitTerms(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function clamp(value: number) {
  return Math.max(12, Math.min(100, Math.round(value)))
}

function shortDate(value?: string) {
  if (!value) return '--'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : `${parsed.getMonth() + 1}/${parsed.getDate()}`
}

function pretty(value: string) {
  try {
    return JSON.stringify(JSON.parse(value), null, 2)
  } catch {
    return value
  }
}

function human(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (match) => match.toUpperCase())
}

function currency(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

export default App
