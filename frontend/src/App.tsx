import { useState, useRef, useEffect } from 'react'
import { fetchJson } from './api'
import { useBootstrap } from './hooks/useBootstrap'
import { useCsrf } from './hooks/useCsrf'
import { useAssistant } from './hooks/useAssistant'
import Layout from './layout/Layout'
import type { AppPageKey } from './layout/Sidebar'

import DashboardPage from './pages/DashboardPage'
import GigOptimizerPage from './pages/GigOptimizerPage'
import CompetitorPage from './pages/CompetitorPage'
import MetricsPage from './pages/MetricsPage'
import SettingsPage from './pages/SettingsPage'
import CopilotPage from './pages/CopilotPage'
import AIBrainPage from './pages/AIBrainPage'

import type { ComparisonTimelinePoint, ComparisonDiffPayload, FailedLoginAttemptRecord, ScraperSummary } from './types'

export default function App() {
  const { data, loading, error: bootstrapError, refresh } = useBootstrap()
  const { csrfToken, refreshCsrf } = useCsrf(data)
  const assistant = useAssistant(csrfToken, refreshCsrf)

  const [activePage, setActivePage] = useState<AppPageKey>('dashboard')
  const [gigUrl, setGigUrl] = useState('')
  const [terms, setTerms] = useState('')
  const [manualInput, setManualInput] = useState('')
  const [liveMode, setLiveMode] = useState(false)
  const [sortKey, setSortKey] = useState<'rank_position' | 'conversion_proxy_score' | 'reviews_count' | 'starting_price'>('rank_position')
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [maxResults, setMaxResults] = useState(10)
  const [autoCompareEnabled, setAutoCompareEnabled] = useState(false)
  const [autoCompareMinutes, setAutoCompareMinutes] = useState(5)
  const [showExtensionPrompt, setShowExtensionPrompt] = useState(true)
  const [extensionInstalled, setExtensionInstalled] = useState(false)
  const [knowledgeFile, setKnowledgeFile] = useState<File | null>(null)

  const lastMarketplaceSyncRef = useRef({ gigUrl: '', terms: '' })

  const displayError = error || bootstrapError

  useEffect(() => {
    let timer = 0
    function handleExtensionMessage(event: MessageEvent) {
      if (!event.data || event.data.source !== 'gigoptimizer-extension') return
      if (event.data.type === 'ready') {
        setExtensionInstalled(true)
        setShowExtensionPrompt(false)
      }
    }
    window.addEventListener('message', handleExtensionMessage)
    window.postMessage({ source: 'gigoptimizer-dashboard', type: 'gigoptimizer-extension-ping' }, window.location.origin)
    timer = window.setTimeout(() => {
      const dismissed = window.localStorage.getItem('gigoptimizer-extension-install-dismissed') === '1'
      if (!dismissed) setShowExtensionPrompt(true)
    }, 1200)
    return () => {
      window.removeEventListener('message', handleExtensionMessage)
      window.clearTimeout(timer)
    }
  }, [])

  useEffect(() => {
    if (!data) return
    const marketplace = data.state.notifications?.marketplace ?? {}
    const comparisonGigUrl = String(data.state.gig_comparison?.gig_url ?? '').trim()
    const comparisonTerms = Array.isArray(data.state.gig_comparison?.detected_search_terms)
      ? data.state.gig_comparison?.detected_search_terms ?? []
      : []
    const savedGigUrl = String(marketplace.my_gig_url ?? '').trim()
    const savedTerms = Array.isArray(marketplace.search_terms) ? marketplace.search_terms : []
    const nextGigUrl = savedGigUrl || comparisonGigUrl
    const nextTerms = (savedTerms.length ? savedTerms : comparisonTerms).join(', ')

    setGigUrl((current) => preserveMarketplaceDraft(current, lastMarketplaceSyncRef.current.gigUrl) ? current : nextGigUrl)
    setTerms((current) => preserveMarketplaceDraft(current, lastMarketplaceSyncRef.current.terms) ? current : nextTerms)
    lastMarketplaceSyncRef.current = { gigUrl: nextGigUrl, terms: nextTerms }
    setMaxResults(Number(marketplace.max_results ?? 10))
    setAutoCompareEnabled(Boolean(marketplace.auto_compare_enabled ?? false))
    setAutoCompareMinutes(Number(marketplace.auto_compare_interval_minutes ?? 5))
  }, [data?.state.notifications?.marketplace, data?.state.gig_comparison])

  async function withCsrfRetry<T>(operation: (token: string) => Promise<T>): Promise<T> {
    try {
      return await operation(csrfToken)
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : 'Request failed.'
      if (!/csrf/i.test(detail)) throw reason
      const nextToken = await refreshCsrf()
      return operation(nextToken)
    }
  }

  async function postJob(jobType: string, payload: Record<string, unknown> = {}) {
    if (!data) return
    setBusy(jobType)
    setError('')
    setMessage('')
    try {
      await withCsrfRetry((token) => fetchJson('/api/v2/jobs', { method: 'POST', body: JSON.stringify({ job_type: jobType, ...payload }) }, token))
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
      await withCsrfRetry((token) => fetchJson('/api/marketplace/recommendations/apply', { method: 'POST', body: JSON.stringify({ action_type: actionType, proposed_value: proposedValue }) }, token))
      setMessage('Recommendation added to the HITL queue.')
      void refresh()
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
      await withCsrfRetry((token) => fetchJson(`/api/queue/${recordId}/${action}`, { method: 'POST', body: JSON.stringify({ reviewer_notes: '' }) }, token))
      setMessage(`Queue item ${action}d.`)
      void refresh()
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
      await withCsrfRetry((token) => fetchJson('/api/settings', {
        method: 'POST',
        body: JSON.stringify({
          marketplace: { enabled: true, my_gig_url: gigUrl, search_terms: splitTerms(terms), max_results: maxResults, auto_compare_enabled: autoCompareEnabled, auto_compare_interval_minutes: autoCompareMinutes },
          slack: { enabled: true }
        })
      }, token))
      setMessage('Marketplace settings saved.')
      void refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save settings.')
    } finally {
      setBusy('')
    }
  }

  async function runNotificationTest(channel: 'slack') {
    if (!data) return
    setBusy(`test-${channel}`)
    try {
      const response = await withCsrfRetry((token) => fetchJson<{ result: { detail: string } }>('/api/settings/notifications/test', { method: 'POST', body: JSON.stringify({ channel }) }, token))
      setMessage(response.result.detail)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Unable to test ${channel}.`)
    } finally {
      setBusy('')
    }
  }

  async function uploadDataset() {
    if (!data || !knowledgeFile) return
    setBusy('upload-dataset')
    try {
      const contentBase64 = await fileToBase64(knowledgeFile)
      await withCsrfRetry((token) => fetchJson('/api/v2/datasets/upload', {
        method: 'POST',
        body: JSON.stringify({ filename: knowledgeFile.name, content_type: knowledgeFile.type || 'application/octet-stream', content_base64: contentBase64, gig_url: gigUrl })
      }, token))
      setKnowledgeFile(null)
      setMessage(`Uploaded ${knowledgeFile.name} to the copilot knowledge base.`)
      void refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Dataset upload failed.')
    } finally {
      setBusy('')
    }
  }

  async function deleteDataset(documentId: string) {
    if (!data) return
    setBusy(`delete-dataset-${documentId}`)
    try {
      await withCsrfRetry((token) => fetchJson(`/api/v2/datasets/${documentId}`, { method: 'DELETE' }, token))
      setMessage('Dataset removed from the copilot knowledge base.')
      void refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Dataset deletion failed.')
    } finally {
      setBusy('')
    }
  }

  async function reviewSecurityAttempt(attemptId: string, action: 'save' | 'discard') {
    if (!data) return
    setBusy(`security-${action}-${attemptId}`)
    try {
      await withCsrfRetry((token) => fetchJson(`/api/security/login-attempts/${attemptId}/${action}`, { method: 'POST' }, token))
      setMessage(action === 'save' ? 'Security capture saved.' : 'Security capture discarded.')
      void refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Security review action failed.')
    } finally {
      setBusy('')
    }
  }

  async function copyExtensionToken(token: string) {
    if (!token) return
    try {
      await navigator.clipboard.writeText(token)
      setMessage('Extension token copied to clipboard.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to copy the extension token.')
    }
  }

  function dismissExtensionPrompt() {
    window.localStorage.setItem('gigoptimizer-extension-install-dismissed', '1')
    setShowExtensionPrompt(false)
  }

  async function runCopilotTrainingExport() {
    if (!data) return
    setBusy('copilot-training-export')
    try {
      await withCsrfRetry((token) => fetchJson('/api/copilot/training/export', { method: 'POST' }, token))
      setMessage('Exported a fresh copilot training bundle.')
      void refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Export failed.')
    } finally {
      setBusy('')
    }
  }

  async function refreshHostinger() {
    if (!data) return
    setBusy('hostinger-refresh')
    try {
      await fetchJson('/api/hostinger/status', { method: 'GET' })
      setMessage('Hostinger status refreshed.')
      void refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to refresh Hostinger status.')
    } finally {
      setBusy('')
    }
  }

  function exportChat() {
    const markdown = assistant.messages.map(msg => `**${msg.role === 'assistant' ? 'Copilot' : 'You'}:** ${msg.text}`).join('\n\n---\n\n')
    const blob = new Blob([markdown], { type: 'text/markdown' })
    const anchor = document.createElement('a')
    anchor.href = URL.createObjectURL(blob)
    anchor.download = `copilot-chat-${Date.now()}.md`
    anchor.click()
    URL.revokeObjectURL(anchor.href)
  }

  async function sendAssistantFeedback(messageId: number, rating: 1 | -1) {
    setBusy(`feedback-${messageId}`)
    try {
      await withCsrfRetry((token) => fetchJson('/api/assistant/feedback', { method: 'POST', body: JSON.stringify({ message_id: messageId, rating }) }, token))
      setMessage(rating > 0 ? 'Saved positive copilot feedback.' : 'Saved negative copilot feedback.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save copilot feedback.')
    } finally {
      setBusy('')
    }
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

  if (loading || !data) return <main className="shell loading">Preparing the blueprint dashboard...</main>

  const report = data.state.latest_report ?? {}
  const comparison = data.state.gig_comparison ?? {}
  const blueprint = comparison.implementation_blueprint ?? {}
  const scraperRun = data.state.scraper_run ?? {}
  const hostinger = data.hostinger ?? {}
  const datasets = data.datasets ?? []
  const failureLogin = (data.security?.failed_login_attempts ?? []) as FailedLoginAttemptRecord[]
  const comparisonDiffPayload = (data.comparison_diff ?? { available: false, summary: '', changes: [] }) as ComparisonDiffPayload
  const timelinePoints = (data.timeline ?? []) as ComparisonTimelinePoint[]
  const radarData = [
    { name: 'Discovery', value: Math.max(12, Math.min(100, Math.round((data.state.metrics_history.at(-1)?.ctr ?? 0) * 12))) },
    { name: 'Conversion', value: Math.max(12, Math.min(100, Math.round((data.state.metrics_history.at(-1)?.conversion_rate ?? 0) * 10))) },
    { name: 'Trust', value: Math.max(12, Math.min(100, Math.round(report.optimization_score ?? 0))) }
  ]
  const quickPrompts = buildAssistantQuickPrompts(comparison, blueprint, scraperRun)

  return (
    <Layout
      activePage={activePage}
      onNavigate={setActivePage}
      pageTitle={activePage.charAt(0).toUpperCase() + activePage.slice(1)}
      wsLive={true}
      username={data.state.auth?.username || 'Admin'}
    >
      {(message || displayError) && <section className={`flash ${displayError ? 'flash--error' : ''}`} style={{ margin: '16px 24px' }}>{displayError || message}</section>}

      {activePage === 'dashboard' && (
        <DashboardPage
          heroMetrics={[
            { label: 'Optimization score', value: String(report.optimization_score ?? '--') },
            { label: 'Recommended title', value: blueprint.recommended_title ?? 'Run a market compare' },
            { label: 'Page-one gigs tracked', value: String(comparison.competitor_count ?? 0) },
            { label: 'Primary search term', value: String(comparison.primary_search_term ?? '--') }
          ]}
          scraperStatus={String(scraperRun.status ?? 'idle')}
          competitorCount={comparison.competitor_count ?? 0}
          pageOneCount={(comparison.first_page_top_10 ?? []).length}
          lastRunMessage={String(scraperRun.last_status_message ?? 'never')}
          dataLoaded={Boolean(data)}
          shouldShowExtensionPrompt={Boolean(data.extension_install?.enabled && !extensionInstalled && showExtensionPrompt)}
          extensionInstall={{
            apiBaseUrl: data.extension_install?.api_base_url || 'https://animha.co.in',
            tokenConfigured: Boolean(data.extension_install?.token_configured),
            apiToken: data.extension_install?.api_token || '',
            downloadUrl: data.extension_install?.download_url || '/downloads/fiverr-market-capture.zip',
            guideUrl: data.extension_install?.guide_url || '/extension/install'
          }}
          onCopyExtensionToken={copyExtensionToken}
          onDismissExtensionPrompt={dismissExtensionPrompt}
          comparisonStatus={String(comparison.status ?? 'idle')}
          topRankedGig={{
            title: String(comparison.top_ranked_gig?.title ?? 'Run a market compare'),
            sellerName: String(comparison.top_ranked_gig?.seller_name ?? 'Unknown seller'),
            rank: String(comparison.top_ranked_gig?.rank_position ?? 1),
            price: comparison.top_ranked_gig?.starting_price,
            reviews: String(comparison.top_ranked_gig?.reviews_count ?? '--'),
            term: String(comparison.primary_search_term ?? '--')
          }}
          topRankedReasons={comparison.top_ranked_gig?.why_on_page_one ?? []}
          whyCompetitorsWin={comparison.why_competitors_win ?? report.competitive_gap_analysis?.why_competitors_win ?? []}
          myGigTitle={String(comparison.my_gig?.title ?? '--')}
          myGigPrice={comparison.my_gig?.starting_price}
          myGigReviews={String(comparison.my_gig?.reviews_count ?? '--')}
          marketAnchorPrice={comparison.market_anchor_price}
          detectedTerms={comparison.detected_search_terms ?? []}
          titlePatterns={comparison.title_patterns ?? []}
          whatToImplement={comparison.what_to_implement ?? blueprint.weekly_actions ?? []}
          doThisFirst={comparison.do_this_first ?? (blueprint as Record<string, any>).do_this_first ?? []}
          failedLoginAttempts={failureLogin}
          onReviewSecurityAttempt={reviewSecurityAttempt}
          busy={busy}
          currentGigUrl={gigUrl}
          currentTerms={terms}
          topTrackedGigTitle={String(comparison.top_ranked_gig?.title ?? '--')}
        />
      )}

      {activePage === 'optimizer' && (
        <GigOptimizerPage
          liveMode={liveMode}
          onSetLiveMode={setLiveMode}
          gigUrl={gigUrl}
          onGigUrlChange={setGigUrl}
          terms={terms}
          onTermsChange={setTerms}
          manualInput={manualInput}
          onManualInputChange={setManualInput}
          busy={busy}
          onRunJob={postJob}
          maxResults={maxResults}
          onMaxResultsChange={setMaxResults}
          autoCompareEnabled={autoCompareEnabled}
          onToggleAutoCompare={() => setAutoCompareEnabled(!autoCompareEnabled)}
          autoCompareMinutes={autoCompareMinutes}
          onAutoCompareMinutesChange={setAutoCompareMinutes}
          onSaveMarketplaceSettings={saveMarketplaceSettings}
          onRunNotificationTest={runNotificationTest}
          slackConfigured={data.state.notifications?.slack?.configured ?? false}
          recommendedTitle={blueprint.recommended_title ?? ''}
          recommendedTags={blueprint.recommended_tags ?? []}
          titleOptions={blueprint.title_options ?? []}
          descriptionBlueprint={blueprint.description_blueprint ?? []}
          descriptionFull={blueprint.description_full}
          descriptionOptions={blueprint.description_options ?? []}
          pricingStrategy={blueprint.pricing_strategy ?? []}
          recommendedPackages={blueprint.recommended_packages ?? []}
          trustBoosters={blueprint.trust_boosters ?? []}
          faqRecommendations={blueprint.faq_recommendations ?? []}
          personaFocus={blueprint.persona_focus ?? []}
          onQueueRecommendation={queueRecommendation}
          onOpenAIBrain={() => setActivePage('brain')}
        />
      )}

      {activePage === 'competitors' && (
        <CompetitorPage
          pageOneTopTen={(comparison.first_page_top_10 ?? []).slice(0, 10)}
          oneByOne={comparison.one_by_one_recommendations ?? []}
          comparisonMessage={comparison.message}
          competitors={data.competitors ?? []}
          sortKey={sortKey}
          onSortKeyChange={setSortKey}
          timeline={timelinePoints}
          timelineChart={timelinePoints.map(t => ({ ...t, label: t.created_at || '' }))}
          comparisonDiff={comparisonDiffPayload}
        />
      )}

      {activePage === 'metrics' && (
        <MetricsPage
          metricsHistory={data.state.metrics_history ?? []}
          radar={radarData}
          competitorCount={comparison.competitor_count ?? 0}
          keywordScore={comparison.keyword_score ?? {}}
          primarySearchTerm={comparison.primary_search_term ?? ''}
          marketAnchorPrice={comparison.market_anchor_price}
          scraperSummary={(data.scraper_summary ?? { total_runs: 0, success_rate: 0, failure_rate: 0, avg_duration_ms: 0, last_success_at: '', last_error: '' }) as ScraperSummary}
          scraperLogs={data.scraper_logs ?? []}
          trendingQueries={report.niche_pulse?.trending_queries ?? []}
          topSearchTitles={comparison.top_search_titles ?? []}
          connectorHealth={data.state.setup_health?.connectors ?? []}
        />
      )}

      {activePage === 'settings' && (
        <SettingsPage
          knowledgeFile={knowledgeFile}
          onKnowledgeFileChange={setKnowledgeFile}
          onUploadDataset={uploadDataset}
          datasets={datasets}
          busy={busy}
          onDeleteDataset={deleteDataset}
          onAskCopilotAboutDataset={async (filename) => { setActivePage('copilot'); void assistant.sendMessage(`What can I use from ${filename} for my gig?`) }}
          memoryDocuments={data.memory?.knowledge_documents ?? []}
          copilotTraining={{
            status: data.copilot_training?.status || 'idle',
            trainExamples: Math.max(0, Number(data.copilot_training?.train_examples ?? 0)),
            holdoutExamples: Math.max(0, Number(data.copilot_training?.holdout_examples ?? 0)),
            preferenceExamples: Math.max(0, Number(data.copilot_training?.preference_examples ?? 0)),
            positiveFeedback: Math.max(0, Number(data.copilot_training?.feedback?.positive ?? 0)),
            recentTopics: Array.isArray(data.copilot_training?.recent_topics) ? data.copilot_training.recent_topics : []
          }}
          onRunCopilotTrainingExport={runCopilotTrainingExport}
          onAskCopilotLearned={async () => { setActivePage('copilot'); void assistant.sendMessage('What has the copilot learned from recent chats?') }}
          n8nProvider={(data as any).config?.ai_provider ?? 'n8n'}
          n8nWebhookUrl={(data as any).copilot?.model ?? '--'}
          latestAssistantTimestamp={'--'}
          queue={data.state.queue ?? []}
          selectedQueue={(data.state.queue ?? [])[0] ?? null}
          onReviewQueue={reviewQueue}
          activeJob={null}
          jobRuns={data.job_runs ?? []}
          hostinger={{
            status: hostinger.status,
            configured: hostinger.configured,
            projectName: hostinger.project_name,
            domain: hostinger.domain,
            selectedVm: hostinger.selected_vm?.id ?? hostinger.selected_vm?.name ?? hostinger.virtual_machine_id,
            lastCheckedAt: hostinger.last_checked_at,
            errorMessage: hostinger.error_message,
            metrics: hostinger.metrics ? JSON.stringify(hostinger.metrics) : '',
            projectLogs: Array.isArray(hostinger.project_logs) ? hostinger.project_logs.map((L: any, i: number) => ({ id: L.id ?? String(i), message: L.message ?? L.action ?? L.type ?? '', timestamp: L.createdAt ?? L.timestamp ?? L.date ?? '' })) : []
          }}
          onRefreshHostinger={refreshHostinger}
        />
      )}

      {activePage === 'copilot' && (
        <CopilotPage
          sessionId={assistant.sessionId}
          messages={assistant.messages}
          busy={assistant.busy}
          waitingForFirstChunk={assistant.waitingForFirstChunk}
          input={manualInput}
          onInputChange={setManualInput}
          onSendMessage={async (prefill) => { 
            await assistant.sendMessage(prefill ?? manualInput)
            if (!prefill) setManualInput('')
          }}
          onExportChat={exportChat}
          onSendFeedback={sendAssistantFeedback}
          quickPrompts={quickPrompts}
        />
      )}

      {activePage === 'brain' && (
        <AIBrainPage />
      )}
    </Layout>
  )
}

function splitTerms(value: string) {
  return value.split(/[\n,;]+/).map((item) => item.trim()).filter(Boolean)
}

function preserveMarketplaceDraft(currentValue: string, previousSyncedValue: string) {
  const current = currentValue.trim()
  const previous = previousSyncedValue.trim()
  return Boolean(current) && current !== previous
}

function fileToBase64(file: File) {
  return new Promise<string>((resolve) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result ?? '')
      const commaIndex = result.indexOf(',')
      resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result)
    }
    reader.readAsDataURL(file)
  })
}
