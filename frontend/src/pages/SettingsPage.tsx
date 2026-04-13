import type { DatasetRecord, JobRun, QueueRecord } from '../types'
import { MetaItem, pretty } from './helpers'

interface HostingerData {
  status?: string
  configured?: boolean
  project_name?: string
  domain?: string
  virtual_machine_id?: string
  last_checked_at?: string
  error_message?: string
  metrics?: Record<string, unknown>
  project_logs?: Array<Record<string, unknown>>
  selected_vm?: {
    id?: string
    name?: string
  }
}

interface SettingsPageProps {
  knowledgeFile: File | null
  onKnowledgeFileChange: (file: File | null) => void
  onUploadDataset: () => Promise<void>
  datasets: DatasetRecord[]
  busy: string
  onDeleteDataset: (documentId: string) => Promise<void>
  onAskCopilotAboutDataset: (filename: string) => Promise<void>
  memoryDocuments: Array<Record<string, unknown>>
  queue: QueueRecord[]
  selectedQueue?: QueueRecord
  onReviewQueue: (recordId: string, action: 'approve' | 'reject') => Promise<void>
  activeJob?: JobRun
  jobRuns: JobRun[]
  hostinger: HostingerData
  onRefreshHostinger: () => Promise<void>
}

function human(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (match) => match.toUpperCase())
}

export default function SettingsPage({
  knowledgeFile,
  onKnowledgeFileChange,
  onUploadDataset,
  datasets,
  busy,
  onDeleteDataset,
  onAskCopilotAboutDataset,
  memoryDocuments,
  queue,
  selectedQueue,
  onReviewQueue,
  activeJob,
  jobRuns,
  hostinger,
  onRefreshHostinger,
}: SettingsPageProps) {
  return (
    <>
      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Knowledge base</h2><span>{datasets.length} file(s)</span></div>
          <p className="inline-note">
            Upload CSV, JSON, Markdown, HTML, TXT, or DOCX files. The copilot will retrieve from these files when you ask
            questions about your gig, competitors, reviews, package strategy, or niche history.
          </p>
          <div className="form-grid">
            <input
              type="file"
              accept=".txt,.md,.markdown,.json,.csv,.html,.htm,.docx"
              onChange={(event) => onKnowledgeFileChange(event.target.files?.[0] ?? null)}
            />
            <button onClick={() => void onUploadDataset()} disabled={busy === 'upload-dataset' || !knowledgeFile}>
              {busy === 'upload-dataset' ? 'Uploading...' : 'Upload dataset'}
            </button>
          </div>
          <div className="table">
            {datasets.length ? datasets.map((item) => (
              <div className="row row--stacked" key={item.id}>
                <div className="row-topline">
                  <strong>{item.filename}</strong>
                  <span className={`status status--${item.status === 'ready' ? 'ok' : 'queued'}`}>{item.status}</span>
                </div>
                <p>{item.preview || 'No preview extracted yet.'}</p>
                <div className="row-metrics">
                  <span>{Math.max(1, Math.round((item.size_bytes || 0) / 1024))} KB</span>
                  <span>{item.metadata?.chunk_count ?? 0} chunks</span>
                  <span>{item.created_at ?? '--'}</span>
                </div>
                <div className="button-row button-row--two">
                  <button className="secondary" onClick={() => void onAskCopilotAboutDataset(item.filename)}>
                    Ask copilot
                  </button>
                  <button
                    className="secondary"
                    onClick={() => void onDeleteDataset(item.id)}
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
          <div className="card-head"><h2>Copilot memory</h2><span>{memoryDocuments.length} linked docs</span></div>
          <ul className="bullet-list">
            {memoryDocuments.map((item) => (
              <li key={String(item.id)}>{String(item.filename ?? 'dataset')} - {String(item.preview ?? '').slice(0, 140)}</li>
            ))}
          </ul>
          {!memoryDocuments.length ? (
            <p className="inline-note">Once you upload data, the copilot will pull relevant snippets into each answer.</p>
          ) : null}
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>HITL queue</h2><span>{queue.length}</span></div>
          {selectedQueue ? (
            <>
              <div className="progress"><div style={{ width: `${selectedQueue.confidence_score}%` }} /></div>
              <div className="diff"><pre>{pretty(selectedQueue.current_value)}</pre><pre>{pretty(selectedQueue.proposed_value)}</pre></div>
              <div className="pill-row">{(selectedQueue.validator_issues ?? []).map((issue) => <span className="pill" key={issue.code}>{issue.code}: {issue.message}</span>)}</div>
              <div className="button-row button-row--two">
                <button onClick={() => void onReviewQueue(selectedQueue.id, 'approve')} disabled={busy === `approve-${selectedQueue.id}`}>Approve</button>
                <button className="secondary" onClick={() => void onReviewQueue(selectedQueue.id, 'reject')} disabled={busy === `reject-${selectedQueue.id}`}>Reject</button>
              </div>
            </>
          ) : <p>No queue items yet.</p>}
        </article>

        <article className="card">
          <div className="card-head"><h2>Job progress</h2><a href="/rq">queue overview</a></div>
          {activeJob ? <div className="job"><div className="progress"><div style={{ width: `${Math.max(5, Math.round((activeJob.progress || 0) * 100))}%` }} /></div><strong>{human(activeJob.run_type)}</strong><p>{activeJob.current_stage || activeJob.output_summary || 'Queued'}</p></div> : <p>No jobs yet.</p>}
          <div className="table">{jobRuns.map((job) => <div className="row" key={job.run_id}><div><strong>{human(job.run_type)}</strong><p>{job.output_summary || job.current_stage || 'Queued'}</p></div><span className={`status status--${job.status}`}>{job.status}</span></div>)}</div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Hostinger ops</h2><button className="secondary" onClick={() => void onRefreshHostinger()} disabled={busy === 'hostinger-refresh'}>{busy === 'hostinger-refresh' ? 'Refreshing...' : 'Refresh ops'}</button></div>
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
            {(hostinger.project_logs ?? []).slice(0, 5).map((item, index) => (
              <div className="feed-item" key={`${String(item.id ?? index)}`}>
                <strong>{String(item.message ?? item.action ?? item.type ?? 'Project event')}</strong>
                <p>{String(item.createdAt ?? item.timestamp ?? item.date ?? '--')}</p>
              </div>
            ))}
          </div>
        </article>
      </section>
    </>
  )
}
