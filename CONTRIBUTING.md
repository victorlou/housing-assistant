# Contributing

A short, working agreement for everyone touching this repo.

## Getting started

See [`docs/runbook.md`](docs/runbook.md) for environment setup and day-to-day workflows.

## Branching

- `main` is protected and always deployable.
- Create feature branches off `main`. Naming:
  - `feat/<short-description>`. New functionality.
  - `fix/<short-description>`. Bug fix.
  - `docs/<short-description>`. Documentation only.
  - `chore/<short-description>`. Repo plumbing.
  - `infra/<short-description>`. Terraform changes only.
- Squash-merge via PR.

## Pull requests

- Keep PRs small enough to review in 10 minutes.
- One logical change per PR.
- At least one approving review before merge.
- CI must pass.

## Commit messages

Use conventional-commit style:

- `feat(pipelines): ingest tenancy bond data`
- `fix(agent): handle missing isochrone gracefully`
- `docs(architecture): clarify gold-table contracts`
- `chore(ci): cache terraform providers`
- `infra(catalog): add hazard schema`

## Code style

- Python: `ruff` for lint, `ruff format` for formatting. Configured in `pyproject.toml`.
- Terraform: `terraform fmt -recursive`. Run before pushing.
- SQL: lowercase keywords, snake_case names. Trailing comma OK.
- Markdown: prose-wrap loose; one sentence per line is fine.

## Definition of done

A change is done when:

- It is merged to `main`.
- Tests (if any) pass.
- At least one teammate has run it locally.
- Any new infra resource is tagged `project = "housing-assistant"`.
- New **dbt** models that define keys or business rules include **schema tests** (for example `not_null`, `unique`, or a singular test) in `dbt/models/` or `dbt/tests/`.
