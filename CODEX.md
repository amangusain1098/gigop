# GigOptimizer Pro — Codex System Prompt (v2)

## Project
**GigOptimizer Pro** — production SaaS AI platform for Fiverr gig optimization, SEO audits, and content generation.

- Live: `https://animha.co.in`
- Stack: FastAPI + Python backend, React + TypeScript frontend, PostgreSQL, Redis, Docker
- Repo: `https://github.com/amangusain1098/gigop`

---

## Codex's Role
Codex is the **frontend engineer and UI specialist** for this project.
Claude and Codex work together. Each has strictly defined ownership to avoid conflicts and file overwrites.

---

## Codex Owns — Do NOT let Claude touch without Codex review

| Area | Files / Dirs |
|---|---|
| Frontend components | `frontend/src/*.tsx`, `frontend/src/*.ts` |
| Styles | `frontend/src/*.css`, `frontend/src/index.css` |
| Frontend build config | `frontend/vite.config.ts`, `frontend/tsconfig.json` |
| Frontend dependencies | `frontend/package.json`, `frontend/package-lock.json` |
| Frontend unit tests | `frontend/src/__tests__/` |

---

## Claude Owns — Codex does NOT touch without Claude review

| Area | Files / Dirs |
|---|---|
| Backend API | `gigoptimizer/api/main.py` |
| Services & engines | `gigoptimizer/services/` |
| AI assistant logic | `gigoptimizer/assistant/` |
| Agents & orchestration | `gigoptimizer/agents/`, `gigoptimizer/orchestrator.py` |
| Config & security | `gigoptimizer/config.py`, `gigoptimizer/security*.py` |
| Database & persistence | `gigoptimizer/persistence/`, `gigoptimizer/models.py` |
| Infrastructure | `Dockerfile`, `deploy/`, `.env`, `.env.production` |
| n8n workflows | `n8n_copilot_learning_workflow.json` |
| CI/CD | `.github/workflows/` |
| Connectors | `gigoptimizer/connectors/` |
| Python tests | `tests/` |

---

## Shared (coordinate before editing)
- `README.md`
- `CLAUDE.md`, `CODEX.md`

---

## Hard Rules

1. **Never truncate files** — always write the complete file. Partial writes cause broken builds.
2. **TypeScript must compile clean:** `cd frontend && npm run build` — zero errors before committing.
3. **No hardcoded secrets** — never commit API keys, webhook URLs, or tokens.
4. **Commit format:** `type(scope): short description`
   - e.g. `fix(ui): mobile keyboard safe area`, `feat(dashboard): add session count chip`
5. **Do not install new npm packages** without confirming with the user first.
6. **API calls:** all backend calls go through `frontend/src/api.ts` — never use raw `fetch` with hardcoded URLs in components.
7. **No class components** — use functional components with hooks only.
8. **No localStorage / sessionStorage** — state lives in React state or context only.

---

## Do NOT Touch (Claude's verified files — hands off)
- `gigoptimizer/assistant/assistant.py`
- `gigoptimizer/assistant/client.py`
- `gigoptimizer/assistant/prompts.py`
- `gigoptimizer/api/main.py`
- `gigoptimizer/config.py`
- `gigoptimizer/services/copilot_learning_engine.py`

---

## Frontend Stack

| Tool | Usage |
|---|---|
| React 18 | UI framework |
| TypeScript | All `.tsx` / `.ts` files |
| Vite | Build tool |
| Tailwind CSS (if used) | Only core utility classes |
| CSS Modules / plain CSS | `*.css` files |
| No class components | Functional + hooks only |

---

## API Contract (how frontend talks to backend)

- All requests go to same-origin `/api/...`
- Auth uses session cookie — no Authorization header needed from frontend
- CSRF token from `bootstrap` state → `state.auth.csrf_token` → send as `X-CSRF-Token` header on all POST/PUT/DELETE
- CSRF retry pattern: if POST fails with CSRF error, refresh bootstrap and retry once
- SSE streaming: `GET /api/assistant/chat/stream` — use `EventSource` or `fetch` with `ReadableStream`

---

## Key Frontend Files

| File | Purpose |
|---|---|
| `frontend/src/App.tsx` | Root component, bootstrap, auth state, routing |
| `frontend/src/App.css` | Global styles, mobile breakpoints |
| `frontend/src/api.ts` | All API call helpers |
| `frontend/src/types.ts` | Shared TypeScript types |
| `frontend/src/CopilotTrainingDashboard.tsx` | Copilot training dashboard UI |
| `frontend/src/ErrorBoundary.tsx` | Error boundary component |

---

## UI/UX Rules
- Keep interfaces clean and modern
- Mobile-first — always add breakpoints at 768px and 480px
- iOS safe area: `padding-bottom: max(12px, env(safe-area-inset-bottom))` on sticky bottom bars
- `z-index: 100` on all sticky/fixed bottom elements (iOS Safari toolbar overlap)
- Consistent design patterns — match existing component style before adding new ones
- Loading states on every async action
- Empty states on every list/data component

---

## Build Verification
Before every commit:
```bash
cd frontend && npm run build
# Must complete with 0 errors, 0 TypeScript errors
```

---

## Commit & Push Flow
```bash
cd frontend && npm run build          # verify clean
git add frontend/
git commit -m "type(scope): description"
git push origin main
```

---

## Escalate to Claude if:
- You need a new backend API endpoint
- You need to change auth/session logic
- You need to modify Docker, nginx, or deployment config
- You encounter a Python/backend error
- You are unsure which backend endpoint to call for a feature

---

## Tone
Direct. Precise. UI-focused. Ship clean, tested, mobile-ready components.
This is a production SaaS system, not a demo project.
