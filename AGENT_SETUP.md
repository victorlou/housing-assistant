# Agent Setup Guide

This document summarizes what's been created and what you need to do next.

## ✅ What's Been Created

### Documentation (docs/internal-workings/)
- **README.md** — Navigation hub for all guides (start here)
- **01-langgraph-agents-101.md** — LangGraph fundamentals with diagrams
- **02-agent-implementation-guide.md** — Housing Assistant design + Day 1-5 roadmap
- **03-mlflow-evaluation-deployment.md** — MLflow integration guide
- **04-lakebase-auth-state.md** — User state management with ER diagrams

**Total reading time: ~2 hours**

### Skeleton Code (agents/)
- **state.py** — AgentState class definition
- **agent.py** — StateGraph with nodes (inject_context, agent, tools)
- **tools/** — Six @tool functions (all stubbed, ready to implement)
- **prompts/system.md** — System prompt template
- **deploy.py** — MLflow logging & serving
- **requirements.txt** — All dependencies
- **eval/golden_dataset.jsonl** — Test cases for evaluation
- **tests/test_tools.py** — Test template for score_affordability

### Updated Files
- **agents/README.md** — Links to guides + quick start
- **docs/architecture.md** — Added link to internal-workings

## 🎯 Next Steps (Day 1-5 Roadmap)

Follow the development roadmap from [02-agent-implementation-guide.md](docs/internal-workings/02-agent-implementation-guide.md):

### Day 1: Foundations
- [ ] Read 01-langgraph-agents-101.md
- [ ] Skim 02-agent-implementation-guide.md
- [ ] Implement **score_affordability** (pure Python, no Databricks)
- [ ] Write unit tests for scoring logic
- [ ] Test edge cases (budget too tight, edge of threshold, etc.)

### Day 2: Graph Skeleton
- [ ] Read 02-agent-implementation-guide.md in full
- [ ] Stub all six tools (return hardcoded data)
- [ ] Compile the StateGraph locally
- [ ] Test basic loop (START → agent → tools → agent → END)
- [ ] Verify disambiguation logic (agent asks clarifying Q)

### Day 3: Data Connections
- [ ] Implement **query_genie** (async polling to Genie API)
- [ ] Implement **compute_isochrone** (SQL to fact_isochrone table)
- [ ] Implement **lookup_hazards** (SQL to dim_hazard table)
- [ ] Test with real gold table data

### Day 4: State Persistence
- [ ] Read 04-lakebase-auth-state.md
- [ ] Implement **save_user_profile** (psycopg2 UPSERT)
- [ ] Implement **set_alert** (psycopg2 INSERT)
- [ ] Test Lakebase connection
- [ ] Verify SSO → user_id mapping

### Day 5: Evaluation & Deployment
- [ ] Read 03-mlflow-evaluation-deployment.md
- [ ] Populate golden_dataset.jsonl (5-10 test cases)
- [ ] Run MLflow evaluation
- [ ] Log model to Unity Catalog
- [ ] Create serving endpoint (via Terraform)
- [ ] End-to-end test via Databricks App

## 🚀 Quick Start (Minimal Setup)

To test locally **without Databricks**:

```bash
cd agents

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Test the graph skeleton
python -c "
from agent import agent_graph
from state import AgentState

result = agent_graph.invoke({
    'messages': [{'role': 'user', 'content': 'Test message'}],
    'user_id': 'test-user',
    'session_id': 'test-session',
})

print('Graph works!')
print(f'Messages: {len(result[\"messages\"])}')
"
```

**Expected output:**
```
Graph works!
Messages: 2
```

(One user message + one agent response/clarification)

## 📚 Key Files to Know

| File | Purpose |
|------|---------|
| `agents/state.py` | AgentState definition (what flows between nodes) |
| `agents/agent.py` | StateGraph + nodes (the orchestrator) |
| `agents/tools/*.py` | Individual @tool functions |
| `agents/prompts/system.md` | System prompt (loaded at runtime) |
| `agents/deploy.py` | MLflow logging + serving |
| `docs/internal-workings/02-*` | Implementation guide (reference while coding) |
| `docs/architecture.md` | System design (data layers, Genie, Lakebase) |

## ⚙️ Development Workflow

### Local Testing
```bash
# Run tests
pytest tests/

# Test agent locally
python -c "from agent import agent_graph; ..."

# View MLflow UI
mlflow ui
# Open http://localhost:5000
```

### Deploy to MLflow
```bash
# Log model (requires Databricks credentials in ~/.databrickscfg)
python deploy.py dev

# This will:
# 1. Log agent graph to MLflow
# 2. Log system prompt as artifact
# 3. Run evaluation (if golden_dataset.jsonl exists)
# 4. Register to Unity Catalog (housing.app.housing_agent)
```

### Create Serving Endpoint
```bash
# Via Terraform (see terraform/modules/agent_serving/)
cd terraform/envs/dev
terraform apply -target=databricks_model_serving_endpoint.housing_agent
```

## 📋 Checklist for Production

Before deploying to production:

- [ ] All 6 tools implemented + tested
- [ ] System prompt refined (no breakage, good disambiguation)
- [ ] Golden dataset complete (5+ test cases per major flow)
- [ ] MLflow evaluation metrics > targets (correctness > 0.85)
- [ ] Model registered to Unity Catalog
- [ ] Service principal `sp-housing-app` has grants
- [ ] Lakebase migrations applied (`alembic upgrade head`)
- [ ] Serving endpoint created with correct env vars
- [ ] App integrated with endpoint URL
- [ ] Monitoring dashboard set up (latency, errors, token usage)

## 🆘 Troubleshooting

**Graph won't compile?**
- Check `state.py` imports all required types
- Verify all tools are @tool-decorated with typed signatures
- Ensure ToolNode gets list of tools

**Tools fail silently?**
- Add print statements in tool functions
- Check CURRENT_USER_ID / CURRENT_SESSION_ID env vars
- Verify Databricks/Lakebase connections

**MLflow evaluate fails?**
- Check golden_dataset.jsonl is valid JSONL (one object per line)
- Ensure model_uri is correct (run mlflow.ui to find it)
- Verify model has input_example and signature defined

**Serving endpoint won't start?**
- Check service principal has USE_MODEL grant
- Verify environment variables are set (LAKEBASE_HOST, etc.)
- Check model logs in Databricks UI

## 📖 Further Reading

- [LangGraph docs](https://langchain-ai.github.io/langgraph/)
- [MLflow docs](https://mlflow.org/docs/latest/index.html)
- [Databricks SDK docs](https://databricks-sdk-py.readthedocs.io/)
- [Genie API docs](https://docs.databricks.com/en/genie/index.html) (Databricks internal)

## Questions?

Refer to the appropriate guide:
- **LangGraph**: 01-langgraph-agents-101.md
- **Housing Agent design**: 02-agent-implementation-guide.md
- **MLflow workflow**: 03-mlflow-evaluation-deployment.md
- **Lakebase & auth**: 04-lakebase-auth-state.md
- **System design**: docs/architecture.md

Good luck! 🚀
