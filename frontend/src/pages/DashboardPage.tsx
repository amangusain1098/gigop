import type { DatasetRecord } from '../types'
import { Metric, MetaItem, currency } from './helpers'

interface DashboardPageProps {
  optimizationScore: number | string
  recommendedTitle: string
  pageOneTracked: number
  primarySearchTerm: string
  scraperStatus: string
  competitorCount: number
  lastRunMessage: string
  extensionPromptVisible: boolean
  extensionDownloadUrl: string
  extensionGuideUrl: string
  extensionTokenConfigured: boolean
  extensionToken: string
  extensionApiBaseUrl: string
  onCopyExtensionToken: (token: string) => Promise<void>
  onDismissExtensionPrompt: () => void
  comparisonStatus: string
  topRankedTitle: string
  topRankedSeller: string
  topRankedRank: string
  topRankedPrice?: number | null
  topRankedReviews: string
  topRankedTerm: string
  topRankedReasons: string[]
  whyCompetitorsWin: string[]
  myGigTitle: string
  myGigPrice?: number | null
  myGigReviews: string
  marketAnchorPrice?: number | null
  detectedTerms: string[]
  titlePatterns: string[]
  whatToImplement: string[]
  doThisFirst: string[]
  currentGigUrl: string
  currentTerms: string
  topTrackedGigTitle: string
  datasets: DatasetRecord[]
}

