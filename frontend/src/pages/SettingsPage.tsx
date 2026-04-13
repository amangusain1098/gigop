import type { SettingsPageProps } from './shared'
import { MetaItem, human, pretty, shortDate } from './shared'

export default function SettingsPage({
  knowledgeFile,
  onKnowledgeFileChange,
  onUploadDataset,
  datasets,
  busy,
  onDeleteDataset,
  onAskCopilotAboutDataset,
  memoryDocuments,
  copilotTraining,
  onRunCopilotTrainingExport,
  onAskCopilotLearned,
  n8nProvider,
  n8nWebhookUrl,
  latestAssistantTimestamp,
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
                  <span>{item.created_at ? shortDate(item.created_at) : '--'}</span>
                </div>
                <div className="button-row button-row--two">
                  <button className="secondary" onClick={() => void onAskCopilotAboutDataset(item.filename)}>Ask copilot</button>
                  <button className="secondary" onClick={() => void onDeleteDataset(item.id)} disabled={busy === `delete-dataset-${item.id}`}>
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
              <li key={item.id}>{item.filename} - {item.preview.slice(0, 140)}</li>
            ))}
          </ul>
          {!memoryDocuments.length ? (
            <p className="inline-note">Once you upload data, the copilot will pull relevant snippets into each answer.</p>
          ) : null}
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Copilot training data</h2><span className={`status status--${copilotTraining.status === 'completed' ? 'ok' : 'queued'}`}>{copilotTraining.status}</span></div>
          <div className="meta-grid">
            <MetaItem label="Train examples" value={String(copilotTraining.trainExamples)} />
            <MetaItem label="Holdout examples" value={String(copilotTraining.holdoutExamples)} />
            <MetaItem label="Preference pairs" value={String(copilotTraining.preferenceExamples)} />
            <MetaItem label="Positive feedback" value={String(copilotTraining.positiveFeedback)} />
          </div>
          <p className="inline-note">
            This training bundle is built from live copilot chats, upload context, and your thumbs up/down signals.
          </p>
          <div className="pill-row">
            {copilotTraining.recentTopics.slice(0, 6).map((topic) => (
              <span className="pill" key={topic}>{topic}</span>
            ))}
          </div>
          <div className="button-row button-row--two">
            <button onClick={() => void onRunCopilotTrainingExport()} disabled={busy === 'copilot-training-export'}>
              {busy === 'copilot-training-export' ? 'Exporting...' : 'Export training bundle'}
            </button>
            <button className="secondary" onClick={() => void onAskCopilotLearned()}>
              Ask what it learned
            </button>
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>n8n Automation</h2><span className="status status--queued">monitoring</span></div>
          <div className="meta-grid">
            <MetaItem label="AI Provider" value={n8nProvider} />
            <MetaItem label="Webhook URL" value={n8nWebhookUrl} />
            <MetaItem label="Last copilot response" value={latestAssistantTimestamp} />
          </div>
          <div className="pill-row">
            {['Daily gig health', 'Competitor alert', 'Knowledge refresh', 'Report generator', 'Stripe sync'].map((workflow) => (
              <span className="pill" key={workflow}>{workflow}</span>
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
              <div className="diff"><pre>{pretty(String(selectedQueue.current_value))}</pre><pre>{pretty(String(selectedQueue.proposed_value))}</pre></div>
              <div className="pill-row">{(selectedQueue.validator_issues ?? []).map((issue) => <span className="pill" key={issue.code}>{issue.code}: {issue.message}</span>)}</div>
              <div className="button-row button-row--two">
                <button onClick={() => void onReviewQueue(selectedQueue.id, 'approve')} disabled={busy === `approve-${selectedQueue.id}`}>Approve</button>
                <button className="secondary" onClick={() => void onReviewQueue(selectedQueue.id, 'reject')} disabled={busy === `reject-${selectedQueue.id}`}>Reject</button>
              </div>
            </>
          ) : <p>No queue items yet.</p>}
        </article>

        <article className="card">
          <div className="card-head"><h2>Job progress</h2></div>
          {activeJob ? <div className="job"><div className="progress"><div style={{ width: `${Math.max(5, Math.round((activeJob.progress || 0) * 100))}%` }} /></div><strong>{human(activeJob.run_type)}</strong><p>{activeJob.current_stage || activeJob.output_summary || 'Queued'}</p></div> : <p>No jobs yet.</p>}
          <div className="table">{jobRuns.map((job) => <div className="row" key={job.run_id}><div><strong>{human(job.run_type)}</strong><p>{job.output_summary || job.current_stage || 'Queued'}</p></div><span className={`status status--${job.status}`}>{job.status}</span></div>)}</div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Hostinger ops</h2><button className="secondary" onClick={() => void onRefreshHostinger()} disabled={busy === 'hostinger-refresh'}>{busy === 'hostinger-refresh' ? 'Refreshing...' : 'Refresh ops'}</button></div>
          <div className="meta-grid">
            <MetaItem label="Status" value={hostinger.status ?? 'disabled'} />
            <MetaItem label="Configured" value={hostinger.configured ? 'Yes' : 'No'} />
            <MetaItem label="Project" value={hostinger.projectName ?? '--'} />
            <MetaItem label="Domain" value={hostinger.domain ?? '--'} />
            <MetaItem label="Selected VM" value={hostinger.selectedVm ?? '--'} />
            <MetaItem label="Last checked" value={hostinger.lastCheckedAt ?? '--'} />
          </div>
          {hostinger.errorMessage ? <p className="inline-note">{hostinger.errorMessage}</p> : null}
          <h3>Metrics snapshot</h3>
          <pre>{pretty(hostinger.metrics)}</pre>
          <h3>Recent project logs</h3>
          <div className="feed-list">
            {hostinger.projectLogs.slice(0, 5).map((item, index) => (
              <div className="feed-item" key={item.id ?? index}>
                <strong>{item.message || 'Project event'}</strong>
                <p>{item.timestamp || '--'}</p>
              </div>
            ))}
          </div>
        </article>
      </section>
    </>
  )
}
