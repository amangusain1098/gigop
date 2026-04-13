import { useEffect, useMemo, useState } from 'react'

import {
  fetchTrainingDashboard,
  fetchTrainingPredictions,
  ingestTrainingText,
  runTrainingCycle,
  runTrainingDashboardTests,
  updateTrainingSchedule,
  type TrainingDashboardPayload,
  type TrainingPredictionPayload,
} from '../api'
import { useToast } from '../components/ui'
import { EmptyState, shortDate } from './helpers'

interface AIBrainPageProps {
  csrfToken: string
  refreshCsrf: () => Promise<string>
}

const SCHEDULE_INTERVALS = [1, 3, 6, 12, 24]

function recordValue(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function numberValue(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function textValue(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function wordPredictions(payload: TrainingPredictionPayload) {
  const source = Array.isArray(payload.predictions) ? payload.predictions : []
  return source.map((item) => {
    if (typeof item === 'string') {
      return { word: item, score: 0 }
    }
    const entry = recordValue(item)
    return {
      word: textValue(entry.word) || textValue(entry.text) || '--',
      score: numberValue(entry.score),
    }
  })
}

export default function AIBrainPage({ csrfToken, refreshCsrf }: AIBrainPageProps) {
  const [dashboard, setDashboard] = useState<TrainingDashboardPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [predictionInput, setPredictionInput] = useState('')
  const [predictions, setPredictions] = useState<Array<{ word: string; score: number }>>([])
  const [ingestOpen, setIngestOpen] = useState(false)
  const [ingestText, setIngestText] = useState('')
  const toast = useToast()

  async function withCsrfRetry<T>(operation: (token: string) => Promise<T>) {
    try {
      return await operation(csrfToken)
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : 'Request failed.'
      if (!/csrf/i.test(detail)) throw reason
      const nextToken = await refreshCsrf()
      return operation(nextToken)
    }
  }

  async function loadDashboard() {
    try {
      const payload = await fetchTrainingDashboard()
      setDashboard(payload)
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load AI Brain data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadDashboard()
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      const query = predictionInput.trim()
      if (!query) {
        setPredictions([])
        return
      }
      try {
        const payload = await fetchTrainingPredictions(query, 8)
        setPredictions(wordPredictions(payload))
      } catch {
        setPredictions([])
      }
    }, 300)

    return () => window.clearTimeout(timer)
  }, [predictionInput])

  const stats = useMemo(() => {
    const source = recordValue(dashboard?.stats)
    return {
      vocabSize: numberValue(source.vocab_size),
      documentsIngested: numberValue(source.documents_ingested),
      trainingCycles: numberValue(source.training_cycles),
      bigramPairs: numberValue(source.bigram_pairs),
    }
  }, [dashboard])

  const topWords = useMemo(() => {
    const source = Array.isArray(dashboard?.top_words) ? dashboard?.top_words : []
    return source.slice(0, 20).map((item) => {
      const record = recordValue(item)
      return {
        word: textValue(record.word) || '--',
        score: numberValue(record.score),
        frequency: numberValue(record.frequency),
        idf: numberValue(record.idf),
      }
    })
  }, [dashboard])

  const activity = Array.isArray(dashboard?.recent_activity) ? dashboard?.recent_activity.slice(0, 20) : []
  const schedule = recordValue(dashboard?.schedule)
  const testResults = recordValue(dashboard?.test_results)

  async function runAction(name: string, action: () => Promise<unknown>, successMessage: string) {
    setBusy(name)
    try {
      await action()
      toast.success(successMessage)
      await loadDashboard()
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : 'Action failed.')
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      <section className="content-grid">
        {[['Vocabulary', stats.vocabSize], ['Documents', stats.documentsIngested], ['Cycles', stats.trainingCycles], ['Bigrams', stats.bigramPairs]].map(([label, value]) => (
          <article className="card" key={String(label)}>
            <div className="card-head"><h2>{label}</h2></div>
            <div className="metric metric--brain">
              <strong>{String(value)}</strong>
            </div>
          </article>
        ))}
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Top learned words</h2><span>{topWords.length}</span></div>
          {loading ? <div className="table">{Array.from({ length: 6 }).map((_, index) => <div className="skeleton-row" key={index} />)}</div> : topWords.length ? (
            <div className="table">
              {topWords.map((item) => (
                <div className="row row--stacked" key={item.word}>
                  <div className="row-topline">
                    <strong>{item.word}</strong>
                    <span>{item.score.toFixed(2)}</span>
                  </div>
                  <div className="progress"><div style={{ width: `${Math.min(100, Math.max(8, item.score * 10))}%` }} /></div>
                  <div className="row-metrics">
                    <span>Freq {item.frequency}</span>
                    <span>IDF {item.idf.toFixed(2)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon="AI" title="No learned words yet" hint={error || 'The AI Brain will fill in once the training endpoint returns data.'} />
          )}
        </article>

        <article className="card">
          <div className="card-head"><h2>Word prediction demo</h2><span>top 8</span></div>
          <input value={predictionInput} onChange={(event) => setPredictionInput(event.target.value)} placeholder="Type a phrase like wordpress spe..." />
          {predictions.length ? (
            <div className="pill-row">
              {predictions.map((item) => (
                <span className="pill" key={`${item.word}-${item.score}`}>{item.word} ({item.score.toFixed(2)})</span>
              ))}
            </div>
          ) : (
            <p className="inline-note">Start typing to preview likely next words from the current model.</p>
          )}
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Recent activity feed</h2><span>{activity.length}</span></div>
          {activity.length ? (
            <div className="feed-list">
              {activity.map((item, index) => {
                const record = recordValue(item)
                return (
                  <div className="feed-item" key={`${textValue(record.id) || index}`}>
                    <strong>{textValue(record.title) || textValue(record.event) || 'Learning event'}</strong>
                    <p>{textValue(record.detail) || textValue(record.message) || '--'}</p>
                    <span>{shortDate(textValue(record.created_at) || textValue(record.timestamp))}</span>
                  </div>
                )
              })}
            </div>
          ) : (
            <EmptyState icon="LG" title="No recent activity yet" hint={error || 'Training events will appear here after the first successful cycle.'} />
          )}
        </article>

        <article className="card">
          <div className="card-head"><h2>Training controls</h2><span>{busy || 'ready'}</span></div>
          <div className="button-row button-row--three">
            <button disabled={busy === 'train'} onClick={() => void runAction('train', () => withCsrfRetry(runTrainingCycle), 'Training cycle queued.')}>{busy === 'train' ? 'Running...' : 'Run training now'}</button>
            <button className="secondary" disabled={busy === 'tests'} onClick={() => void runAction('tests', () => withCsrfRetry(runTrainingDashboardTests), 'Training tests started.')}>{busy === 'tests' ? 'Running...' : 'Run tests'}</button>
            <button className="secondary" onClick={() => setIngestOpen((current) => !current)}>{ingestOpen ? 'Close ingest' : 'Ingest text'}</button>
          </div>
          {ingestOpen ? (
            <div className="stack">
              <textarea rows={6} value={ingestText} onChange={(event) => setIngestText(event.target.value)} placeholder="Paste text to teach the copilot..." />
              <button disabled={busy === 'ingest' || !ingestText.trim()} onClick={() => void runAction('ingest', () => withCsrfRetry((token) => ingestTrainingText({ content: ingestText, source_type: 'manual_ingest', source: 'ai_brain' }, token)), 'Text sent to the training pipeline.')}>{busy === 'ingest' ? 'Ingesting...' : 'Submit text'}</button>
            </div>
          ) : null}
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Training schedule</h2><span>{String(schedule.enabled ?? false) === 'true' ? 'enabled' : 'paused'}</span></div>
          <div className="meta-grid">
            <div className="meta-item"><span>Interval</span><strong>{textValue(schedule.interval_label) || `${numberValue(schedule.interval_hours) || 0}h`}</strong></div>
            <div className="meta-item"><span>Last run</span><strong>{shortDate(textValue(schedule.last_run_at))}</strong></div>
            <div className="meta-item"><span>Next run</span><strong>{shortDate(textValue(schedule.next_run_at))}</strong></div>
            <div className="meta-item"><span>Status</span><strong>{String(schedule.enabled ?? false) === 'true' ? 'Enabled' : 'Paused'}</strong></div>
          </div>
          <div className="pill-row">
            {SCHEDULE_INTERVALS.map((hours) => (
              <button key={hours} className="quick-prompt-chip" disabled={busy === `schedule-${hours}`} onClick={() => void runAction(`schedule-${hours}`, () => withCsrfRetry((token) => updateTrainingSchedule({ interval_hours: hours, enabled: true }, token)), `Training schedule set to every ${hours} hour(s).`)}>
                {hours}h
              </button>
            ))}
            <button className="secondary" disabled={busy === 'schedule-pause'} onClick={() => void runAction('schedule-pause', () => withCsrfRetry((token) => updateTrainingSchedule({ enabled: false }, token)), 'Training schedule paused.')}>Pause</button>
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>Test results</h2><span>last run</span></div>
          <div className="meta-grid">
            <div className="meta-item"><span>Passed</span><strong>{String(numberValue(testResults.passed))}</strong></div>
            <div className="meta-item"><span>Failed</span><strong>{String(numberValue(testResults.failed))}</strong></div>
            <div className="meta-item"><span>Errors</span><strong>{String(numberValue(testResults.errors))}</strong></div>
            <div className="meta-item"><span>Updated</span><strong>{shortDate(textValue(testResults.updated_at))}</strong></div>
          </div>
        </article>
      </section>
    </>
  )
}
