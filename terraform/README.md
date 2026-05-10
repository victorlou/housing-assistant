# Terraform

All infrastructure-as-code for Housing Assistant lives here.

## Layout

```
terraform/
├── envs/
│   └── dev/                # the dev environment
│       ├── main.tf         # composes modules
│       ├── backend.tf      # remote state config
│       ├── providers.tf    # databricks, aws providers
│       ├── variables.tf
│       └── terraform.tfvars.example
└── modules/
    ├── catalog/            # Unity Catalog: catalog, schemas, volumes, grants
    ├── compute/            # Serverless SQL Warehouse, cluster policies
    ├── lakebase/           # Lakebase (managed Postgres) instance + UC mirroring
    ├── secrets/            # Databricks-backed secret scope
    └── app/                # Databricks App + service principal + grants
```

## Conventions

- One environment (`dev`) for now. If we add a second, copy `envs/dev` to `envs/<new>`.
- Modules are small and single-purpose. New resource type means a new module, unless it's clearly part of an existing one.
- Tag every resource with `project = "housing-assistant"` for cost tracking.
- Never commit `terraform.tfvars` or `.terraform/`.
- Remote state lives in an S3 bucket configured in `backend.tf` (set up once, then forget).

## Workflow

See `docs/runbook.md` for full instructions. The short version:

```bash
cd terraform/envs/dev
terraform init
terraform plan
terraform apply
```

CI runs `terraform fmt`, `terraform validate`, and `terraform plan` on every PR that touches `terraform/`. `apply` is manual for now. We don't auto-apply infrastructure changes.
