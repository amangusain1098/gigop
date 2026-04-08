import { startTransition, useEffect, useRef, useState, type KeyboardEvent } from 'react'
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
import type { BootstrapPayload, CompetitorRecord, DashboardEvent, DatasetRecord, JobRun, LegacyState, QueueRecord } from './types'
import './App.css'

type TitleOption = { label: string; title: string; rationale: string }
type DescriptionOption = { label: string; summary: string; text: string; paired_title?: string; notes?: string[] }
type PersonaFocus = { persona: string; score: number; pain_point: string; emphasis: string[] }
type RecommendedPackage = { name: string; price: number; delivery_days?: number | null; highlights?: string[] }
type CompetitorRecommendation = {
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

function App() {
  const [data, setData] = useState<BootstrapPayload | null>(null)
  const [gigUrl, setGigUrl] = useState('')
  const [terms, setTerms] = useState('')
  const [manualInput, setManualInput] = useState('')
  const [liveMode, setLiveMode] = useState(false)
  const [sortKey, setSortKey] = useState<'rank_position' | 'conversion_proxy_score' | 'reviews_count' | 'starting_price'>('rank_position')
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [maxResults, setMaxResults] = useState(10)
  const [autoCompareEnabled, setAutoCompareEnabled] = useState(false)
  const [autoCompareMinutes, setAutoCompareMinutes] = useState(5)
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [assistantInput, setAssistantInput] = useState('')
  const [assistantBusy, setAssistantBusy] = useState(false)
  const [assistantMessages, setAssistantMessages] = useState<Array<{ role: 'user' | 'assistant'; text: string; suggestions?: string[] }>>([])
  const [assistantInitialized, setAssistantInitialized] = useState(false)
  const [knowledgeFile, setKnowledgeFile] = useState<File | null>(null)
  const datasetInputRef = useRef<HTMLInputElement | null>(null)
  const assistantLogRef = useRef<HTMLDivElement | null>(null)
  const assistantInputRef = useRef<HTMLTextAreaElement | null>(null)

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

  useEffect(() => {
    if (!assistantOpen) return
    const frame = window.requestAnimationFrame(() => {
      assistantLogRef.current?.scrollTo({
        top: assistantLogRef.current.scrollHeight,
        behavior: 'smooth',
      })
      assistantInputRef.current?.focus()
    })
    return () => window.cancelAnimationFrame(frame)
  }, [assistantOpen, assistantMessages.length, assistantBusy])

  function applyBootstrap(payload: BootstrapPayload) {
    setData(payload)
    const marketplace = payload.state.notifications?.marketplace ?? {}
    setGigUrl(String(marketplace.my_gig_url ?? payload.state.gig_comparison?.gig_url ?? ''))
    setTerms((marketplace.search_terms ?? payload.state.gig_comparison?.detected_search_terms ?? []).join(', '))
    setMaxResults(Number(marketplace.max_results ?? 10))
    setAutoCompareEnabled(Boolean(marketplace.auto_compare_enabled ?? false))
    setAutoCompareMinutes(Number(marketplace.auto_compare_interval_minutes ?? 5))
    const nextAssistantMessages = buildAssistantMessages(payload)
    if (nextAssistantMessages.length) {
      setAssistantMessages(nextAssistantMessages)
      setAssistantInitialized(true)
    } else if (!assistantInitialized) {
      setAssistantMessages(buildAssistantMessages(payload))
      setAssistantInitialized(true)
    }
  }

  function applyEvent(event: DashboardEvent) {
    if (!data) return
    if (event.type === 'state') {
      const nextState = event.payload as LegacyState
      setData({
        ...data,
        state: { ...data.state, ...nextState },
        queue: nextState.queue ?? data.queue,
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

  async function withCsrfRetry<T>(operation: (csrfToken: string) => Promise<T>): Promise<T> {
    if (!data) {
      throw new Error('Dashboard is still loading.')
    }
    try {
      return await operation(data.state.auth.csrf_token)
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : 'Request failed.'
      if (!/csrf/i.test(detail)) {
        throw reason
      }
      const payload = await loadBootstrap()
      startTransition(() => applyBootstrap(payload))
      return operation(payload.state.auth.csrf_token)
    }
  }

  async function refresh() {
    try {
      applyBootstrap(await loadBootstrap())
      setMessage('Dashboard refreshed.')
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Refresh failed.')
    }
  }

  async function refreshHostinger() {
    if (!data) return
    setBusy('hostinger-refresh')
    setError('')
    setMessage('')
    try {
      const response = await fetchJson<{ hostinger: Record<string, any> }>('/api/hostinger/status', { method: 'GET' })
      setData({ ...data, hostinger: response.hostinger })
      setMessage('Hostinger status refreshed.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to refresh Hostinger status.')
    } finally {
      setBusy('')
    }
  }

  async function postJob(jobType: string, payload: Record<string, unknown> = {}) {
    if (!data) return
    setBusy(jobType)
    setError('')
    setMessage('')
    try {
      const response = await withCsrfRetry((csrfToken) =>
        fetchJson<BootstrapPayload>(
          '/api/v2/jobs',
          {
            method: 'POST',
            body: JSON.stringify({ job_type: jobType, ...payload }),
          },
          csrfToken,
        ),
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
    setError('')
    setMessage('')
    try {
      const nextState = await withCsrfRetry((csrfToken) =>
        fetchJson<LegacyState>(
          '/api/marketplace/recommendations/apply',
          {
            method: 'POST',
            body: JSON.stringify({ action_type: actionType, proposed_value: proposedValue }),
          },
          csrfToken,
        ),
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
    setError('')
    setMessage('')
    try {
      const nextState = await withCsrfRetry((csrfToken) =>
        fetchJson<LegacyState>(
          `/api/queue/${recordId}/${action}`,
          { method: 'POST', body: JSON.stringify({ reviewer_notes: '' }) },
          csrfToken,
        ),
      )
      setData({ ...data, state: { ...data.state, ...nextState }, queue: nextState.queue ?? data.queue })
      setMessage(`Queue item ${action}d.`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Queue action failed.')
    } finally {
      setBusy('')
    }
  }

  async function saveMarketplaceSettings() {
    if (!data) return
    setBusy('save-settings')
    setError('')
    setMessage('')
    try {
      const settings = await withCsrfRetry((csrfToken) =>
        fetchJson<Record<string, any>>(
          '/api/settings',
          {
            method: 'POST',
            body: JSON.stringify({
              marketplace: {
                enabled: true,
                my_gig_url: gigUrl,
                search_terms: splitTerms(terms),
                max_results: maxResults,
                auto_compare_enabled: autoCompareEnabled,
                auto_compare_interval_minutes: autoCompareMinutes,
              },
              slack: {
                enabled: true,
              },
            }),
          },
          csrfToken,
        ),
      )
      setData({ ...data, state: { ...data.state, notifications: settings } })
      setMessage('Marketplace settings saved.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save settings.')
    } finally {
      setBusy('')
    }
  }

  async function runNotificationTest(channel: 'slack') {
    if (!data) return
    setBusy(`test-${channel}`)
    setError('')
    setMessage('')
    try {
      const response = await withCsrfRetry((csrfToken) =>
        fetchJson<{ result: { detail: string } }>(
          '/api/settings/notifications/test',
          {
            method: 'POST',
            body: JSON.stringify({ channel }),
          },
          csrfToken,
        ),
      )
      setMessage(response.result.detail)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Unable to test ${channel}.`)
    } finally {
      setBusy('')
    }
  }

  async function sendAssistantMessage(prefill?: string) {
    if (!data) return
    const question = (prefill ?? assistantInput).trim()
    if (!question) return
    setAssistantBusy(true)
    setAssistantMessages((current) => [...current, { role: 'user', text: question }])
    setAssistantInput('')
    try {
      const response = await withCsrfRetry((csrfToken) =>
        fetchJson<{ assistant: { reply: string; suggestions?: string[] }; assistant_history?: Array<Record<string, any>> }>(
          '/api/assistant/chat',
          {
            method: 'POST',
            body: JSON.stringify({ message: question }),
          },
          csrfToken,
        ),
      )
      const nextMessages = mapAssistantHistory(response.assistant_history ?? [], data)
      if (nextMessages.length) {
        setAssistantMessages(nextMessages)
      } else {
        setAssistantMessages((current) => [
          ...current,
          {
            role: 'assistant',
            text: response.assistant.reply,
            suggestions: response.assistant.suggestions ?? [],
          },
        ])
      }
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : 'Assistant request failed.'
      setAssistantMessages((current) => [
        ...current,
        {
          role: 'assistant',
          text: detail,
          suggestions: [],
        },
      ])
    } finally {
      setAssistantBusy(false)
    }
  }

  async function uploadDataset() {
    if (!data || !knowledgeFile) return
    setBusy('upload-dataset')
    setError('')
    setMessage('')
    try {
      const contentBase64 = await fileToBase64(knowledgeFile)
      const response = await withCsrfRetry((csrfToken) =>
        fetchJson<BootstrapPayload>(
          '/api/v2/datasets/upload',
          {
            method: 'POST',
            body: JSON.stringify({
              filename: knowledgeFile.name,
              content_type: knowledgeFile.type || 'application/octet-stream',
              content_base64: contentBase64,
              gig_url: gigUrl,
            }),
          },
          csrfToken,
        ),
      )
      applyBootstrap(response)
      setKnowledgeFile(null)
      if (datasetInputRef.current) {
        datasetInputRef.current.value = ''
      }
      setMessage(`Uploaded ${knowledgeFile.name} to the copilot knowledge base.`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Dataset upload failed.')
    } finally {
      setBusy('')
    }
  }

  async function deleteDataset(documentId: string) {
    if (!data) return
    setBusy(`delete-dataset-${documentId}`)
    setError('')
    setMessage('')
    try {
      const response = await withCsrfRetry((csrfToken) =>
        fetchJson<BootstrapPayload>(
          `/api/v2/datasets/${documentId}`,
          {
            method: 'DELETE',
          },
          csrfToken,
        ),
      )
      applyBootstrap(response)
      setMessage('Dataset removed from the copilot knowledge base.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Dataset deletion failed.')
    } finally {
      setBusy('')
    }
  }

  function handleAssistantKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void sendAssistantMessage()
    }
  }

  if (!data) {
    return <main className="shell loading">Preparing the blueprint dashboard...</main>
  }

  const report = data.state.latest_report ?? {}
  const comparison = data.state.gig_comparison ?? {}
  const blueprint = comparison.implementation_blueprint ?? {}
  const scraperRun = data.state.scraper_run ?? {}
  const hostinger = data.hostinger ?? {}
  const datasets = data.datasets ?? []
  const aiSettings = (data.state.notifications?.ai ?? {}) as Record<string, any>
  const slackSettings = (data.state.notifications?.slack ?? {}) as Record<string, any>
  const myGig = (comparison.my_gig ?? {}) as Record<string, any>
  const titleOptions = (blueprint.title_options ?? []) as TitleOption[]
  const descriptionOptions = (blueprint.description_options ?? []) as DescriptionOption[]
  const recommendedPackages = (blueprint.recommended_packages ?? []) as RecommendedPackage[]
  const personaFocus = (blueprint.persona_focus ?? []) as PersonaFocus[]
  const pageOneTopTen = ((comparison.first_page_top_10 ?? []) as CompetitorRecord[]).slice(0, 10)
  const oneByOne = (comparison.one_by_one_recommendations ?? []) as CompetitorRecommendation[]
  const topRankedGig = (comparison.top_ranked_gig ?? pageOneTopTen[0] ?? {}) as Record<string, any>
  const topRankedReasons = (comparison.why_top_ranked_gig_is_first ?? topRankedGig.why_on_page_one ?? []) as string[]
  const assistantQuickPrompts = buildAssistantQuickPrompts(comparison, blueprint, scraperRun)
  const activeJob = data.job_runs.find((job: JobRun) => ['queued', 'running'].includes(job.status)) ?? data.job_runs[0]
  const competitorSource = pageOneTopTen.length ? pageOneTopTen : data.competitors
  const competitors = [...competitorSource].sort((a, b) => {
    if (sortKey === 'rank_position') {
      return Number(a.rank_position ?? 999) - Number(b.rank_position ?? 999)
    }
    const left = Number(a[sortKey] ?? 0)
    const right = Number(b[sortKey] ?? 0)
    return sortKey === 'starting_price' ? left - right : right - left
  })
  const queue: QueueRecord[] = (data.state.queue?.length ? data.state.queue : data.queue) as QueueRecord[]
  const selectedQueue = queue[0]
  const radar = [
    { name: 'Discovery', value: clamp((data.state.metrics_history.at(-1)?.ctr ?? 0) * 12) },
    { name: 'Conversion', value: clamp((data.state.metrics_history.at(-1)?.conversion_rate ?? 0) * 10) },
    { name: 'Keywords', value: clamp((report.niche_pulse?.trending_queries?.length ?? 0) * 16) },
    { name: 'Actions', value: clamp((blueprint.weekly_actions?.length ?? 0) * 18) },
    { name: 'Trust', value: clamp(report.optimization_score ?? 0) },
  ]
  const assistantProviderLabel = aiSettings.provider === 'n8n' ? 'n8n webhook' : String(aiSettings.provider ?? 'local fallback')
  const assistantStatusLabel = aiSettings.enabled
    ? (aiSettings.configured ? `${assistantProviderLabel} configured` : `${assistantProviderLabel} fallback`)
    : 'local market fallback'

  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">GigOptimizer Pro Blueprint</p>
          <h1>Live Fiverr visibility, page-one competitor tracking, and exact gig changes to publish next.</h1>
          <p className="lede">
            This dashboard watches Fiverr page one, compares your gig against the current top 10 public results, and turns
            that into queueable title, description, keyword, pricing, and trust recommendations.
          </p>
        </div>
        <div className="hero-grid">
          <Metric label="Optimization score" value={String(report.optimization_score ?? '--')} />
          <Metric label="Recommended title" value={blueprint.recommended_title ?? 'Run a market compare'} />
          <Metric label="Page-one gigs tracked" value={String(pageOneTopTen.length || comparison.competitor_count || 0)} />
          <Metric label="Primary search term" value={String(comparison.primary_search_term ?? '--')} />
        </div>
      </section>

      {(message || error) && <section className={`flash ${error ? 'flash--error' : ''}`}>{error || message}</section>}

      <section className="commands card">
        <div className="card-head">
          <h2>Run jobs</h2>
          <label><input checked={liveMode} onChange={(event) => setLiveMode(event.target.checked)} type="checkbox" /> live connectors</label>
        </div>
        <div className="form-grid">
          <input value={gigUrl} onChange={(event) => setGigUrl(event.target.value)} placeholder="My Fiverr gig URL" />
          <input value={terms} onChange={(event) => setTerms(event.target.value)} placeholder="wordpress speed, pagespeed insights, core web vitals" />
        </div>
        <textarea rows={4} value={manualInput} onChange={(event) => setManualInput(event.target.value)} placeholder="Title | price | rating | reviews | delivery | url" />
        <div className="button-row">
          <button onClick={() => postJob('pipeline', { use_live_connectors: liveMode })} disabled={busy === 'pipeline'}>{busy === 'pipeline' ? 'Queueing...' : 'Run pipeline'}</button>
          <button onClick={() => postJob('marketplace_compare', { gig_url: gigUrl, search_terms: splitTerms(terms) })} disabled={busy === 'marketplace_compare'}>{busy === 'marketplace_compare' ? 'Queueing...' : 'Compare gig vs top 10'}</button>
          <button onClick={() => postJob('marketplace_scrape', { search_terms: splitTerms(terms) })} disabled={busy === 'marketplace_scrape'}>{busy === 'marketplace_scrape' ? 'Queueing...' : 'Scan market'}</button>
          <button onClick={() => postJob('manual_compare', { gig_url: gigUrl, search_terms: splitTerms(terms), competitor_input: manualInput })} disabled={busy === 'manual_compare' || !manualInput.trim()}>{busy === 'manual_compare' ? 'Queueing...' : 'Analyze manual input'}</button>
          <button onClick={() => postJob('weekly_report', { use_live_connectors: liveMode })} disabled={busy === 'weekly_report'}>{busy === 'weekly_report' ? 'Queueing...' : 'Run weekly report'}</button>
          <button className="secondary" onClick={() => void refresh()} disabled={busy === 'refresh'}>Refresh dashboard</button>
        </div>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Marketplace settings</h2><span>{slackSettings.configured ? 'Slack ready' : 'Slack optional'}</span></div>
          <div className="form-grid">
            <input value={gigUrl} onChange={(event) => setGigUrl(event.target.value)} placeholder="Default Fiverr gig URL" />
            <input value={terms} onChange={(event) => setTerms(event.target.value)} placeholder="Search terms used for page-one tracking" />
            <input type="number" min={10} max={25} value={maxResults} onChange={(event) => setMaxResults(Number(event.target.value || 10))} placeholder="Max competitor results" />
            <input type="number" min={5} max={240} value={autoCompareMinutes} onChange={(event) => setAutoCompareMinutes(Number(event.target.value || 5))} placeholder="Auto compare interval (minutes)" />
          </div>
          <div className="button-row button-row--three">
            <button className="secondary" onClick={() => setAutoCompareEnabled((current) => !current)}>
              {autoCompareEnabled ? 'Auto compare: on' : 'Auto compare: off'}
            </button>
            <button onClick={() => void saveMarketplaceSettings()} disabled={busy === 'save-settings'}>{busy === 'save-settings' ? 'Saving...' : 'Save settings'}</button>
            <button className="secondary" onClick={() => void runNotificationTest('slack')} disabled={busy === 'test-slack'}>{busy === 'test-slack' ? 'Testing...' : 'Test Slack'}</button>
          </div>
          <p className="inline-note">The page-one leaderboard uses the first search term as the primary Fiverr query, then compares those top 10 gigs against your gig one by one.</p>
        </article>

        <article className="card">
          <div className="card-head"><h2>Page-one leader</h2><span className={`status status--${comparison.status ?? 'pending'}`}>{comparison.status ?? 'idle'}</span></div>
          <div className="meta-grid">
            <MetaItem label="Leader rank" value={`#${String(topRankedGig.rank_position ?? 1)}`} />
            <MetaItem label="Leader price" value={currency(topRankedGig.starting_price)} />
            <MetaItem label="Leader reviews" value={String(topRankedGig.reviews_count ?? '--')} />
            <MetaItem label="Leader term" value={String(topRankedGig.matched_term ?? comparison.primary_search_term ?? '--')} />
          </div>
          <div className="option-card">
            <p className="eyebrow">Current top gig</p>
            <strong>{String(topRankedGig.title ?? 'Run a market compare')}</strong>
            <p>{String(topRankedGig.seller_name ?? 'Unknown seller')}</p>
            <ul className="bullet-list compact">
              {topRankedReasons.map((item: string) => <li key={item}>{item}</li>)}
            </ul>
          </div>
          <h3>Why competitors win</h3>
          <ul className="bullet-list">
            {((comparison.why_competitors_win ?? report.competitive_gap_analysis?.why_competitors_win ?? []) as string[]).map((item: string) => <li key={item}>{item}</li>)}
          </ul>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Knowledge base</h2><span>{datasets.length} file(s)</span></div>
          <p className="inline-note">
            Upload CSV, JSON, Markdown, HTML, TXT, or DOCX files. The copilot will retrieve from these files when you ask
            questions about your gig, competitors, reviews, package strategy, or niche history.
          </p>
          <div className="form-grid">
            <input
              ref={datasetInputRef}
              type="file"
              accept=".txt,.md,.markdown,.json,.csv,.html,.htm,.docx"
              onChange={(event) => setKnowledgeFile(event.target.files?.[0] ?? null)}
            />
            <button onClick={() => void uploadDataset()} disabled={busy === 'upload-dataset' || !knowledgeFile}>
              {busy === 'upload-dataset' ? 'Uploading...' : 'Upload dataset'}
            </button>
          </div>
          <div className="table">
            {datasets.length ? datasets.map((item: DatasetRecord) => (
              <div className="row row--stacked" key={item.id}>
                <div className="row-topline">
                  <strong>{item.filename}</strong>
                  <span className={`status status--${item.status === 'ready' ? 'ok' : 'queued'}`}>{item.status}</span>
                </div>
                <p>{item.preview || 'No preview extracted yet.'}</p>
                <div className="row-metrics">
                  <span>{Math.max(1, Math.round((item.size_bytes || 0) / 1024))} KB</span>
                  <span>{item.metadata?.chunk_count ?? 0} chunks</span>
                  <span>{item.created_at ? shortDate(item.created_at) : '--'}</span>
                </div>
                <div className="button-row button-row--two">
                  <button className="secondary" onClick={() => void sendAssistantMessage(`What can I use from ${item.filename} for my Fiverr gig right now?`)}>
                    Ask copilot
                  </button>
                  <button
                    className="secondary"
                    onClick={() => void deleteDataset(item.id)}
                    disabled={busy === `delete-dataset-${item.id}`}
                  >
                    {busy === `delete-dataset-${item.id}` ? 'Removing...' : 'Delete'}
                  </button>
                </div>
              </div>
            )) : <p>No datasets uploaded yet.</p>}
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>Copilot memory</h2><span>{(data.memory?.knowledge_documents ?? []).length} linked docs</span></div>
          <ul className="bullet-list">
            {((data.memory?.knowledge_documents ?? []) as Array<Record<string, any>>).map((item) => (
              <li key={String(item.id)}>{String(item.filename ?? 'dataset')} - {String(item.preview ?? '').slice(0, 140)}</li>
            ))}
          </ul>
          {!((data.memory?.knowledge_documents ?? []) as Array<Record<string, any>>).length ? (
            <p className="inline-note">Once you upload data, the copilot will pull relevant snippets into each answer.</p>
          ) : null}
        </article>
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
          <div className="card-head"><h2>Market score radar</h2><span>{comparison.competitor_count ?? 0} competitors</span></div>
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
          <div className="card-head"><h2>My gig vs market</h2><span>{comparison.primary_search_term ?? '--'}</span></div>
          <div className="meta-grid">
            <MetaItem label="My gig title" value={String(myGig.title ?? '--')} />
            <MetaItem label="My visible price" value={currency(myGig.starting_price)} />
            <MetaItem label="My public reviews" value={String(myGig.reviews_count ?? '--')} />
            <MetaItem label="Market anchor price" value={currency(comparison.market_anchor_price)} />
            <MetaItem label="Detected search terms" value={(comparison.detected_search_terms ?? []).join(', ') || '--'} />
            <MetaItem label="Top title patterns" value={(comparison.title_patterns ?? []).join(', ') || '--'} />
          </div>
          <h3>What to implement next</h3>
          <ul className="bullet-list">
            {((comparison.what_to_implement ?? blueprint.weekly_actions ?? []) as string[]).map((item: string) => <li key={item}>{item}</li>)}
          </ul>
          <h3>Do this first</h3>
          <ul className="bullet-list">
            {((comparison.do_this_first ?? blueprint.do_this_first ?? []) as string[]).map((item: string) => <li key={item}>{item}</li>)}
          </ul>
        </article>

        <article className="card">
          <div className="card-head"><h2>Live Fiverr feed</h2><span className={`status status--${scraperRun.status ?? 'pending'}`}>{scraperRun.status ?? 'idle'}</span></div>
          <div className="meta-grid">
            <MetaItem label="Search terms" value={(scraperRun.search_terms ?? []).join(', ') || '--'} />
            <MetaItem label="Last status" value={scraperRun.last_status_message ?? '--'} />
            <MetaItem label="Total results" value={String(scraperRun.total_results ?? 0)} />
            <MetaItem label="Last URL" value={scraperRun.last_url ?? '--'} />
          </div>
          <div className="split-grid">
            <div>
              <h3>Recent scrape events</h3>
              <div className="feed-list">
                {((scraperRun.recent_events ?? []) as Array<Record<string, any>>).slice(-6).reverse().map((event: Record<string, any>, index: number) => (
                  <div className="feed-item" key={`${event.timestamp ?? index}-${event.stage ?? ''}`}>
                    <span className={`status status--${event.level ?? 'ok'}`}>{event.stage ?? 'update'}</span>
                    <strong>{event.message ?? 'Marketplace update'}</strong>
                    <p>{event.term || event.url || '--'}</p>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3>Recent gigs found</h3>
              <div className="table">
                {((scraperRun.recent_gigs ?? []) as Array<Record<string, any>>).slice(0, 6).map((item: Record<string, any>) => (
                  <div className="row" key={`${item.url}-${item.title}`}>
                    <div>
                      <strong>{item.rank_position ? `#${item.rank_position} ` : ''}{item.title}</strong>
                      <p>{item.seller_name || 'Unknown seller'}</p>
                    </div>
                    <div className="row-metrics">
                      <span>{currency(item.starting_price)}</span>
                      <span>{item.rating ?? '--'} ★</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Top 10 gigs on Fiverr page one</h2><span>{pageOneTopTen.length}</span></div>
          <div className="table">
            {pageOneTopTen.map((item) => (
              <div className="row row--stacked" key={`${item.url}-${item.rank_position ?? item.title}`}>
                <div className="row-topline">
                  <strong>#{item.rank_position ?? '?'} {item.title}</strong>
                  <span className={`status status--${item.is_first_page ? 'active' : 'queued'}`}>{item.is_first_page ? 'page one' : 'tracked'}</span>
                </div>
                <p>{item.seller_name || 'Unknown seller'}</p>
                <p>{(item.why_on_page_one ?? item.win_reasons ?? []).join(' ') || 'No ranking reasons captured yet.'}</p>
                <div className="row-metrics">
                  <span>{currency(item.starting_price)}</span>
                  <span>{item.rating ?? '--'} ★</span>
                  <span>{item.reviews_count ?? '--'} reviews</span>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>How to beat each top-10 gig</h2><span>{oneByOne.length}</span></div>
          <div className="feed-list">
            {oneByOne.map((item) => (
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
            ))}
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Publish-ready title and tag options</h2><a href="/dashboard-legacy">legacy view</a></div>
          <Block title="Recommended title" body={blueprint.recommended_title ?? 'No title yet.'} action={() => queueRecommendation('title_update', blueprint.recommended_title)} busy={busy === 'title_update'} />
          <Block title="Recommended tags" body={(blueprint.recommended_tags ?? []).join(', ') || 'No tags yet.'} action={() => queueRecommendation('keyword_tag_update', blueprint.recommended_tags ?? [])} busy={busy === 'keyword_tag_update'} />
          <div className="option-list">
            {titleOptions.map((option: TitleOption) => (
              <div className="option-card" key={option.label}>
                <p className="eyebrow">{option.label}</p>
                <strong>{option.title}</strong>
                <p>{option.rationale}</p>
                <button className="secondary" onClick={() => queueRecommendation('title_update', option.title)} disabled={busy === 'title_update'}>Queue this title</button>
              </div>
            ))}
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>Description modes</h2><span>{descriptionOptions.length}</span></div>
          <Block title="Description blueprint" body={(blueprint.description_blueprint ?? []).join(' | ') || 'No description guidance yet.'} action={() => queueRecommendation('description_update', blueprint.description_full)} busy={busy === 'description_update'} />
          <div className="option-list">
            {descriptionOptions.map((option: DescriptionOption) => (
              <div className="option-card" key={option.label}>
                <p className="eyebrow">{option.label}</p>
                <strong>{option.paired_title || option.label}</strong>
                <p>{option.summary}</p>
                <pre>{option.text}</pre>
                <button className="secondary" onClick={() => queueRecommendation('description_update', option.text)} disabled={busy === 'description_update'}>Queue this description</button>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Pricing, packages, and trust</h2><span>{currency(comparison.market_anchor_price)}</span></div>
          <h3>Pricing strategy</h3>
          <ul className="bullet-list">
            {((blueprint.pricing_strategy ?? []) as string[]).map((item: string) => <li key={item}>{item}</li>)}
          </ul>
          <h3>Recommended packages</h3>
          <div className="package-grid">
            {recommendedPackages.map((pkg: RecommendedPackage) => (
              <div className="package-card" key={pkg.name}>
                <strong>{pkg.name}</strong>
                <p>{currency(pkg.price)}</p>
                <ul className="bullet-list compact">
                  {(pkg.highlights ?? []).map((item: string) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ))}
          </div>
          <h3>Trust boosters</h3>
          <ul className="bullet-list">
            {((blueprint.trust_boosters ?? []) as string[]).map((item: string) => <li key={item}>{item}</li>)}
          </ul>
        </article>

        <article className="card">
          <div className="card-head"><h2>FAQ and persona focus</h2><span>{personaFocus.length}</span></div>
          <h3>FAQ recommendations</h3>
          <ul className="bullet-list">
            {((blueprint.faq_recommendations ?? []) as string[]).map((item: string) => <li key={item}>{item}</li>)}
          </ul>
          <h3>Persona focus</h3>
          <div className="option-list">
            {personaFocus.map((item: PersonaFocus) => (
              <div className="option-card" key={item.persona}>
                <strong>{item.persona}</strong>
                <p>Score: {item.score}</p>
                <p>{item.pain_point}</p>
                <p>{item.emphasis.join(', ')}</p>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>HITL queue</h2><span>{queue.length}</span></div>
          {selectedQueue ? (
            <>
              <div className="progress"><div style={{ width: `${selectedQueue.confidence_score}%` }} /></div>
              <div className="diff"><pre>{pretty(selectedQueue.current_value)}</pre><pre>{pretty(selectedQueue.proposed_value)}</pre></div>
              <div className="pill-row">{(selectedQueue.validator_issues ?? []).map((issue: { code: string; message: string }) => <span className="pill" key={issue.code}>{issue.code}: {issue.message}</span>)}</div>
              <div className="button-row button-row--two">
                <button onClick={() => reviewQueue(selectedQueue.id, 'approve')} disabled={busy === `approve-${selectedQueue.id}`}>Approve</button>
                <button className="secondary" onClick={() => reviewQueue(selectedQueue.id, 'reject')} disabled={busy === `reject-${selectedQueue.id}`}>Reject</button>
              </div>
            </>
          ) : <p>No queue items yet.</p>}
        </article>

        <article className="card">
          <div className="card-head"><h2>Job progress</h2><a href="/rq">queue overview</a></div>
          {activeJob ? <div className="job"><div className="progress"><div style={{ width: `${Math.max(5, Math.round((activeJob.progress || 0) * 100))}%` }} /></div><strong>{human(activeJob.run_type)}</strong><p>{activeJob.current_stage || activeJob.output_summary || 'Queued'}</p></div> : <p>No jobs yet.</p>}
          <div className="table">{data.job_runs.map((job: JobRun) => <div className="row" key={job.run_id}><div><strong>{human(job.run_type)}</strong><p>{job.output_summary || job.current_stage || 'Queued'}</p></div><span className={`status status--${job.status}`}>{job.status}</span></div>)}</div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head">
            <h2>Competitors</h2>
            <select value={sortKey} onChange={(event) => setSortKey(event.target.value as typeof sortKey)}>
              <option value="rank_position">page rank</option>
              <option value="conversion_proxy_score">conversion</option>
              <option value="reviews_count">reviews</option>
              <option value="starting_price">price</option>
            </select>
          </div>
          <div className="table">
            {competitors.map((item) => (
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
            ))}
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>Hostinger ops</h2><button className="secondary" onClick={refreshHostinger} disabled={busy === 'hostinger-refresh'}>{busy === 'hostinger-refresh' ? 'Refreshing...' : 'Refresh ops'}</button></div>
          <div className="meta-grid">
            <MetaItem label="Status" value={String(hostinger.status ?? 'disabled')} />
            <MetaItem label="Configured" value={hostinger.configured ? 'Yes' : 'No'} />
            <MetaItem label="Project" value={String(hostinger.project_name ?? '--')} />
            <MetaItem label="Domain" value={String(hostinger.domain ?? '--')} />
            <MetaItem label="Selected VM" value={String(hostinger.selected_vm?.id ?? hostinger.selected_vm?.name ?? hostinger.virtual_machine_id ?? '--')} />
            <MetaItem label="Last checked" value={String(hostinger.last_checked_at ?? '--')} />
          </div>
          {hostinger.error_message ? <p className="inline-note">{hostinger.error_message}</p> : null}
          <h3>Metrics snapshot</h3>
          <pre>{pretty(JSON.stringify(hostinger.metrics ?? {}, null, 2))}</pre>
          <h3>Recent project logs</h3>
          <div className="feed-list">
            {((hostinger.project_logs ?? []) as Array<Record<string, any>>).slice(0, 5).map((item: Record<string, any>, index: number) => (
              <div className="feed-item" key={`${item.id ?? index}`}>
                <strong>{String(item.message ?? item.action ?? item.type ?? 'Project event')}</strong>
                <p>{String(item.createdAt ?? item.timestamp ?? item.date ?? '--')}</p>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Keyword pulse</h2><span>{(report.niche_pulse?.trending_queries ?? []).length}</span></div>
          <div className="pill-row">{(report.niche_pulse?.trending_queries ?? []).map((item: string) => <span className="pill" key={item}>{item}</span>)}</div>
          <h3>Top live search titles</h3>
          <ul className="bullet-list">{((comparison.top_search_titles ?? []) as string[]).map((item: string) => <li key={item}>{item}</li>)}</ul>
        </article>
        <article className="card">
          <div className="card-head"><h2>System health</h2><span className={`status status--${data.health.status}`}>{data.health.status}</span></div>
          <div className="table">{(data.state.setup_health?.connectors ?? []).map((item: Record<string, string>) => <div className="row" key={item.connector}><div><strong>{item.connector}</strong><p>{item.detail}</p></div><span className={`status status--${item.status}`}>{item.status}</span></div>)}</div>
        </article>
      </section>

      <button className="assistant-toggle" onClick={() => setAssistantOpen((current) => !current)}>
        {assistantOpen ? 'Close Copilot' : 'Open Copilot'}
      </button>

      {assistantOpen ? (
        <aside className="assistant-shell">
          <div className="assistant-head">
            <div>
              <p className="eyebrow">Gig Copilot</p>
              <strong>Ask from live app data</strong>
              <p className="assistant-subtitle">{assistantStatusLabel}</p>
              <div className="pill-row">
                <span className="pill">{String(comparison.primary_search_term ?? 'no primary term')}</span>
                <span className="pill">{topRankedGig.title ? `#1 ${topRankedGig.seller_name || 'leader'}` : 'no live leader yet'}</span>
                <span className="pill">{scraperRun.status ?? 'idle'} feed</span>
                <span className="pill">{datasets.length} knowledge file(s)</span>
              </div>
            </div>
            <button className="secondary" onClick={() => setAssistantOpen(false)}>Hide</button>
          </div>
          <div className="pill-row assistant-quick-prompts">
            {assistantQuickPrompts.map((suggestion) => (
              <button
                className="secondary pill-button"
                key={suggestion}
                onClick={() => void sendAssistantMessage(suggestion)}
                disabled={assistantBusy}
              >
                {suggestion}
              </button>
            ))}
          </div>
          <div className="assistant-log" ref={assistantLogRef}>
            {assistantMessages.map((entry, index) => (
              <div className={`assistant-bubble assistant-bubble--${entry.role}`} key={`${entry.role}-${index}`}>
                <strong>{entry.role === 'assistant' ? 'Copilot' : 'You'}</strong>
                <p>{entry.text}</p>
                {entry.suggestions?.length ? (
                  <div className="pill-row assistant-suggestion-row">
                    {entry.suggestions.map((suggestion) => (
                      <button
                        className="secondary pill-button"
                        key={suggestion}
                        onClick={() => void sendAssistantMessage(suggestion)}
                        disabled={assistantBusy}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
            {assistantBusy ? (
              <div className="assistant-bubble assistant-bubble--assistant assistant-bubble--pending">
                <strong>Copilot</strong>
                <p>Thinking through your live gig data...</p>
              </div>
            ) : null}
          </div>
          <div className="assistant-compose">
            <textarea
              ref={assistantInputRef}
              rows={3}
              value={assistantInput}
              onChange={(event) => setAssistantInput(event.target.value)}
              onKeyDown={handleAssistantKeyDown}
              placeholder="Ask anything about your gig, page-one competitors, title, pricing, trust, keywords, or what to change next..."
            />
            <button onClick={() => void sendAssistantMessage()} disabled={assistantBusy || !assistantInput.trim()}>
              {assistantBusy ? 'Thinking...' : 'Send'}
            </button>
          </div>
        </aside>
      ) : null}
    </main>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return <div className="meta-item"><span>{label}</span><strong>{value}</strong></div>
}

function Block({ title, body, action, busy }: { title: string; body: string; action: () => void; busy: boolean }) {
  return <div className="block"><div><p className="eyebrow">{title}</p><strong>{body}</strong></div><button className="secondary" onClick={action} disabled={busy || isPlaceholderText(body)}>Queue</button></div>
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

function isPlaceholderText(value: string) {
  const normalized = value.trim().toLowerCase()
  return !normalized || normalized === '--' || normalized.startsWith('no ')
}

function buildAssistantMessages(payload: BootstrapPayload) {
  const history = mapAssistantHistory(payload.assistant_history ?? payload.memory?.assistant_history ?? [], payload)
  if (history.length) return history
  return [
    {
      role: 'assistant' as const,
      text: "Ask me anything about your live Fiverr market position. I answer from the current page-one leaderboard, your gig comparison, and your recent scraper feed.",
      suggestions: buildAssistantQuickPrompts(payload.state.gig_comparison ?? {}, (payload.state.gig_comparison ?? {}).implementation_blueprint ?? {}, payload.state.scraper_run ?? {}),
    },
  ]
}

function mapAssistantHistory(items: Array<Record<string, any>>, payload: BootstrapPayload | null) {
  const quickPrompts = payload
    ? buildAssistantQuickPrompts(payload.state.gig_comparison ?? {}, (payload.state.gig_comparison ?? {}).implementation_blueprint ?? {}, payload.state.scraper_run ?? {})
    : []
  const mapped = [...items]
    .sort((left, right) => {
      const leftTime = Date.parse(String(left.created_at ?? ''))
      const rightTime = Date.parse(String(right.created_at ?? ''))
      if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime) && leftTime !== rightTime) {
        return leftTime - rightTime
      }
      return Number(left.id ?? 0) - Number(right.id ?? 0)
    })
    .map((item) => ({
      role: (item.role === 'user' ? 'user' : 'assistant') as 'user' | 'assistant',
      text: String(item.content ?? '').trim(),
      suggestions: item.role === 'assistant' ? ((item.metadata?.suggestions as string[] | undefined) ?? []) : undefined,
    }))
    .filter((item) => item.text)
  if (!mapped.length) return []
  const last = mapped[mapped.length - 1]
  if (last.role === 'assistant' && !last.suggestions?.length) {
    last.suggestions = quickPrompts
  }
  return mapped
}

function buildAssistantQuickPrompts(comparison: Record<string, any>, blueprint: Record<string, any>, scraperRun: Record<string, any>) {
  const primaryTerm = String(comparison.primary_search_term ?? '').trim()
  const topGig = comparison.top_ranked_gig ?? {}
  const topAction = blueprint.top_action ?? {}
  const prompts = [
    primaryTerm ? `Why is #1 ranking for ${primaryTerm}?` : '',
    topGig.title ? `How do I beat #1 ${String(topGig.seller_name ?? 'competitor')}?` : '',
    blueprint.recommended_title ? 'Rewrite my title using the current market demand.' : 'What title should I use now?',
    topAction.action_text ? 'What should I do first and why?' : '',
    scraperRun.last_status_message ? 'What is the live Fiverr feed showing right now?' : '',
    'How should I price my packages now?',
  ]
  return Array.from(new Set(prompts.filter(Boolean))).slice(0, 5)
}

function fileToBase64(file: File) {
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

export default App
