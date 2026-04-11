import { useEffect, useRef, useState, useCallback } from 'react'
import { fetchJson } from './api'

interface TopWord { word: string; freq: number; idf: number }
interface ModelStats { vocab_size: number; doc_count: number; bigram_count: number; top_words: TopWord[] }
interface LearningEvent {
  event_id: string; timestamp: string; source: string; source_type: string
  tokens_learned?: number; new_words?: number
}
interface TestResults {
  status: string; total: number; passed: number; failed: number; errors: number
  elapsed_s?: number; run_at?: string; output_tail?: string
}
interface Schedule {
  enabled: boolean; interval: string; interval_seconds: number
  last_run: string | null; next_run: string | null; run_count: number
}
interface CorpusDoc { id: string; source: string; source_type: string; ingested_at: string; token_count: number; text_preview: string }
interface DashboardStats {
  version: string; model: ModelStats
  totals: { total_docs: number; total_tokens: number; total_new_words: number; last_updated?: string }
  schedule: Schedule; recent_learning: LearningEvent[]
  test_results: TestResults; corpus_docs: CorpusDoc[]
}
interface Completion { type: string; completion: string; score: number; full_suggestion: string }

function ts(iso: string | null | undefined) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString() } catch { return iso }
}
function statusColor(s: string) {
  if (s === 'pass') return '#22c55e'
  if (s === 'fail' || s === 'error') return '#ef4444'
  if (s === 'never_run') return '#94a3b8'
  return '#f59e0b'
}
function sourceIcon(t: string) {
  if (t === 'conversation') return '💬'
  if (t === 'cron') return '⏰'
  if (t === 'manual') return '✏️'
  return '📄'
}
function btnStyle(bg: string): React.CSSProperties {
  return { background: bg, color: '#fff', border: 'none', borderRadius: 8, padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }
}
function kpiCard(color?: string): React.CSSProperties {
  return { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '14px 16px', textAlign: 'center', borderTop: `3px solid ${color ?? '#e2e8f0'}` }
}
const panelStyle: React.CSSProperties = { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 20, marginBottom: 20 }
const panelTitle: React.CSSProperties = { margin: '0 0 14px', fontSize: 15, fontWeight: 700, color: '#1e293b' }
const inputStyle: React.CSSProperties = { width: '100%', padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 13, outline: 'none', marginTop: 4, boxSizing: 'border-box' }
const labelStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', fontSize: 13, fontWeight: 600, color: '#374151' }

type Panel = 'overview' | 'predict' | 'tests' | 'corpus' | 'schedule' | 'ingest'

