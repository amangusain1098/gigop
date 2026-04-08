const stateUrl = "/api/state";
const wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/dashboard`;

let metricsChart = null;
let pingIntervalId = null;
let currentNotifications = null;
let currentCsrfToken = document.body?.dataset?.csrfToken || "";
let csrfRefreshInFlight = null;

async function refreshSession(force = false) {
  if (csrfRefreshInFlight && !force) return csrfRefreshInFlight;
  csrfRefreshInFlight = fetch("/api/auth/session", {
    headers: { Accept: "application/json" },
  })
    .then(async (response) => {
      const payload = await response.json();
      if (response.status === 401 || payload?.authenticated === false) {
        window.location.href = "/login";
        throw new Error("Authentication required.");
      }
      if (payload?.csrf_token) {
        currentCsrfToken = payload.csrf_token;
        if (document.body?.dataset) document.body.dataset.csrfToken = payload.csrf_token;
      }
      return payload;
    })
    .finally(() => {
      csrfRefreshInFlight = null;
    });
  return csrfRefreshInFlight;
}

async function fetchJson(url, options = {}, retryOnCsrf = true) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (!["GET", "HEAD"].includes(method) && currentCsrfToken) {
    headers["X-CSRF-Token"] = currentCsrfToken;
  }
  const response = await fetch(url, {
    headers,
    ...options,
  });
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (error) {
    payload = {};
  }
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Authentication required.");
  }
  if (response.status === 403 && retryOnCsrf && /csrf/i.test(String(payload.detail || text || ""))) {
    await refreshSession(true);
    return fetchJson(url, options, false);
  }
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with status ${response.status}`);
  }
  return payload;
}

function statusClass(status) {
  return `status-pill status-${String(status || "idle").replace(/\s+/g, "_").toLowerCase()}`;
}

function reportHref(path) {
  if (!path) return "#";
  const fileName = path.split(/[\\/]/).pop();
  return `/reports/${fileName}`;
}

function setStatus(message) {
  document.getElementById("status-banner").textContent = message;
}

function renderMetricChips(report) {
  const audit = report?.conversion_audit || {};
  const container = document.getElementById("metric-chips");
  container.innerHTML = `
    <div class="metric-chip">Score ${report?.optimization_score ?? "--"}</div>
    <div class="metric-chip">CTR ${audit.impression_to_click_rate ?? "--"}%</div>
    <div class="metric-chip">Conversion ${audit.click_to_order_rate ?? "--"}%</div>
  `;
}

function renderMetricsChart(history) {
  const ctx = document.getElementById("metrics-chart");
  const labels = history.map((point) => new Date(point.timestamp).toLocaleDateString());
  const ctr = history.map((point) => point.ctr);
  const conversion = history.map((point) => point.conversion_rate);
  const impressions = history.map((point) => point.impressions);

  if (metricsChart) metricsChart.destroy();
  metricsChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "CTR %",
          data: ctr,
          borderColor: "#0d6e6e",
          backgroundColor: "rgba(13,110,110,0.12)",
          tension: 0.25,
          yAxisID: "y",
        },
        {
          label: "Conversion %",
          data: conversion,
          borderColor: "#b55d34",
          backgroundColor: "rgba(181,93,52,0.12)",
          tension: 0.25,
          yAxisID: "y",
        },
        {
          label: "Impressions",
          data: impressions,
          borderColor: "#47403a",
          backgroundColor: "rgba(71,64,58,0.08)",
          tension: 0.25,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { boxWidth: 16 } },
      },
      scales: {
        y: { type: "linear", position: "left", beginAtZero: true },
        y1: { type: "linear", position: "right", beginAtZero: true, grid: { drawOnChartArea: false } },
      },
    },
  });
}

function renderKeywordPulse(report) {
  const container = document.getElementById("keyword-pulse");
  const pulse = report?.niche_pulse || {};
  const keywords = pulse.trending_queries || [];
  const liveSignals = pulse.live_keyword_signals || [];
  if (!keywords.length) {
    container.innerHTML = `<div class="empty-state">No keyword pulse is available yet.</div>`;
    return;
  }

  container.innerHTML = keywords.map((keyword) => {
    const signal = liveSignals.find((item) => item.keyword.toLowerCase() === keyword.toLowerCase());
    const meta = signal
      ? `Source: ${signal.source} | Trend ${signal.trend_score ?? "--"} | Volume ${signal.search_volume ?? "--"}`
      : "Snapshot-derived signal";
    return `
      <article class="keyword-card">
        <strong>${keyword}</strong>
        <div class="keyword-meta">${meta}</div>
        <button class="button button-ghost" data-apply-keyword="${keyword}">Apply to Gig</button>
      </article>
    `;
  }).join("");

  container.querySelectorAll("[data-apply-keyword]").forEach((button) => {
    button.addEventListener("click", async () => {
      await postKeyword(button.dataset.applyKeyword);
    });
  });
}

function renderAgentHealth(items) {
  const container = document.getElementById("agent-health");
  if (!items.length) {
    container.innerHTML = `<div class="empty-state">Agent health has not been recorded yet.</div>`;
    return;
  }
  container.innerHTML = items.map((item) => `
    <article class="health-card">
      <strong>${item.agent_name}</strong>
      <span class="${statusClass(item.status)}">${item.status}</span>
      <div class="health-meta">Last run: ${item.last_run_at ? new Date(item.last_run_at).toLocaleString() : "Never"}</div>
      <div class="health-meta">Cost per run: $${Number(item.cost_per_run || 0).toFixed(2)}</div>
      ${item.last_error ? `<div class="health-meta">Last error: ${item.last_error}</div>` : ""}
    </article>
  `).join("");
}

