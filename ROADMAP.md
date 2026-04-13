# GigOptimizer Pro — V2 Roadmap

**Last updated:** 2026-04-13  
**Status:** Active development  
**Live:** https://animha.co.in

---

## Current State (post-V1 fixes)

| Area | Status |
|------|--------|
| Backend API (FastAPI) | Stable |
| AI Copilot chat | Working — n8n webhook / deterministic fallback |
| Copilot Training Dashboard | Working (CSRF fixed, SSE fixed) |
| Real-time WebSocket dashboard | Working |
| Health Score engine | Built, endpoint exists, not in UI |
| Tag Gap Analyzer | Built, not in UI |
| Price Alert service | Built, no Slack notification wired |
| HITL approval queue | Built, UI exists in Settings |
| Frontend V2 components | Partially done (Tasks 1–3 of 8) |
| n8n learning monitor | Active, runs every 4h |
| Tests | 86/86 passing |

---

## PHASE 1 — Complete V2 Frontend (Codex, 1–2 weeks)

> Unblock all backend features that exist but have no UI.

### 1A. App.tsx Page Split (Codex Task 4) — **HIGHEST PRIORITY**

Split the 1900-line `App.tsx` into dedicated page files. `shared.tsx` props are already written.

```
DashboardPage.tsx     — hero KPIs, scraper status, top competitor card
GigOptimizerPage.tsx  — title/description/tag recommendations, HITL queue
CompetitorPage.tsx    — page-one table, one-by-one analysis, timeline chart
MetricsPage.tsx       — radar chart, keyword scores, scraper logs
SettingsPage.tsx      — datasets, knowledge upload, n8n config, queue review
CopilotPage.tsx       — full-screen chat, feedback thumbs, session controls
AIBrainPage.tsx       — NEW (Task 5)
```

**Why it matters:** Current 1900-line file makes every change risky. Page split = faster Codex iteration, cleaner routing, smaller bundles.

### 1B. AI Brain Page (Codex Task 5)

Dedicated route `/ai-brain` surfacing what already exists in the backend:

- Learning stats bar — vocab size, doc count, token count, bigram count
- Word cloud table from `/api/copilot/training-dashboard`
- Word prediction demo (live as-you-type)
- Training activity feed (recent_learning events)
- Run Training Cycle button + schedule toggle
- Test suite results panel

**This page already has 100% of its data from existing endpoints. Zero backend work needed.**

### 1C. Feedback Loop UI (Codex Task 6)

- Thumbs up/down on copilot messages → calls `/api/assistant/feedback`
- Endpoint exists. UI just needs to wire it.
- Rating stored in DB → feeds `copilot_training_service` → influences HITL queue weighting

### 1D. Mobile + Empty States (Codex Tasks 7–8)

- Bottom nav for mobile (sidebar collapses)
- Touch targets ≥ 44px
- Skeleton loaders during API fetch
- Empty states for: no competitors, no datasets, no chat history

---

## PHASE 2 — Real AI Provider (Claude, 1 week)

> The copilot is currently running on n8n webhooks with a deterministic fallback. Swap in a real LLM.

### 2A. Wire Claude/OpenAI API Key

The `client.py` and `ai_overview_service.py` already have full OpenAI and Anthropic client implementations. They just need an API key in `.env.production`.

**Option A — Claude (Anthropic):**
```bash
# Add to /opt/gigoptimizer-pro/.env.production
AI_PROVIDER=anthropic
AI_API_KEY=sk-ant-...
AI_MODEL=claude-haiku-4-5-20251001   # cheap and fast
```

**Option B — OpenAI:**
```bash
AI_PROVIDER=openai
AI_API_KEY=sk-...
AI_MODEL=gpt-4o-mini
```

**Impact:** Copilot goes from rule-based deterministic responses to real conversational AI. Every user question gets a real answer grounded in the live market data context.

### 2B. Improve RAG Grounding

Current RAG (`rag.py`) is TF-IDF on JSONL. It works but has no semantic understanding.

**Upgrade path:**
- Add `sentence-transformers` (all-MiniLM-L6-v2, 80MB, offline) for embedding
- Store embeddings alongside chunks in `rag_chunks.jsonl`
- Switch retriever from TF-IDF dot product to cosine similarity on embeddings
- Better chunk recall for domain-specific Fiverr terms

**Owner: Claude**  
**Effort: 2–3 days**

### 2C. Session Memory Persistence

Current `ConversationMemory` writes `.jsonl` files to disk (`data/conversations/`).

**Problem:** Container restarts wipe the conversations directory (unless volume-mounted).

**Fix:** Move conversation memory to the SQLite DB alongside `assistant_messages` table. Already have `BlueprintRepository` — add a `conversations` table.

---

## PHASE 3 — Revenue + Conversion Features (Claude, 2–3 weeks)

> Features that directly improve Fiverr ranking and gig conversion.

### 3A. Gig Health Score UI

`GigHealthScoreEngine` already scores across 5 dimensions:
- SEO (title keyword density, tag coverage)
- CRO (description hook, CTA, proof blocks)
- Competitive (vs page-one leader)
- Social Proof (reviews, rating)
- Delivery (packages, turnaround)

Endpoint `/api/gig-health-score` exists. **Needs:**
- Score widget on DashboardPage (gauge or bar showing 0–100)
- Dimension breakdown with specific fix recommendations
- Historical trend (score over time, stored in metrics history)
- Slack alert when score drops below threshold

**Owner: Claude (backend integration) + Codex (UI widget)**

### 3B. Tag Gap Alerts

`TagGapAnalyzer` already compares your tags vs page-one competitors. **Needs:**
- Surface top 5 missing high-value tags in GigOptimizerPage
- "Add Tag" button → queues to HITL for approval
- Weekly Slack digest showing which new tags appeared in top 10

