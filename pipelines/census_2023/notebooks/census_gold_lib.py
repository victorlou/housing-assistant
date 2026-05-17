"""Manifest-driven census gold helpers (used by silver/gold DLT notebooks)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "census_2023_gold.yml"


def load_gold_manifest() -> dict[str, Any]:
    if not _MANIFEST_PATH.is_file():
        raise FileNotFoundError(
            f"census_2023_gold.yml not found; expected at {_MANIFEST_PATH}"
        )
    with _MANIFEST_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def metric_specs(manifest: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    manifest = manifest or load_gold_manifest()
    return manifest["metrics"]


def census_year(manifest: dict[str, Any] | None = None) -> int:
    manifest = manifest or load_gold_manifest()
    return int(manifest.get("census_year", 2023))


def metric_value_expr(dataset: str, field_name: str):
    """Conditional aggregation for one (dataset, field_name) pair."""
    return F.max(
        F.when(
            (F.col("dataset") == dataset) & (F.col("field_name") == field_name),
            F.col("value"),
        )
    )


def pivot_manifest_metrics(
    metrics: DataFrame,
    export_keys: list[str],
    manifest: dict[str, Any] | None = None,
) -> DataFrame:
    """Wide pivot: one row per sa2_code/sa2_name with manifest export columns."""
    specs = metric_specs(manifest)
    missing = [k for k in export_keys if k not in specs]
    if missing:
        raise KeyError(f"Unknown manifest metric keys: {missing}")

    aggs = []
    for key in export_keys:
        spec = specs[key]
        aggs.append(
            metric_value_expr(spec["dataset"], spec["field_name"]).alias(key),
        )

    return metrics.groupBy("sa2_code", "sa2_name").agg(*aggs)


def all_feature_export_keys(manifest: dict[str, Any] | None = None) -> list[str]:
    manifest = manifest or load_gold_manifest()
    keys: list[str] = list(manifest.get("suburb_enrichment", []))
    for mart_cols in manifest.get("marts", {}).values():
        keys.extend(mart_cols)
    return sorted(set(keys))
