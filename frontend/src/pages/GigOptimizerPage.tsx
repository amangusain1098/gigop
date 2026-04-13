import { Block, type DescriptionOption, type PersonaFocus, type RecommendedPackage, type TitleOption, currency } from './helpers'

interface GigOptimizerPageProps {
  liveMode: boolean
  onSetLiveMode: (value: boolean) => void
  gigUrl: string
  onGigUrlChange: (value: string) => void
  terms: string
  onTermsChange: (value: string) => void
  manualInput: string
  onManualInputChange: (value: string) => void
  busy: string
  onRunJob: (jobType: string, payload?: Record<string, unknown>) => Promise<void>
  maxResults: number
  onMaxResultsChange: (value: number) => void
  autoCompareEnabled: boolean
  onToggleAutoCompare: () => void
  autoCompareMinutes: number
  onAutoCompareMinutesChange: (value: number) => void
  onSaveMarketplaceSettings: () => Promise<void>
  onRunNotificationTest: (channel: 'slack') => Promise<void>
  slackConfigured: boolean
  recommendedTitle: string
  recommendedTags: string[]
  titleOptions: TitleOption[]
  descriptionBlueprint: string[]
  descriptionFull: string
  descriptionOptions: DescriptionOption[]
  pricingStrategy: string[]
  recommendedPackages: RecommendedPackage[]
  trustBoosters: string[]
  faqRecommendations: string[]
  personaFocus: PersonaFocus[]
  missingTags: string[]
  powerTags: string[]
  tagCoverageScore: string
  onQueueRecommendation: (actionType: string, proposedValue: unknown) => Promise<void>
  onOpenAIBrain: () => void
}