function renderSetupHealth(setupHealth) {
  const container = document.getElementById("setup-health");
  if (!container) return;
  const connectors = setupHealth?.connectors || [];
  const checks = setupHealth?.checks || [];
  if (!connectors.length && !checks.length) {
    container.innerHTML = `<div class="empty-state">Setup health has not been calculated yet.</div>`;
    return;
  }
  const connectorCard = `
    <article class="action-card">
      <strong>Connector readiness</strong>
      ${connectors.length ? `<ul>${connectors.map((item) => `<li><span class="${statusClass(item.status)}">${item.status}</span> ${item.connector}: ${item.detail}</li>`).join("")}</ul>` : `<div class="empty-state">No connector status found.</div>`}
    </article>
  `;
  const checksCard = `
    <article class="action-card">
      <strong>Operational checklist</strong>
      ${checks.length ? `<ul>${checks.map((item) => `<li><span class="${statusClass(item.status)}">${item.status}</span> ${item.label}: ${item.detail}</li>`).join("")}</ul>` : `<div class="empty-state">No readiness checks found.</div>`}
    </article>
  `;
  container.innerHTML = connectorCard + checksCard;
}

function renderScraperRun(scraperRun) {
  const summary = document.getElementById("scraper-summary");
  const gigsContainer = document.getElementById("scraper-gigs");
  const feed = document.getElementById("scraper-activity-feed");
  if (!summary || !gigsContainer || !feed) return;

  const terms = scraperRun?.search_terms || [];
  const events = scraperRun?.recent_events || [];
  const gigs = scraperRun?.recent_gigs || [];

  summary.innerHTML = `
    <div class="health-meta">Status: <span class="${statusClass(scraperRun?.status || "idle")}">${scraperRun?.status || "idle"}</span></div>
    <div class="health-meta">Started: ${scraperRun?.started_at ? new Date(scraperRun.started_at).toLocaleString() : "Not started"}</div>
    <div class="health-meta">Finished: ${scraperRun?.finished_at ? new Date(scraperRun.finished_at).toLocaleString() : "Running or not started"}</div>
    <div class="health-meta">Search terms: ${terms.length ? terms.join(", ") : "None configured"}</div>
    <div class="health-meta">Last URL: ${scraperRun?.last_url ? `<a class="report-link" href="${scraperRun.last_url}" target="_blank" rel="noreferrer">${scraperRun.last_url}</a>` : "No page opened yet"}</div>
    <div class="health-meta">Total results: ${scraperRun?.total_results ?? 0}</div>
    <div class="health-meta">Message: ${scraperRun?.last_status_message || "Waiting for a scrape run."}</div>
    <div class="health-meta">Debug HTML: ${scraperRun?.debug_html_path ? scraperRun.debug_html_path : "Not generated"}</div>
    <div class="health-meta">Debug Screenshot: ${scraperRun?.debug_screenshot_path ? scraperRun.debug_screenshot_path : "Not generated"}</div>
  `;

  if (!gigs.length) {
    gigsContainer.innerHTML = `<div class="empty-state">No competitor gigs have been captured yet.</div>`;
  } else {
    gigsContainer.innerHTML = gigs.map((gig) => `
      <article class="keyword-card">
        <strong>${gig.title}</strong>
        <div class="keyword-meta">Seller: ${gig.seller_name || "--"} | Price: ${gig.starting_price ?? "--"} | Rating: ${gig.rating ?? "--"} | Term: ${gig.matched_term || "--"}</div>
        ${gig.url ? `<a class="report-link" href="${gig.url}" target="_blank" rel="noreferrer">Open live gig</a>` : ""}
      </article>
    `).join("");
  }

  if (!events.length) {
    feed.innerHTML = `<div class="empty-state">No live scraper events yet. Run the scraper to watch queries and parsed gigs stream in here.</div>`;
  } else {
    feed.innerHTML = events.slice().reverse().map((event) => `
      <article class="activity-event activity-${String(event.level || "info").toLowerCase()}">
        <div class="activity-row">
          <strong>${event.stage}</strong>
          <span class="small-text">${event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ""}</span>
        </div>
        <div class="small-text">${event.message || "Update received."}</div>
        <div class="small-text">
          ${event.term ? `Term: ${event.term}` : ""}
          ${event.result_count !== null && event.result_count !== undefined ? ` | Results: ${event.result_count}` : ""}
          ${event.gig_title ? ` | Gig: ${event.gig_title}` : ""}
          ${event.seller_name ? ` | Seller: ${event.seller_name}` : ""}
        </div>
        ${event.debug_html_path ? `<div class="small-text">Debug HTML: ${event.debug_html_path}</div>` : ""}
        ${event.debug_screenshot_path ? `<div class="small-text">Debug Screenshot: ${event.debug_screenshot_path}</div>` : ""}
        ${event.url ? `<a class="report-link" href="${event.url}" target="_blank" rel="noreferrer">Open source page</a>` : ""}
      </article>
    `).join("");
  }
}

