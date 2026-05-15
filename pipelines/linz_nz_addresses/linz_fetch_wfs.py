"""LINZ LDS WFS paging: config dict or YAML; ${VAR} placeholders in YAML base_url."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlencode

import requests
import yaml

_ENV_PATTERN = re.compile(r"\$\{([^}:]+)\}")

REQUIRED_WFS_KEYS = (
    "base_url",
    "version",
    "type_names",
    "output_format",
    "page_size",
)


def expand_env_placeholders(value: str) -> str:
    """Replace ${VAR} with os.environ[VAR]. Used when loading YAML for local runs."""

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        got = os.environ.get(name)
        if got is None or got == "":
            raise RuntimeError(f"Environment variable {name} is not set (required by config).")
        return got

    return _ENV_PATTERN.sub(repl, value)


def load_config(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Config must be a mapping, got {type(raw).__name__}")
    wfs = raw.get("wfs")
    if not isinstance(wfs, dict):
        raise ValueError("Config missing 'wfs' mapping")
    for key in REQUIRED_WFS_KEYS:
        if key not in wfs:
            raise ValueError(f"wfs.{key} is required")
    landing = raw.get("landing", {})
    if not isinstance(landing, dict):
        raise ValueError("'landing' must be a mapping when present")
    if "file_stem" not in landing:
        raise ValueError("landing.file_stem is required")
    return raw


def wfs_base_url(cfg: dict[str, Any]) -> str:
    return expand_env_placeholders(str(cfg["wfs"]["base_url"]))


def build_getfeature_params(
    cfg: dict[str, Any],
    *,
    start_index: int,
) -> dict[str, str]:
    wfs = cfg["wfs"]
    params: dict[str, str] = {
        "SERVICE": "WFS",
        "VERSION": str(wfs["version"]),
        "REQUEST": "GetFeature",
        "TYPENAMES": str(wfs["type_names"]),
        "COUNT": str(int(wfs["page_size"])),
        "STARTINDEX": str(int(start_index)),
        "OUTPUTFORMAT": str(wfs["output_format"]),
    }
    srs = wfs.get("srs_name")
    if srs:
        params["SRSNAME"] = str(srs)
    extra = wfs.get("extra_query_params") or {}
    if not isinstance(extra, dict):
        raise ValueError("wfs.extra_query_params must be a mapping")
    for k, v in extra.items():
        params[str(k)] = str(v)
    return params


def parse_feature_collection(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if not isinstance(body, dict):
        return []
    if body.get("type") == "FeatureCollection" and isinstance(body.get("features"), list):
        return [f for f in body["features"] if isinstance(f, dict)]
    if body.get("type") == "Feature" or "geometry" in body or "properties" in body:
        return [body]
    features = body.get("features")
    if isinstance(features, list):
        return [f for f in features if isinstance(f, dict)]
    return []


def iter_wfs_pages(
    cfg: dict[str, Any],
    *,
    session: requests.Session | None = None,
) -> Iterator[list[dict[str, Any]]]:
    wfs = cfg["wfs"]
    base_root = str(wfs["base_url"])
    if "${" in base_root:
        base_root = wfs_base_url(cfg)
    timeout = float(wfs.get("request_timeout_seconds", 120))
    max_retries = int(wfs.get("max_retries", 5))
    backoff = float(wfs.get("retry_backoff_seconds", 3.0))
    max_pages = wfs.get("max_pages")
    max_pages_int = int(max_pages) if max_pages is not None else None

    sess = session or requests.Session()
    start_index = 0
    page_no = 0

    while True:
        if max_pages_int is not None and page_no >= max_pages_int:
            break
        params = build_getfeature_params(cfg, start_index=start_index)
        query = urlencode(params)
        url = f"{base_root}?{query}"

        payload: dict[str, Any] | list[Any] | None = None
        for attempt in range(max_retries):
            try:
                resp = sess.get(url, timeout=timeout)
                if resp.status_code in (429, 502, 503, 504) and attempt < max_retries - 1:
                    time.sleep(backoff * (attempt + 1))
                    continue
                resp.raise_for_status()
                payload = resp.json()
                break
            except (requests.RequestException, json.JSONDecodeError) as exc:
                if attempt < max_retries - 1:
                    time.sleep(backoff * (attempt + 1))
                    continue
                raise RuntimeError(
                    f"WFS request failed after {max_retries} attempts: {exc}"
                ) from exc

        if payload is None:
            raise RuntimeError("WFS request produced no response body")

        features = parse_feature_collection(payload)
        page_no += 1
        yield features
        if not features:
            break
        start_index += len(features)
        page_size = int(wfs["page_size"])
        if len(features) < page_size:
            break


def default_output_path(cfg: dict[str, Any], output_dir: Path) -> Path:
    stem = str(cfg["landing"]["file_stem"])
    day = date.today().strftime("%Y%m%d")
    return output_dir / f"{stem}_{day}.jsonl"


def fetch_to_jsonl_hashed(
    cfg: dict[str, Any],
    *,
    output_path: Path,
    session: requests.Session | None = None,
) -> tuple[int, str]:
    """Write GeoJSON features as JSONL; return (feature_count, sha256 of file bytes)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    digest = hashlib.sha256()
    with output_path.open("wb") as fh:
        for page in iter_wfs_pages(cfg, session=session):
            for feature in page:
                line = json.dumps(feature, separators=(",", ":"), ensure_ascii=False) + "\n"
                blob = line.encode("utf-8")
                fh.write(blob)
                digest.update(blob)
                total += 1
    return total, digest.hexdigest()


def fetch_to_jsonl(
    cfg: dict[str, Any],
    *,
    output_path: Path,
    session: requests.Session | None = None,
) -> int:
    n, _ = fetch_to_jsonl_hashed(cfg, output_path=output_path, session=session)
    return n


def with_wfs_overrides(cfg: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """Return a deep-copied config with selected wfs keys overridden (CLI smoke tests)."""
    out = copy.deepcopy(cfg)
    wfs = out.setdefault("wfs", {})
    for k, v in overrides.items():
        if v is not None:
            wfs[k] = v
    return out


_REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch LINZ WFS into JSONL (default config: config/sources/linz_nz_addresses.yml)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_REPO_ROOT / "config" / "sources" / "linz_nz_addresses.yml",
        help="Path to YAML (default: config/sources/linz_nz_addresses.yml)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSONL file, or a directory (default: ./out/<stem>_YYYYMMDD.jsonl)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Override wfs.max_pages for smoke tests",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.max_pages is not None:
        cfg = with_wfs_overrides(cfg, max_pages=args.max_pages)

    if args.output is None:
        out = default_output_path(cfg, _REPO_ROOT / "out")
    elif args.output.is_dir():
        out = default_output_path(cfg, args.output)
    else:
        out = args.output

    total = fetch_to_jsonl(cfg, output_path=out)
    print(f"Wrote {total} features to {out}")
    print(
        f'Upload to UC with: databricks fs cp --recursive "{out}" "<volume_path>/" --profile <name>'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
