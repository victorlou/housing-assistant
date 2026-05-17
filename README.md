# Housing Assistant

> An AI-native, NZ-wide housing affordability assistant. Built on Databricks for the 2026 Databricks Hackathon (Track 1 — Social Impact / Open Data).

Housing affordability is the defining issue of New Zealand's decade. Renters, first-home buyers, and the planners who shape policy all wrestle with the same problem: the data they need — rents, incomes, transit, schools, hazards, crime — is fragmented across a dozen agencies, in a dozen formats, refreshed on a dozen different cadences. Nobody has a single, defensible national picture of where it is actually feasible to live well.

Housing Assistant is a Databricks-native application that closes that gap. It ingests open NZ data into a lakehouse, exposes it through Genie for natural-language Q&A, layers an AI agent on top to reason over the user's constraints and propose action, and persists state in Lakebase so the experience improves with every interaction. There are two faces to the product:

- **A consumer view**, where a renter or first-home buyer types their constraints in plain English and gets a ranked, explainable shortlist of suburbs they can actually afford.
- **A planner view**, where a council, Kāinga Ora, or community housing provider explores national affordability dynamics, identifies emerging cliffs, and stress-tests interventions.

The consumer view is the hook; the planner view is the heart of the value proposition.

## How it works

The system has four layers.

The **lakehouse** sits over open NZ data, modelled bronze to silver to gold with Lakeflow Declarative Pipelines. Sources include MBIE Tenancy Bond rents, Stats NZ income and census, REINZ House Price Index, Police crime statistics, Education Counts school data, LINZ parcels, regional GTFS transit feeds, and NIWA / EQC hazard layers. Unity Catalog governs everything.

A **Genie Space** sits on the gold catalog with a curated semantic model (synonyms, joins, business glossary). Users and the agent alike can ask questions like *"show me suburbs nationally with median rent under $700/week and income deciles in the bottom 40%"* and get a clean answer.

An **AI agent**, built with the Mosaic AI Agent Framework, reasons over user constraints and calls tools: `query_genie`, `compute_isochrone`, `score_affordability`, `lookup_hazards`, `save_user_profile`, `set_alert`. The agent does multi-step work: disambiguating place names, weighing tradeoffs, generating natural-language explanations.

**Lakebase, a Databricks App, and an AI/BI dashboard** form the surface. Lakebase (managed Postgres) holds user profiles, saved searches, conversation history, and alert subscriptions. The Databricks App is the consumer-facing chat experience. The AI/BI dashboard tells the macro story for the planner view.

A diagram lives at [`docs/architecture.md`](docs/architecture.md).

## Tech stack

Everything is Databricks-native, deployed via Terraform.

| Layer | Technology |
|---|---|
| Cloud | AWS, `us-west-2` |
| Workspace | Databricks Premium, serverless-only metastore |
| Storage / Governance | Unity Catalog, managed volumes |
| Pipelines | Lakeflow Declarative Pipelines (DLT) |
| Compute | Serverless SQL Warehouse |
| Semantic / Q&A | Databricks Genie |
| Agents | AgentBricks / Mosaic AI Agent Framework |
| State | Lakebase (managed Postgres) |
| Frontend | Databricks App (frontend stack TBD) |
| Dashboards | Databricks AI/BI Dashboards |
| IaC | Terraform |
| CI/CD | GitHub Actions |

## Repository layout

```
housing-assistant/
├── README.md                    ← you are here
├── docs/                        ← project docs (read these next)
│   ├── architecture.md
│   ├── data-sources.md
│   ├── personas.md
│   └── runbook.md
├── terraform/                   ← all infra-as-code
│   ├── envs/dev/
│   └── modules/
├── pipelines/                   ← Lakeflow Declarative Pipelines (bronze→silver→gold)
├── agents/                      ← agent definitions, tools, evaluation
├── app/                         ← Databricks App (frontend + backend)
├── dashboards/                  ← AI/BI dashboard exports
├── notebooks/                   ← exploration, prototypes
├── data/                        ← canonical source registry (sources.yaml)
└── .github/                     ← CI workflows, PR template, CODEOWNERS
```

Most top-level folders have a `README.md`. Pipeline-specific operator YAML lives under each `pipelines/<name>/` folder.

## Getting started

> Full setup instructions are in [`docs/runbook.md`](docs/runbook.md). Quick version below.

```bash
# clone
git clone git@github.com:victorlou/housing-assistant.git
cd housing-assistant

# infra
cd terraform/envs/dev
# set DATABRICKS_CONFIG_PROFILE (or HOST + TOKEN); see docs/runbook.md
terraform init
terraform plan
terraform apply
```

You will need Databricks credentials in the environment (for example `databricks auth login --profile <name>` plus `DATABRICKS_CONFIG_PROFILE=<name>` for Terraform) and AWS credentials with read access to the workspace when your task needs S3 or other AWS access. Local Python setup is in [`docs/runbook.md`](docs/runbook.md).

## Further reading

- [Architecture deep-dive](docs/architecture.md)
- [Open data source catalogue](docs/data-sources.md)
- [Personas](docs/personas.md)
- [Developer runbook](docs/runbook.md)