function renderCompetitiveAnalysis(report) {
  const container = document.getElementById("competitive-analysis");
  const analysis = report?.competitive_gap_analysis;
  if (!analysis) {
    container.innerHTML = `<div class="empty-state">Enable live connectors and marketplace scraping to compare with public Fiverr competitors.</div>`;
    return;
  }

  const topCompetitors = analysis.top_competitors || [];
  const competitorCards = topCompetitors.map((gig) => `
    <article class="action-card">
      <strong>${gig.title}</strong>
      <div class="health-meta">Matched term: ${gig.matched_term || "--"} | Proxy score: ${gig.conversion_proxy_score ?? "--"}</div>
      <div class="health-meta">Price: ${gig.starting_price ?? "--"} | Rating: ${gig.rating ?? "--"} | Reviews: ${gig.reviews_count ?? "--"}${gig.delivery_days ? ` | Delivery: ${gig.delivery_days} day(s)` : ""}</div>
      ${gig.url ? `<a class="report-link" href="${gig.url}" target="_blank" rel="noreferrer">Open gig</a>` : ""}
      ${gig.win_reasons?.length ? `<ul>${gig.win_reasons.map((reason) => `<li>${reason}</li>`).join("")}</ul>` : `<div class="empty-state">No visible win reasons extracted.</div>`}
    </article>
  `).join("");

  container.innerHTML = `
    <article class="action-card">
      <strong>Proxy warning</strong>
      <p class="small-text">${analysis.proxy_warning}</p>
      ${analysis.search_terms?.length ? `<p class="small-text">Search terms used: ${analysis.search_terms.join(", ")}</p>` : ""}
      ${analysis.title_patterns?.length ? `<p class="small-text">Trending title patterns: ${analysis.title_patterns.join(", ")}</p>` : ""}
    </article>
    <article class="action-card">
      <strong>Why competitors are likely winning more clicks or conversions</strong>
      ${analysis.why_competitors_win?.length ? `<ul>${analysis.why_competitors_win.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No reasons generated yet.</div>`}
    </article>
    <article class="action-card">
      <strong>What to implement</strong>
      ${analysis.what_to_implement?.length ? `<ul>${analysis.what_to_implement.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No implementation actions generated yet.</div>`}
    </article>
    <article class="action-card">
      <strong>Your advantages</strong>
      ${analysis.my_advantages?.length ? `<ul>${analysis.my_advantages.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No advantage notes yet.</div>`}
    </article>
    ${competitorCards}
  `;
}

function renderGigComparison(comparison) {
  const container = document.getElementById("gig-comparison");
  if (!container) return;
  if (!comparison) {
    container.innerHTML = `<div class="empty-state">Paste your Fiverr gig URL and run a comparison to see what the market is doing better, which titles dominate search, and what to implement next.</div>`;
    return;
  }

  const myGig = comparison.my_gig || null;
  const topCompetitors = comparison.top_competitors || [];
  const titlePatterns = comparison.title_patterns || [];
  const topSearchTitles = comparison.top_search_titles || [];
  const searchTerms = comparison.detected_search_terms || [];
  const whyCompetitorsWin = comparison.why_competitors_win || [];
  const whatToImplement = comparison.what_to_implement || [];
  const myAdvantages = comparison.my_advantages || [];
  const implementation = comparison.implementation_blueprint || {};
  const recommendedPackages = implementation.recommended_packages || [];
  const comparisonReport = comparison.latest_report_file?.html_path
    ? reportHref(comparison.latest_report_file.html_path)
    : "";
  const titleOptions = implementation.title_options || [];
  const descriptionOptions = implementation.description_options || [];

  container.innerHTML = `
    <article class="action-card">
      <strong>Comparison status</strong>
      <div class="health-meta">Status: <span class="${statusClass(comparison.status || "idle")}">${comparison.status || "idle"}</span></div>
      <div class="health-meta">Source: ${comparison.comparison_source || "live"}</div>
      <div class="health-meta">Message: ${comparison.message || "No comparison has run yet."}</div>
      <div class="health-meta">Gig URL: ${comparison.gig_url ? `<a class="report-link" href="${comparison.gig_url}" target="_blank" rel="noreferrer">${comparison.gig_url}</a>` : "Not set"}</div>
      <div class="health-meta">Competitors compared: ${comparison.competitor_count ?? 0}</div>
      <div class="health-meta">Market anchor price: ${comparison.market_anchor_price !== null && comparison.market_anchor_price !== undefined ? `$${comparison.market_anchor_price}` : "--"}</div>
      <div class="health-meta">Detected search terms: ${searchTerms.length ? searchTerms.join(", ") : "Not detected yet"}</div>
      <div class="health-meta">Last compared: ${comparison.last_compared_at ? new Date(comparison.last_compared_at).toLocaleString() : "Not run yet"}</div>
      ${comparisonReport ? `<a class="report-link" href="${comparisonReport}" target="_blank" rel="noreferrer">Open latest market report</a>` : ""}
    </article>
    <article class="action-card">
      <strong>My gig summary</strong>
      ${myGig ? `
        <div class="health-meta">Title: ${myGig.title || "--"}</div>
        <div class="health-meta">Seller: ${myGig.seller_name || "--"}</div>
        <div class="health-meta">Starting price: ${myGig.starting_price ?? "--"}</div>
        <div class="health-meta">Rating: ${myGig.rating ?? "--"} | Reviews: ${myGig.reviews_count ?? "--"}</div>
        <div class="health-meta">Tags: ${(myGig.tags || []).join(", ") || "--"}</div>
        <p class="small-text">${myGig.description_excerpt || "No public description excerpt was detected."}</p>
      ` : `<div class="empty-state">Your gig page has not been loaded yet.</div>`}
    </article>
    <article class="action-card">
      <strong>Recommended title to implement</strong>
      ${implementation.recommended_title ? `<div class="copy-block"><code>${implementation.recommended_title}</code></div>` : `<div class="empty-state">No market-ready title generated yet.</div>`}
      ${implementation.recommended_title ? `<div class="hero-actions"><button class="button button-secondary" data-queue-title="${implementation.recommended_title.replace(/"/g, "&quot;")}">Queue This Title</button></div>` : ""}
      ${implementation.title_variants?.length ? `<div class="comparison-subtitle">Other title variants</div><ul>${implementation.title_variants.map((item) => `<li>${item}</li>`).join("")}</ul>` : ""}
    </article>
    <article class="action-card">
      <strong>Market-based title options</strong>
      ${titleOptions.length ? titleOptions.map((item) => `
        <div class="comparison-option">
          <div class="comparison-subtitle">${item.label}</div>
          <div class="copy-block"><code>${item.title}</code></div>
          <p class="small-text">${item.rationale}</p>
          <div class="hero-actions"><button class="button button-ghost" data-queue-title="${item.title.replace(/"/g, "&quot;")}">Queue Title</button></div>
        </div>
      `).join("") : `<div class="empty-state">No title options generated yet.</div>`}
    </article>
    <article class="action-card">
      <strong>Recommended tags</strong>
      ${implementation.recommended_tags?.length ? `<ul>${implementation.recommended_tags.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No tag recommendations generated yet.</div>`}
      ${implementation.recommended_tags?.length ? `<div class="hero-actions"><button class="button button-secondary" data-queue-tags='${JSON.stringify(implementation.recommended_tags).replace(/'/g, "&apos;")}'>Queue Recommended Tags</button></div>` : ""}
    </article>
    <article class="action-card">
      <strong>Description you can use</strong>
      ${implementation.description_opening ? `<p class="small-text">${implementation.description_opening}</p>` : ""}
      ${implementation.description_blueprint?.length ? `<ul>${implementation.description_blueprint.map((item) => `<li>${item}</li>`).join("")}</ul>` : ""}
      ${implementation.description_full ? `<pre class="description-block">${implementation.description_full}</pre>` : `<div class="empty-state">No description block generated yet.</div>`}
      ${implementation.description_full ? `<div class="hero-actions"><button class="button button-secondary" data-queue-description="${encodeURIComponent(implementation.description_full)}">Queue This Description</button></div>` : ""}
    </article>
    <article class="action-card">
      <strong>Market-based description options</strong>
      ${descriptionOptions.length ? descriptionOptions.map((item) => `
        <div class="comparison-option">
          <div class="comparison-subtitle">${item.label}</div>
          ${item.paired_title ? `<div class="health-meta">Pair with title: ${item.paired_title}</div>` : ""}
          <p class="small-text">${item.summary || ""}</p>
          <pre class="description-block">${item.text}</pre>
          ${item.notes?.length ? `<ul>${item.notes.map((note) => `<li>${note}</li>`).join("")}</ul>` : ""}
          <div class="hero-actions"><button class="button button-ghost" data-queue-description="${encodeURIComponent(item.text)}">Queue Description</button></div>
        </div>
      `).join("") : `<div class="empty-state">No description options generated yet.</div>`}
    </article>
    <article class="action-card">
      <strong>Pricing and package positioning</strong>
      ${implementation.pricing_strategy?.length ? `<ul>${implementation.pricing_strategy.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No pricing strategy generated yet.</div>`}
      ${recommendedPackages.length ? `<div class="comparison-subtitle">Suggested package ladder</div><ul>${recommendedPackages.map((pkg) => `<li>${pkg.name}: $${pkg.price} - ${pkg.focus}</li>`).join("")}</ul>` : ""}
    </article>
    <article class="action-card">
      <strong>Trust and FAQ gaps</strong>
      ${implementation.trust_boosters?.length ? `<div class="comparison-subtitle">Trust boosters</div><ul>${implementation.trust_boosters.map((item) => `<li>${item}</li>`).join("")}</ul>` : ""}
      ${implementation.faq_recommendations?.length ? `<div class="comparison-subtitle">FAQ to add</div><ul>${implementation.faq_recommendations.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No FAQ gaps generated yet.</div>`}
    </article>
    <article class="action-card">
      <strong>Persona and follow-up pack</strong>
      ${implementation.persona_focus?.length ? `<div class="comparison-subtitle">Best personas to target</div><ul>${implementation.persona_focus.map((item) => `<li>${item.persona} (${item.score}): ${item.pain_point}</li>`).join("")}</ul>` : ""}
      ${implementation.review_follow_up_template ? `<div class="comparison-subtitle">Review follow-up template</div><pre class="description-block">${implementation.review_follow_up_template}</pre>` : ""}
      ${implementation.external_traffic_actions?.length ? `<div class="comparison-subtitle">External traffic ideas</div><ul>${implementation.external_traffic_actions.map((item) => `<li>${item}</li>`).join("")}</ul>` : ""}
      ${implementation.caution_notes?.length ? `<div class="comparison-subtitle">Caution notes</div><ul>${implementation.caution_notes.map((item) => `<li>${item}</li>`).join("")}</ul>` : ""}
    </article>
    <article class="action-card">
      <strong>5-minute market watch actions</strong>
      ${implementation.weekly_actions?.length ? `<ul>${implementation.weekly_actions.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No recurring actions generated yet.</div>`}
    </article>
    <article class="action-card">
      <strong>Why competitors are ranking or converting better</strong>
      ${whyCompetitorsWin.length ? `<ul>${whyCompetitorsWin.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No competitor reasons yet.</div>`}
    </article>
    <article class="action-card">
      <strong>What you should implement</strong>
      ${whatToImplement.length ? `<ul>${whatToImplement.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No implementation plan generated yet.</div>`}
    </article>
    <article class="action-card">
      <strong>Top search title patterns</strong>
      ${titlePatterns.length ? `<ul>${titlePatterns.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No title patterns extracted yet.</div>`}
      ${topSearchTitles.length ? `<div class="comparison-subtitle">Leading public titles</div><ul>${topSearchTitles.map((item) => `<li>${item}</li>`).join("")}</ul>` : ""}
    </article>
    <article class="action-card">
      <strong>Your existing advantages</strong>
      ${myAdvantages.length ? `<ul>${myAdvantages.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No clear advantage notes yet.</div>`}
    </article>
    ${topCompetitors.map((gig) => `
      <article class="action-card">
        <strong>${gig.title}</strong>
        <div class="health-meta">Seller: ${gig.seller_name || "--"} | Price: ${gig.starting_price ?? "--"} | Rating: ${gig.rating ?? "--"} | Reviews: ${gig.reviews_count ?? "--"}</div>
        <div class="health-meta">Matched term: ${gig.matched_term || "--"} | Conversion proxy: ${gig.conversion_proxy_score ?? "--"}</div>
        ${gig.url ? `<a class="report-link" href="${gig.url}" target="_blank" rel="noreferrer">Open competitor gig</a>` : ""}
        ${gig.win_reasons?.length ? `<ul>${gig.win_reasons.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No visible win reasons extracted.</div>`}
      </article>
    `).join("")}
  `;

  container.querySelectorAll("[data-queue-title]").forEach((button) => {
    button.addEventListener("click", async () => {
      await queueMarketRecommendation("title_update", button.dataset.queueTitle);
    });
  });
  container.querySelectorAll("[data-queue-description]").forEach((button) => {
    button.addEventListener("click", async () => {
      await queueMarketRecommendation("description_update", decodeURIComponent(button.dataset.queueDescription || ""));
    });
  });
  container.querySelectorAll("[data-queue-tags]").forEach((button) => {
    button.addEventListener("click", async () => {
      const payload = JSON.parse((button.dataset.queueTags || "[]").replace(/&apos;/g, "'"));
      await queueMarketRecommendation("keyword_tag_update", payload);
    });
  });
}

function renderAIOverview(report) {
  const container = document.getElementById("ai-overview");
  const ai = report?.ai_overview;
  if (!ai) {
    container.innerHTML = `<div class="empty-state">AI overview has not been generated yet.</div>`;
    return;
  }
  container.innerHTML = `
    <article class="action-card">
      <strong>${ai.provider || "AI"} ${ai.model ? `| ${ai.model}` : ""}</strong>
      <div class="health-meta">Status: ${ai.status || "unknown"}</div>
      ${ai.summary ? `<p class="small-text">${ai.summary}</p>` : `<div class="empty-state">No AI summary is available yet.</div>`}
      ${ai.next_steps?.length ? `<ul>${ai.next_steps.map((item) => `<li>${item}</li>`).join("")}</ul>` : ""}
    </article>
  `;
}

function renderQueue(records) {
  const body = document.getElementById("approval-queue");
  if (!records.length) {
    body.innerHTML = `<tr><td colspan="7" class="empty-state">No approval records yet. Run the pipeline to generate change drafts.</td></tr>`;
    return;
  }
  body.innerHTML = records.map((record) => {
    const issues = (record.validator_issues || []).map((issue) => issue.message).join(" | ");
    const actionButtons = record.status === "pending"
      ? `
        <div class="table-actions">
          <button class="button button-ghost" data-approve="${record.id}">Approve</button>
          <button class="button button-danger" data-reject="${record.id}">Reject</button>
        </div>
      `
      : `<span class="small-text">${issues || "No action needed."}</span>`;
    return `
      <tr>
        <td>${record.agent_name}</td>
        <td>${record.action_type}</td>
        <td><span class="${statusClass(record.status)}">${record.status}</span></td>
        <td>${record.confidence_score}</td>
        <td>${record.current_value}</td>
        <td>${record.proposed_value}</td>
        <td>${actionButtons}</td>
      </tr>
    `;
  }).join("");

  body.querySelectorAll("[data-approve]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        setStatus("Approving queued change...");
        await fetchJson(`/api/queue/${button.dataset.approve}/approve`, { method: "POST", body: JSON.stringify({}) });
      } catch (error) {
        setStatus(error.message);
      }
    });
  });

  body.querySelectorAll("[data-reject]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        setStatus("Rejecting queued change...");
        await fetchJson(`/api/queue/${button.dataset.reject}/reject`, { method: "POST", body: JSON.stringify({}) });
      } catch (error) {
        setStatus(error.message);
      }
    });
  });
}

function renderLatestReport(report) {
  const container = document.getElementById("latest-report");
  if (!report) {
    container.innerHTML = `<div class="empty-state">No report has been generated yet.</div>`;
    return;
  }
  const blocks = [
    { label: "Title Variants", items: report.title_variants || [] },
    { label: "Priority Actions", items: report.weekly_action_plan || [] },
    { label: "Pricing Recommendations", items: report.pricing_recommendations || [] },
    { label: "Review Actions", items: report.review_actions || [] },
  ];
  container.innerHTML = blocks.map((block) => `
    <article class="action-card">
      <strong>${block.label}</strong>
      ${block.items.length ? `<ul>${block.items.map((item) => `<li>${item}</li>`).join("")}</ul>` : `<div class="empty-state">No items.</div>`}
    </article>
  `).join("");
}

function renderReports(reports) {
  const container = document.getElementById("reports-list");
  if (!reports.length) {
    container.innerHTML = `<div class="empty-state">No reports generated yet.</div>`;
    return;
  }
  container.innerHTML = reports.map((report) => `
    <article class="report-card">
      <strong>${report.report_id}</strong>
      <div class="report-meta">${new Date(report.generated_at).toLocaleString()} | ${String(report.report_type || "weekly").replace(/_/g, " ")}</div>
      <a class="report-link" href="${reportHref(report.html_path)}" target="_blank" rel="noreferrer">Open HTML report</a>
    </article>
  `).join("");
}

function renderComparisonHistory(history) {
  const container = document.getElementById("comparison-history");
  if (!container) return;
  if (!history?.length) {
    container.innerHTML = `<div class="empty-state">No market-watch snapshots stored yet.</div>`;
    return;
  }
  container.innerHTML = history.map((item) => `
    <article class="report-card">
      <strong>${item.recommended_title || "No recommended title yet"}</strong>
      <div class="report-meta">${item.captured_at ? new Date(item.captured_at).toLocaleString() : ""} | ${item.comparison_source || "live"} | competitors ${item.competitor_count ?? 0}</div>
      <div class="small-text">${item.implementation_summary || "No summary generated."}</div>
      ${item.recommended_tags?.length ? `<div class="small-text">Tags: ${item.recommended_tags.join(", ")}</div>` : ""}
      ${item.report_html_path ? `<a class="report-link" href="${reportHref(item.report_html_path)}" target="_blank" rel="noreferrer">Open market report</a>` : ""}
    </article>
  `).join("");
}

function renderSettings(notifications) {
  currentNotifications = notifications || currentNotifications;
  if (!currentNotifications) return;

  const email = currentNotifications.email || {};
  document.getElementById("email-enabled").checked = Boolean(email.enabled);
  document.getElementById("email-smtp-host").value = email.smtp_host || "smtp.gmail.com";
  document.getElementById("email-smtp-port").value = email.smtp_port || 587;
  document.getElementById("email-smtp-username").value = email.smtp_username || "";
  document.getElementById("email-from-address").value = email.from_address || "";
  document.getElementById("email-to-addresses").value = (email.to_addresses || []).join(", ");
  document.getElementById("email-use-tls").checked = email.use_tls !== false;
  document.getElementById("email-config-status").textContent = email.configured
    ? "Email delivery is configured."
    : "Email is not configured yet.";

  const slack = currentNotifications.slack || {};
  document.getElementById("slack-enabled").checked = Boolean(slack.enabled);
  document.getElementById("slack-config-status").textContent = slack.configured ? "Slack webhook saved." : "Slack is not configured yet.";

  const whatsapp = currentNotifications.whatsapp || {};
  document.getElementById("whatsapp-enabled").checked = Boolean(whatsapp.enabled);
  document.getElementById("whatsapp-phone-number-id").value = whatsapp.phone_number_id || "";
  document.getElementById("whatsapp-recipient-number").value = whatsapp.recipient_number || "";
  document.getElementById("whatsapp-api-version").value = whatsapp.api_version || "v23.0";
  document.getElementById("whatsapp-config-status").textContent = whatsapp.configured
    ? "WhatsApp Cloud API is configured."
    : "WhatsApp is not configured yet.";

  const ai = currentNotifications.ai || {};
  document.getElementById("ai-enabled").checked = Boolean(ai.enabled);
  document.getElementById("ai-provider").value = ai.provider || "openai";
  document.getElementById("ai-model").value = ai.model || "gpt-5.4-mini";
  document.getElementById("ai-api-base-url").value = ai.api_base_url || "https://api.openai.com/v1";
  document.getElementById("ai-config-status").textContent = ai.configured
    ? `AI overview is configured for ${ai.provider || "provider"} / ${ai.model || "model"}.`
    : "AI overview is disabled.";

  const marketplace = currentNotifications.marketplace || {};
  document.getElementById("marketplace-enabled").checked = Boolean(marketplace.enabled);
  document.getElementById("marketplace-search-terms").value = (marketplace.search_terms || []).join(", ");
  document.getElementById("marketplace-max-results").value = marketplace.max_results || 12;
  document.getElementById("marketplace-search-url-template").value = marketplace.search_url_template || "https://www.fiverr.com/search/gigs?query={query}";
  document.getElementById("marketplace-reader-enabled").checked = marketplace.reader_enabled !== false;
  document.getElementById("marketplace-reader-base-url").value = marketplace.reader_base_url || "https://r.jina.ai/http://";
  document.getElementById("settings-marketplace-my-gig-url").value = marketplace.my_gig_url || "";
  document.getElementById("marketplace-my-gig-url").value = marketplace.my_gig_url || "";
  document.getElementById("marketplace-auto-compare-enabled").checked = Boolean(marketplace.auto_compare_enabled);
  document.getElementById("marketplace-auto-compare-interval").value = marketplace.auto_compare_interval_minutes || 5;
  document.getElementById("marketplace-serpapi-engine").value = marketplace.serpapi_engine || "google";
  document.getElementById("marketplace-serpapi-num-results").value = marketplace.serpapi_num_results || 10;
  document.getElementById("marketplace-config-status").textContent = marketplace.enabled
    ? `Marketplace scraping is enabled for live competitor comparison.${marketplace.reader_enabled !== false ? " Free reader fallback is enabled." : ""}${marketplace.auto_compare_enabled ? ` Auto-compare runs every ${marketplace.auto_compare_interval_minutes || 5} minutes.` : ""}${marketplace.serpapi_configured ? " SerpApi fallback is configured." : ""}`
    : "Marketplace competitor scraping is disabled.";

  const events = currentNotifications.events || {};
  document.getElementById("event-pipeline-run").checked = Boolean(events.pipeline_run);
  document.getElementById("event-queue-pending").checked = Boolean(events.queue_pending);
  document.getElementById("event-approval-decision").checked = Boolean(events.approval_decision);
  document.getElementById("event-report-generated").checked = Boolean(events.report_generated);
  document.getElementById("event-error").checked = Boolean(events.error);
}

function renderState(state) {
  currentCsrfToken = state?.auth?.csrf_token || currentCsrfToken;
  document.getElementById("snapshot-path").textContent = state.snapshot_path;
  renderMetricChips(state.latest_report);
  renderMetricsChart(state.metrics_history || []);
  renderKeywordPulse(state.latest_report);
  renderAgentHealth(state.agent_health || []);
  renderSetupHealth(state.setup_health || {});
  renderScraperRun(state.scraper_run || {});
  renderGigComparison(state.gig_comparison);
  renderCompetitiveAnalysis(state.latest_report);
  renderQueue(state.queue || []);
  renderAIOverview(state.latest_report);
  renderLatestReport(state.latest_report);
  renderReports(state.recent_reports || []);
  renderComparisonHistory(state.comparison_history || []);
  renderSettings(state.notifications || currentNotifications);
}

async function loadState() {
  const state = await fetchJson(stateUrl);
  renderState(state);
  setStatus("Dashboard synced.");
}

async function runPipeline() {
  setStatus("Running pipeline...");
  try {
    await fetchJson("/api/run", {
      method: "POST",
      body: JSON.stringify({
        use_live_connectors: document.getElementById("live-connectors-toggle").checked,
      }),
    });
  } catch (error) {
    setStatus(error.message);
  }
}

async function generateReport() {
  setStatus("Generating weekly report...");
  try {
    await fetchJson("/api/reports/run", {
      method: "POST",
      body: JSON.stringify({
        use_live_connectors: document.getElementById("live-connectors-toggle").checked,
      }),
    });
  } catch (error) {
    setStatus(error.message);
  }
}

async function runMarketplaceScraper() {
  setStatus("Running live marketplace scraper...");
  try {
    await fetchJson("/api/marketplace/run", {
      method: "POST",
      body: JSON.stringify({
        search_terms: (document.getElementById("marketplace-search-terms")?.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      }),
    });
  } catch (error) {
    setStatus(error.message);
  }
}

async function startMarketplaceVerification() {
  setStatus("Opening Fiverr verification browser...");
  try {
    await fetchJson("/api/marketplace/verification/start", {
      method: "POST",
      body: JSON.stringify({
        search_terms: (document.getElementById("marketplace-search-terms")?.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      }),
    });
    setStatus("Verification browser launched. Complete the Fiverr challenge there and the scraper will retry automatically.");
  } catch (error) {
    setStatus(error.message);
  }
}

async function compareMyGig() {
  const gigUrl = document.getElementById("marketplace-my-gig-url")?.value?.trim() || "";
  const settingsGigUrl = document.getElementById("settings-marketplace-my-gig-url");
  if (settingsGigUrl && gigUrl) settingsGigUrl.value = gigUrl;
  setStatus("Comparing your gig against the live Fiverr market...");
  try {
    await fetchJson("/api/marketplace/compare-gig", {
      method: "POST",
      body: JSON.stringify({
        gig_url: gigUrl,
        search_terms: (document.getElementById("marketplace-search-terms")?.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      }),
    });
  } catch (error) {
    setStatus(error.message);
  }
}

async function compareManualMarket() {
  const gigUrl = document.getElementById("marketplace-my-gig-url")?.value?.trim() || "";
  const competitorInput = document.getElementById("manual-competitor-input")?.value || "";
  setStatus("Analyzing your pasted competitor market input...");
  try {
    await fetchJson("/api/marketplace/compare-manual", {
      method: "POST",
      body: JSON.stringify({
        gig_url: gigUrl,
        competitor_input: competitorInput,
        search_terms: (document.getElementById("marketplace-search-terms")?.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      }),
    });
  } catch (error) {
    setStatus(error.message);
  }
}

function buildFiverrCaptureScript() {
  return `(function () {
  const query = new URL(location.href).searchParams.get('query') || '';
  const numberFromText = (value) => {
    const match = String(value || '').replace(/,/g, '').match(/(\\d+(?:\\.\\d+)?)/);
    return match ? Number(match[1]) : null;
  };
  const text = (root, selectors) => {
    for (const selector of selectors) {
      const node = root.querySelector(selector);
      if (node && node.innerText && node.innerText.trim()) return node.innerText.trim();
    }
    return '';
  };
  const href = (root) => {
    const link = root.querySelector('a[href*="/gig/"], a[href*="/services/"], a[href*="/users/"]');
    if (!link) return '';
    try { return new URL(link.getAttribute('href'), location.origin).toString(); } catch { return link.href || ''; }
  };
  const items = Array.from(document.querySelectorAll('article'))
    .map((card) => {
      const title = text(card, ['h3', '[data-testid="gig-card-title"]', 'a[aria-label]']);
      const seller = text(card, ['[data-testid="seller-name"]', '[class*="seller"]']);
      const priceText = text(card, ['[data-testid="gig-card-price"]', '[class*="price"]']);
      const ratingText = text(card, ['[data-testid="gig-card-rating"]', '[class*="rating"]']);
      const reviewsText = text(card, ['[data-testid="gig-card-reviews"]', '[class*="reviews"]']);
      const delivery = text(card, ['[data-testid="delivery-time"]', '[class*="delivery"]']);
      const snippet = text(card, ['p', '[data-testid="gig-card-description"]']);
      const url = href(card);
      if (!title && !url) return null;
      return {
        title,
        seller_name: seller,
        starting_price: numberFromText(priceText),
        rating: numberFromText(ratingText),
        reviews_count: numberFromText(reviewsText),
        delivery_days: numberFromText(delivery),
        snippet,
        url
      };
    })
    .filter(Boolean)
    .slice(0, 12);
  const payload = JSON.stringify({ source: 'browser_capture', searchTerm: query, capturedAt: new Date().toISOString(), gigs: items }, null, 2);
  const finish = () => alert('Gig data copied. Return to GigOptimizer and paste it into Imported competitor input.');
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(payload).then(finish).catch(() => window.prompt('Copy this captured Fiverr JSON', payload));
  } else {
    window.prompt('Copy this captured Fiverr JSON', payload);
  }
})();`;
}

async function copyFiverrCaptureScript() {
  const script = buildFiverrCaptureScript();
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(script);
      setStatus("Fiverr capture script copied. Open Fiverr search results, paste it into the browser console, run it, then paste the copied JSON back here.");
      return;
    }
  } catch (error) {
    // fall through to prompt
  }
  window.prompt("Copy this Fiverr capture script", script);
  setStatus("Fiverr capture script ready. Run it on a Fiverr search result page, then paste the copied JSON back here.");
}

async function postKeyword(keyword) {
  setStatus(`Submitting keyword '${keyword}'...`);
  try {
    await fetchJson("/api/keywords/apply", {
      method: "POST",
      body: JSON.stringify({ keyword }),
    });
  } catch (error) {
    setStatus(error.message);
  }
}

async function queueMarketRecommendation(actionType, proposedValue) {
  setStatus(`Queueing ${actionType.replace(/_/g, " ")}...`);
  try {
    await fetchJson("/api/marketplace/recommendations/apply", {
      method: "POST",
      body: JSON.stringify({
        action_type: actionType,
        proposed_value: proposedValue,
      }),
    });
    setStatus("Recommendation added to the approval queue.");
  } catch (error) {
    setStatus(error.message);
  }
}

function settingsPayload() {
  return {
    email: {
      enabled: document.getElementById("email-enabled").checked,
      smtp_host: document.getElementById("email-smtp-host").value.trim(),
      smtp_port: Number(document.getElementById("email-smtp-port").value || 587),
      smtp_username: document.getElementById("email-smtp-username").value.trim(),
      smtp_password: document.getElementById("email-smtp-password").value.trim(),
      from_address: document.getElementById("email-from-address").value.trim(),
      to_addresses: document.getElementById("email-to-addresses").value.split(",").map((item) => item.trim()).filter(Boolean),
      use_tls: document.getElementById("email-use-tls").checked,
    },
    slack: {
      enabled: document.getElementById("slack-enabled").checked,
      webhook_url: document.getElementById("slack-webhook-url").value.trim(),
    },
    whatsapp: {
      enabled: document.getElementById("whatsapp-enabled").checked,
      access_token: document.getElementById("whatsapp-access-token").value.trim(),
      phone_number_id: document.getElementById("whatsapp-phone-number-id").value.trim(),
      recipient_number: document.getElementById("whatsapp-recipient-number").value.trim(),
      api_version: document.getElementById("whatsapp-api-version").value.trim() || "v23.0",
    },
    ai: {
      enabled: document.getElementById("ai-enabled").checked,
      provider: document.getElementById("ai-provider").value.trim() || "openai",
      model: document.getElementById("ai-model").value.trim() || "gpt-5.4-mini",
      api_base_url: document.getElementById("ai-api-base-url").value.trim() || "https://api.openai.com/v1",
      api_key: document.getElementById("ai-api-key").value.trim(),
    },
    marketplace: {
      enabled: document.getElementById("marketplace-enabled").checked,
      search_terms: document.getElementById("marketplace-search-terms").value.split(",").map((item) => item.trim()).filter(Boolean),
      max_results: Number(document.getElementById("marketplace-max-results").value || 12),
      search_url_template: document.getElementById("marketplace-search-url-template").value.trim(),
      reader_enabled: document.getElementById("marketplace-reader-enabled").checked,
      reader_base_url: document.getElementById("marketplace-reader-base-url").value.trim() || "https://r.jina.ai/http://",
      my_gig_url: document.getElementById("settings-marketplace-my-gig-url").value.trim(),
      auto_compare_enabled: document.getElementById("marketplace-auto-compare-enabled").checked,
      auto_compare_interval_minutes: Number(document.getElementById("marketplace-auto-compare-interval").value || 5),
      serpapi_api_key: document.getElementById("marketplace-serpapi-api-key").value.trim(),
      serpapi_engine: document.getElementById("marketplace-serpapi-engine").value.trim() || "google",
      serpapi_num_results: Number(document.getElementById("marketplace-serpapi-num-results").value || 10),
    },
    events: {
      pipeline_run: document.getElementById("event-pipeline-run").checked,
      queue_pending: document.getElementById("event-queue-pending").checked,
      approval_decision: document.getElementById("event-approval-decision").checked,
      report_generated: document.getElementById("event-report-generated").checked,
      error: document.getElementById("event-error").checked,
    },
  };
}

async function saveSettings(event) {
  event.preventDefault();
  setStatus("Saving configuration...");
  try {
    const settings = await fetchJson("/api/settings", {
      method: "POST",
      body: JSON.stringify(settingsPayload()),
    });
    renderSettings(settings);
    document.getElementById("email-smtp-password").value = "";
    document.getElementById("slack-webhook-url").value = "";
    document.getElementById("whatsapp-access-token").value = "";
    document.getElementById("ai-api-key").value = "";
    document.getElementById("marketplace-serpapi-api-key").value = "";
    setStatus("Configuration saved.");
  } catch (error) {
    setStatus(error.message);
  }
}

async function testChannel(channel) {
  setStatus(`Sending ${channel} test notification...`);
  try {
    await fetchJson("/api/settings/notifications/test", {
      method: "POST",
      body: JSON.stringify({ channel }),
    });
    setStatus(`${channel[0].toUpperCase()}${channel.slice(1)} test notification sent.`);
  } catch (error) {
    setStatus(error.message);
  }
}

async function logout() {
  try {
    await fetchJson("/api/auth/logout", { method: "POST", body: JSON.stringify({}) });
  } finally {
    window.location.href = "/login";
  }
}

function connectWebSocket() {
  const socket = new WebSocket(wsUrl);
  socket.addEventListener("open", () => {
    setStatus("Live dashboard connected.");
    if (pingIntervalId) window.clearInterval(pingIntervalId);
    pingIntervalId = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 20000);
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "state") {
      renderState(message.payload);
      setStatus("Dashboard synced.");
    } else if (message.type === "scraper_activity") {
      renderScraperRun(message.payload);
      setStatus(message.payload?.last_status_message || "Live scraper update received.");
    }
  });
  socket.addEventListener("close", () => {
    if (pingIntervalId) {
      window.clearInterval(pingIntervalId);
      pingIntervalId = null;
    }
    setStatus("WebSocket disconnected. Reconnecting...");
    window.setTimeout(connectWebSocket, 1500);
  });
}

function registerServiceWorker() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/service-worker.js").catch(() => {});
  }
}

const comparisonGigUrlField = document.getElementById("marketplace-my-gig-url");
const settingsGigUrlField = document.getElementById("settings-marketplace-my-gig-url");
if (comparisonGigUrlField && settingsGigUrlField) {
  comparisonGigUrlField.addEventListener("input", () => {
    settingsGigUrlField.value = comparisonGigUrlField.value;
  });
  settingsGigUrlField.addEventListener("input", () => {
    comparisonGigUrlField.value = settingsGigUrlField.value;
  });
}

document.getElementById("run-pipeline").addEventListener("click", runPipeline);
document.getElementById("generate-report").addEventListener("click", generateReport);
document.getElementById("compare-my-gig").addEventListener("click", compareMyGig);
document.getElementById("compare-manual-market").addEventListener("click", compareManualMarket);
document.getElementById("copy-fiverr-capture-script").addEventListener("click", copyFiverrCaptureScript);
document.getElementById("run-marketplace-scraper").addEventListener("click", runMarketplaceScraper);
document.getElementById("start-marketplace-verification").addEventListener("click", startMarketplaceVerification);
document.getElementById("settings-form").addEventListener("submit", saveSettings);
document.getElementById("test-email").addEventListener("click", () => testChannel("email"));
document.getElementById("test-slack").addEventListener("click", () => testChannel("slack"));
document.getElementById("test-whatsapp").addEventListener("click", () => testChannel("whatsapp"));

const logoutButton = document.getElementById("logout-button");
if (logoutButton) logoutButton.addEventListener("click", logout);

registerServiceWorker();
loadState().then(connectWebSocket).catch((error) => {
  setStatus(error.message);
});
