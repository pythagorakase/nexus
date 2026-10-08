"""The vendored Natural Earth files match their manifest (issue #840, offline)."""

from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

import pytest

from nexus.agents.orrery.geo_reference import (
    LAYER_NAMES,
    MANIFEST_PATH,
    NaturalEarthLayer,
    NaturalEarthManifest,
    load_manifest,
)

MANIFEST = load_manifest()
DIRECTORY = MANIFEST_PATH.parent


def test_manifest_validates() -> None:
    assert isinstance(MANIFEST, NaturalEarthManifest)
    assert MANIFEST.dataset == "Natural Earth"
    assert MANIFEST.release == "5.1.1"
    assert MANIFEST.scale == "10m"
    assert tuple(layer.layer for layer in MANIFEST.layers) == LAYER_NAMES
    assert {(repair.layer, repair.ne_id) for repair in MANIFEST.repairs} == {
        ("admin_0", 1159320575),
        ("admin_1", 1159309897),
    }
    assert (DIRECTORY / "LICENSE.md").is_file()


@pytest.mark.parametrize("layer", MANIFEST.layers, ids=lambda layer: layer.layer)
def test_zip_sha256_matches_manifest(layer: NaturalEarthLayer) -> None:
    digest = hashlib.sha256((DIRECTORY / layer.file).read_bytes()).hexdigest()
    assert digest == layer.sha256, f"{layer.file} changed without a manifest change"


@pytest.mark.parametrize("layer", MANIFEST.layers, ids=lambda layer: layer.layer)
def test_zip_holds_shapefile_and_release(layer: NaturalEarthLayer) -> None:
    with zipfile.ZipFile(DIRECTORY / layer.file) as archive:
        members = set(archive.namelist())
        assert layer.shapefile in members
        version = archive.read(f"{Path(layer.shapefile).stem}.VERSION.txt")
    assert version.decode("ascii").strip() == MANIFEST.release


def test_manifest_rejects_a_missing_layer() -> None:
    data = MANIFEST.model_dump()
    data["layers"] = data["layers"][:2]
    with pytest.raises(ValueError, match="exactly land, admin_0, admin_1"):
        NaturalEarthManifest.model_validate(data)
