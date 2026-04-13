# GigOptimizer Pro — V2 Frontend Brief for Codex

**Date:** 2026-04-12
**Branch:** main
**Your role:** Frontend Engineer — React + TypeScript + CSS

---

## What Is GigOptimizer Pro?

A production SaaS AI platform that helps Fiverr sellers:
- Optimize their gig titles, descriptions, tags, and packages using AI
- Track and beat their competitors on page one
- Get real-time SEO scores, keyword analysis, and market data
- Have a built-in AI copilot that learns from every conversation and gets smarter daily

The backend is fully built (FastAPI + PostgreSQL + Redis). Your job in v2 is to make the frontend a real, modern SaaS product — not a scrolling wall of cards.

---

## What Exists Today (v1)

One massive file: `App.tsx` (1914 lines), with:
- 30+ `useState` calls in a single component
- No navigation — everything stacks vertically, user scrolls forever
- No sidebar or routing
- No page separation
- Basic mobile support only
- Flash messages instead of toast notifications
- No loading skeletons or empty states

It works but it is not scalable and looks like a prototype.

---

## What V2 Needs to Be

A proper SaaS dashboard with:
- **Sidebar navigation** — user clicks to go between sections instead of scrolling
- **Separated pages** — each section is its own component
- **Shared UI system** — reusable Button, Card, Badge, Toast, Skeleton components
- **Custom hooks** — auth, CSRF, assistant SSE all extracted out of App.tsx
- **Mobile first** — works perfectly on phone including iOS safe areas
- **AI learning UI** — the most important new section: show the user how the AI is getting smarter every day with live stats, feedback buttons, and training controls

---

## The AI Learning System (Most Important Part of V2)

The backend already has a full AI learning engine (`CopilotLearningEngine`). It:
- Ingests every conversation the user has with the copilot
- Builds a vocabulary model (TF-IDF) from all conversations
- Learns bigram patterns (word pairs that commonly follow each other)
- Predicts word completions based on what it has learned
- Runs training cycles on a schedule (every 6 hours by default)
- Tracks vocabulary growth, document count, and learning events

**What is missing: the UI to make this visible and interactive.**

The user currently has no idea the AI is learning. They can't see it happening, can't feed it, can't control it. V2 fixes this.

---

## V2 Folder Structure (Target)

```
frontend/src/
  App.tsx                         ← slim root: auth, bootstrap, router (~150 lines)
  layout/
    Sidebar.tsx                   ← left nav
    TopBar.tsx                    ← top bar with live status
    Layout.tsx                    ← wraps sidebar + topbar + page content
  pages/
    GigOptimizerPage.tsx          ← gig analysis, title/desc/tag results
    CompetitorPage.tsx            ← competitor table, comparison, radar chart
    CopilotPage.tsx               ← AI assistant chat panel
    AIBrainPage.tsx               ← NEW: AI learning dashboard (see below)
    MetricsPage.tsx               ← live metrics, keyword quality
    SettingsPage.tsx              ← connectors, queue review, job runs
  components/
    ui/
      Button.tsx
      Card.tsx
      Badge.tsx
      Toast.tsx
      Skeleton.tsx
    charts/
      MetricsLineChart.tsx
      RadarScoreChart.tsx
      VocabGrowthChart.tsx        ← NEW: shows vocab size over time
  hooks/
    useBootstrap.ts
    useCsrf.ts
    useAssistant.ts
  types.ts
  api.ts
```

---

## Task 1 — Shared UI Components

Create `frontend/src/components/ui/`. These are used everywhere else.

### Button.tsx
```tsx
type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps {
  variant?: Variant       // default: 'primary'
  size?: Size             // default: 'md'
  loading?: boolean       // shows spinner, disables click
  disabled?: boolean
  onClick?: () => void
  children: React.ReactNode
  type?: 'button' | 'submit'
}
```
CSS classes: `.btn`, `.btn--primary`, `.btn--secondary`, `.btn--danger`, `.btn--ghost`, `.btn--sm`, `.btn--lg`, `.btn--loading`

### Badge.tsx
```tsx
type Status = 'active' | 'ok' | 'error' | 'warning' | 'queued' | 'pending' | 'idle'

interface BadgeProps {
  status: Status
  label?: string   // if omitted, uses status as label
}
// renders: ● active  (coloured dot + text)
```

