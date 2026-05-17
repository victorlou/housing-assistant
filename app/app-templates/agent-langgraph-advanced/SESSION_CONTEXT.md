# Session Context — Kāinga UI Revamp

## Application Summary

**Name:** Kāinga (Māori for home/village) — NZ housing affordability assistant  
**Stack:** LangGraph advanced template on Databricks Apps, FastAPI backend, Vite + React 18 frontend  
**Purpose:** Helps NZ consumers (renters/first-home buyers) and planners (council/government) find and analyse suburbs based on commute, affordability, and climate risk

---

## Key File Locations

### Agent Server
- `agent_server/agent.py` — LangGraph agent definition, tools list, state
- `agent_server/prompts.py` — System prompt (consumer + planner personas)
- `agent_server/utils_memory.py:214–274` — Memory tools: `get_user_memory`, `save_user_memory`, `delete_user_memory`
- `agent_server/start_server.py` — FastAPI + MLflow setup, Lakebase init

### UI (e2e-chatbot-app-next)
- `client/src/components/app-sidebar.tsx:54` — "Chatbot" text → change to "Kāinga"
- `client/src/index.css` — CSS design tokens (color, typography, shadows)
- `client/src/App.tsx` — Routes
- `client/src/components/message.tsx` — Renders all message parts (text, tools, MCP, reasoning)
- `client/src/components/elements/tool.tsx` — Generic tool card (Pending/Running/Completed states)
- `client/src/components/elements/mcp-tool.tsx` — MCP tool card with approval actions
- `client/src/components/greeting.tsx` — Homepage empty state
- `client/src/components/chat.tsx` — Main chat logic (useChat hook)
- `client/src/layouts/ChatLayout.tsx` — Sidebar + main content layout
- `client/src/contexts/SessionContext.tsx` — user id, email, name
- `server/src/routes/chat.ts` — Next.js API layer, proxies to FastAPI agent

---

## Agent Tools (Current)

| Tool | Purpose | Returns |
|------|---------|---------|
| `find_affordable_suburbs` | Combined commute + rent + hazard filter | Ranked suburb list with rent, affordability band, hazard, income decile |
| `compute_isochrone` | Reachable suburbs within time window | List of reachable suburbs |
| `score_affordability` | Single suburb rent-to-income analysis | rent_to_income_pct, affordability_band |
| `lookup_hazards` | Flood + coastal risk for suburb | flood_risk, coastal_risk, overall_risk |
| `get_user_memory` | Semantic search over saved preferences | JSON values |
| `save_user_memory` | Store a preference key-value | success/error |
| `delete_user_memory` | Remove a preference | success/error |
| `get_current_time` | Utility | ISO datetime |

**New tools to add (backend):**
- `render_visualization(title, mermaid_code, description)` — frontend trigger for Mermaid modal, returns `{"status": "rendered"}`
- `suggest_saved_search(suburb_name, median_rent_weekly, commute_minutes, commute_mode, hazard_risk, affordability_band)` — frontend trigger for save modal, returns `{"saved": True}`

---

## UI Stack Details

- **Framework:** Vite + React 18.2, React Router DOM 6.22, TypeScript 5.9
- **Styling:** TailwindCSS v4.1, Radix UI primitives, shadcn-style `ui/` wrappers
- **Animations:** Framer Motion v11 (installed, underused)
- **Icons:** Lucide React
- **Themes:** `next-themes` with CSS vars, `attribute="class"`, supports dark mode
- **Toast:** Sonner (installed)
- **Mermaid:** needs `npm install mermaid` in `client/`

---

## Current Color Tokens (index.css)
- Primary: `#2272b4` (blue-600)
- Secondary: `#f6f7f9` (grey-050)
- Destructive: `#c82d4c` (red-600)
- Success: `#277c43` (green-600)
- Warning: `#be501e`

**New semantic tokens to add:**
```css
--color-affordable: #277c43;
--color-moderate: #be501e;
--color-stressed: #c82d4c;
--color-hazard-low: #277c43;
--color-hazard-medium: #be501e;
--color-hazard-high: #c82d4c;
--color-memory: #6366f1;  /* indigo — for memory tool cards */
```

---

## Memory Architecture

- **Short-term (session):** `AsyncCheckpointSaver` → Lakebase PostgreSQL, keyed by `thread_id`
- **Long-term (user):** `AsyncDatabricksStore` → Lakebase, namespace `("user_memories", user_id.replace(".", "-"))`
- Memory data example stored by agent:
  ```json
  { "budget_weekly": 750, "commute_origin": "Britomart", "mode": "transit", "commute_minutes": 30, "hazard_constraint": "no high flood risk", "school_needed": true }
  ```
- `user_id` comes from session: `X-Forwarded-Email` header → `SessionContext`
- `thread_id` comes from: `custom_inputs.thread_id` → `context.conversation_id` → generated UUID7

---

## New Components to Build

| Component | Path | Purpose |
|-----------|------|---------|
| `MemoryTool` | `client/src/components/elements/memory-tool.tsx` | Purple/indigo card for memory tool calls, animated brain icon |
| `VisualizationModal` | `client/src/components/elements/visualization-modal.tsx` | Full-screen Mermaid diagram modal |
| `SavedSearchModal` | `client/src/components/saved-search-modal.tsx` | "Save this suburb?" prompt modal |
| `SuburbCard` | `client/src/components/suburb-card.tsx` | Reusable suburb card (tool results + saved searches page) |
| `SavedSearchesPage` | `client/src/pages/SavedSearchesPage.tsx` | `/saved` route, grid of SuburbCards from localStorage |
| `ConstraintsPage` | `client/src/pages/ConstraintsPage.tsx` | `/constraints` route, displays/edits saved user preferences |
| `use-saved-searches` | `client/src/hooks/use-saved-searches.ts` | localStorage CRUD hook for saved suburbs |

---

## Routing Changes (App.tsx)
Add routes: `/saved` → `SavedSearchesPage`, `/constraints` → `ConstraintsPage`

---

## Tool Display Mapping (tool.tsx)
```ts
const TOOL_LABELS: Record<string, string> = {
  find_affordable_suburbs: "Searching affordable suburbs…",
  compute_isochrone: "Calculating commute times…",
  score_affordability: "Analysing affordability…",
  lookup_hazards: "Checking hazard risks…",
  get_user_memory: "Recalling your preferences…",
  save_user_memory: "Saving preference…",
  delete_user_memory: "Removing preference…",
  render_visualization: "", // invisible
  suggest_saved_search: "", // invisible
};
```

---

## Saved Search localStorage Schema
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
Key: `kainga_saved_searches` in localStorage.

---

## Misc Notes
- `framer-motion` already in package.json — just not used yet
- Sidebar collapse already supported by Radix `useSidebar()` hook — icon-only mode works
- `SessionContext` exposes `session.user.name`, `.email`, `.id` — use for personalized greeting
- Sonner `<Toaster>` already mounted in `App.tsx` — just call `toast()` from anywhere
- Tool cards already distinguish standard tools vs MCP tools — memory tools need a third path in `message.tsx`
- `render_visualization` and `suggest_saved_search` tool calls must be intercepted BEFORE normal tool rendering in `message.tsx` and never shown as tool cards