export default function DashboardPage({
  optimizationScore,
  recommendedTitle,
  pageOneTracked,
  primarySearchTerm,
  scraperStatus,
  competitorCount,
  lastRunMessage,
  extensionPromptVisible,
  extensionDownloadUrl,
  extensionGuideUrl,
  extensionTokenConfigured,
  extensionToken,
  extensionApiBaseUrl,
  onCopyExtensionToken,
  onDismissExtensionPrompt,
  comparisonStatus,
  topRankedTitle,
  topRankedSeller,
  topRankedRank,
  topRankedPrice,
  topRankedReviews,
  topRankedTerm,
  topRankedReasons,
  whyCompetitorsWin,
  myGigTitle,
  myGigPrice,
  myGigReviews,
  marketAnchorPrice,
  detectedTerms,
  titlePatterns,
  whatToImplement,
  doThisFirst,
  currentGigUrl,
  currentTerms,
  topTrackedGigTitle,
  datasets,
}: DashboardPageProps) {
  return (
    <>
      <section className="hero">
        <div>
          <p className="eyebrow">GigOptimizer Pro V2</p>
          <h1>Live Fiverr visibility, page-one competitor tracking, and exact gig changes to publish next.</h1>
          <p className="lede">
            This workspace watches Fiverr page one, compares your gig against the current top 10 public results, and turns
            that into clear changes you can publish with confidence.
          </p>
        </div>
        <div className="hero-grid">
          <Metric label="Optimization score" value={String(optimizationScore ?? '--')} />
          <Metric label="Recommended title" value={recommendedTitle || 'Run a market compare'} />
          <Metric label="Page-one gigs tracked" value={String(pageOneTracked)} />
          <Metric label="Primary search term" value={primarySearchTerm || '--'} />
        </div>
      </section>

      <div className="status-bar">
        <span className={`status-bar-item status--${scraperStatus === 'running' ? 'warning' : scraperStatus === 'ok' || scraperStatus === 'completed' ? 'ok' : 'queued'}`}>
          Scraper: {scraperStatus || 'idle'}
        </span>
        <span className="status-bar-item">
          {competitorCount} competitors · {pageOneTracked} page-one
        </span>
        <span className="status-bar-item">
          Last run: {lastRunMessage ? lastRunMessage.slice(0, 40) : 'never'}
        </span>
        <span className="status-bar-item status--ok">
          Data: loaded
        </span>
      </div>

      {extensionPromptVisible ? (
        <section className="card extension-prompt">
          <div className="card-head">
            <h2>Install the Fiverr capture extension</h2>
            <span className="status status--queued">recommended</span>
          </div>
          <p className="inline-note">
            This site can’t silently install a Chrome extension, but it can guide you and prefill the details you need.
          </p>
          <div className="meta-grid">
            <MetaItem label="API base URL" value={extensionApiBaseUrl || 'https://animha.co.in'} />
            <MetaItem label="Token" value={extensionTokenConfigured ? 'Ready to copy' : 'Not configured'} />
          </div>
          <div className="button-row">
            <a className="button-link" href={extensionDownloadUrl} target="_blank" rel="noopener noreferrer">Download extension ZIP</a>
            <a className="button-link button-link--secondary" href={extensionGuideUrl} target="_blank" rel="noopener noreferrer">Open install guide</a>
            <button className="secondary" onClick={() => void onCopyExtensionToken(extensionToken)} disabled={!extensionToken}>Copy API token</button>
            <button className="secondary" onClick={onDismissExtensionPrompt}>Dismiss</button>
          </div>
        </section>
      ) : null}

      <section className="content-grid">
        <article className="card">
          <div className="card-head">
            <h2>Page-one leader</h2>
            <span className={`status status--${comparisonStatus || 'pending'}`}>{comparisonStatus || 'idle'}</span>
          </div>
          <div className="meta-grid">
            <MetaItem label="Leader rank" value={topRankedRank} />
            <MetaItem label="Leader price" value={currency(topRankedPrice)} />
            <MetaItem label="Leader reviews" value={topRankedReviews} />
            <MetaItem label="Leader term" value={topRankedTerm || '--'} />
          </div>
          <div className="option-card">
            <p className="eyebrow">Current top gig</p>
            <strong>{topRankedTitle || 'Run a market compare'}</strong>
            <p>{topRankedSeller || 'Unknown seller'}</p>
            <ul className="bullet-list compact">
              {topRankedReasons.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
          <h3>Why competitors win</h3>
          <ul className="bullet-list">
            {whyCompetitorsWin.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </article>

        <article className="card">
          <div className="card-head"><h2>My gig vs market</h2><span>{primarySearchTerm || '--'}</span></div>
          <div className="meta-grid">
            <MetaItem label="My gig title" value={myGigTitle || '--'} />
            <MetaItem label="My visible price" value={currency(myGigPrice)} />
            <MetaItem label="My public reviews" value={myGigReviews} />
            <MetaItem label="Market anchor price" value={currency(marketAnchorPrice)} />
            <MetaItem label="Detected search terms" value={detectedTerms.join(', ') || '--'} />
            <MetaItem label="Top title patterns" value={titlePatterns.join(', ') || '--'} />
          </div>
          <h3>What to implement next</h3>
          <ul className="bullet-list">
            {whatToImplement.map((item) => <li key={item}>{item}</li>)}
          </ul>
          <h3>Do this first</h3>
          <ul className="bullet-list">
            {doThisFirst.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head">
            <h2>Active marketplace target</h2>
            <span>{detectedTerms.length || 0} search term(s)</span>
          </div>
          <div className="meta-grid">
            <MetaItem label="Current gig URL" value={currentGigUrl || '--'} />
            <MetaItem label="Current search terms" value={currentTerms || '--'} />
            <MetaItem label="Detected primary term" value={primarySearchTerm || '--'} />
            <MetaItem label="Top tracked gig" value={topTrackedGigTitle || '--'} />
            <MetaItem label="Knowledge files" value={String(datasets.length)} />
            <MetaItem label="Scraper state" value={scraperStatus || 'idle'} />
          </div>
          <p className="inline-note">
            The compare and scrape actions always use the exact gig URL and keywords currently shown in the optimizer inputs.
          </p>
        </article>
        <article className="card">
          <div className="card-head">
            <h2>Workspace summary</h2>
            <span>{datasets.length} knowledge file(s)</span>
          </div>
          <p className="inline-note">
            Use the Gig Optimizer page to change your target keyword and gig URL, then switch to Competitors or Metrics to review what changed.
          </p>
          <ul className="bullet-list">
            <li>Current primary term: {primarySearchTerm || '--'}</li>
            <li>Scraper status: {scraperStatus || 'idle'}</li>
            <li>Knowledge files linked: {datasets.length}</li>
          </ul>
        </article>
      </section>
    </>
  )
}
