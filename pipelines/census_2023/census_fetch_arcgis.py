"""Page Stats NZ 2023 Census ArcGIS FeatureServer layers into GeoJSON JSONL."""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

ARCGIS_HOST = "https://services2.arcgis.com/vKb0s8tBIA3bdocZ/arcgis/rest/services"

LAYERS: dict[str, dict[str, Any]] = {
    "households_sa2": {
        "service": "2023_Census_totals_by_topic_for_households_by_SA2",
        "layer_id": 1,
        "file_stem": "census_2023_households_sa2",
    },
    "dwellings_sa2": {
        "service": "2023_Census_totals_by_topic_for_dwellings_by_SA2",
        "layer_id": 1,
        "file_stem": "census_2023_dwellings_sa2",
    },
}


def layer_query_url(service: str, layer_id: int) -> str:
    return f"{ARCGIS_HOST}/{service}/FeatureServer/{layer_id}/query"


def layer_metadata_url(service: str, layer_id: int) -> str:
    return f"{ARCGIS_HOST}/{service}/FeatureServer/{layer_id}?f=json"


def iter_arcgis_features(
    service: str,
    layer_id: int,
    *,
    page_size: int = 2000,
    return_geometry: bool = True,
    out_sr: int = 4326,
    session: requests.Session | None = None,
    max_retries: int = 5,
    backoff_seconds: float = 3.0,
) -> Iterator[dict[str, Any]]:
    """Yield GeoJSON feature dicts from paged /query."""
    sess = session or requests.Session()
    offset = 0
    url = layer_query_url(service, layer_id)

    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true" if return_geometry else "false",
            "outSR": str(out_sr),
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
            "f": "geojson",
        }
        full_url = f"{url}?{urlencode(params)}"

        payload: dict[str, Any] | None = None
        for attempt in range(max_retries):
            try:
                resp = sess.get(full_url, timeout=180)
                if resp.status_code in (429, 502, 503, 504) and attempt < max_retries - 1:
                    time.sleep(backoff_seconds * (attempt + 1))
                    continue
                resp.raise_for_status()
                payload = resp.json()
                break
            except (requests.RequestException, json.JSONDecodeError) as exc:
                if attempt < max_retries - 1:
                    time.sleep(backoff_seconds * (attempt + 1))
                    continue
                raise RuntimeError(f"ArcGIS query failed after {max_retries} attempts") from exc

        if payload is None:
            raise RuntimeError("ArcGIS query returned no payload")

        if payload.get("error"):
            raise RuntimeError(f"ArcGIS error: {payload['error']}")

        features = payload.get("features") or []
        if not features:
            break

        for feature in features:
            if isinstance(feature, dict):
                yield feature

        if len(features) < page_size:
            break
        offset += len(features)


def fetch_layer_to_jsonl_hashed(
    layer_key: str,
    output_path: Path,
    *,
    return_geometry: bool = True,
    session: requests.Session | None = None,
) -> tuple[int, str]:
    """Write features as JSONL; return (count, sha256 hex)."""
    if layer_key not in LAYERS:
        raise ValueError(f"Unknown layer_key {layer_key!r}; expected one of {list(LAYERS)}")
    spec = LAYERS[layer_key]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    digest = hashlib.sha256()
    with output_path.open("wb") as fh:
        for feature in iter_arcgis_features(
            spec["service"],
            int(spec["layer_id"]),
            return_geometry=return_geometry,
            session=session,
        ):
            line = json.dumps(feature, separators=(",", ":"), ensure_ascii=False) + "\n"
            blob = line.encode("utf-8")
            fh.write(blob)
            digest.update(blob)
            total += 1

    return total, digest.hexdigest()


def fetch_layer_field_dictionary_csv(
    layer_key: str,
    output_path: Path,
    *,
    session: requests.Session | None = None,
) -> int:
    """Write ArcGIS field name → alias map for VAR_* columns; return field count."""
    if layer_key not in LAYERS:
        raise ValueError(f"Unknown layer_key {layer_key!r}; expected one of {list(LAYERS)}")
    spec = LAYERS[layer_key]
    sess = session or requests.Session()
    resp = sess.get(
        layer_metadata_url(spec["service"], int(spec["layer_id"])),
        timeout=120,
    )
    resp.raise_for_status()
    meta = resp.json()
    if meta.get("error"):
        raise RuntimeError(f"ArcGIS error: {meta['error']}")

    fields = meta.get("fields") or []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["field_name", "alias", "type"])
        for field in fields:
            writer.writerow(
                [
                    field.get("name", ""),
                    field.get("alias", ""),
                    field.get("type", ""),
                ]
            )
    return len(fields)
