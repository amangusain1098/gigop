# GigOptimizer Pro — Codex V2 Frontend Brief

**Date:** 2026-04-12
**Branch:** main (work directly on main, commit incrementally)
**Last commit:** `750386b chore(v2): Claude + Codex role prompts`

---

## Context

The current frontend (`App.tsx`, 1914 lines) is a single massive component.
It works but it has serious problems:
- One God component with 30+ `useState` calls — impossible to maintain
- No navigation / routing — everything is stacked vertically
- No sidebar — user scrolls endlessly to find sections
- No component separation — everything is in `App.tsx`
- Mobile experience is poor — long scrolling page with no navigation

**V2 goal: Turn it into a real SaaS dashboard** — sidebar navigation, split into separate page components, fast, mobile-first, clean UI.

---

## V2 Architecture Target

```
frontend/src/
  App.tsx                          ← slim root: auth, bootstrap, routing only (~200 lines)
  layout/
    Sidebar.tsx                    ← left nav
    TopBar.tsx                     ← top header with user/status
    Layout.tsx                     ← wraps Sidebar + TopBar + <Outlet>
  pages/
    GigOptimizerPage.tsx           ← gig URL input, run analysis, results
    CompetitorPage.tsx             ← competitor table, comparison, radar chart
    CopilotPage.tsx                ← AI assistant chat panel
    TrainingDashboard.tsx          ← copilot learning stats (already exists, move here)
    MetricsPage.tsx                ← live metrics chart, keyword scores
    SettingsPage.tsx               ← connectors health, queue review, job runs
  components/
    ui/
      Button.tsx                   ← shared button variants
      Card.tsx                     ← shared card container
      Badge.tsx                    ← status badges (active/error/queued)
      Toast.tsx                    ← replace all flash messages
      Spinner.tsx                  ← loading spinner
      Skeleton.tsx                 ← loading skeletons for data cards
    charts/
      MetricsLineChart.tsx
      RadarScoreChart.tsx
  hooks/
    useBootstrap.ts                ← bootstrap fetch + polling logic
    useCsrf.ts                     ← csrf token + refresh
    useAssistant.ts                ← assistant SSE streaming logic
  types.ts                         ← keep as-is, add v2 types
  api.ts                           ← keep as-is, add new helpers
```

---

## Tasks (do in this order)

---

### Task 1 — Shared UI components (no logic, just UI)

**Files to create:** `frontend/src/components/ui/`

#### `Button.tsx`
```tsx
type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size = 'sm' | 'md' | 'lg'
interface Props {
  variant?: Variant
  size?: Size
  loading?: boolean
  disabled?: boolean
  onClick?: () => void
  children: React.ReactNode
  type?: 'button' | 'submit'
  className?: string
}
```
- `loading` shows a small inline spinner + disables button
- Variants map to CSS classes: `.btn`, `.btn--primary`, `.btn--secondary`, `.btn--danger`, `.btn--ghost`

#### `Badge.tsx`
```tsx
type Status = 'active' | 'ok' | 'error' | 'warning' | 'queued' | 'pending'
interface Props { status: Status; label?: string }
```
- Maps to existing CSS `.status--active`, `.status--error` etc.
- Dot indicator + label text

#### `Card.tsx`
```tsx
interface Props {
  title?: string
  subtitle?: string
  action?: React.ReactNode    // button/badge in card header
  children: React.ReactNode
  className?: string
}
```

#### `Toast.tsx`
Replace all `setMessage` / `setError` flash section with a proper toast system.
- `useToast()` hook returns `{ toast }` where `toast.success(msg)`, `toast.error(msg)`, `toast.info(msg)`
- Toasts appear bottom-right, auto-dismiss after 4s
- Max 3 toasts visible at once, stack vertically

#### `Skeleton.tsx`
```tsx
interface Props { width?: string; height?: string; className?: string }
// renders an animated loading placeholder div
```
Use in every data-loading section.

---

### Task 2 — Sidebar layout

**Files to create:** `frontend/src/layout/Sidebar.tsx`, `Layout.tsx`, `TopBar.tsx`

#### Sidebar nav items:
```
🏠  Dashboard          → /
🎯  Gig Optimizer      → /gig
📊  Competitors        → /competitors
🤖  Copilot Chat       → /copilot
📈  Metrics            → /metrics
🧠  Training           → /training
⚙️  Settings           → /settings
```

- Sidebar is 240px wide on desktop, collapses to icon-only (48px) on mobile
- Active item: left border accent + background highlight
- Bottom of sidebar: logged-in username + logout button
- Sidebar state (collapsed/expanded) saved in `localStorage` with key `gigop-sidebar`

#### TopBar:
- App name/logo left
- Live status indicator right: green dot + "Live" when WebSocket connected, grey dot + "Offline" when not
- On mobile: hamburger icon to open sidebar as overlay

#### Layout wrapper:
```tsx
// Layout.tsx
<div className="layout">
  <Sidebar />
  <div className="layout__main">
    <TopBar />
    <main className="layout__content">
      {children}
    </main>
  </div>
</div>
```

---

### Task 3 — Extract pages from App.tsx

Split the current monolithic `App.tsx` into page components. **Do not delete logic** — move it as-is, then clean up.

| Page | Current section in App.tsx | What it contains |
|---|---|---|
| `GigOptimizerPage.tsx` | hero section + commands card + content-grid (first) | Gig URL input, title suggestions, description, tags, packages |
| `CompetitorPage.tsx` | competitor table + radar chart | Competitor records table, sort, comparison timeline |
| `CopilotPage.tsx` | assistant panel | Chat messages, SSE streaming, input bar |
| `MetricsPage.tsx` | charts section + keyword quality | Line chart, radar chart, keyword scores, scraper visibility |
| `TrainingDashboard.tsx` | already exists as `CopilotTrainingDashboard.tsx` | Move to pages/, keep identical |
| `SettingsPage.tsx` | queue review + job runs + health + knowledge base | All admin/config sections |

