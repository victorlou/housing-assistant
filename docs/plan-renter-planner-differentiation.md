# Plan: Differentiate Renter vs Planner Mode

> **Status:** Proposed — awaiting approval  
> **Branch:** `worktree-housing-dev`  
> **Scope:** Agent server layer + minimal frontend signal changes

---

## Context and Problem

Kāinga serves two distinct personas out of one undifferentiated agent:

- **Consumer / Renter (Sarah)** — chat-first, looking for a suburb to rent in, budget + commute + schools + hazard constraints
- **Planner / Council Analyst (Daniel)** — data-first, macro affordability analysis, trend monitoring, policy decision support

The organising team flagged three problems:

1. **Genie Space ≠ AI/BI Dashboard confusion.** The system prompt describes the Genie Space MCP tool as `ask`, but actual tool names surfaced to the model are `query_space_*` and `poll_response_*`. Users and reviewers believe the agent is "generating a dashboard from a prompt" when it actually returns inline tabular data in chat. The embedded Lakeview dashboard in the Dashboard tab is a completely separate, pre-built surface the agent cannot modify.

2. **No user-type signal.** The agent tries to infer consumer vs planner from conversational cues, with no first-turn identification mechanism and no memory of role between sessions.

3. **Planner workflow is shallow and missing a key tool.** The `lakehouse-gold-schema.md` already documents an `affordability_context(ta_name)` tool that queries `ta__month` (monthly rent trends) and `ta__quarter` (quarterly affordability indices, 25 years back to 2001). This tool does not exist in `agent_server/tools/`. Planners have no clean way to get TA-level trend data without routing through the Genie Space — which has variable output format and 60-second latency.

---

## What Will Change

| File | Change type | Summary |
|---|---|---|
| `agent_server/prompts.py` | Surgical additions | User-type identification, Genie/Dashboard distinction, planner orientation message, `affordability_context` guidance, planner workflow expansion |
| `agent_server/tools/affordability_context.py` | **New file** | Queries `ta__month` + `ta__quarter` for TA-level trend and affordability index data |
| `agent_server/tools/__init__.py` | 1-line export | Export `affordability_context` |
| `agent_server/agent.py` | 2-line change | Import + register `affordability_context` in the tools list |
| `e2e-chatbot-app-next/client/src/pages/DashboardPage.tsx` | Add a banner | Planner orientation strip above the embedded dashboard |
| `e2e-chatbot-app-next/client/src/components/greeting.tsx` | Swap 2 prompts | Replace 2 of 4 consumer-only starters with planner-oriented ones |

---

## Change 1 — `agent_server/prompts.py` (surgical additions)

Four specific sections are added/modified. The consumer workflow and Mermaid rules are untouched.

### 1a. Clarify Genie Space vs AI/BI Dashboard (tool description block)

Replace the current `ask (Genie space …)` description with:

```
**Genie Space (tool names: query_space_*, poll_response_*)**
Your bulk data tool. Translates natural language into SQL against housing.gold.* and returns
results INLINE in this chat as text and tables. This is NOT the AI/BI Dashboard.
Call it after compute_isochrone for bulk rent/income/demographic data, or directly for
any ad-hoc data question that doesn't need isochrone scoping.
Example: "Give me median weekly rent, income decile, and rent-to-income % for these suburbs:
[list]. Order by rent-to-income desc."
Do NOT use for: hazard risk (use lookup_hazards), commute reachability (use compute_isochrone),
TA-level trends (use affordability_context).

NOTE: The AI/BI Dashboard in the sidebar's Dashboard tab is a separate embedded Lakeview
dashboard. The agent cannot create or modify it. When a planner asks for a "dashboard view",
clarify that the Dashboard tab already shows the macro picture (choropleth, cliff watch,
hazard overlay), and offer to generate an inline Mermaid comparison chart instead.
```

### 1b. Add `affordability_context` tool description

After the `lookup_hazards` entry, add:

```
**affordability_context(ta_name)**
PLANNER TOOL — call for any TA-level trend or affordability index question.
Returns:
  - Recent 12 months of rent from ta__month (median_rent_nzd, lower_quartile_rent_nzd,
    housing_register, housing_register_per_10k_pop)
  - Recent 8 quarters of HUD affordability indices from ta__quarter
    (rent_affordability_index, mortgage_affordability_index, deposit_affordability_index,
    median_to_median_ratio — 25 years of history available)
  - Computed trend label: "rising" / "stable" / "falling" (based on rent 12-month window)
Trigger phrases: "TA trend", "affordability index", "rent growth", "which TAs are worsening",
"cliff watch", "time series", "year-on-year", "quarterly trend", "housing register".
Do NOT call for individual suburb lookups — use score_affordability for suburb-level data.
Do NOT call for consumers — call score_affordability instead.
```

### 1c. User-type identification (add at the very top of the system prompt, before all other sections)

