# Kāinga — UI Revamp Plan

## Context
Kāinga is a NZ housing affordability assistant built on LangGraph advanced template (Vite + React + TailwindCSS + Radix UI + Framer Motion on client; FastAPI + LangGraph on backend). The current UI is functional but lacks identity, animations, domain-specific visualizations, and convenience pages. This plan revamps the system across 9 pillars — to be tackled incrementally, not all at once.

---

## Stack Recap
- **Client**: Vite + React 18 + TailwindCSS v4 + Radix UI + Framer Motion (installed) + Lucide icons + Sonner toasts
- **Server (Next.js layer)**: Node + Express-style routes in `server/src/routes/`
- **Agent**: LangGraph + FastAPI + Lakebase memory
- **Existing animation lib**: Framer Motion v11 (already installed, underused)
- **Mermaid**: needs `npm install mermaid` on client

---

Done -
## Pillar 1 — Branding & Identity
**App name: Kāinga**

**Files to touch:**
- `client/src/components/app-sidebar.tsx` — line 54-56: replace `"Chatbot"` span
- `client/src/index.css` — color token overrides
- `client/src/index.html` — `<title>` and favicon

**Changes:**
1. Replace `"Chatbot"` text → `Kāinga` + SVG wordmark/icon in sidebar header
2. Create `client/src/assets/logo.svg` — simple house + NZ fern motif or clean wordmark
3. Add domain-specific semantic CSS tokens to `index.css`:
   - `--color-affordable`, `--color-moderate`, `--color-stressed` (green/amber/red)
   - `--color-hazard-low`, `--color-hazard-medium`, `--color-hazard-high`
   - `--color-memory` (indigo/purple — used for memory tool cards)
