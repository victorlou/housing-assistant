# Personas

Housing Assistant is one product with two faces, sharing a single data backbone, semantic model, and agent. The two personas below differ only in their UX surface and the questions they emphasise.

## Persona 1. The renter / first-home buyer

### Who they are

Sarah, 34, recently relocated for a new role in Britomart, Auckland. Partner works from home. One child, age 6. Budget $750/week rent. Cares deeply about commute, school options, and not living in a flood zone after Cyclone Gabrielle scared her family. She has used Trade Me and OneRoof and found them disjointed and surface-level. She doesn't trust dropdown filters to capture what she actually needs.

### What she wants

To describe her life in plain English and get a shortlist of suburbs that actually work for her, with the tradeoffs explained.

### What she gets

A chat-driven Databricks App. She types her constraints, the agent asks one or two clarifying questions, then returns a ranked list with map view and per-suburb explanation. She can save the search, get alerts on listings that match, and refine over time.

A typical interaction:

> **Sarah types:** *"I work in Britomart, my partner works from home, we've got a 6-year-old, budget $750/week rent. I don't drive. Hate flood zones."*
>
> **Agent (calling Genie + isochrone + hazards):** *"Three constraints in tension here: your budget rules out most of central Auckland, the 30-minute transit constraint rules out West/South Auckland edges, and the no-flood-zone constraint rules out parts of New Lynn and Glen Eden. Top three matches:*
>
> 1. *Onehunga. Median rent $710, 24 min by bus, Royal Oak Primary EQI 423, no flood risk. Closest match overall.*
> 2. *Mt Albert. Median rent $755, 22 min by train, Edendale School EQI 405, low flood risk on the eastern side only.*
> 3. *Sandringham. Median rent $720, 28 min by bus, Sandringham School EQI 441, no flood risk."*
>
> **Sarah:** *"Save Onehunga and tell me when 3-bed listings come up under $750."*
>
> **Agent:** *"Saved. I'll check daily and email you when matches appear."*

Three things happen behind the scenes that are worth highlighting:

1. The agent disambiguates a tradeoff Sarah did not explicitly know was a tradeoff (budget vs. distance vs. flood).
2. Lakebase persists the search and the alert. The app remembers her, and the next session starts richer.
3. Genie is doing all the heavy data work, but the user never sees it. They just see a friendly assistant.

## Persona 2. The council planner

### Who they are

Daniel, 41, senior strategy advisor at a large Auckland council. He is responsible for the council's housing affordability strategy. His current toolkit is a stack of Excel files cross-referenced manually with council valuation data and Stats NZ extracts. Decisions about consenting, public housing land, and intervention investment hinge on whether he can spot affordability inflections early.

He is also a stand-in for similar roles at Kāinga Ora, MBIE, MSD, regional councils, and community housing providers like Habitat for Humanity NZ and Salvation Army Social Policy Unit.

### What he wants

A national, always-current picture of where rents are growing faster than incomes, where affordability cliffs are emerging, and where interventions are most likely to be effective. He wants to ask questions in his own words and get answers he can put in front of the mayor.

### What he gets

The AI/BI dashboard plus Genie-driven natural-language exploration. The dashboard exposes:

- A national choropleth of rent-to-income ratio by territorial authority, with trend.
- "Cliff watch": territorial authorities where rent growth has outpaced income growth by more than two standard deviations over the trailing four quarters.
- Demographic crosscuts: affordability dynamics by household size, age cohort, and ethnicity (where Stats NZ data permits at the chosen geography).
- Hazard exposure: percentage of low-income suburbs in flood / coastal-inundation zones (the "double burden" map).

He uses Genie alongside the dashboard to answer ad-hoc questions: *"which TAs have seen rent grow more than 8% YoY while incomes grew under 3%?"*, *"which Auckland local boards have the worst affordability for households in income decile 1–3?"*

## Anti-personas (deliberately not our user)

- **Real estate agents.** Tempting market, but we'd compete with CoreLogic and create commercial complexity. Out of scope.
- **Investors looking for yield.** Different question, different ethical framing. Out of scope.
- **Voters at election time.** Adjacent and tempting. Different data sources, different risk profile. Out of scope.
