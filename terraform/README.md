# Terraform

All infrastructure-as-code for Housing Assistant.

For *what* the architecture is, see [`docs/architecture.md`](../docs/architecture.md). For day-to-day development workflows, see [`docs/runbook.md`](../docs/runbook.md). This README is the reference for developers working inside `terraform/`.

## Layout

```
terraform/
├── envs/dev/                # the dev environment — composes modules and wires cross-cutting grants
└── modules/
    ├── identity/            # jobs service principal (the app SP is auto-created by databricks_app)
    ├── secrets/             # Databricks-backed secret scope
    ├── catalog/             # Unity Catalog: housing catalog, bronze/silver/gold/app schemas, bronze volumes, jobs SP grants
    ├── compute/             # serverless 2X-Small SQL warehouse with auto-stop
    ├── lakebase/            # Lakebase Autoscaling project (Postgres for user state)
    └── app/                 # Databricks App with warehouse binding
```

## Composition pattern

Modules create resources and expose IDs. The env at `envs/dev/main.tf` composes modules **and** owns cross-cutting grants and permissions. This avoids the chicken-and-egg of "module A needs SP B but SP B is created in module A".

For example, the catalog module grants the jobs SP write access (since it's the catalog's own SP), but grants involving the app's auto-created SP (gold read, app schema read/write, warehouse CAN_USE) live in the env file.

## Grant style

We use `databricks_grant` (singular, additive), not `databricks_grants` (plural, authoritative). Singular grants stack across modules without fighting each other. Don't mix them on the same target.

## Conventions

- One environment (`dev`) for now. To add another, copy `envs/dev` to `envs/<name>`.
- Modules are small and single-purpose. New resource type usually means a new module unless it's clearly part of an existing one.
- Tag every resource with `project = "housing-assistant"` (or set `properties.project` for UC-governed objects). It shows up in `system.billing.usage`.
- All compute is serverless. The workspace's metastore is `Serverless only`, so we cannot create classic clusters with custom node types.
- Use snake_case for resource names, variables, and outputs. Match Terraform's idiomatic style.

## Provider versions

Pinned in `envs/dev/versions.tf`. We use `databricks/databricks ~> 1.85`, which currently resolves to `1.114.x`. The `.terraform.lock.hcl` keeps the team on the exact same provider version.

If you upgrade the provider, run `terraform plan` carefully — Beta resources (notably Lakebase) sometimes shift attribute names between releases.

## Authentication

The provider auto-discovers credentials in this order:

1. `DATABRICKS_HOST` + `DATABRICKS_TOKEN` environment variables.
2. The Databricks CLI profile selected by `DATABRICKS_CONFIG_PROFILE`.
3. The default profile in `~/.databrickscfg`.

The simplest path: `databricks configure --token` once, then run `terraform plan` with no extra setup. Override per-call by exporting env vars or setting `databricks_profile` in `terraform.tfvars`.

## State

Local state for now. `.terraform/` and any `*.tfstate*` files are gitignored. Coordinate with the team before applying when more than one person could touch infra at the same time.

The S3 backend block is commented in [`envs/dev/backend.tf`](envs/dev/backend.tf) — flip the comments and run `terraform init -migrate-state` once a shared bucket is in place.

## Lakebase: Beta resource caveat

The `databricks_postgres_project` resource is Beta. The project resource is stable, but configuring the auto-created production endpoint's autoscaling range and scale-to-zero is not yet exposed cleanly through Terraform. We treat that as a one-time post-apply step.

The runbook ([Common operations → Enable scale-to-zero](../docs/runbook.md#enable-scale-to-zero-on-lakebase-one-time-after-first-apply)) has the exact steps. Do this immediately after first apply so the dev instance doesn't bill 24/7.

## Workflow

Full instructions in [`docs/runbook.md`](../docs/runbook.md). Quick version:

```bash
cd terraform/envs/dev
terraform init
terraform fmt -check -recursive ../..
terraform validate
terraform plan
terraform apply
```

CI runs `terraform fmt -check`, `terraform init -backend=false`, and `terraform validate` on every PR that touches `terraform/`. `apply` is manual.

## Adding a new module

1. Create `modules/<name>/` with `main.tf`, `variables.tf`, `outputs.tf`.
2. Compose it in `envs/dev/main.tf` — pass any inputs from other modules' outputs.
3. If the new module's resources need grants involving service principals it doesn't own, add those at the env level next to the existing `databricks_grant` and `databricks_permissions` blocks.
4. Run `terraform fmt`, then `terraform validate`, then `terraform plan` and read it carefully.