function splitTerms(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

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
  maxResults,
  onMaxResultsChange,
  autoCompareEnabled,
  onToggleAutoCompare,
  autoCompareMinutes,
  onAutoCompareMinutesChange,
  onSaveMarketplaceSettings,
  onRunNotificationTest,
  slackConfigured,
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
  missingTags,
  powerTags,
  tagCoverageScore,
  onQueueRecommendation,
  onOpenAIBrain,
}: GigOptimizerPageProps) {
  const searchTerms = splitTerms(terms)

  return (
    <>
      <section className="commands card">
        <div className="card-head">
          <h2>Run jobs</h2>
          <label><input checked={liveMode} onChange={(event) => onSetLiveMode(event.target.checked)} type="checkbox" /> live connectors</label>
        </div>
        <div className="form-grid">
          <input value={gigUrl} onChange={(event) => onGigUrlChange(event.target.value)} placeholder="My Fiverr gig URL" />
          <input value={terms} onChange={(event) => onTermsChange(event.target.value)} placeholder="react app, figma ui, animation" />
        </div>
        <textarea rows={4} value={manualInput} onChange={(event) => onManualInputChange(event.target.value)} placeholder="Title | price | rating | reviews | delivery | url" />
        <div className="button-row">
          <button onClick={() => void onRunJob('pipeline', { use_live_connectors: liveMode })} disabled={busy === 'pipeline'}>{busy === 'pipeline' ? 'Queueing...' : 'Run pipeline'}</button>
          <button onClick={() => void onRunJob('marketplace_compare', { gig_url: gigUrl, search_terms: searchTerms })} disabled={busy === 'marketplace_compare'}>{busy === 'marketplace_compare' ? 'Queueing...' : 'Compare gig vs top 10'}</button>
          <button onClick={() => void onRunJob('marketplace_scrape', { gig_url: gigUrl, search_terms: searchTerms })} disabled={busy === 'marketplace_scrape'}>{busy === 'marketplace_scrape' ? 'Queueing...' : 'Scan market'}</button>
          <button onClick={() => void onRunJob('manual_compare', { gig_url: gigUrl, search_terms: searchTerms, competitor_input: manualInput })} disabled={busy === 'manual_compare' || !manualInput.trim()}>{busy === 'manual_compare' ? 'Queueing...' : 'Analyze manual input'}</button>
          <button onClick={() => void onRunJob('weekly_report', { use_live_connectors: liveMode })} disabled={busy === 'weekly_report'}>{busy === 'weekly_report' ? 'Queueing...' : 'Run weekly report'}</button>
          <button className="secondary" onClick={onOpenAIBrain}>Open AI Brain</button>
        </div>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Marketplace settings</h2><span>{slackConfigured ? 'Slack ready' : 'Slack optional'}</span></div>
          <div className="form-grid">
            <input value={gigUrl} onChange={(event) => onGigUrlChange(event.target.value)} placeholder="Default Fiverr gig URL" />
            <input value={terms} onChange={(event) => onTermsChange(event.target.value)} placeholder="Search terms used for page-one tracking" />
            <input type="number" min={10} max={25} value={maxResults} onChange={(event) => onMaxResultsChange(Number(event.target.value || 10))} placeholder="Max competitor results" />
            <input type="number" min={5} max={240} value={autoCompareMinutes} onChange={(event) => onAutoCompareMinutesChange(Number(event.target.value || 5))} placeholder="Auto compare interval (minutes)" />
          </div>
          <div className="button-row button-row--three">
            <button className="secondary" onClick={onToggleAutoCompare}>
              {autoCompareEnabled ? 'Auto compare: on' : 'Auto compare: off'}
            </button>
            <button onClick={() => void onSaveMarketplaceSettings()} disabled={busy === 'save-settings'}>{busy === 'save-settings' ? 'Saving...' : 'Save settings'}</button>
            <button className="secondary" onClick={() => void onRunNotificationTest('slack')} disabled={busy === 'test-slack'}>{busy === 'test-slack' ? 'Testing...' : 'Test Slack'}</button>
          </div>
          <p className="inline-note">The page-one leaderboard uses the first search term as the primary Fiverr query, then compares those top 10 gigs against your gig one by one.</p>
        </article>

        <article className="card">
          <div className="card-head"><h2>Tag gap analysis</h2><span>{tagCoverageScore}</span></div>
          <h3>Missing tags</h3>
          <div className="pill-row">{missingTags.map((item) => <span className="pill" key={item}>{item}</span>)}</div>
          <h3>Power tags</h3>
          <div className="pill-row">{powerTags.map((item) => <span className="pill" key={item}>{item}</span>)}</div>
          <p className="inline-note">Use the tag gap card to close what page-one gigs are using that your gig is not.</p>
        </article>
      </section>

      <section className="content-grid">
        <article className="card">
          <div className="card-head"><h2>Publish-ready title and tag options</h2><span>{recommendedTags.length} tags</span></div>
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
          <div className="card-head"><h2>Description modes</h2><span>{descriptionOptions.length}</span></div>
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
          <div className="card-head"><h2>Pricing, packages, and trust</h2><span>{recommendedPackages.length} packages</span></div>
          <h3>Pricing strategy</h3>
          <ul className="bullet-list">
            {pricingStrategy.map((item) => <li key={item}>{item}</li>)}
          </ul>
          <h3>Recommended packages</h3>
          <div className="package-grid">
            {recommendedPackages.map((pkg) => (
              <div className="package-card" key={pkg.name}>
                <strong>{pkg.name}</strong>
                <p>{currency(pkg.price)}</p>
                <ul className="bullet-list compact">
                  {(pkg.highlights ?? []).map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ))}
          </div>
          <h3>Trust boosters</h3>
          <ul className="bullet-list">
            {trustBoosters.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </article>

        <article className="card">
          <div className="card-head"><h2>FAQ and persona focus</h2><span>{personaFocus.length}</span></div>
          <h3>FAQ recommendations</h3>
          <ul className="bullet-list">
            {faqRecommendations.map((item) => <li key={item}>{item}</li>)}
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