### Card.tsx
```tsx
interface CardProps {
  title?: string
  subtitle?: string
  action?: React.ReactNode    // top-right slot: badge, button, etc.
  children: React.ReactNode
  className?: string
  loading?: boolean           // shows skeleton overlay when true
}
```

### Toast.tsx + useToast hook
Replace all `setMessage` / `setError` state with a toast system.
```tsx
// useToast.ts
export function useToast() {
  // returns: toast.success(msg), toast.error(msg), toast.info(msg), toast.warning(msg)
}

// ToastContainer.tsx — render at root level inside App.tsx
// Toasts appear bottom-right, auto-dismiss after 4s
// Max 3 visible, stack upward
// Each toast has: icon + message + close button
```

### Skeleton.tsx
```tsx
interface SkeletonProps {
  width?: string    // default: '100%'
  height?: string   // default: '1rem'
  rounded?: boolean // for circular avatars etc
}
// renders: animated grey shimmer div
```

CSS for shimmer:
```css
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton {
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
  border-radius: 4px;
}
```

---

## Task 2 — Sidebar + Layout

### Sidebar.tsx

Navigation items (in order):
```
🏠  Dashboard          → overview with key metrics
🎯  Gig Optimizer      → run gig analysis
📊  Competitors        → competitor table + radar chart
🤖  Copilot            → AI assistant chat
🧠  AI Brain           → NEW: AI learning stats (most important)
📈  Metrics            → live metrics + keyword scores
⚙️  Settings           → connectors, queue, job runs
```

Behaviour:
- 240px wide on desktop
- Collapses to 48px icon-only on tablet (≤ 1024px), expand on hover
- On mobile (≤ 768px): hidden by default, slides in as overlay when hamburger tapped
- Active item: left border accent (3px) + light background highlight
- Bottom: username chip + logout button

### TopBar.tsx
- Left: app logo + current page title
- Right side chips (small, styled):
  - WebSocket status: `● Live` (green) or `○ Offline` (grey)
  - Active sessions: `💬 3 active` (fetched from `/api/assistant/sessions/count` every 60s)
- Mobile: hamburger menu button on the left

### Layout.tsx
```tsx
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="layout">
      <Sidebar />
      <div className="layout__body">
        <TopBar />
        <main className="layout__content">{children}</main>
      </div>
    </div>
  )
}
```

---

## Task 3 — Custom Hooks

Extract logic out of App.tsx.

### useBootstrap.ts
```ts
export function useBootstrap(): {
  data: BootstrapPayload | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}
// Fetches on mount, re-fetches every 30s
// On error: sets error state, does not crash
```

### useCsrf.ts
```ts
export function useCsrf(data: BootstrapPayload | null): {
  csrfToken: string
  refreshCsrf: () => Promise<string>
}
// csrfToken = data?.state.auth.csrf_token ?? ''
// refreshCsrf: calls loadBootstrap(), returns new token
```

### useAssistant.ts
```ts
export function useAssistant(csrfToken: string, refreshCsrf: () => Promise<string>): {
  messages: AssistantHistoryMessage[]
  busy: boolean
  waitingForFirstChunk: boolean
  sendMessage: (text: string) => Promise<void>
  clearHistory: () => void
  initialized: boolean
  sessionId: string | null
}
// Wraps all SSE streaming logic from App.tsx (~200 lines)
```

---

## Task 4 — Split App.tsx Into Pages

Move sections from the 1914-line App.tsx into their own page files.
Do NOT delete logic — move it exactly as-is first, then clean up.

| Page File | What Goes There |
|---|---|
| `GigOptimizerPage.tsx` | Gig URL input, run button, title options, description options, tag suggestions, package recommendations |
| `CompetitorPage.tsx` | Competitor records table, sort controls, comparison timeline, radar chart |
| `CopilotPage.tsx` | Chat messages list, SSE streaming, input bar, session history |
| `MetricsPage.tsx` | Line chart (impressions/clicks/orders), radar chart, keyword quality card, scraper visibility |
| `SettingsPage.tsx` | Queue review, job runs table, connector health, knowledge base, dataset upload |
| `AIBrainPage.tsx` | NEW — see Task 5 below |

Each page receives only what it needs via props. Use `useCsrf` and `useBootstrap` hooks instead of prop-drilling everything.

---

## Task 5 — AI Brain Page (Most Important New Feature)

