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
[▶ Run Training Now]   [🧪 