**Owner: Claude**  
**Effort: 1 day**

### 3C. Price Alert Notifications

`PriceAlertService` detects when competitors drop or raise prices. Currently fires no notification.

**Needs:**
- Hook into `notification_service.py` to send Slack alert
- Add baseline reset UI in Settings (button: "Reset price baseline")
- Show active price alerts in a banner on DashboardPage

**Owner: Claude**  
**Effort: 1 day**

### 3D. Weekly Report PDF/Email

`WeeklyReportService` and `generate_market_watch_report` already exist.

**Needs:**
- n8n workflow: every Monday at 9am → call `/api/reports/weekly` → post to Slack
- Add `/api/reports/weekly` endpoint that returns the report payload
- Codex: "Download Weekly Report" button in MetricsPage

**Owner: Claude (endpoint + n8n workflow)**  
**Effort: 2 days**

### 3E. A/B Title Tracking

Currently generates multiple title variants but has no way to track which one performed.

**Add:**
- "Active Title" field in GigSnapshot (which variant is currently live)
- When user manually sets active title → records event with timestamp
- Metric tracking: compare impression/click metrics before and after title change
- 30-day report: "Title A had 12 impressions, Title B had 28"

**Owner: Claude**  
**Effort: 3–4 days**

---

## PHASE 4 — Multi-Gig Support (Claude, 2 weeks)

> Currently the entire system is single-gig. All `gig_id` exists in the DB but the UI only shows one.

### 4A. Gig Switcher

- `gig_id` is already in every DB table — architecture supports multiple gigs
- Frontend needs a dropdown/selector to switch active gig
- Backend: `/api/gigs` endpoint returning all tracked gig URLs
- Per-gig state in bootstrap response

### 4B. Gig Portfolio Overview

- Dashboard showing all gigs at once: health score, rank, last scrape time
- Aggregate view: "total revenue impact across all gigs"
- Alert if any gig drops in rank or health score drops below threshold

**Owner: Claude (API) + Codex (UI)**  
**Effort: 1 week**

---

## PHASE 5 — Multi-User SaaS (Claude, 3–4 weeks)

> Currently single-admin. To sell this as a SaaS product, needs user accounts.

### 5A. User Auth

Current auth is a single admin password (HMAC session cookie). **Needs:**
- Users table in DB with hashed passwords
- Registration flow (invite-only or open)
- Per-user gig_id namespace isolation
- JWT or extend current HMAC session to carry `user_id`

### 5B. Billing Integration

- Stripe subscription (monthly/annual)
- Free tier: 1 gig, 7-day history
- Pro tier: unlimited gigs, 90-day history, weekly reports, Slack alerts
- Enforce plan limits in API middleware

### 5C. Onboarding Flow

- First-login wizard: enter Fiverr gig URL → trigger first scrape → show initial health score
- Progress tracker: "3 of 5 setup steps complete"
- Email confirmation (SendGrid)

**Owner: Claude (auth, billing backend) + Codex (UI flows)**

---

## PHASE 6 — Connector Upgrades (Claude, ongoing)

> External data quality directly determines insight quality.

| Connector | Current State | Next Step |
|-----------|--------------|-----------|
| `fiverr_marketplace.py` | HTML scraper, working | Add retry + rate limiting |
| `fiverr_scraper.py` | Seller metrics from profile page | Add order queue depth signal |
| `google_trends.py` | Pytrends-based, working | Add regional breakdown |
| `semrush.py` | API client exists, needs key | Wire `SEMRUSH_API_KEY` in env |
| `serpapi.py` | API client exists, needs key | Wire `SERPAPI_API_KEY` in env |
| `pagespeed.py` | Working | Auto-run on gig URL after scrape |

---

## Priority Order (What to Build Next)

```
NOW (this week):
  1. Deploy current fixes → ssh root@animha.co.in + git pull + docker compose up
  2. Add AI_PROVIDER=anthropic + AI_API_KEY to .env.production → real copilot
  3. Codex: Task 4 (App.tsx page split) → unblocks all further Codex work

NEXT SPRINT (1–2 weeks):
  4. Codex: Tasks 5–8 (AI Brain page, feedback, mobile, empty states)
  5. Claude: Health Score UI widget + Slack alert
  6. Claude: Price Alert → Slack notification
  7. Claude: Tag Gap surface in GigOptimizerPage

SPRINT 3 (2–4 weeks):
  8. Claude: Improve RAG with sentence-transformers
  9. Claude: Weekly Report endpoint + n8n workflow
  10. Claude: Session memory → DB persistence
  11. Claude: A/B title tracking

MONTH 2:
  12. Multi-gig switcher + portfolio view
  13. Multi-user auth (if going SaaS)
  14. Stripe billing integration
```

---

## Quick Wins (< 1 day each)

These are backend-complete, just need to be turned on:

1. **Set `AI_PROVIDER=anthropic` on server** → copilot becomes real AI immediately
2. **Wire `SEMRUSH_API_KEY`** → keyword difficulty data populates automatically
3. **Wire `SERPAPI_API_KEY`** → better competitor discovery
4. **Price Alert → Slack**: 10 lines in `notification_service.py`
5. **Tag Gap surface**: pass `tag_gap_analyzer.analyze()` result into bootstrap state

---

## Architecture Constraints (Do Not Break)

- Never skip layers: `agents → orchestrator → services → API`
- Never touch: `assistant.py`, `client.py`, `prompts.py` (conversational routing is hand-tuned)
- All secrets in `.env.production` — never hardcoded
- Every Python edit: `python3 -m py_compile <file>` before commit
- File writes: always via Python `open().write()` — never bash heredoc on Windows mount
- Git commits: always from `/tmp/gigop_commit` clone, never from mounted drive directly
