# App

The Databricks App that hosts the consumer chat experience. Authenticates via workspace SSO; talks to the agent serving endpoint and Lakebase.

## Layout

The frontend stack is **TBD** pending team discussion (likely Streamlit for speed, or React + FastAPI for polish).

The likely shape, once decided:

```
app/
├── frontend/               # Streamlit OR React+Next, depending on stack choice
├── backend/                # FastAPI service if we go React
├── databricks_app.yml      # Databricks App definition
└── README.md
```

If Streamlit:

```
app/
├── streamlit_app.py
├── pages/
├── components/
├── databricks_app.yml
└── requirements.txt
```

If React + FastAPI:

```
app/
├── frontend/               # Next.js
├── backend/                # FastAPI service that talks to the agent + Lakebase
├── databricks_app.yml
└── README.md
```

## What it does

- Authenticates the user via workspace SSO.
- Streams agent responses (chat).
- Renders a map of ranked suburbs with explanations.
- Lists the user's saved searches and alerts.
- Persists conversation history to Lakebase via the agent's `save_user_profile` tool.

## What it does NOT do

- Talk to Genie directly. All Genie access goes via the agent.
- Manage authentication. Workspace SSO only.
- Hold business logic. Ranking, scoring, and reasoning live in the agent.

## Local development

Instructions land here once the frontend stack is chosen.
