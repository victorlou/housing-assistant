from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.linz_wfs import (
    build_getfeature_params,
    expand_env_vars,
    load_config,
    parse_feature_collection,
    wfs_base_url,
    with_wfs_overrides,
)

_CONFIG = Path(__file__).resolve().parents[1] / "config" / "sources" / "linz_nz_addresses.yml"


def test_load_source_config() -> None:
    cfg = load_config(_CONFIG)
    assert cfg["wfs"]["type_names"] == "layer-105689"
    assert cfg["landing"]["file_stem"] == "linz_nz_addresses"


def test_expand_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINZ_API_KEY", "abc")
    assert expand_env_vars("x=${LINZ_API_KEY}!") == "x=abc!"


def test_wfs_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINZ_API_KEY", "test-key-123")
    cfg = load_config(_CONFIG)
    url = wfs_base_url(cfg)
    assert "test-key-123" in url
    assert url.endswith("/wfs")


def test_build_getfeature_params() -> None:
    cfg = load_config(_CONFIG)
    p = build_getfeature_params(cfg, start_index=4000)
    assert p["STARTINDEX"] == "4000"
    assert p["COUNT"] == "2000"
    assert p["TYPENAMES"] == "layer-105689"


def test_parse_feature_collection_geojson() -> None:
    body = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"a": 1}}]}
    feats = parse_feature_collection(body)
    assert len(feats) == 1
    assert feats[0]["type"] == "Feature"


def test_with_wfs_overrides() -> None:
    cfg = load_config(_CONFIG)
    over = with_wfs_overrides(cfg, max_pages=2)
    assert over["wfs"]["max_pages"] == 2
    assert cfg["wfs"].get("max_pages") is None


@pytest.mark.parametrize(
    "body,expected",
    [
        ([{"x": 1}], 1),
        ({"type": "Feature", "geometry": None}, 1),
        ({}, 0),
    ],
)
def test_parse_feature_collection_edges(body: object, expected: int) -> None:
    assert len(parse_feature_collection(body)) == expected
