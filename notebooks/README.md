# Notebooks

Exploratory work, prototypes, and one-off analysis.

## Conventions

- Notebooks here are **scratch space**. They are not deployed, and pipelines, agents, and the app never depend on them.
- When a notebook produces something worth keeping, port the logic into the appropriate folder (`pipelines/`, `agents/`, `app/`) and delete or archive the notebook.
- Name notebooks with a date prefix and a short description: `2026-05-12-explore-bond-data.py`.
- Prefer Databricks notebooks (`.py` with `# COMMAND` markers) over `.ipynb` so diffs are reviewable.

## What lives here

- Initial source exploration before authoring a pipeline.
- One-off data-quality investigations.
- Sketches of agent prompts before they harden into `agents/prompts/`.
- Ad-hoc analyses for presentations ("what's the most striking single number we can show?").
