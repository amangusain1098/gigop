# Codex Round 3 Brief — GigOptimizer Pro

**Date:** 2026-04-11  
**Branch:** main  
**Last commit:** `4f4a268 fix(scraper): tighten seller URL regex`

---

## What was just fixed (do NOT revert or touch)

| File | Fix |
|---|---|
| `gigoptimizer/connectors/fiverr_marketplace.py` | Seller URL regex now requires `?` immediately after username — prevents gig title links from being consumed as seller names (was returning 0 gigs). All 3 `test_marketplace_reader` tests now pass. |
| `gigoptimizer/api/main.py` | Double memory injection removed — `ConversationMemory.summary()` only injected into prompt when non-empty, and second injection in grounding_lines fallback path removed. |
| `gigoptimizer/assistant/api_routes.py` | Truncated `[` at line 249 restored — file was 256→258 lines, AST clean. |
| `frontend/src/App.css` | Mobile breakpoints added at 768px and 480px. |

---

## Current test state

- **95 pure-Python tests** run via `python3 -m unittest discover tests/ -q`
- **3 pass, 0 fail** for `test_marketplace_reader`
- **28 pass, 0 fail** for `test_marketplace_reader + test_conversation_memory + test_assistant`
- 17 tests error-out due to missing `fastapi`/`httpx`/`sqlalchemy` in sandbox — not code bugs
- All Python files: AST clean (`python3 -c "import ast, pathlib; ..."`)

---

## Tasks for Codex Round 3

### 1. Frontend build verification (MUST DO FIRST)
```
cd frontend && npm run build
```
Fix any TypeScript errors before proceeding. The App.tsx has streaming SSE code and ReactMarkdown import — confirm it compiles clean.

### 2. Unit tests for intent classification
**File:** `tests/test_intent_classification.py`  
Write a `unittest.TestCase` covering `_classify_intent()` from `gigoptimizer/assistant/assistant.py`:
- greetings: "hi", "hello", "hey", "good morning", "hola"
- thanks: "thanks", "thank you", "ty", "thx", "cheers"  
- how_are_you: "how are you", "hows it going", "whats up"
- identity: "who are you", "are you a bot", "what is your name"
- capability: "what can you do", "help me", "how does this work"
- task (must NOT match above): "optimize my logo gig title", "what keywords rank best for video editing", "analyze my fiverr competitors", "write seo tags for my gig"
- edge cases: empty string → "empty", 9+ word sentences → "task"

### 3. iOS keyboard safe area for chat compose bar
**File:** `frontend/src/App.css`  
Find the `.compose-inner` or `.chat-input-row` selector and add:
```css
padding-bottom: max(12px, env(safe-area-inset-bottom));
```
Also ensure `position: sticky; bottom: 0;` has `z-index: 100` to stay above iOS Safari toolbar.

### 4. Scraper: surface seller parse errors in API response
**File:** `gigoptimizer/assistant/api_routes.py`  
In the competitor analysis endpoint (look for `FiverrMarketplaceConnector`), if the returned list of gigs is empty, add a `"warning"` field to the JSON response:
```python
if not gigs:
    result["warning"] = "No competitor gigs parsed — Fiverr may have changed markup or returned a challenge page."
```
Do not raise an exception — return the warning alongside the empty result so the frontend can display it gracefully.

### 5. Dashboard: show live copilot session count
**File:** `gigoptimizer/api/main.py` and `frontend/src/App.tsx`  
Add a GET endpoint `/api/assistant/sessions/count` that returns:
```json
{"active_sessions": 3, "total_sessions": 47}
```
Count by scanning `data/conversations/` for `.jsonl` files. Active = modified within last 30 minutes.  
In the frontend status bar (`.live-status-bar` added by Codex), add a chip: `💬 3 active sessions`.

### 6. Error boundary for assistant chat panel
**File:** `frontend/src/App.tsx`  
Wrap the entire assistant chat JSX in a React error boundary component. If streaming throws or the fetch fails, show a fallback UI:
```
⚠️ Copilot is temporarily unavailable. Try refreshing.
```
Do NOT use a class component — use the pattern with `react-error-boundary` or a simple `try/catch` in the `sendAssistantMessage` function that sets an `assistantError` state and renders the fallback inline.

---

## Critical constraints

1. **Do NOT touch** `gigoptimizer/assistant/assistant.py`, `gigoptimizer/assistant/client.py`, `gigoptimizer/assistant/prompts.py` — these were hand-crafted and verified. Any edit to these files will break conversational routing.
2. **Do NOT truncate files** — if you edit a file, always write the complete file content. Truncated files cause SyntaxError and break the entire backend.
3. **Run AST check after every Python file edit:**
   ```bash
   python3 -m py_compile <file.py>
   ```
4. **Run tests after scraper changes:**
   ```bash
   python3 -m unittest tests.test_marketplace_reader -v
   ```
5. After all changes, commit with descriptive messages and push to `main`.

---

## Mount/path notes for Codex environment

- Windows path: `D:\gigoptimizer-pro\`
- If using bash: `/sessions/.../mnt/gigoptimizer-pro/`
- git index.lock may appear in mounted repo — if `git add` fails, clone to `/tmp/`, commit there, copy back.