**File:** `frontend/src/pages/AIBrainPage.tsx`

This page shows the user exactly how their AI copilot is learning and growing.
The backend already provides all data from `GET /api/copilot/training-dashboard`.

### Sections to build:

#### 1. Learning Stats Bar (top of page)
Four stat cards in a row:
```
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Vocabulary     │ │  Documents      │ │  Training Runs  │ │  Bigram Pairs   │
│  12,847 words   │ │  438 ingested   │ │  47 cycles      │ │  8,231 pairs    │
│  ↑ +342 today   │ │  ↑ +12 today    │ │  last: 2h ago   │ │  learned        │
└─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘
```
Data source: `response.model.vocab_size`, `response.model.doc_count`, `response.totals`, `response.model.bigram_count`

#### 2. Top Learned Words (word cloud style table)
Show top 20 words the AI has learned ranked by frequency × IDF score.
Each row: word | frequency | IDF score | relevance bar
Data source: `response.model.top_words`

#### 3. Word Prediction Demo
A live input where user types a partial word or phrase and sees what the AI predicts.
```
Type a word: [ fiverr___________ ]   →   Predictions:
                                         1. fiverr gig (score: 0.94)
                                         2. fiverr seller (score: 0.87)
                                         3. fiverr ranking (score: 0.81)
```
Calls `GET /api/copilot/training-dashboard/predict?q=<input>&top_n=8`
Debounce: 300ms after user stops typing.

#### 4. Recent Learning Activity (feed)
Scrollable feed of the last 20 learning events:
```
● 2h ago   Auto training cycle — ingested 12 conversations, +342 tokens
● 5h ago   Manual ingest — "SEO guide.txt" — +891 tokens, 23 new words
● 11h ago  Auto training cycle — ingested 8 conversations, +201 tokens
```
Data source: `response.recent_learning`

#### 5. Training Controls
Three action buttons in a card:
```
[▶ Run Training Now]   [🧪 Run Tests]   [📤 Ingest Text]
```
- **Run Training Now**: POST `/api/copilot/training-dashboard/train` — shows spinner while running, then refreshes stats
- **Run Tests**: POST `/api/copilot/training-dashboard/run-tests` — shows result badge (pass/fail count)
- **Ingest Text**: opens a modal with a textarea — user pastes text + sets source name — POST `/api/copilot/training-dashboard/ingest`

All POSTs use CSRF token from `useCsrf`. Pattern: send `X-Internal-API-Key` header is NOT needed from frontend — only n8n uses that. Frontend uses normal session cookie + CSRF token.

#### 6. Training Schedule Card
Shows current schedule:
```
Auto-training: ● Active
Interval: Every 6 hours
Last run: 2 hours ago
Next run: In 4 hours
Total runs: 47
```
Interval selector: `[1h] [3h] [6h] [12h] [24h]` as pill buttons
Toggle switch: Enable / Pause auto-training
PUT `/api/copilot/training-dashboard/schedule` on change

#### 7. Test Results Card
Last test run summary:
```
Tests: ✅ 28 passed  ❌ 0 failed  ⚠️ 0 errors
Status: passed
Last run: 3 hours ago
```
Data source: `response.test_results`

---

## Task 6 — Feedback Loop UI (How AI Gets Smarter From User Actions)

The AI learns from every conversation AND from user feedback. Build these feedback entry points:

### 6a. Thumbs Up/Down on Copilot Messages
In `CopilotPage.tsx`, every AI message gets feedback buttons:
```
AI: "Your gig title 'Logo Design Pro' is ranked..."
                                    [👍] [👎]
```
On thumbs up: POST to `/api/copilot/training-dashboard/ingest` with the message as text, source: `"user_feedback_positive"`, source_type: `"feedback"`
On thumbs down: show a small text box "What was wrong?" → submit with source_type: `"feedback_negative"`

This means every interaction trains the model when the user signals quality.

### 6b. Ingest from Queue Approvals
When user approves a queue item (in SettingsPage), the approved change gets auto-ingested.
Show a small note: `✅ Approved — added to AI training corpus`
POST to ingest endpoint with source: `"queue_approval"`, source_type: `"approved_optimization"`

### 6c. Manual Corpus Feed (in AIBrainPage)
Already covered in Task 5 Ingest Text modal. Let user also:
- Paste a Fiverr competitor's gig description to teach the AI what top sellers write
- Upload a `.txt` file directly
- Add a URL label so the AI knows where the knowledge came from