export default function CopilotTrainingDashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [activePanel, setActivePanel] = useState<Panel>('overview')
  const [predictQuery, setPredictQuery] = useState('')
  const [completions, setCompletions] = useState<Completion[]>([])
  const predictTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [ingestText, setIngestText] = useState('')
  const [ingestSource, setIngestSource] = useState('')
  const [scheduleInterval, setScheduleInterval] = useState('6h')
  const [scheduleEnabled, setScheduleEnabled] = useState(true)
  const [testOutput, setTestOutput] = useState('')
  const logRef = useRef<HTMLPreElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const d = await fetchJson<DashboardStats>('/api/copilot/training-dashboard')
      setStats(d)
      setScheduleInterval(d.schedule?.interval ?? '6h')
      setScheduleEnabled(d.schedule?.enabled ?? true)
    } catch (e: unknown) { setLoadError(String(e)) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])
  useEffect(() => { const t = setInterval(() => { void load() }, 30000); return () => clearInterval(t) }, [load])

  useEffect(() => {
    if (predictTimeout.current) clearTimeout(predictTimeout.current)
    if (!predictQuery.trim()) { setCompletions([]); return }
    predictTimeout.current = setTimeout(async () => {
      try {
        const r = await fetchJson<{ completions: Completion[] }>(
          `/api/copilot/training-dashboard/predict?q=${encodeURIComponent(predictQuery)}&top_n=10`
        )
        setCompletions(r.completions ?? [])
      } catch { setCompletions([]) }
    }, 300)
  }, [predictQuery])

  function flash(m: string) { setMsg(m); setTimeout(() => setMsg(''), 4000) }

  async function runTraining() {
    setBusy('train')
    try {
      const r = await fetchJson<{ steps: unknown[] }>('/api/copilot/training-dashboard/train', {
        method: 'POST', headers: { 'X-CSRF-Token': 'skip' }, body: JSON.stringify({}),
      })
      flash(`Training cycle complete — ${r.steps?.length ?? 0} step(s) run`)
      void load()
    } catch (e) { flash('Training failed: ' + String(e)) }
    finally { setBusy('') }
  }

  async function runTests() {
    setBusy('tests')
    setTestOutput('')
    try {
      const r = await fetchJson<TestResults>('/api/copilot/training-dashboard/run-tests', {
        method: 'POST', headers: { 'X-CSRF-Token': 'skip' }, body: JSON.stringify({}),
      })
      setTestOutput(r.output_tail ?? '')
      void load()
      setTimeout(() => logRef.current?.scrollIntoView({ behavior: 'smooth' }), 300)
    } catch (e) { flash('Test run failed: ' + String(e)) }
    finally { setBusy('') }
  }

  async function submitIngest() {
    if (!ingestText.trim()) { flash('Enter text to ingest'); return }
    setBusy('ingest')
    try {
      const r = await fetchJson<{ ingested: boolean; tokens_learned?: number; new_words?: number }>(
        '/api/copilot/training-dashboard/ingest',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'skip' },
          body: JSON.stringify({ text: ingestText, source: ingestSource || 'manual-ui', source_type: 'manual' }),
        }
      )
      if (r.ingested) {
        flash(`Ingested: ${r.tokens_learned ?? 0} tokens, ${r.new_words ?? 0} new words`)
        setIngestText('')
        setIngestSource('')
        void load()
      } else {
        flash('Not ingested — text may be too short')
      }
    } catch (e) { flash('Ingest failed: ' + String(e)) }
    finally { setBusy('') }
  }

  async function saveSchedule() {
    setBusy('schedule')
    try {
      await fetchJson('/api/copilot/training-dashboard/schedule', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'skip' },
        body: JSON.stringify({ interval: scheduleInterval, enabled: scheduleEnabled }),
      })
      flash('Schedule saved')
      void load()
    } catch (e) { flash('Save failed: ' + String(e)) }
    finally { setBusy('') }
  }

  if (loading && !stats) return (
    <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Loading Copilot Training Dashboard…</div>
  )
  if (loadError) return (
    <div style={{ padding: 40 }}>
      <div style={{ color: '#ef4444', marginBottom: 12 }}>{loadError}</div>
      <button onClick={() => void load()}>Retry</button>
    </div>
  )

  const s = stats!
  const tr = s.test_results
  const sc = s.schedule
  const PANELS: [Panel, string][] = [
    ['overview', '📊 Overview'],
    ['predict', '🔮 Word Prediction'],
    ['tests', '🧪 Tests'],
    ['corpus', '📂 Corpus'],
    ['schedule', '⏰ Schedule'],
    ['ingest', '➕ Ingest'],
  ]

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', maxWidth: 1100, margin: '0 auto', padding: '24px 16px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>🧠 Copilot Training Dashboard</h1>
          <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 13 }}>
            Model v{s.version} · {s.model.vocab_size.toLocaleString()} words · {s.model.doc_count} docs ingested
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => void runTraining()} disabled={busy === 'train'} style={btnStyle('#3b82f6')}>
            {busy === 'train' ? '⏳ Training…' : '▶ Run Training Cycle'}
          </button>
          <button onClick={() => void load()} style={btnStyle('#64748b')}>↻ Refresh</button>
        </div>
      </div>

      {msg && (
        <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 8, padding: '10px 14px', marginBottom: 16, color: '#166534', fontSize: 13 }}>
          {msg}
        </div>
      )}

      {/* KPI cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 24 }}>
        {([
          { label: 'Vocabulary', value: s.model.vocab_size.toLocaleString(), icon: '📚', color: '#3b82f6' },
          { label: 'Documents', value: s.totals.total_docs?.toLocaleString() ?? '0', icon: '📄', color: '#8b5cf6' },
          { label: 'Tokens Learned', value: s.totals.total_tokens?.toLocaleString() ?? '0', icon: '🔤', color: '#06b6d4' },
          { label: 'New Words', value: s.totals.total_new_words?.toLocaleString() ?? '0', icon: '✨', color: '#f59e0b' },
          { label: 'Bigrams', value: s.model.bigram_count.toLocaleString(), icon: '🔗', color: '#64748b' },
          { label: 'Cron Cycles', value: sc.run_count?.toString() ?? '0', icon: '⏰', color: '#64748b' },
          {
            label: 'Tests',
            value: tr.status === 'never_run' ? 'Not run' : `${tr.passed}/${tr.total}`,
            icon: tr.status === 'pass' ? '✅' : tr.status === 'never_run' ? '⬜' : '❌',
            color: statusColor(tr.status),
          },
        ] as { label: string; value: string; icon: string; color: string }[]).map(card => (
          <div key={card.label} style={kpiCard(card.color)}>
            <div style={{ fontSize: 20, marginBottom: 4 }}>{card.icon}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: card.color }}>{card.value}</div>
            <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{card.label}</div>
          </div>
        ))}
      </div>

      {/* Tab nav */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '2px solid #e2e8f0', paddingBottom: 0 }}>
        {PANELS.map(([id, label]) => (
          <button key={id} onClick={() => setActivePanel(id)} style={{
            border: 'none', background: 'none', padding: '8px 14px', cursor: 'pointer', fontSize: 13,
            fontWeight: activePanel === id ? 700 : 400,
            color: activePanel === id ? '#3b82f6' : '#64748b',
            borderBottom: activePanel === id ? '2px solid #3b82f6' : '2px solid transparent',
            marginBottom: -2,
          }}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Overview ── */}
      {activePanel === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div style={panelStyle}>
            <h3 style={panelTitle}>Top Learned Words</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {s.model.top_words.slice(0, 24).map(w => (
                <span key={w.word} style={{
                  background: `hsl(${Math.floor(w.idf * 40)}, 70%, 92%)`,
                  border: `1px solid hsl(${Math.floor(w.idf * 40)}, 60%, 80%)`,
                  borderRadius: 20, padding: '3px 10px', fontSize: 12, color: '#1e293b',
                  fontWeight: w.freq > 5 ? 600 : 400,
                }}>
                  {w.word}<span style={{ color: '#94a3b8', fontSize: 10, marginLeft: 4 }}>×{w.freq}</span>
                </span>
              ))}
              {s.model.top_words.length === 0 && (
                <p style={{ color: '#94a3b8', fontSize: 13 }}>No vocabulary yet — run a training cycle to populate.</p>
              )}
            </div>
          </div>

          <div style={panelStyle}>
            <h3 style={panelTitle}>Recent Learning Events</h3>
            {s.recent_learning.length === 0
              ? <p style={{ color: '#94a3b8', fontSize: 13 }}>No learning events yet.</p>
              : s.recent_learning.slice(0, 8).map(ev => (
                <div key={ev.event_id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 12, marginBottom: 8 }}>
                  <span style={{ fontSize: 16 }}>{sourceIcon(ev.source_type)}</span>
                  <div>
                    <div style={{ fontWeight: 600, color: '#1e293b' }}>{ev.source}</div>
                    <div style={{ color: '#64748b' }}>
                      {ev.tokens_learned != null ? `${ev.tokens_learned} tokens · ${ev.new_words ?? 0} new words · ` : ''}{ts(ev.timestamp)}
                    </div>
                  </div>
                </div>
              ))
            }
          </div>

          <div style={panelStyle}>
            <h3 style={panelTitle}>⏰ Cron Schedule</h3>
            <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
              <tbody>
                {([
                  ['Status', sc.enabled ? '🟢 Active' : '🔴 Paused'],
                  ['Interval', sc.interval],
                  ['Last Run', ts(sc.last_run)],
                  ['Next Run', ts(sc.next_run)],
                  ['Cycles Run', sc.run_count?.toString() ?? '0'],
                ] as [string, string][]).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ color: '#64748b', paddingRight: 12, paddingBottom: 6, width: 120 }}>{k}</td>
                    <td style={{ fontWeight: 500, color: '#1e293b' }}>{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={panelStyle}>
            <h3 style={panelTitle}>🧪 Latest Test Results</h3>
            {tr.status === 'never_run'
              ? <div>
                  <p style={{ color: '#94a3b8', fontSize: 13, marginBottom: 12 }}>Tests have not been run yet.</p>
                  <button onClick={() => { setActivePanel('tests'); void runTests() }} style={btnStyle('#3b82f6')}>Run Tests Now</button>
                </div>
              : <div>
                  <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
                    {([['Total', tr.total, '#64748b'], ['Passed', tr.passed, '#22c55e'], ['Failed', tr.failed, '#ef4444'], ['Errors', tr.errors, '#f59e0b']] as [string, number, string][]).map(([l, v, c]) => (
                      <div key={l} style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 22, fontWeight: 700, color: c }}>{v}</div>
                        <div style={{ fontSize: 11, color: '#94a3b8' }}>{l}</div>
                      </div>
                    ))}
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>
                    <span style={{ color: statusColor(tr.status), fontWeight: 600 }}>{tr.status.toUpperCase()}</span>
                    {tr.elapsed_s != null ? ` · ${tr.elapsed_s}s` : ''}
                    {tr.run_at ? ` · ${ts(tr.run_at)}` : ''}
                  </div>
                </div>
            }
          </div>
        </div>
      )}

      {/* ── Word Prediction ── */}
      {activePanel === 'predict' && (
        <div style={panelStyle}>
          <h3 style={panelTitle}>🔮 AI Word and Query Prediction</h3>
          <p style={{ color: '#64748b', fontSize: 13, marginBottom: 16 }}>
            Type a partial query. The copilot predicts completions from its learned vocabulary —
            this powers unpredictable-question handling in real conversations.
          </p>
          <input value={predictQuery} onChange={e => setPredictQuery(e.target.value)}
            placeholder="e.g. optimize my fi…" style={inputStyle} autoFocus />
          {completions.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
                {completions.length} completion{completions.length !== 1 ? 's' : ''} found
              </div>
              {completions.map((c, i) => (
                <div key={i} onClick={() => setPredictQuery(c.full_suggestion)}
                  style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', marginBottom: 6, borderRadius: 8, background: '#f8fafc', border: '1px solid #e2e8f0', cursor: 'pointer' }}>
                  <span style={{ fontSize: 16 }}>{c.type === 'phrase' ? '🔗' : '🔤'}</span>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontWeight: 600, color: '#1e293b' }}>{c.full_suggestion}</span>
                    <span style={{ fontSize: 11, color: '#94a3b8', marginLeft: 8 }}>+{c.completion}</span>
                  </div>
                  <span style={{ fontSize: 11, color: '#64748b', background: '#e2e8f0', borderRadius: 4, padding: '2px 6px' }}>
                    score {c.score}
                  </span>
                </div>
              ))}
            </div>
          )}
          {predictQuery.trim() && completions.length === 0 && (
            <p style={{ color: '#94a3b8', fontSize: 13, marginTop: 16 }}>
              No completions for "{predictQuery}" — ingest more documents or run a training cycle to expand vocabulary.
            </p>
          )}
          {s.model.vocab_size === 0 && (
            <div style={{ background: '#fef9c3', border: '1px solid #fde047', borderRadius: 8, padding: 14, marginTop: 20, fontSize: 13 }}>
              Vocabulary is empty. Run a Training Cycle first to populate the prediction model.
            </div>
          )}
        </div>
      )}

      {/* ── Tests ── */}
      {activePanel === 'tests' && (
        <div style={panelStyle}>
          <h3 style={panelTitle}>🧪 Test Suite</h3>
          <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
            <button onClick={() => void runTests()} disabled={busy === 'tests'} style={btnStyle('#3b82f6')}>
              {busy === 'tests' ? '⏳ Running…' : '▶ Run All Tests'}
            </button>
          </div>
          {tr.status !== 'never_run' && (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
              {([
                { label: 'Status', value: tr.status.toUpperCase(), color: statusColor(tr.status) },
                { label: 'Total', value: tr.total, color: '#1e293b' },
                { label: 'Passed', value: tr.passed, color: '#22c55e' },
                { label: 'Failed', value: tr.failed, color: '#ef4444' },
                { label: 'Errors', value: tr.errors, color: '#f59e0b' },
                { label: 'Time', value: tr.elapsed_s != null ? `${tr.elapsed_s}s` : '—', color: '#64748b' },
              ] as { label: string; value: string | number; color: string }[]).map(item => (
                <div key={item.label} style={kpiCard(item.color)}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: item.color }}>{item.value}</div>
                  <div style={{ fontSize: 11, color: '#64748b' }}>{item.label}</div>
                </div>
              ))}
            </div>
          )}
          <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 8 }}>
            Suites: test_copilot_round3 · test_marketplace_reader · test_conversation_memory · test_assistant
          </div>
          {(testOutput || tr.output_tail) && (
            <pre ref={logRef} style={{
              background: '#0f172a', color: '#e2e8f0', borderRadius: 8, padding: 16,
              fontSize: 11, overflowX: 'auto', whiteSpace: 'pre-wrap', maxHeight: 400, overflowY: 'auto',
            }}>
              {testOutput || tr.output_tail}
            </pre>
          )}
        </div>
      )}

      {/* ── Corpus ── */}
      {activePanel === 'corpus' && (
        <div style={panelStyle}>
          <h3 style={panelTitle}>📂 Ingested Corpus ({s.corpus_docs.length} documents)</h3>
          {s.corpus_docs.length === 0
            ? <p style={{ color: '#94a3b8', fontSize: 13 }}>No documents ingested yet. Use the Ingest tab to add training data.</p>
            : s.corpus_docs.map(doc => (
              <div key={doc.id} style={{ background: '#f8fafc', borderRadius: 8, padding: '10px 14px', border: '1px solid #e2e8f0', marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{sourceIcon(doc.source_type)} {doc.source}</span>
                  <span style={{ fontSize: 11, color: '#94a3b8' }}>{ts(doc.ingested_at)}</span>
                </div>
                <div style={{ fontSize: 12, color: '#64748b', marginBottom: 6 }}>{doc.token_count} tokens · {doc.source_type}</div>
                <div style={{ fontSize: 12, color: '#94a3b8', fontStyle: 'italic' }}>
                  {doc.text_preview.slice(0, 180)}{doc.text_preview.length > 180 ? '…' : ''}
                </div>
              </div>
            ))
          }
        </div>
      )}

      {/* ── Schedule ── */}
      {activePanel === 'schedule' && (
        <div style={panelStyle}>
          <h3 style={panelTitle}>⏰ Cron Training Schedule</h3>
          <p style={{ color: '#64748b', fontSize: 13, marginBottom: 20 }}>
            The copilot automatically scans your conversations and ingests new Q&amp;A pairs on this schedule.
            The more frequently it runs, the faster it learns from real user interactions.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 400 }}>
            <label style={labelStyle}>
              Training Interval
              <select value={scheduleInterval} onChange={e => setScheduleInterval(e.target.value)} style={inputStyle}>
                <option value="1h">Every 1 hour</option>
                <option value="6h">Every 6 hours (recommended)</option>
                <option value="12h">Every 12 hours</option>
                <option value="24h">Every 24 hours</option>
                <option value="48h">Every 48 hours</option>
              </select>
            </label>
            <label style={{ ...labelStyle, flexDirection: 'row', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
              <input type="checkbox" checked={scheduleEnabled} onChange={e => setScheduleEnabled(e.target.checked)} style={{ width: 16, height: 16 }} />
              Enable automatic cron training
            </label>
            <button onClick={() => void saveSchedule()} disabled={busy === 'schedule'} style={btnStyle('#3b82f6')}>
              {busy === 'schedule' ? '⏳ Saving…' : '💾 Save Schedule'}
            </button>
          </div>
          <div style={{ marginTop: 24, background: '#f8fafc', borderRadius: 8, padding: 16, border: '1px solid #e2e8f0' }}>
            <h4 style={{ margin: '0 0 12px', fontSize: 13 }}>Current State</h4>
            <table style={{ fontSize: 13, borderCollapse: 'collapse', width: '100%' }}>
              <tbody>
                {([
                  ['Status', sc.enabled ? '🟢 Enabled' : '🔴 Disabled'],
                  ['Interval', `${sc.interval} (${sc.interval_seconds}s)`],
                  ['Last Run', ts(sc.last_run)],
                  ['Next Run', ts(sc.next_run)],
                  ['Total Cycles', sc.run_count?.toString() ?? '0'],
                ] as [string, string][]).map(([k, v]) => (
                  <tr key={k} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ color: '#64748b', padding: '6px 12px 6px 0', width: 160 }}>{k}</td>
                    <td style={{ color: '#1e293b', fontWeight: 500 }}>{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Ingest ── */}
      {activePanel === 'ingest' && (
        <div style={panelStyle}>
          <h3 style={panelTitle}>➕ Manually Ingest Training Data</h3>
          <p style={{ color: '#64748b', fontSize: 13, marginBottom: 20 }}>
            Paste any text — gig descriptions, FAQs, conversations, docs — to teach the copilot new vocabulary.
            Longer, domain-specific content produces better word prediction.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 700 }}>
            <label style={labelStyle}>
              Source label (optional)
              <input value={ingestSource} onChange={e => setIngestSource(e.target.value)}
                placeholder="e.g. fiverr-gig-description, faq-doc" style={inputStyle} />
            </label>
            <label style={labelStyle}>
              Text to ingest
              <textarea value={ingestText} onChange={e => setIngestText(e.target.value)}
                placeholder="Paste gig descriptions, FAQs, help docs, or any domain text here…"
                rows={10} style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }} />
            </label>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => void submitIngest()} disabled={busy === 'ingest' || !ingestText.trim()} style={btnStyle('#22c55e')}>
                {busy === 'ingest' ? '⏳ Ingesting…' : '➕ Ingest Text'}
              </button>
              <button onClick={() => { setIngestText(''); setIngestSource('') }} style={btnStyle('#64748b')}>Clear</button>
            </div>
            <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 8, padding: 12, fontSize: 12, color: '#166534' }}>
              💡 <strong>Tip:</strong> After ingesting, switch to the Word Prediction tab to verify the new completions work.
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
