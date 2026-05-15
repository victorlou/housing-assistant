"""LINZ LDS WFS fetch CLI. Implementation: pipelines/linz_nz_addresses/linz_fetch_wfs.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_FETCH_PATH = (
    Path(__file__).resolve().parent.parent / "pipelines" / "linz_nz_addresses" / "linz_fetch_wfs.py"
)


def _load_fetch():
    spec = importlib.util.spec_from_file_location("_linz_fetch_wfs", _FETCH_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load LINZ fetch module at {_FETCH_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_linz = _load_fetch()

build_getfeature_params = _linz.build_getfeature_params
default_output_path = _linz.default_output_path
expand_env_vars = _linz.expand_env_placeholders
fetch_to_jsonl = _linz.fetch_to_jsonl
iter_wfs_pages = _linz.iter_wfs_pages
load_config = _linz.load_config
parse_feature_collection = _linz.parse_feature_collection
with_wfs_overrides = _linz.with_wfs_overrides
wfs_base_url = _linz.wfs_base_url

__all__ = [
    "build_getfeature_params",
    "default_output_path",
    "expand_env_vars",
    "fetch_to_jsonl",
    "iter_wfs_pages",
    "load_config",
    "parse_feature_collection",
    "wfs_base_url",
    "with_wfs_overrides",
]


def main() -> int:
    return _linz.main()


if __name__ == "__main__":
    raise SystemExit(main())