---

## Task 7 — Mobile & iOS Polish

Add to `App.css`:

```css
/* Sidebar responsive */
@media (max-width: 1024px) {
  .sidebar { width: 48px; }
  .sidebar .nav-label { display: none; }
}

@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    left: -240px;
    width: 240px;
    height: 100vh;
    transition: left 0.25s ease;
    z-index: 200;
  }
  .sidebar--open { left: 0; }
  .sidebar-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    z-index: 199;
  }
  .sidebar--open + .sidebar-overlay { display: block; }
  .layout__body { margin-left: 0; }
}

/* iOS safe area — chat input bar */
.compose-bar {
  position: sticky;
  bottom: 0;
  z-index: 100;
  padding-bottom: max(12px, env(safe-area-inset-bottom));
}

/* Responsive grid */
.content-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
}
@media (max-width: 480px) {
  .content-grid { grid-template-columns: 1fr; }
  .stats-bar { flex-direction: column; }
}
```

---

## Task 8 — Loading + Empty States

### Loading skeletons
Every card that fetches data shows skeleton while loading:
```tsx
{loading ? (
  <>
    <Skeleton height="1.2rem" width="60%" />
    <Skeleton height="1rem" className="mt-2" />
    <Skeleton height="1rem" width="80%" className="mt-1" />
  </>
) : (
  <ActualContent />
)}
```

### Empty states
Every table/list with no data:
```tsx
// EmptyState component
interface EmptyStateProps {
  icon: string        // emoji
  title: string
  hint?: string
  action?: React.ReactNode  // optional CTA button
}

// Usage:
<EmptyState
  icon="📭"
  title="No competitors found yet"
  hint="Run a gig analysis to populate this table"
  action={<Button onClick={runAnalysis}>Run Analysis</Button>}
/>
```

---

## Hard Constraints

1. **Do NOT touch any file outside `frontend/`** — all backend files are Claude's territory
2. **Never truncate a file** — always write the complete file when editing
3. **Build must stay clean:** `cd frontend && npm run build` — zero TypeScript errors before every commit
4. **No `any` types** — strict TypeScript throughout
5. **No new npm packages** without checking first — ask before installing anything
6. **CSRF on all POST/PUT/DELETE:** send `X-CSRF-Token` header using token from `useCsrf` hook. On CSRF error, refresh token and retry once.
7. **All API calls through `api.ts`** — never use raw `fetch` with hardcoded URLs in components

---

## API Reference

| Endpoint | Method | Returns |
|---|---|---|
| `/api/bootstrap` | GET | Full app state, auth, csrf_token |
| `/api/assistant/chat/stream` | GET (SSE) | Streaming chat tokens |
| `/api/assistant/sessions/count` | GET | `{ active_sessions, total_sessions }` |
| `/api/copilot/training-dashboard` | GET | Full learning stats |
| `/api/copilot/training-dashboard/predict` | GET `?q=&top_n=` | Word predictions |
| `/api/copilot/training-dashboard/train` | POST | Trigger training cycle |
| `/api/copilot/training-dashboard/run-tests` | POST | Run test suite |
| `/api/copilot/training-dashboard/ingest` | POST `{ text, source, source_type }` | Ingest text into corpus |
| `/api/copilot/training-dashboard/schedule` | GET | Current schedule |
| `/api/copilot/training-dashboard/schedule` | PUT `{ interval, enabled }` | Update schedule |

---

## Commit Convention (one commit per task)

```
feat(ui): add Button, Badge, Card, Toast, Skeleton components
feat(layout): add Sidebar, TopBar, Layout with responsive behaviour
refactor(app): extract useBootstrap, useCsrf, useAssistant hooks
refactor(pages): split App.tsx into GigOptimizerPage, CompetitorPage, etc.
feat(ai-brain): add AIBrainPage with learning stats, word predictor, training controls
feat(copilot): add thumbs up/down feedback on AI messages
feat(mobile): iOS safe area, sidebar overlay, responsive grid
feat(ux): add loading skeletons and empty states across all pages
```

---

## Escalate to Claude If

- You need a new backend endpoint (I will build it)
- A fetch call returns an unexpected shape (I will fix the API)
- You hit a Python or Docker error
- You are unsure whether something should be frontend or backend logic
