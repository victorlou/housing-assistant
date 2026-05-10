# Developer runbook

This is the practical guide to working on Housing Assistant. If something here is wrong or out of date, fix it in the same PR as the code change. Outdated runbooks are worse than no runbook.

## Prerequisites

You will need:

- **Databricks workspace access.** AWS, `us-west-2`, Premium tier. Workspace admin can grant you access.
- **Personal access token** (Databricks → User Settings → Access Tokens). Used for CLI and Terraform.
- **AWS credentials** with at least read access to the Databricks-managed buckets, only if your task needs it. Most tasks do not.
- **Local toolchain:**
  - `terraform` ≥ 1.7
  - `databricks` CLI ≥ 0.230
  - Python 3.11
  - `uv` for Python env management (recommended) or `venv` + `pip`
  - `pre-commit` for hooks
  - Node 20 + pnpm (only if you're working on the React frontend)
- **GitHub access** to `github.com/victorlou/housing-assistant`. Branch protection is enabled on `main`; you'll work on feature branches and merge via PR.

## First-time setup

```bash
# clone and enter
git clone git@github.com:victorlou/housing-assistant.git
cd housing-assistant

# install pre-commit
pre-commit install

# configure databricks CLI
databricks configure --token
# host: https://<your-workspace>.cloud.databricks.com
# token: <your PAT>

# verify access
databricks workspace list /
```

## Working on infrastructure (Terraform)

```bash
cd terraform/envs/dev

# only the first time on a new machine
cp terraform.tfvars.example terraform.tfvars
# fill in your values; never commit terraform.tfvars

terraform init
terraform plan
# review the plan carefully before applying
terraform apply
```

Conventions:

- All shared infrastructure lives in `terraform/modules/*` and is composed in `terraform/envs/dev/main.tf`.
- A new resource type generally means a new module. Keep modules small and single-purpose.
- Never commit `terraform.tfvars` or `.terraform/` directories. Both are in `.gitignore`.
- Remote state lives in an S3 bucket configured in `backend.tf`.

## Working on pipelines

Pipelines are Lakeflow Declarative Pipelines defined in `pipelines/`. Each source has its own subfolder.

```bash
# develop locally with the databricks CLI bundle
cd pipelines/<source>

# deploy and run
databricks bundle deploy --target dev
databricks bundle run <pipeline-name> --target dev

# tail the pipeline's run logs
databricks pipelines get-update <update-id>
```

Conventions:

- One pipeline per source; one "marts" pipeline that fans in from sources to gold.
- Prefer SQL over Python where possible.
- Every pipeline writes to `housing.bronze.*` / `housing.silver.*` / `housing.gold.*` only. Never directly to `housing.app.*`.

## Working on the agent

The agent lives in `agents/`. Each tool is a single Python function with a typed signature; the agent definition wires them together via the Mosaic AI Agent Framework.

```bash
cd agents
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# unit-test a tool
pytest tests/

# deploy the agent to a serving endpoint
python deploy.py --target dev
```

Conventions:

- Tools must have docstrings. Genie and the agent both rely on them.
- All agent traces should be tagged with the user's session ID for debuggability.
- Agent prompts live in `agents/prompts/` as plain `.md` files (no string concatenation in code).

## Working on the app

```bash
cd app
# instructions land here once frontend stack is chosen (Streamlit vs React + FastAPI)
```

Conventions:

- The app talks to two things: the agent serving endpoint and Lakebase. It does not query Genie directly. That goes through the agent.
- Lakebase access is via a service principal token, scoped read/write only to the `app` schema.
- Auth is workspace SSO. No custom auth.

## Day-to-day Git workflow

```bash
# start a new piece of work
git checkout main && git pull
git checkout -b feat/short-description

# work, commit small and often
git add -p
git commit -m "feat(pipelines): ingest tenancy bond data"

# push and open a PR
git push -u origin feat/short-description
gh pr create --fill

# after review, squash-merge via the GitHub UI
```

Branch-naming conventions:

- `feat/...`. New functionality.
- `fix/...`. Bug fix.
- `docs/...`. Documentation only.
- `chore/...`. Repo plumbing.
- `infra/...`. Terraform changes only.

PRs should be small enough to review in 10 minutes. Aim for one logical change per PR.

## Common operations

### Pause Lakebase overnight

The biggest single cost lever. Do this from the Databricks UI (Database Instances → your instance → Stop) or via CLI:

```bash
databricks database-instances stop <instance-id>
```

Resume in the morning. Lakebase resumes in seconds.

### Watch the cost dashboard

```sql
SELECT
  usage_date,
  sku_name,
  SUM(usage_quantity) AS dbus,
  SUM(usage_quantity * list_price) AS estimated_cost
FROM system.billing.usage
WHERE usage_metadata.tags['project'] = 'housing-assistant'
  AND usage_date > current_date - 14
GROUP BY 1, 2
ORDER BY 1 DESC, 4 DESC
```

Save this as a Databricks SQL query so anyone on the team can pull it up in 10 seconds.

### Re-run a failed pipeline

```bash
databricks pipelines start-update --pipeline-id <id> --full-refresh false
```

Use `--full-refresh true` if you've changed schema and want a clean rebuild.

### Check what's deployed

```bash
databricks bundle run --target dev <bundle-name> --validate-only
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `terraform plan` says it wants to delete the catalog | Drift from a manual change | Reconcile by importing the resource: `terraform import ...` |
| Genie answers questions wrong | Semantic model out of date | Re-sync the semantic model in the Genie Space settings |
| Pipeline times out | Source file unexpectedly large or missing | Check the bronze volume; rerun with `--full-refresh false` |
| Lakebase connection refused | Instance is paused | Resume from UI or CLI |
| App shows blank screen | Service principal lost a grant | Reapply Terraform; the grants are declarative |
| Terraform apply fails on Lakebase resource | Feature not enabled in workspace | Raise a workspace request to enable it |

## Escalation

For workspace-level problems (Lakebase enablement, quota increases, region availability) reach out to the workspace admin.

Internal blockers go in the team channel; tag the relevant codeowner.