4. Shift primary from generic blue (#2272b4) → slightly warmer teal (`#1a7a6e`) or keep blue — keep consistent with NZ brand
5. Update `<title>Kāinga</title>` in HTML entry

---

Done - 
## Pillar 2 — Sidebar & Navigation

**Files:**
- `client/src/components/app-sidebar.tsx`
- `client/src/App.tsx` — add new routes
- `client/src/layouts/ChatLayout.tsx`

**Changes:**
1. Sidebar header: logo SVG + "Kāinga" + optional tagline "Find your place in NZ"
2. Nav section below "New Chat":
   - `My Constraints` → `/constraints`
   - `Saved Searches` → `/saved`
3. Footer: show session user name + email (available from `SessionContext`)
4. Collapsed state: show only icons (house icon, bookmark icon) — sidebar primitive already supports this

---

Done
## Pillar 3 — Animations

**Framer Motion is already installed — just needs to be used.**

**Files:**
- `client/src/components/messages.tsx`
- `client/src/components/message.tsx`
- `client/src/components/greeting.tsx`
- `client/src/App.tsx` (route transitions)
- `client/src/components/elements/tool.tsx`

**Changes:**
1. **Message appear**: `motion.div` with `initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}` on each message
2. **Page transition**: `AnimatePresence` wrapping `<Routes>` in `App.tsx`
3. **Tool badge state transition**: animate badge flip (Pending → Running → Completed) via `layoutId`
4. **Greeting stagger**: title + suggested prompts animate in with staggered delay
5. **Sidebar**: spring animation on open/close

---
Done ---
## Pillar 4 — Mermaid Visualization Modals ⭐ New

**Concept**: The agent can call a special frontend-trigger tool `render_visualization(title, mermaid_code, description)`. The frontend detects this tool call and opens a full-screen modal with a rendered Mermaid diagram. This enables the agent to show flowcharts, decision trees, suburb comparison diagrams, etc. between its text responses.

**Backend changes:**
- `agent_server/agent.py` — add `render_visualization` to the tool list as a simple passthrough tool (returns `{"status": "rendered"}`)
- `agent_server/prompts.py` — update system prompt to instruct the agent when to call this tool:
  - After listing multiple suburbs → call with a comparison flowchart
  - After explaining affordability → call with a decision tree ("Can I afford X?")
  - After hazard analysis → call with a risk matrix chart

**Frontend changes:**
- `client/src/components/elements/visualization-modal.tsx` — NEW: full-screen modal that renders Mermaid code
- `client/src/components/message.tsx` — detect `render_visualization` tool call → suppress normal tool UI → trigger modal instead
- Install `mermaid` npm package: `npm install mermaid`
- Modal: title, rendered SVG diagram, close button, optional "Download as PNG" button

**Tool schema:**
```python
render_visualization(
    title: str,          # e.g. "Suburb Comparison"
    mermaid_code: str,   # valid Mermaid syntax
    description: str     # caption below the diagram
)
```

---

Done - 
## Pillar 5 — Memory Tool Special Visualization ⭐ New

**Concept**: When `get_user_memory`, `save_user_memory`, or `delete_user_memory` tool calls appear in the chat, show a distinct memory-themed card instead of the generic tool card.

**Files:**
- `client/src/components/elements/memory-tool.tsx` — NEW: dedicated memory tool renderer
- `client/src/components/message.tsx` — route memory tool calls to `MemoryTool` instead of `Tool`

**Memory Tool Card Design:**
- Purple/indigo color scheme (`--color-memory`)
- Animated brain icon (pulsing when `save_user_memory` is active)
- Human-readable display:
  - `get_user_memory` → "Recalling your preferences…" + showing what was retrieved (budget, commute, etc.)
  - `save_user_memory` → "Saving preference: {key} = {value}" with a save animation
  - `delete_user_memory` → "Forgetting: {key}" with a subtle fade-out effect
- After completion: shows a concise summary of what was stored/retrieved, not raw JSON

---

Done — saves to Lakebase `suburb_saves` table via `/api/saved-searches`; inline card in chat; `use-saved-searches` hook (SWR-backed)
## Pillar 6 — Smart Saved Search Detection + Auto-Save Modal ⭐ New

**Concept**: When the agent's response contains suburb recommendations that a user might want to save, the agent calls a special frontend-trigger tool `suggest_saved_search(suburb_name, median_rent_weekly, commute_minutes, commute_mode, hazard_risk, affordability_band)`. The frontend intercepts this tool call (invisible in chat — not rendered as a tool card), shows a "Save this suburb?" modal, and if confirmed, persists it to localStorage.

**Backend changes:**
- `agent_server/agent.py` — add `suggest_saved_search` tool (returns `{"saved": True}` immediately — it's just a trigger)
- `agent_server/prompts.py` — instruct agent: after recommending a specific suburb with concrete data (rent, commute, hazard), call `suggest_saved_search` with those details. Don't call it for vague mentions, only for concrete suburb recommendations with data.

**Frontend changes:**
- `client/src/components/saved-search-modal.tsx` — NEW: modal showing suburb card + "Save to My Searches" / "Not now" buttons
- `client/src/components/message.tsx` — detect `suggest_saved_search` tool calls → suppress tool card UI entirely → trigger modal
- `client/src/hooks/use-saved-searches.ts` — NEW: localStorage CRUD hook
  ```ts
  useSavedSearches() → { searches, save(suburb), remove(suburb_name), clear() }
  ```
- On "Save" → add to localStorage → show Sonner toast "Onehunga saved to your searches ✓"
- On "Not now" → dismiss, no side effects

**Suburb data stored in localStorage:**
```json
{
  "suburb_name": "Onehunga",
  "median_rent_weekly": 710,
  "commute_minutes": 22,
  "commute_mode": "transit",
  "hazard_risk": "low",
  "affordability_band": "affordable",
  "saved_at": "2026-05-17T..."
}
```

---

Done
## Pillar 7 — Tool Display Consistency

**Files:**
- `client/src/components/elements/tool.tsx`
- `client/src/components/message.tsx`

**Changes:**
1. Human-readable tool name labels (map function names → friendly strings):
   - `find_affordable_suburbs` → "Searching affordable suburbs…"
   - `compute_isochrone` → "Calculating commute times…"
   - `score_affordability` → "Analysing affordability…"
   - `lookup_hazards` → "Checking hazard risks…"
2. **Tool result rich cards**: For housing tools, render structured cards instead of raw JSON accordion
   - `find_affordable_suburbs` result → Suburb card grid (see Pillar 8)
   - `score_affordability` → Affordability meter (green/amber/red band indicator)
   - `lookup_hazards` → Hazard risk card with flood/coastal icons
3. Status badge colors → use semantic CSS tokens (`--success`, `--warning`, `--destructive`)
4. `render_visualization` + `suggest_saved_search` → entirely invisible in chat (no tool card rendered)
5. Memory tools (`get_user_memory`, etc.) → routed to `MemoryTool` component (Pillar 5)

---

Done — `SuburbCard` + `SavedSearchesPage` with grid, empty state, "Clear all", "Start Chat" → `/?query=...`
## Pillar 8 — Suburb Card Component + Saved Searches Page

**New files:**
- `client/src/components/suburb-card.tsx` — Reusable suburb card (used in tool results + saved searches)
- `client/src/pages/SavedSearchesPage.tsx` — `/saved` route

**Suburb Card:**
- Suburb name (prominent)
- Affordability band badge (color-coded)
- Weekly rent
- Commute time + mode icon
- Hazard risk indicators (icons: flood drop, wave)
- "Start Chat" → pre-fills chat with `Tell me more about {suburb}`
- Bookmark icon → save/remove from saved searches

**Saved Searches Page:**
- Grid of `SuburbCard` components from localStorage
- Empty state: friendly illustration + "Start a chat to find suburbs" CTA
- "Clear All" button

---

Needs some rework
## Pillar 9 — User Constraints Page

**New files:**
- `server/src/routes/memory.ts` — `GET /api/memory` → queries `AsyncDatabricksStore` for user's saved memory
- `client/src/pages/ConstraintsPage.tsx` — `/constraints` route

**Page layout:**
- Card grid showing saved constraints (budget, commute origin/mode, hazard preference, household details)
- Each value editable inline → on save → calls agent's `save_user_memory` via `/api/chat` message
- Empty state → "You haven't saved any preferences yet. Start a chat to set them up."
- "Clear All" → calls `delete_user_memory` for each key

---

## Pillar 10 — Homepage / Greeting Improvements

**File:** `client/src/components/greeting.tsx`

**Changes:**
1. Personalized greeting: "Good morning, {user.name}" from `SessionContext`
2. Animated suggested prompts (stagger-in):
   - "Find suburbs near Auckland CBD under $700/week"
   - "What's the flood risk for Onehunga?"
   - "Compare affordability: Mt Eden vs Glen Innes"
   - "Which suburbs have good transit with schools nearby?"
3. If user has saved constraints: "Based on your preferences: transit · 30 min · $750/wk"

---

## Suggested Extras (Optional, Do Later)
- Dark mode audit — ensure new components follow dark mode tokens
- Mobile: swipe-to-open sidebar gesture
- Empty chat history state with illustration
- Mermaid diagram "Download as PNG" export button

---

## Implementation Order (Incremental — Do Not Rush)

| # | Pillar | Effort | Do First? |
|---|--------|--------|-----------|
| 1 | Branding + "Kāinga" rename | 30 min | ✅ Yes |
| 2 | Sidebar nav structure | 30 min | ✅ Yes |
| 3 | Animations (messages, page transitions) | 1–2h | ✅ Yes |
| 7 | Tool display labels + consistency | 1–2h | Next |
| 5 | Memory tool special cards | 1h | Next |
| 8 | Suburb card + Saved Searches page | 2h | Next |
| 10 | Homepage greeting improvements | 1h | Next |
| 4 | Mermaid visualization modals | 3h | After above |
| 6 | Smart saved search detection modal | 2h | After above |
| 9 | User Constraints page + memory API | 3h | Last |

---

## Key Files Reference

| Area | File |
|------|------|
| Sidebar (Chatbot → Kāinga) | `client/src/components/app-sidebar.tsx:54` |
| Global CSS tokens | `client/src/index.css` |
| Routes | `client/src/App.tsx` |
| Message rendering | `client/src/components/message.tsx` |
| Tool display | `client/src/components/elements/tool.tsx` |
| Greeting | `client/src/components/greeting.tsx` |
| Agent tools | `agent_server/agent.py` |
| System prompt | `agent_server/prompts.py` |
| Memory tools | `agent_server/utils_memory.py:214-274` |
| Chat API route | `server/src/routes/chat.ts` |

---

## Verification (After Each Pillar)
- `uv run start-app` → open `localhost:8000`
- Confirm no "Chatbot" text visible
- Send a housing query → verify animations, tool labels, suburb cards
- Trigger a suburb recommendation → verify saved search modal appears
- Call memory tool → verify memory card renders (not generic tool card)
- Ask agent for an analysis → verify Mermaid modal opens
- Navigate to `/saved` and `/constraints` → pages render correctly
- Toggle dark mode → no visual regressions