**Rules when extracting:**
- Each page gets its own props interface with only what it needs from bootstrap state
- Shared state (csrf, auth, bootstrap data) comes via props or a context — do NOT duplicate state
- Each page file must compile clean: `tsc --noEmit`

---

### Task 4 — Custom hooks

**File:** `frontend/src/hooks/useBootstrap.ts`
```ts
// Wraps loadBootstrap() — handles polling every 30s, returns { data, loading, refresh }
export function useBootstrap(): {
  data: BootstrapPayload | null
  loading: boolean
  refresh: () => Promise<void>
}
```

**File:** `frontend/src/hooks/useCsrf.ts`
```ts
// Returns current csrf token + a refresh function
export function useCsrf(data: BootstrapPayload | null): {
  csrfToken: string
  refreshCsrf: () => Promise<string>
}
```

**File:** `frontend/src/hooks/useAssistant.ts`
```ts
// Wraps all assistant SSE logic currently in App.tsx (~200 lines)
export function useAssistant(csrfToken: string, onCsrfRefresh: () => Promise<string>): {
  messages: AssistantHistoryMessage[]
  busy: boolean
  sendMessage: (text: string) => Promise<void>
  clearHistory: () => void
  initialized: boolean
  sessionId: string | null
}
```

---

### Task 5 — Mobile & iOS improvements

**File:** `frontend/src/App.css`

Add to existing CSS:

```css
/* Sidebar overlay on mobile */
@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    left: -240px;
    transition: left 0.25s ease;
    z-index: 200;
    height: 100vh;
  }
  .sidebar--open {
    left: 0;
  }
  .sidebar-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.4);
    z-index: 199;
  }
  .sidebar--open ~ .sidebar-overlay {
    display: block;
  }
}

/* iOS safe area — chat compose bar */
.compose-inner {
  padding-bottom: max(12px, env(safe-area-inset-bottom));
}

/* Sticky bottom bars above iOS Safari toolbar */
.chat-input-row,
.compose-bar {
  position: sticky;
  bottom: 0;
  z-index: 100;
}

/* Card grid responsive */
.content-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1rem;
}

@media (max-width: 480px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}
```

---

### Task 6 — Loading skeletons

Every data card must show a `<Skeleton>` while loading instead of being empty.

Priority order:
1. Competitor table (most visible)
2. Live metrics chart
3. Keyword quality card
4. Training dashboard stats

Use `Skeleton` component from Task 1.

---

### Task 7 — Empty states

Every list/table must have a proper empty state when data is `[]` or `null`:

```tsx
// Example pattern
{competitors.length === 0 ? (
  <div className="empty-state">
    <span className="empty-state__icon">📭</span>
    <p>No competitors found yet.</p>
    <p className="empty-state__hint">Run a gig analysis to populate this table.</p>
  </div>
) : (
  <table>...</table>
)}
```

CSS for `.empty-state`:
```css
.empty-state {
  text-align: center;
  padding: 3rem 1rem;
  color: var(--text-muted);
}
.empty-state__icon { font-size: 2rem; display: block; margin-bottom: 0.5rem; }
.empty-state__hint { font-size: 0.85rem; margin-top: 0.25rem; }
```

---

### Task 8 — Live session count chip (backend already built)

**Endpoint ready:** `GET /api/assistant/sessions/count` → `{ active_sessions: N, total_sessions: N }`

In `TopBar.tsx`, fetch this on mount and every 60s:
```tsx
<span className="chip chip--live">💬 {activeSessions} active</span>
```

CSS:
```css
.chip { padding: 2px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }
.chip--live { background: #dcfce7; color: #16a34a; }
```

---

## Build Verification (run after every task)

```bash
cd frontend && npm run build
# Must complete with 0 TypeScript errors, 0 build errors
```

---

## Commit Convention

```
feat(sidebar): add collapsible sidebar with nav items
feat(ui): add Button, Badge, Card, Toast components
refactor(app): extract GigOptimizerPage from App.tsx
fix(mobile): iOS safe area for compose bar
```

Push after each task — do not batch everything into one commit.

---

## Critical Constraints

1. **Do NOT touch any file outside `frontend/`** — backend is Claude's territory
2. **Do NOT truncate existing files** — always write complete file content
3. **Do NOT install new npm packages** without confirming first
4. **TypeScript must be strict** — no `any` types, no `@ts-ignore`
5. **Do NOT break the CSRF flow** — `CopilotTrainingDashboard` already has `postJson()` with CSRF retry — keep that pattern in all new POST calls
6. **Escalate to Claude if you need:**
   - A new API endpoint
   - Changes to auth/session logic
   - Backend error investigation

---

## API Reference (what's already available)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/bootstrap` | GET | Full app state, auth, csrf_token |
| `/api/assistant/chat/stream` | GET | SSE streaming chat |
| `/api/assistant/sessions/count` | GET | Active/total session counts |
| `/api/copilot/training-dashboard` | GET | Training stats |
| `/api/copilot/training-dashboard/train` | POST | Trigger training |
| `/api/copilot/training-dashboard/run-tests` | POST | Run test suite |
| `/api/copilot/training-dashboard/schedule` | GET/PUT | Training schedule |
| `/api/fiverr/analyze` | POST | Run gig analysis |
| `/api/fiverr/competitors` | GET | Competitor records |