```
## Identifying who you're talking to

Step 1 — ALWAYS call get_user_memory("role") at the start of every conversation.

If memory contains {"role": "consumer"} or {"role": "planner"} → use that workflow. Skip step 2.

Step 2 — If no role is in memory, ask this single question as your FIRST response
(before any suburb analysis or data lookup):
  "Quick question before I start — are you looking for a home to rent or buy,
   or are you analysing housing data for planning or policy work?"

As soon as the user answers:
  - Consumer / renter → call save_user_memory("role", {"role": "consumer"})
  - Planner / council / policy → call save_user_memory("role", {"role": "planner", "organisation": ""})

Never ask the role question again within the same thread.
```

### 1d. Planner first-turn orientation message (add to planner workflow, step 0)

When the planner role is confirmed for the first time (memory was empty and user just answered), include this at the start of the first substantive response:

```
Planner mode — step 0 (first turn only):
When you first confirm a planner role and move to answer their question, open your response
with this orientation (one paragraph, plain text, no heading):

"Kāinga for planners works across two surfaces: this Chat (powered by Genie Space data
queries and dedicated tools for trends, commute isochrones, suburb affordability, and
hazard lookup) and the Dashboard tab in the sidebar (a pre-built Lakeview view showing
rent-to-income by TA, cliff-watch alerts, and hazard overlays). Use the Dashboard for
the macro picture, then ask me here to drill into specific TAs, suburbs, or time windows."

Do NOT repeat this orientation on subsequent turns.
```

### 1e. Expand planner workflow

Replace the current 5-step planner workflow with:

```
## Planner workflow

1. get_user_memory("role analysis context") — load role and any saved focus areas.
2. Scope the question: single TA, a set of TAs, suburb-within-TA, or national?
3. If commute-zone scoping needed: compute_isochrone. Otherwise skip.
4. Bulk demographics and current snapshot — Genie Space (query_space_*):
   - Rent/income/decile for a suburb list after isochrone
   - Cross-TA comparison: "Give me current median rent, rent-to-income %, and income
     decile for these TAs: [list]. Order by rent-to-income desc."
5. TA trend analysis — call affordability_context(ta_name) for any TA that:
   - Shows rent-to-income > 35%, OR
   - The user is specifically asking about trends, growth, or worsening affordability.
   Use ta__quarter data (affordability indices) to describe whether stress is new or
   entrenched; use ta__month data (housing register) to show social-housing pressure.
6. Hazard overlay — call lookup_hazards for the 3–5 most stressed suburbs.
7. Return a markdown table for 3+ suburbs/TAs. Columns as relevant:
   TA / Suburb | Rent/wk | Rent-to-income | Band | Trend | Hazard
8. Call render_visualization if presenting a risk matrix across 3+ dimensions (Mermaid
   flowchart LR, not TD — left-right reads better for TA comparison tables).
9. DO NOT call suggest_saved_search — this is consumer-only.
10. Cite data recency: census_year from score_affordability / data_year; ta_data_month
    from the affordability_context output.
11. End with a proposed follow-on question ("Want me to drill into the suburbs within
    [most stressed TA] that are also in flood zones?").
```

### 1f. Consumer workflow — two additions only

