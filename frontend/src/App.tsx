import { startTransition, useMemo, useEffect, useState, type KeyboardEvent } from 'react'

import { createDashboardSocket, fetchJson, loadBootstrap, streamAssistantReply } from './api'
import { useToast } from './components/ui'
import { useCsrf } from './hooks/useCsrf'
import Layout from './layout/Layout'
import type { AppPageKey } from './layout/Sidebar'
import AIBrainPage from './pages/AIBrainPage'
import CompetitorPage from './pages/CompetitorPage'
import CopilotPage from './pages/CopilotPage'
import DashboardPage from './pages/DashboardPage'
import GigOptimizerPage from './pages/GigOptimizerPage'
import {
  activeJob,
  buildAssistantMessages,
  buildAssistantQuickPrompts,
  buildComparisonDiff,
  buildComparisonTimeline,
  buildConnectorHealth,
  buildKeywordScore,
  buildScraperLogs,
  buildScraperSummary,
  clamp,
  currencyValue,
  fileToBase64,
  mapAssistantHistory,
  numberValue,
  recordArray,
  recordValue,
  splitTerms,
  stringArray,
  textValue,
  type AssistantMessage,
  type CompetitorRecommendation,
  type DescriptionOption,
  type PersonaFocus,
  type RecommendedPackage,
  type TitleOption,
} from './pages/appModel'
import MetricsPage from './pages/MetricsPage'
import SettingsPage from './pages/SettingsPage'
import type { BootstrapPayload, CompetitorRecord, DashboardEvent, JobRun, LegacyState, QueueRecord } from './types'
import './App.css'

const PAGE_TITLES: Record<AppPageKey, string> = {
  dashboard: 'Dashboard',
  optimizer: 'Gig Optimizer',
  competitors: 'Competitors',
  copilot: 'Copilot',
  brain: 'AI Brain',
  metrics: 'Metrics',
  settings: 'Settings',
}

