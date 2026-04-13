import type { DashboardPageProps } from './shared'
import { MetaItem, Metric, currency } from './shared'

export default function DashboardPage({
  heroMetrics,
  scraperStatus,
  competitorCount,
  pageOneCount,
  lastRunMessage,
  dataLoaded,
  shouldShowExtensionPrompt,
  extensionInstall,
  onCopyExtensionToken,
  onDismissExtensionPrompt,
  comparisonStatus,
  topRankedGig,
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
}: DashboardPageProps) {
  return (
    <>
      <section className="hero">
        <div>
          <div className="hero-topbar">
            <p className="eyebrow">GigOptimizer Pro Blueprint</p>
            <a className="hero-link" href="/terms-of-service" target="_blank" rel="noopener noreferrer">Terms of Service</a>
          </div>
          <h1>Live Fiverr visibility, page-one competitor tracking, and exact gig changes to publish next.</h1>
          <p className="lede">
            This dashboard watches Fiverr page one, compares your gig against the current top 10 public results, and turns
            that into queueable title, description, keyword, pricing, and trust recommendations.
          </p>
        </div>
        <div className="hero-grid">
          {heroMetrics.map((metric, i) => (
            <Metric key={i} label={metric.label} value={metric.value} />
          ))}
        </div>
      </section>

      <div className="status-bar">
        <span className={`status-bar-item status--${scraperStatus === 'running' ? 'warning' : scraperStatus === 'ok' || scraperStatus === 'completed' ? 'ok' : 'queued'}`}>
          Scraper: {scraperStatus}
        </span>
        <span className="status-bar-item">
          {competitorCount} competitors · {pageOneCount} page-one
        </span>
        <span className="status-bar-item">
          Last run: {lastRunMessage}
        </span>
        <span className={`status-bar-item status--${dataLoaded ? 'ok' : 'queued'}`}>
          Data: {dataLoaded ? 'loaded' : 'loading'}
        </span>
      </div>

      {shouldShowExtensionPrompt ? (
        <section className="card extension-prompt">
          <div className="card-head">
            <h2>Install the Fiverr capture extension</h2>
            <span className="status status--queued">recommended</span>
          </div>
          <p className="inline-note">
            This site can’t silently install a Chrome extension for you, but it can prompt you to download it and open the
            install guide automatically. Once the extension is loaded, this banner disappears on its own.
          </p>
          <div className="meta-grid">
            <MetaItem label="API base URL" value={extensionInstall.apiBaseUrl} />
            <MetaItem label="Token" value={extensionInstall.tokenConfigured ? 'Ready to copy' : 'Not configured'} />
          </div>
          <div className="button-row">
            <a className="button-link" href={extensionInstall.downloadUrl} target="_blank" rel="noopener noreferrer">Download extension ZIP</a>
            <a className="button-link button-link--secondary" href={extensionInstall.guideUrl} target="_blank" rel="noopener noreferrer">Open install guide</a>
            <button className="secondary" onClick={() => void onCopyExtensionToken(extensionInstall.apiToken)} disabled={!extensionInstall.apiToken}>Copy API token</button>
            <button className="secondary" onClick={onDismissExtensionPrompt}>Dismiss</button>
          </div>
        </section>
      ) : null}

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Page-one leader</h2><span className={`status status--${comparisonStatus ?? 'pending'}`}>{comparisonStatus ?? 'idle'}</span></div>
          <div className="meta-grid">
            <MetaItem label="Leader rank" value={`#${topRankedGig.rank}`} />
            <MetaItem label="Leader price" value={currency(topRankedGig.price)} />
            <MetaItem label="Leader reviews" value={topRankedGig.reviews} />
            <MetaItem label="Leader term" value={topRankedGig.term} />
          </div>
          <div className="option-card">
            <p className="eyebrow">Current top gig</p>
            <strong>{topRankedGig.title}</strong>
            <p>{topRankedGig.sellerName}</p>
            <ul className="bullet-list compact">
              {topRankedReasons.map((item, idx) => <li key={idx}>{item}</li>)}
            </ul>
          </div>
          <h3>Why competitors win</h3>
          <ul className="bullet-list">
            {whyCompetitorsWin.map((item, idx) => <li key={idx}>{item}</li>)}
          </ul>
        </article>

        <article className="card">
          <div className="card-head"><h2>My gig vs market</h2><span>{topRankedGig.term ?? '--'}</span></div>
          <div className="meta-grid">
            <MetaItem label="My gig title" value={myGigTitle} />
            <MetaItem label="My visible price" value={currency(myGigPrice)} />
            <MetaItem label="My public reviews" value={myGigReviews} />
            <MetaItem label="Market anchor price" value={currency(marketAnchorPrice)} />
            <MetaItem label="Detected search terms" value={detectedTerms.join(', ') || '--'} />
            <MetaItem label="Top title patterns" value={titlePatterns.join(', ') || '--'} />
          </div>
          <h3>What to implement next</h3>
          <ul className="bullet-list">
            {whatToImplement.map((item, idx) => <li key={idx}>{item}</li>)}
          </ul>
          <h3>Do this first</h3>
          <ul className="bullet-list">
            {doThisFirst.map((item, idx) => <li key={idx}>{item}</li>)}
          </ul>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head">
            <h2>Active marketplace target</h2>
            <span>{currentTerms.split(',').length} search term(s)</span>
          </div>
          <div className="meta-grid">
            <MetaItem label="Current gig URL" value={currentGigUrl || '--'} />
            <MetaItem label="Current search terms" value={currentTerms || '--'} />
            <MetaItem label="Detected primary term" value={topRankedGig.term || '--'} />
            <MetaItem label="Top tracked gig" value={topTrackedGigTitle || '--'} />
          </div>
          <p className="inline-note">
            The compare and scrape buttons use the exact gig URL and keywords currently shown in the inputs above.
          </p>
        </article>
      </section>
    </>
  )
}
