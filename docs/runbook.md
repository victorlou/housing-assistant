# Developer runbook

This is the practical guide to working on Housing Assistant. If something here is wrong or out of date, fix it in the same PR as the code change. Outdated runbooks are worse than no runbook.

## Prerequisites

You will need:

- **Databricks workspace access.** AWS, `us-west-2`, Premium tier. Workspace admin can grant you access.
- **Databricks CLI** from `databricks auth login --profile <name>` (stored in `~/.databrickscfg`). Terraform uses the same credentials via environment variables (see below), not committed config.
- **AWS credentials** with at least read access to the Databricks-managed buckets, only if your task needs it. Most tasks do not.
- **Local toolchain:**
  - `terraform` ≥ 1.7
  - `databricks` CLI ≥ 0.230
  - Python 3.11
  - `uv` for Python env management (recommended) or `venv` + `pip`
  - `pre-commit` for hooks
  - Node 20 + pnpm (only if you're working on the React frontend)
- **GitHub access** to `github.com/victorlou/housing-assistant`. Branch protection is enabled on `main`; you'll work on feature branches and merge via PR.

## Docker (local Python)

Use this when you want the same Python 3.11 and locked dev tools as CI without touching the host Python install. It does **not** replace the Databricks CLI or Terraform on your machine unless you extend the image.

```bash
# from repository root
docker compose build dev
docker compose run --rm dev
```

Inside the container the repo is at `/workspace` (bind-mounted). Run `ruff check .`, `pytest`, and future app commands there.

For the slim image used when you deploy a long-running service (only application folders, not the full monorepo), see [`docker/README.md`](../docker/README.md).

## First-time setup

```bash
# clone and enter
git clone git@github.com:victorlou/housing-assistant.git
cd housing-assistant

# install pre-commit
pre-commit install

# authenticate CLI (writes ~/.databrickscfg)
databricks auth login --profile <name>

# Terraform reads credentials from the environment (pick one approach; do not commit profile names)
#   Unix:    export DATABRICKS_CONFIG_PROFILE=<name>
#   PowerShell: $env:DATABRICKS_CONFIG_PROFILE = "<name>"
# Alternative: export DATABRICKS_HOST=... and DATABRICKS_TOKEN=... (e.g. CI)

# verify access (same profile as above)
databricks workspace list / --profile <name>
```

## Working on infrastructure (Terraform)

```bash
cd terraform/envs/dev

# optional: only if you set variables such as data_principal_names
# cp terraform.tfvars.example terraform.tfvars

terraform init
terraform plan
# review the plan carefully before applying
terraform apply
```

Ensure `DATABRICKS_CONFIG_PROFILE` (or `DATABRICKS_HOST` / `DATABRICKS_TOKEN`) is set in your shell before `plan` / `apply`, as described in First-time setup.

By default Terraform creates `bronze` / `silver` / `gold` / `app` and the `tenancy_bonds` volume under the existing **`workspace`** catalog (required on accounts where new catalogs must use Default Storage from the UI). To use a dedicated **`housing`** catalog instead, create it in the Catalog UI first, then set `uc_catalog_name = "housing"` in `terraform.tfvars` and re-apply.

After `terraform apply`, copy the output `tenancy_bonds_files_path` (if shown). That is the Unity Catalog volume path where raw tenancy bond files should land. Upload with the Catalog explorer or `databricks fs cp --profile <name> local.csv <tenancy_bonds_files_path>/tenancy_bonds_YYYYMMDD.csv`, using the `{source}_{YYYYMMDD}.csv` naming convention described in `docs/data-sources.md`.

Conventions:

- All shared infrastructure lives in `terraform/modules/*` and is composed in `terraform/envs/dev/main.tf`.
- A new resource type generally means a new module. Keep modules small and single-purpose.
- Never commit `terraform.tfvars` or `.terraform/` directories. Both are in `.gitignore`.
- Remote state lives in an S3 bucket configured in `backend.tf`.

## LINZ NZ Addresses (WFS landings)

1. Set `LINZ_API_KEY` in `.env` (see `.env.example`). Edit `config/sources/linz_nz_addresses.yml` only for non-secret fields (for example `wfs.type_names`).
2. `uv run python -m ingestion.linz_wfs --output ./out` (default config: `config/sources/linz_nz_addresses.yml`).
3. `databricks fs cp` the JSONL into the path from `terraform output linz_nz_addresses_files_path`.
4. Deploy the DLT bundle under `pipelines/linz_nz_addresses/` (`databricks bundle deploy --target dev`).

Details: [`pipelines/linz_nz_addresses/README.md`](../pipelines/linz_nz_addresses/README.md) and [`.devnotes/linz-lds-apis.md`](../.devnotes/linz-lds-apis.md).

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
- Every pipeline writes only under the UC catalog from Terraform (`uc_catalog_name`, default `workspace`) in `bronze` / `silver` / `gold`. Never directly to `<catalog>.app.*`.

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

### Account-level Terraform authentication (one-time setup)

Terraform manages an account-level admin group, so it needs account-level credentials in addition to your workspace credentials. Set this up once:

```bash
databricks auth login \
  --host https://accounts.cloud.databricks.com \
  --account-id <YOUR-ACCOUNT-UUID>
# When prompted for a profile name, use: hackathon-account
```

A browser opens; sign in as an account admin. The CLI caches your token in `~/.databricks/token-cache.json` and adds a `[hackathon-account]` profile to `~/.databrickscfg`. Verify with:

```bash
databricks --profile hackathon-account account groups list
```

You also need to add `databricks_account_id` and `workspace_id` to your `terraform.tfvars`. Both are visible in the account console (`https://accounts.cloud.databricks.com` → User profile / Workspaces).

### Onboard a teammate

Terraform provisions an **account-level** admin group (`housing-assistant-dev-admins`) with full data access on every schema, `USE_CATALOG` on the catalog, and `CAN_MANAGE` on the SQL warehouse. Permissions live in code; **membership lives in the account console**, so adding a teammate is a click and doesn't need a `terraform apply`.

1. Go to https://accounts.cloud.databricks.com → **User management → Groups**.
2. Find `housing-assistant-dev-admins`.
3. **Add member** → search by email → confirm.

The teammate gets workspace access (via the permission assignment in Terraform) and full data access immediately. To remove a teammate, the same flow in reverse. No code change required.

### Enable scale-to-zero on Lakebase (one-time, after first apply)

Lakebase Autoscaling supports suspending the compute when idle, but the setting is **not** controlled by the Terraform `databricks_postgres_project` resource. Enable it once after the project is first created.

**Via the UI (fastest):** Lakebase → Autoscaling → `housing-assistant-dev` → production branch → primary endpoint → Settings → toggle scale-to-zero on, set timeout to 5 minutes.

**Via the CLI:** the project, branch, and endpoint names come straight from `terraform output`:

```bash
ENDPOINT=$(terraform output -raw lakebase_production_endpoint_name)

databricks postgres update-endpoint "$ENDPOINT" \
  spec.suspend_timeout_seconds \
  --json '{"spec": {"suspend_timeout_seconds": 300}}'
```

The exact field name is in flux while the API is in Beta. If the call rejects `suspend_timeout_seconds`, run `databricks postgres get-endpoint "$ENDPOINT"` to see the current schema, then enable scale-to-zero through the UI as a fallback. Once enabled it persists across redeploys.

While you're there, also set the autoscaling range. The default for projects created via the Database instance API is min 4 / max 8 CU; for dev, min 0.5 / max 2 CU is plenty.

### Watch the cost dashboard

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
| Lakebase connection refused | Endpoint suspended (scale-to-zero) | First query reactivates it in a few hundred ms; add retry logic to the app |
| App shows blank screen | Service principal lost a grant | Reapply Terraform; the grants are declarative |
| Terraform apply fails on Lakebase resource | Feature not enabled in workspace, or Beta resource schema changed | Raise a workspace request, or pin the provider version in `versions.tf` |
| `terraform apply` fails on `databricks_catalog` with "Metastore storage root URL does not exist" | Workspace uses Default Storage, which the Terraform provider can't trigger automatically (open issue: databricks/cli#4513) | Create the catalog in the UI with "Default storage" selected, then `terraform import 'module.catalog.databricks_catalog.main' housing` and re-run apply |

## Escalation

For workspace-level problems (Lakebase enablement, quota increases, region availability) reach out to the workspace admin.

Internal blockers go in the team channel; tag the relevant codeowner.