export default function App() {
  const [data, setData] = useState<BootstrapPayload | null>(null)
  const [gigUrl, setGigUrl] = useState('')
  const [terms, setTerms] = useState('')
  const [manualInput, setManualInput] = useState('')
  const [liveMode, setLiveMode] = useState(false)
  const [sortKey, setSortKey] = useState<'rank_position' | 'conversion_proxy_score' | 'reviews_count' | 'starting_price'>('rank_position')
  const [busy, setBusy] = useState('')
  const [maxResults, setMaxResults] = useState(10)
  const [autoCompareEnabled, setAutoCompareEnabled] = useState(false)
  const [autoCompareMinutes, setAutoCompareMinutes] = useState(5)
  const [assistantInput, setAssistantInput] = useState('')
  const [assistantBusy, setAssistantBusy] = useState(false)
  const [assistantMessages, setAssistantMessages] = useState<AssistantMessage[]>([])
  const [knowledgeFile, setKnowledgeFile] = useState<File | null>(null)
  const [activePage, setActivePage] = useState<AppPageKey>('dashboard')
  const [wsLive, setWsLive] = useState(false)
  const [fatalError, setFatalError] = useState('')
  const [extensionPromptDismissed, setExtensionPromptDismissed] = useState(false)
  const toast = useToast()
  const { csrfToken, refreshCsrf } = useCsrf(data)

  useEffect(() => {
    let active = true
    async function init() {
      try {
        const payload = await loadBootstrap()
        if (!active) return
        setFatalError('')
        startTransition(() => applyBootstrap(payload))
      } catch (reason) {
        if (!active) return
        setFatalError(reason instanceof Error ? reason.message : 'Unable to load dashboard.')
      }
    }
    void init()
    const socket = createDashboardSocket((event) => {
      if (!active) return
      startTransition(() => applyEvent(event))
    })
    socket.onopen = () => active && setWsLive(true)
    socket.onclose = () => active && setWsLive(false)
    socket.onerror = () => active && setWsLive(false)
    return () => {
      active = false
      setWsLive(false)
      socket.close()
    }
  }, [])

  function applyBootstrap(payload: BootstrapPayload) {
    setData(payload)
    const marketplace = recordValue(payload.state.notifications?.marketplace)
    const comparisonGigUrl = textValue(payload.state.gig_comparison?.gig_url).trim()
    const comparisonTerms = stringArray(payload.state.gig_comparison?.detected_search_terms)
    const savedGigUrl = textValue(marketplace.my_gig_url).trim()
    const savedTerms = stringArray(marketplace.search_terms)
    setGigUrl(comparisonGigUrl || savedGigUrl)
    setTerms((comparisonTerms.length ? comparisonTerms : savedTerms).join(', '))
    setMaxResults(numberValue(marketplace.max_results) ?? 10)
    setAutoCompareEnabled(Boolean(marketplace.auto_compare_enabled ?? false))
    setAutoCompareMinutes(numberValue(marketplace.auto_compare_interval_minutes) ?? 5)
    setAssistantMessages(buildAssistantMessages(payload))
  }

  function applyEvent(event: DashboardEvent) {
    setData((current) => {
      if (!current) return current
      if (event.type === 'state') {
        const nextState = event.payload as LegacyState
        return { ...current, state: { ...current.state, ...nextState }, queue: nextState.queue ?? current.queue }
      }
      if (event.type === 'scraper_activity') {
        return { ...current, state: { ...current.state, scraper_run: event.payload } }
      }
      if (['job_queued', 'job_progress', 'job_completed', 'job_failed'].includes(event.type)) {
        const incoming = event.payload as JobRun
        return { ...current, job_runs: [incoming, ...current.job_runs.filter((item) => item.run_id !== incoming.run_id)].slice(0, 25) }
      }
      return current
    })
    if (event.type === 'job_completed' || event.type === 'scraper_done') {
      if (event.type === 'scraper_done') toast.info('Scraper finished - dashboard updated.')
      void refresh(false)
    }
  }

  async function withCsrfRetry<T>(operation: (csrfToken: string) => Promise<T>): Promise<T> {
    if (!data) throw new Error('Dashboard is still loading.')
    try {
      return await operation(csrfToken)
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : 'Request failed.'
      if (!/csrf/i.test(detail)) throw reason
      const nextToken = await refreshCsrf()
      const payload = await loadBootstrap()
      startTransition(() => applyBootstrap(payload))
      return operation(nextToken)
    }
  }

  async function refresh(showToast = true) {
    try {
      const payload = await loadBootstrap()
      applyBootstrap(payload)
      setFatalError('')
      if (showToast) toast.info('Dashboard refreshed.')
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : 'Refresh failed.'
      toast.error(detail)
      if (!data) setFatalError(detail)
    }
  }

  async function refreshHostinger() {
    if (!data) return
    setBusy('hostinger-refresh')
    try {
      const response = await fetchJson<{ hostinger: Record<string, unknown> }>('/api/hostinger/status', { method: 'GET' })
      setData({ ...data, hostinger: response.hostinger })
      toast.success('Hostinger status refreshed.')
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : 'Unable to refresh Hostinger status.')
    } finally {
      setBusy('')
    }
  }

  async function postJob(jobType: string, payload: Record<string, unknown> = {}) {
    if (!data) return
    setBusy(jobType)
    try {
      const response = await withCsrfRetry((csrfToken) => fetchJson<BootstrapPayload>('/api/v2/jobs', { method: 'POST', body: JSON.stringify({ job_type: jobType, ...payload }) }, csrfToken))
      applyBootstrap(response)
      toast.success(`Queued ${jobType.replaceAll('_', ' ')} job.`)
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : 'Job request failed.')
    } finally {
      setBusy('')
    }
  }

  async function queueRecommendation(actionType: string, proposedValue: unknown) {
    if (!data) return
    setBusy(actionType)
    try {
      const nextState = await withCsrfRetry((csrfToken) => fetchJson<LegacyState>('/api/marketplace/recommendations/apply', { method: 'POST', body: JSON.stringify({ action_type: actionType, proposed_value: proposedValue }) }, csrfToken))
      setData({ ...data, state: { ...data.state, ...nextState }, queue: nextState.queue ?? data.queue })
      toast.success('Recommendation added to the review queue.')
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : 'Unable to queue the recommendation.')
    } finally {
      setBusy('')
    }
  }

  async function reviewQueue(recordId: string, action: 'approve' | 'reject') {
    if (!data) return
    setBusy(`${action}-${recordId}`)
    try {
      const nextState = await withCsrfRetry((csrfToken) => fetchJson<LegacyState>(`/api/queue/${recordId}/${action}`, { method: 'POST', body: JSON.stringify({ reviewer_notes: '' }) }, csrfToken))
      setData({ ...data, state: { ...data.state, ...nextState }, queue: nextState.queue ?? data.queue })
      toast.success(`Queue item ${action}d.`)
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : 'Queue action failed.')
    } finally {
      setBusy('')
    }
  }

  async function saveMarketplaceSettings() {
    if (!data) return
    setBusy('save-settings')
    try {
      const settings = await withCsrfRetry((csrfToken) => fetchJson<Record<string, unknown>>('/api/settings', { method: 'POST', body: JSON.stringify({ marketplace: { enabled: true, my_gig_url: gigUrl, search_terms: splitTerms(terms), max_results: maxResults, auto_compare_enabled: autoCompareEnabled, auto_compare_interval_minutes: autoCompareMinutes }, slack: { enabled: true } }) }, csrfToken))
      setData({ ...data, state: { ...data.state, notifications: settings } })
      toast.success('Marketplace settings saved.')
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : 'Unable to save settings.')
    } finally {
      setBusy('')
    }
  }

  async function runNotificationTest(channel: 'slack') {
    if (!data) return
    setBusy(`test-${channel}`)
    try {
      const response = await withCsrfRetry((csrfToken) => fetchJson<{ result: { detail: string } }>('/api/settings/notifications/test', { method: 'POST', body: JSON.stringify({ channel }) }, csrfToken))
      toast.success(response.result.detail)
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : `Unable to test ${channel}.`)
    } finally {
      setBusy('')
    }
  }

  async function sendAssistantMessage(prefill?: string) {
    if (!data) return
    const question = (prefill ?? assistantInput).trim()
    if (!question) return
    const userMessageId = `user-${Date.now().toString(36)}`
    const assistantMessageId = `assistant-${Date.now().toString(36)}`
    setAssistantBusy(true)
    setAssistantMessages((current) => [...current, { id: userMessageId, role: 'user', text: question }, { id: assistantMessageId, role: 'assistant', text: '', suggestions: [], pending: true }])
    setAssistantInput('')
    try {
      let streamError = ''
      let streamedText = ''
      let streamFinished = false
      let streamedSuggestions: string[] = []
      await withCsrfRetry((csrfToken) => streamAssistantReply('/api/assistant/chat/stream', { message: question }, {
        onChunk: (chunk) => {
          streamedText += chunk
          setAssistantMessages((current) => current.map((entry) => entry.id === assistantMessageId ? { ...entry, text: streamedText, pending: true, suggestions: streamedSuggestions } : entry))
        },
        onSuggestions: (suggestions) => {
          streamedSuggestions = suggestions
          setAssistantMessages((current) => current.map((entry) => entry.id === assistantMessageId ? { ...entry, suggestions } : entry))
        },
        onDone: (payload) => {
          streamFinished = true
          const nextMessages = mapAssistantHistory(recordArray(payload.assistant_history), data)
          if (nextMessages.length) {
            setAssistantMessages(nextMessages)
            return
          }
          const assistant = recordValue(payload.assistant)
          setAssistantMessages((current) => current.map((entry) => entry.id === assistantMessageId ? { ...entry, text: textValue(assistant.reply).trim() || streamedText.trim(), suggestions: stringArray(assistant.suggestions).length ? stringArray(assistant.suggestions) : streamedSuggestions, pending: false, provider: textValue(assistant.provider) || undefined } : entry))
        },
        onError: (detail) => {
          streamError = detail
        },
      }, csrfToken))
      if (streamError) throw new Error(streamError)
      if (!streamFinished) {
        const response = await withCsrfRetry((csrfToken) => fetchJson<{ assistant: { reply: string; suggestions?: string[]; provider?: string }; assistant_history?: Array<Record<string, unknown>> }>('/api/assistant/chat', { method: 'POST', body: JSON.stringify({ message: question }) }, csrfToken))
        const nextMessages = mapAssistantHistory(response.assistant_history ?? [], data)
        if (nextMessages.length) {
          setAssistantMessages(nextMessages)
        } else {
          setAssistantMessages((current) => current.map((entry) => entry.id === assistantMessageId ? { ...entry, text: response.assistant.reply, suggestions: response.assistant.suggestions ?? [], pending: false, provider: response.assistant.provider } : entry))
        }
      }
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : 'Assistant request failed.'
      setAssistantMessages((current) => current.map((entry) => entry.id === assistantMessageId ? { ...entry, text: detail, suggestions: [], pending: false } : entry))
      toast.error(detail)
    } finally {
      setAssistantBusy(false)
    }
  }

  async function uploadDataset() {
    if (!data || !knowledgeFile) return
    setBusy('upload-dataset')
    try {
      const contentBase64 = await fileToBase64(knowledgeFile)
      const response = await withCsrfRetry((csrfToken) => fetchJson<BootstrapPayload>('/api/v2/datasets/upload', { method: 'POST', body: JSON.stringify({ filename: knowledgeFile.name, content_type: knowledgeFile.type || 'application/octet-stream', content_base64: contentBase64, gig_url: gigUrl }) }, csrfToken))
      applyBootstrap(response)
      setKnowledgeFile(null)
      toast.success(`Uploaded ${knowledgeFile.name} to the knowledge base.`)
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : 'Dataset upload failed.')
    } finally {
      setBusy('')
    }
  }

  async function deleteDataset(documentId: string) {
    if (!data) return
    setBusy(`delete-dataset-${documentId}`)
    try {
      const response = await withCsrfRetry((csrfToken) => fetchJson<BootstrapPayload>(`/api/v2/datasets/${documentId}`, { method: 'DELETE' }, csrfToken))
      applyBootstrap(response)
      toast.success('Dataset removed from the knowledge base.')
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : 'Dataset deletion failed.')
    } finally {
      setBusy('')
    }
  }

  async function askCopilotAboutDataset(filename: string) {
    setActivePage('copilot')
    await sendAssistantMessage(`What can I use from ${filename} for my Fiverr gig right now?`)
  }

  async function handleLogout() {
    if (!data) return
    try {
      await withCsrfRetry((csrfToken) => fetchJson<Record<string, never>>('/api/auth/logout', { method: 'POST', body: JSON.stringify({}) }, csrfToken))
    } catch {
      // Ignore logout failures and still navigate to login.
    } finally {
      window.location.href = '/login'
    }
  }

  async function copyExtensionToken(token: string) {
    if (!token) {
      toast.warning('No extension API token is configured yet.')
      return
    }
    try {
      await navigator.clipboard.writeText(token)
      toast.success('Extension API token copied.')
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : 'Unable to copy the extension token.')
    }
  }

  function handleAssistantKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void sendAssistantMessage()
    }
  }

  if (!data) {
    return (
      <main className="shell loading">
        <div className="loading-panel">
          <strong>{fatalError ? 'Dashboard failed to load' : 'Preparing the blueprint dashboard...'}</strong>
          <p>{fatalError || 'Loading your live workspace and connected market data.'}</p>
          {fatalError ? <button type="button" onClick={() => void refresh(false)}>Try again</button> : null}
        </div>
      </main>
    )
  }

  const report = recordValue(data.state.latest_report)
  const comparison = recordValue(data.state.gig_comparison)
  const blueprint = recordValue(comparison.implementation_blueprint)
  const scraperRun = recordValue(data.state.scraper_run)
  const hostinger = recordValue(data.hostinger)
  const datasets = data.datasets ?? []
  const slackSettings = recordValue(data.state.notifications?.slack)
  const extensionSettings = recordValue(data.state.notifications?.extension)
  const myGig = recordValue(comparison.my_gig)
  const titleOptions = (comparison.title_options ?? blueprint.title_options ?? []) as TitleOption[]
  const descriptionOptions = (blueprint.description_options ?? []) as DescriptionOption[]
  const recommendedPackages = (blueprint.recommended_packages ?? []) as RecommendedPackage[]
  const personaFocus = (blueprint.persona_focus ?? []) as PersonaFocus[]
  const topTen = ((comparison.first_page_top_10 ?? []) as CompetitorRecord[]).slice(0, 10)
  const oneByOne = (comparison.one_by_one_recommendations ?? []) as CompetitorRecommendation[]
  const topRankedGig = recordValue(comparison.top_ranked_gig ?? topTen[0])
  const topRankedReasons = stringArray(comparison.why_top_ranked_gig_is_first).length ? stringArray(comparison.why_top_ranked_gig_is_first) : stringArray(topRankedGig.why_on_page_one)
  const competitorSource = topTen.length ? topTen : data.competitors
  const competitors = [...competitorSource].sort((left, right) => {
    if (sortKey === 'rank_position') return Number(left.rank_position ?? 999) - Number(right.rank_position ?? 999)
    const leftValue = Number(left[sortKey] ?? 0)
    const rightValue = Number(right[sortKey] ?? 0)
    return sortKey === 'starting_price' ? leftValue - rightValue : rightValue - leftValue
  })
  const queue: QueueRecord[] = (data.state.queue?.length ? data.state.queue : data.queue) as QueueRecord[]
  const comparisonHistory = recordArray(data.state.comparison_history)
  const assistantQuickPrompts = buildAssistantQuickPrompts(comparison, blueprint, scraperRun)
  const assistantStarterPrompts = assistantQuickPrompts.slice(0, 3)
  const extensionToken = textValue(extensionSettings.api_token)
  const extensionDownloadUrl = textValue(extensionSettings.download_url) || '/downloads/fiverr-market-capture.zip'
  const extensionGuideUrl = textValue(extensionSettings.guide_url) || '/extension/install'
  const extensionPromptVisible = !extensionPromptDismissed && !Boolean(extensionSettings.installed)
  const pageTitle = PAGE_TITLES[activePage]
  const pageContent = useMemo(() => {
    const comparisonDiff = buildComparisonDiff(comparisonHistory)
    const timeline = buildComparisonTimeline(comparisonHistory)
    const radar = [
      { name: 'Discovery', value: clamp((data.state.metrics_history[data.state.metrics_history.length - 1]?.ctr ?? 0) * 12) },
      { name: 'Conversion', value: clamp((data.state.metrics_history[data.state.metrics_history.length - 1]?.conversion_rate ?? 0) * 10) },
      { name: 'Keywords', value: clamp(stringArray(recordValue(report.niche_pulse).trending_queries).length * 16) },
      { name: 'Actions', value: clamp(stringArray(blueprint.weekly_actions).length * 18) },
      { name: 'Trust', value: clamp(numberValue(report.optimization_score) ?? 0) },
    ]
    switch (activePage) {
      case 'dashboard':
        return <DashboardPage optimizationScore={numberValue(report.optimization_score) ?? '--'} recommendedTitle={textValue(blueprint.recommended_title)} pageOneTracked={topTen.length} primarySearchTerm={textValue(comparison.primary_search_term)} scraperStatus={textValue(scraperRun.status)} competitorCount={numberValue(comparison.competitor_count) ?? competitors.length} lastRunMessage={textValue(scraperRun.last_status_message)} extensionPromptVisible={extensionPromptVisible} extensionDownloadUrl={extensionDownloadUrl} extensionGuideUrl={extensionGuideUrl} extensionTokenConfigured={Boolean(extensionToken)} extensionToken={extensionToken} extensionApiBaseUrl={window.location.origin} onCopyExtensionToken={copyExtensionToken} onDismissExtensionPrompt={() => setExtensionPromptDismissed(true)} comparisonStatus={textValue(comparison.status)} topRankedTitle={textValue(topRankedGig.title)} topRankedSeller={textValue(topRankedGig.seller_name)} topRankedRank={topRankedGig.rank_position ? `#${String(topRankedGig.rank_position)}` : '--'} topRankedPrice={numberValue(topRankedGig.starting_price)} topRankedReviews={String(topRankedGig.reviews_count ?? '--')} topRankedTerm={textValue(topRankedGig.matched_term) || textValue(comparison.primary_search_term)} topRankedReasons={topRankedReasons} whyCompetitorsWin={stringArray(comparison.why_competitors_win).length ? stringArray(comparison.why_competitors_win) : stringArray(recordValue(report.competitive_gap_analysis).why_competitors_win)} myGigTitle={textValue(myGig.title)} myGigPrice={numberValue(myGig.starting_price)} myGigReviews={String(myGig.reviews_count ?? '--')} marketAnchorPrice={numberValue(comparison.market_anchor_price)} detectedTerms={stringArray(comparison.detected_search_terms)} titlePatterns={stringArray(comparison.title_patterns)} whatToImplement={stringArray(comparison.what_to_implement).length ? stringArray(comparison.what_to_implement) : stringArray(blueprint.weekly_actions)} doThisFirst={stringArray(comparison.do_this_first).length ? stringArray(comparison.do_this_first) : stringArray(blueprint.do_this_first)} currentGigUrl={gigUrl} currentTerms={terms} topTrackedGigTitle={textValue(topTen[0]?.title)} datasets={datasets} />
      case 'optimizer':
        return <GigOptimizerPage liveMode={liveMode} onSetLiveMode={setLiveMode} gigUrl={gigUrl} onGigUrlChange={setGigUrl} terms={terms} onTermsChange={setTerms} manualInput={manualInput} onManualInputChange={setManualInput} busy={busy} onRunJob={postJob} maxResults={maxResults} onMaxResultsChange={setMaxResults} autoCompareEnabled={autoCompareEnabled} onToggleAutoCompare={() => setAutoCompareEnabled((current) => !current)} autoCompareMinutes={autoCompareMinutes} onAutoCompareMinutesChange={setAutoCompareMinutes} onSaveMarketplaceSettings={saveMarketplaceSettings} onRunNotificationTest={runNotificationTest} slackConfigured={Boolean(slackSettings.configured)} recommendedTitle={textValue(blueprint.recommended_title)} recommendedTags={stringArray(blueprint.recommended_tags)} titleOptions={titleOptions} descriptionBlueprint={stringArray(blueprint.description_blueprint)} descriptionFull={textValue(blueprint.description_full)} descriptionOptions={descriptionOptions} pricingStrategy={stringArray(blueprint.pricing_strategy)} recommendedPackages={recommendedPackages} trustBoosters={stringArray(blueprint.trust_boosters)} faqRecommendations={stringArray(blueprint.faq_recommendations)} personaFocus={personaFocus} missingTags={stringArray(recordValue(comparison.tag_gap).missing_tags)} powerTags={stringArray(recordValue(comparison.tag_gap).power_tags)} tagCoverageScore={String(numberValue(recordValue(comparison.tag_gap).coverage_score) ?? '--')} onQueueRecommendation={queueRecommendation} onOpenAIBrain={() => setActivePage('brain')} />
      case 'competitors':
        return <CompetitorPage pageOneTopTen={topTen} oneByOne={oneByOne} comparisonMessage={textValue(comparison.message) || textValue(comparison.status_message) || textValue(scraperRun.last_status_message)} competitors={competitors} sortKey={sortKey} onSortKeyChange={setSortKey} timeline={timeline} timelineChart={timeline} comparisonDiff={comparisonDiff} radar={radar} competitorCount={numberValue(comparison.competitor_count) ?? competitors.length} />
      case 'copilot':
        return <CopilotPage messages={assistantMessages} busy={assistantBusy} input={assistantInput} onInputChange={setAssistantInput} onSendMessage={sendAssistantMessage} onKeyDown={handleAssistantKeyDown} assistantStarterPrompts={assistantStarterPrompts} assistantQuickPrompts={assistantQuickPrompts} />
      case 'brain':
        return <AIBrainPage csrfToken={csrfToken} refreshCsrf={refreshCsrf} />
      case 'metrics':
        return <MetricsPage metricsHistory={data.state.metrics_history} keywordScore={buildKeywordScore(comparison, report)} primarySearchTerm={textValue(comparison.primary_search_term)} marketAnchorPrice={currencyValue(numberValue(comparison.market_anchor_price))} scraperSummary={buildScraperSummary(comparison, scraperRun)} scraperLogs={buildScraperLogs(comparison, scraperRun)} trendingQueries={stringArray(recordValue(report.niche_pulse).trending_queries)} topSearchTitles={stringArray(comparison.top_search_titles)} connectorHealth={buildConnectorHealth(recordValue(data.state.setup_health).connectors, data.state.connector_status)} />
      case 'settings':
        return <SettingsPage knowledgeFile={knowledgeFile} onKnowledgeFileChange={setKnowledgeFile} onUploadDataset={uploadDataset} datasets={datasets} busy={busy} onDeleteDataset={deleteDataset} onAskCopilotAboutDataset={askCopilotAboutDataset} memoryDocuments={recordArray(data.memory?.knowledge_documents)} queue={queue} selectedQueue={queue[0]} onReviewQueue={reviewQueue} activeJob={activeJob(data.job_runs)} jobRuns={data.job_runs} hostinger={hostinger} onRefreshHostinger={refreshHostinger} />
      default:
        return null
    }
  }, [activePage, assistantBusy, assistantInput, assistantMessages, assistantQuickPrompts, assistantStarterPrompts, autoCompareEnabled, autoCompareMinutes, blueprint, busy, comparison, comparisonHistory, competitors, csrfToken, data, datasets, extensionDownloadUrl, extensionGuideUrl, extensionPromptVisible, extensionToken, gigUrl, hostinger, knowledgeFile, liveMode, manualInput, maxResults, oneByOne, personaFocus, queue, refreshCsrf, report, scraperRun, slackSettings, sortKey, terms, titleOptions, topRankedGig, topRankedReasons, topTen])

  return (
    <Layout
      activePage={activePage}
      pageTitle={pageTitle}
      wsLive={wsLive}
      username={data.state.auth.username}
      onNavigate={setActivePage}
      onLogout={() => { void handleLogout() }}
    >
      {pageContent}
    </Layout>
  )
}
