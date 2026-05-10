# Scripts

Helper scripts for development and deployment. Nothing here is ever called from production code paths. These are for humans.

## What goes here

- One-off scripts to bootstrap or migrate something.
- Cost-report generators.
- Local convenience wrappers for `databricks` CLI commands we run often.
- Demo-day helpers (e.g., reset Lakebase to a clean state for the live demo).

## Conventions

- Bash or Python. Prefer Python when the script does anything non-trivial.
- Every script has a header comment: what it does, who runs it, when.
- Scripts that touch infrastructure require a confirmation prompt unless explicitly run with `--yes`.