Add to consumer workflow (don't change existing steps):

```
DO NOT call affordability_context — it returns TA-level data that is not meaningful
for individual suburb searches. Use score_affordability for suburb rent figures.
```

---

## Change 2 — New tool: `agent_server/tools/affordability_context.py`

Implements the `affordability_context(ta_name)` stub already documented in `docs/lakehouse-gold-schema.md`.

### Pattern
Follows the exact same structure as `score_affordability.py`:
- Imports `execute_statement`, `CATALOG`, `SCHEMA` from `tools/utils.py`
- Uses `@tool` from `langchain_core.tools`
- Uses the Statement Execution API (no Spark)
- TA fuzzy matching via direct ILIKE on `ta__month.ta_name` (no `resolve_suburb_fuzzy` — that function operates on the `suburb` table, not `ta__month`)

### Tool signature and docstring

```python
@tool
def affordability_context(ta_name: str) -> dict:
    """Get TA-level affordability trends for planner analysis.

    Returns recent monthly rent data from ta__month and quarterly HUD affordability
    indices from ta__quarter. Use this — not score_affordability — when the user
    asks about territorial-authority trends, rent growth, affordability indices,
    the housing register, or quarter-on-quarter changes.

    DO NOT call for individual suburbs or for consumer (renter) queries.

    Args:
        ta_name: Territorial authority name (e.g. "Auckland", "Wellington City",
                 "Christchurch City", "New Zealand" for the national rollup).

    Returns:
        Dict with:
          - ta: matched TA name
          - monthly_rent: list of last 12 months [{month, median_rent_nzd,
              lower_quartile_rent_nzd, housing_register, housing_register_per_10k_pop}]
          - quarterly_indices: list of last 8 quarters [{quarter_label,
              rent_affordability_index, mortgage_affordability_index,
              deposit_affordability_index, median_to_median_ratio}]
          - rent_trend: "rising" | "stable" | "falling"
          - rent_change_12m_pct: % change over the 12-month window (float or null)
          - error: present only if TA not found
    """
```

### SQL queries

**Query 1 — last 12 months from `ta__month`:**
```sql
SELECT date, median_rent_nzd, lower_quartile_rent_nzd,
       housing_register, housing_register_per_10k_pop
FROM {CATALOG}.{SCHEMA}.ta__month
WHERE ta_name ILIKE :ta
ORDER BY date DESC
LIMIT 12
```

**Query 2 — last 8 quarters from `ta__quarter`:**
```sql
SELECT quarter_label, rent_affordability_index, mortgage_affordability_index,
       deposit_affordability_index, median_to_median_ratio
FROM {CATALOG}.{SCHEMA}.ta__quarter
WHERE ta_name ILIKE :ta
ORDER BY quarter DESC
LIMIT 8
```

**Trend computation:** Compare average of oldest 3 vs newest 3 monthly `median_rent_nzd`:
- rising if newest_avg > oldest_avg × 1.02
- falling if newest_avg < oldest_avg × 0.98
- stable otherwise

Return data sorted oldest → newest (reverse the DESC-fetched list).

---

## Change 3 — `agent_server/agent.py` (2 lines)

```python
# add import at top with other tool imports
from agent_server.tools.affordability_context import affordability_context

# add to tools list in init_agent(), after lookup_hazards
tools = [
    get_current_time,
    compute_isochrone,
    score_affordability,
    lookup_hazards,
    affordability_context,   # ← add this
    suggest_saved_search,
    render_visualization,
] + memory_tools()
```

---

## Change 4 — `DashboardPage.tsx` (orientation banner)

Add a compact info strip immediately inside the outer `motion.div`, before the loading check. Import `Link` from `react-router-dom` (already used elsewhere in the app).

```tsx
{/* Planner orientation strip */}
<div className="flex items-center justify-between gap-4 px-4 py-2 border-b bg-muted/40 text-xs text-muted-foreground shrink-0">
  <span>
    Macro affordability view — use{' '}
    <Link to="/" className="font-medium text-foreground underline-offset-2 hover:underline">
      Chat
    </Link>{' '}
    to drill into any TA, suburb, or risk shown here.
  </span>
</div>
```

This is the "1-line explanation surfaced in the UI" requested by the organising team. It is not generated by the agent (it's static), but the agent also delivers the orientation paragraph on first planner turn (Change 1d).

---

## Change 5 — `greeting.tsx` (swap 2 suggested prompts)

Replace 2 of the 4 consumer-only `SUGGESTED_PROMPTS` with planner-oriented starters so the empty-state screen speaks to both audiences:

```typescript
// Before
const SUGGESTED_PROMPTS = [
  'Best suburbs within 30 min transit of Newmarket under $650 a week',
  'Is Takanini at high flood or coastal risk?',
  'Compare rent and affordability in Avondale and New Lynn',
  'Which suburbs near Manukau have the lowest income deciles?',
];

// After
const SUGGESTED_PROMPTS = [
  'Best suburbs within 30 min transit of Newmarket under $650 a week',   // consumer
  'Is Takanini at high flood or coastal risk?',                           // consumer
  'Which TAs had the fastest rent growth over the last 4 quarters?',      // planner
  'Show affordability index trends for Auckland and Wellington City',      // planner
];
```

---

## What Is Explicitly NOT Changed

- Consumer workflow steps (intact, proven)
- Mermaid visualization rules and validation
- Memory tooling (`get_user_memory`, `save_user_memory`, `delete_user_memory`)
- Genie Space MCP server configuration or space ID
- The embedded AI/BI Dashboard definition (`dashboards/planner/`)
- Data pipelines
- No frontend mode toggle — user type is determined via memory + first-turn question only

---

## Verification Steps

After implementation, test with `uv run start-app` in `app/app-templates/agent-langgraph-advanced/`:

1. **First-turn disambiguation**: New chat with cleared memory → agent asks consumer/planner question → answer "planner" → agent saves role, next response includes orientation paragraph mentioning Dashboard tab.

2. **Planner trend query**: Send "Show me Auckland affordability trends for the last year" → agent calls `affordability_context("Auckland")` → returns rent trend + quarterly indices.

3. **Genie vs Dashboard clarity**: Send "Can you create a dashboard?" → agent explains it cannot modify the AI/BI Dashboard, offers a Mermaid chart or points to the Dashboard tab.

4. **Consumer flow unchanged**: New chat with no memory → answer "renter" → sends "Best suburbs near Newmarket under $650" → agent runs consumer workflow without calling `affordability_context`.

5. **Dashboard page**: Navigate to `/dashboard` → orientation strip visible above the embedded dashboard with "Chat" link.

6. **No `suggest_saved_search` for planners**: Run full planner analysis → confirm no save-search prompt is triggered.
