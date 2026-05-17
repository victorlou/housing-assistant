"""Page ArcGIS MapServer/FeatureServer flood layers into GeoJSON JSONL."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
import yaml

_REGIONS_FILE = Path(__file__).resolve().parent.parent / "regions.yaml"


def load_layers_config(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load layer specs from regions.yaml; keys are layer `id` fields."""
    path = path or _REGIONS_FILE
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    layers = raw.get("layers") if isinstance(raw, dict) else None
    if not isinstance(layers, list):
        raise ValueError(f"{path}: expected top-level 'layers' list")

    out: dict[str, dict[str, Any]] = {}
    for spec in layers:
        if not isinstance(spec, dict) or "id" not in spec:
            raise ValueError(f"{path}: layer needs an 'id'")
        key = str(spec["id"])
        for required in ("base", "layer_id", "file_stem"):
            if required not in spec:
                raise ValueError(f"{path}: layer {key} missing {required!r}")
        out[key] = spec
    return out


def layer_query_url(base: str, layer_id: int) -> str:
    return f"{base.rstrip('/')}/{layer_id}/query"


def iter_arcgis_features(
    base: str,
    layer_id: int,
    *,
    page_size: int = 500,
    return_geometry: bool = True,
    out_sr: int = 4326,
    session: requests.Session | None = None,
    max_retries: int = 5,
    backoff_seconds: float = 3.0,
) -> Iterator[dict[str, Any]]:
    """Yield GeoJSON-like feature dicts from paged /query (Esri JSON)."""
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", "housing-assistant/1.0")
    offset = 0
    url = layer_query_url(base, layer_id)

    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true" if return_geometry else "false",
            "outSR": str(out_sr),
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
            "f": "json",
        }
        full_url = f"{url}?{urlencode(params)}"

        payload: dict[str, Any] | None = None
        for attempt in range(max_retries):
            try:
                resp = sess.get(full_url, timeout=300)
                if resp.status_code in (429, 502, 503, 504) and attempt < max_retries - 1:
                    time.sleep(backoff_seconds * (attempt + 1))
                    continue
                resp.raise_for_status()
                esri = resp.json()
                if esri.get("error"):
                    raise RuntimeError(f"ArcGIS error: {esri['error']}")
                features = []
                for row in esri.get("features") or []:
                    geom = row.get("geometry")
                    attrs = row.get("attributes") or {}
                    if geom and return_geometry:
                        geo = _esri_to_geojson_geom(geom)
                        if geo is None:
                            continue
                        features.append(
                            {
                                "type": "Feature",
                                "geometry": geo,
                                "properties": attrs,
                            }
                        )
                    else:
                        features.append({"type": "Feature", "properties": attrs})
                payload = {"type": "FeatureCollection", "features": features}
                break
            except (requests.RequestException, json.JSONDecodeError) as exc:
                if attempt < max_retries - 1:
                    time.sleep(backoff_seconds * (attempt + 1))
                    continue
                raise RuntimeError(f"ArcGIS query failed after {max_retries} attempts") from exc

        if payload is None:
            raise RuntimeError("ArcGIS query returned no payload")

        features = payload.get("features") or []
        if not features:
            break

        for feature in features:
            if isinstance(feature, dict):
                yield feature

        if len(features) < page_size:
            break
        offset += len(features)


def _close_ring(ring: list[Any]) -> list[Any] | None:
    if len(ring) < 3:
        return None
    closed = list(ring)
    if closed[0] != closed[-1]:
        closed.append(closed[0])
    if len(closed) < 4:
        return None
    return closed


def _esri_to_geojson_geom(geom: dict[str, Any]) -> dict[str, Any] | None:
    if "rings" in geom:
        rings = []
        for ring in geom["rings"]:
            closed = _close_ring(ring)
            if closed:
                rings.append(closed)
        if not rings:
            return None
        return {"type": "Polygon", "coordinates": rings}
    if "paths" in geom:
        paths = geom["paths"]
        return (
            {"type": "MultiLineString", "coordinates": paths}
            if len(paths) > 1
            else {"type": "LineString", "coordinates": paths[0]}
        )
    if "x" in geom and "y" in geom:
        return {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
    return geom


def fetch_layer_to_jsonl_hashed(
    layer_key: str,
    output_path: Path,
    *,
    layers: dict[str, dict[str, Any]] | None = None,
    return_geometry: bool = True,
    max_features: int | None = None,
    session: requests.Session | None = None,
) -> tuple[int, str]:
    registry = layers or load_layers_config()
    spec = registry[layer_key]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    digest = hashlib.sha256()
    with output_path.open("wb") as fh:
        page_size = int(spec.get("page_size", 500))
        for feature in iter_arcgis_features(
            str(spec["base"]),
            int(spec["layer_id"]),
            return_geometry=return_geometry,
            page_size=page_size,
            session=session,
        ):
            line = json.dumps(feature, separators=(",", ":"), ensure_ascii=False) + "\n"
            blob = line.encode("utf-8")
            fh.write(blob)
            digest.update(blob)
            total += 1
            if max_features is not None and total >= max_features:
                break

    return total, digest.hexdigest()
