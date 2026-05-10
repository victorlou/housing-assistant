# Agents

The AI agent that powers the consumer experience and any agentic capability used by the planner view.

## Layout

```
agents/
├── housing_assistant/
│   ├── agent.py            # agent definition (Mosaic AI Agent Framework)
│   ├── tools/              # one file per tool
│   │   ├── query_genie.py
│   │   ├── compute_isochrone.py
│   │   ├── score_affordability.py
│   │   ├── lookup_hazards.py
│   │   ├── save_user_profile.py
│   │   └── set_alert.py
│   ├── prompts/            # plain-text prompts (no string concat in code)
│   ├── deploy.py           # deploy to a serving endpoint
│   └── tests/
└── README.md
```

## Tool contracts

Every tool is a Python function with a typed signature and a docstring. The docstring is what Genie and the agent read to understand when to use the tool. Keep them clear and specific.

Example:

```python
def compute_isochrone(origin_h3: str, mode: str, minutes: int) -> list[str]:
    """
    Return the list of H3 cells reachable from `origin_h3` in `minutes` or fewer
    by `mode`. `mode` is one of: "transit", "drive", "walk".
    """
```

## Conventions

- Tools are pure where possible. They read from the lakehouse or Lakebase but should not have hidden state.
- The agent invokes Genie via the `query_genie` tool, never directly via HTTP.
- All agent calls log a trace to `housing.app.agent_traces` with the user's session ID.
- Prompts live as `.md` files in `prompts/` and are loaded at runtime.

## Local development

```bash
cd agents
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
pytest tests/
python -m housing_assistant.deploy --target dev
```

See `docs/runbook.md` for the full developer workflow.
