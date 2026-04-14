import type { GigOptimizerPageProps } from './shared'
import { Block } from './shared'

export default function GigOptimizerPage({
  liveMode,
  onSetLiveMode,
  gigUrl,
  onGigUrlChange,
  terms,
  onTermsChange,
  manualInput,
  onManualInputChange,
  busy,
  onRunJob,
  onRunMagicRewrite,
  recommendedTitle,
  recommendedTags,
  titleOptions,
  descriptionBlueprint,
  descriptionFull,
  descriptionOptions,
  pricingStrategy,
  recommendedPackages,
  trustBoosters,
  faqRecommendations,
  personaFocus,
  onQueueRecommendation,
  onOpenAIBrain,
}: GigOptimizerPageProps) {
  return (
    <>
      <section className="commands card">
        <div className="card-head">
          <h2>Run jobs</h2>
          <label><input checked={liveMode} onChange={(event) => onSetLiveMode(event.target.checked)} type="checkbox" /> live connectors</label>
        </div>
        <div className="form-grid">
          <input value={gigUrl} onChange={(event) => onGigUrlChange(event.target.value)} placeholder="My Fiverr gig URL" />
          <input value={terms} onChange={(event) => onTermsChange(event.target.value)} placeholder="wordpress speed, pagespeed insights, core web vitals" />
        </div>
        <textarea rows={4} value={manualInput} onChange={(event) => onManualInputChange(event.target.value)} placeholder="Title | price | rating | reviews | delivery | url" />
        <div className="button-row">
          <button onClick={() => void onRunJob('pipeline', { use_live_connectors: liveMode })} disabled={busy === 'pipeline'}>{busy === 'pipeline' ? 'Queueing...' : 'Run pipeline'}</button>
          <button onClick={() => void onRunJob('marketplace_compare', { gig_url: gigUrl, search_terms: terms.split(',').map(s => s.trim()) })} disabled={busy === 'marketplace_compare'}>{busy === 'marketplace_compare' ? 'Queueing...' : 'Compare gig vs top 10'}</button>
          <button onClick={() => void onRunJob('marketplace_scrape', { gig_url: gigUrl, search_terms: terms.split(',').map(s => s.trim()) })} disabled={busy === 'marketplace_scrape'}>{busy === 'marketplace_scrape' ? 'Queueing...' : 'Scan market'}</button>
          <button onClick={() => void onRunJob('manual_compare', { gig_url: gigUrl, search_terms: terms.split(',').map(s => s.trim()), competitor_input: manualInput })} disabled={busy === 'manual_compare' || !manualInput.trim()}>{busy === 'manual_compare' ? 'Queueing...' : 'Analyze manual input'}</button>
          <button onClick={() => void onRunJob('weekly_report', { use_live_connectors: liveMode })} disabled={busy === 'weekly_report'}>{busy === 'weekly_report' ? 'Queueing...' : 'Run weekly report'}</button>
          <button className="secondary" onClick={onOpenAIBrain}>Training Dashboard</button>
        </div>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Publish-ready title and tag options</h2><a href="/dashboard-legacy">legacy view</a></div>
          <Block title="Recommended title" body={recommendedTitle || 'No title yet.'} action={() => void onQueueRecommendation('title_update', recommendedTitle)} busy={busy === 'title_update'} />
          <Block title="Recommended tags" body={recommendedTags.join(', ') || 'No tags yet.'} action={() => void onQueueRecommendation('keyword_tag_update', recommendedTags)} busy={busy === 'keyword_tag_update'} />
          <div className="option-list">
            {titleOptions.map((option) => (
              <div className="option-card" key={option.label}>
                <p className="eyebrow">{option.label}</p>
                <strong>{option.title}</strong>
                <p>{option.rationale}</p>
                <button className="secondary" onClick={() => void onQueueRecommendation('title_update', option.title)} disabled={busy === 'title_update'}>Queue this title</button>
              </div>
            ))}
          </div>
        </article>

        <article className="card">
          <div className="card-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h2>Description modes</h2><span>{descriptionOptions.length}</span>
            </div>
            <button className="primary" onClick={() => void onRunMagicRewrite()} disabled={busy === 'magic_rewrite'}>
              {busy === 'magic_rewrite' ? "Generating..." : "✨ Generate with DeepSeek AI"}
            </button>
          </div>
          <Block title="Description blueprint" body={descriptionBlueprint.join(' | ') || 'No description guidance yet.'} action={() => void onQueueRecommendation('description_update', descriptionFull)} busy={busy === 'description_update'} />
          <div className="option-list">
            {descriptionOptions.map((option) => (
              <div className="option-card" key={option.label}>
                <p className="eyebrow">{option.label}</p>
                <strong>{option.paired_title || option.label}</strong>
                <p>{option.summary}</p>
                <pre>{option.text}</pre>
                <button className="secondary" onClick={() => void onQueueRecommendation('description_update', option.text)} disabled={busy === 'description_update'}>Queue this description</button>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Pricing, packages, and trust</h2></div>
          <h3>Pricing strategy</h3>
          <ul className="bullet-list">
            {pricingStrategy.map((item, idx) => <li key={idx}>{item}</li>)}
          </ul>
          <h3>Recommended packages</h3>
          <div className="package-grid">
            {recommendedPackages.map((pkg) => (
              <div className="package-card" key={pkg.name}>
                <strong>{pkg.name}</strong>
                <p>${pkg.price}</p>
                <ul className="bullet-list compact">
                  {(pkg.highlights ?? []).map((item, idx) => <li key={idx}>{item}</li>)}
                </ul>
              </div>
            ))}
          </div>
          <h3>Trust boosters</h3>
          <ul className="bullet-list">
            {trustBoosters.map((item, idx) => <li key={idx}>{item}</li>)}
          </ul>
        </article>

        <article className="card">
          <div className="card-head"><h2>FAQ and persona focus</h2><span>{personaFocus.length}</span></div>
          <h3>FAQ recommendations</h3>
          <ul className="bullet-list">
            {faqRecommendations.map((item, idx) => <li key={idx}>{item}</li>)}
          </ul>
          <h3>Persona focus</h3>
          <div className="option-list">
            {personaFocus.map((item) => (
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
    </>
  )
}
