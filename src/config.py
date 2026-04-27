"""Source configuration loader for CRCP Benthic Explorer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sources.json"

REQUIRED_FIELDS = {"id", "dataset_id", "erddap_server", "display_name"}


@dataclass(frozen=True)
class SourceConfig:
    """Immutable descriptor for a single ERDDAP data source."""

    id: str
    dataset_id: str
    erddap_server: str
    display_name: str
    coralnet_source_id: Optional[int] = None
    expected_bounds: Optional[dict] = None


def _load_all(config_path: Path = _CONFIG_PATH) -> dict[str, SourceConfig]:
    """Read sources.json and return a mapping of source id → SourceConfig."""
    with open(config_path) as f:
        raw = json.load(f)

    sources: dict[str, SourceConfig] = {}
    for entry in raw["sources"]:
        missing = REQUIRED_FIELDS - entry.keys()
        if missing:
            raise ValueError(
                f"Source entry missing required fields: {missing}"
            )
        sources[entry["id"]] = SourceConfig(
            id=entry["id"],
            dataset_id=entry["dataset_id"],
            erddap_server=entry["erddap_server"],
            display_name=entry["display_name"],
            coralnet_source_id=entry.get("coralnet_source_id"),
            expected_bounds=entry.get("expected_bounds"),
        )
    return sources


_SOURCES: dict[str, SourceConfig] | None = None


def _ensure_loaded() -> dict[str, SourceConfig]:
    global _SOURCES
    if _SOURCES is None:
        _SOURCES = _load_all()
    return _SOURCES


def get_source(source_id: str) -> SourceConfig:
    """Return the SourceConfig for a given source id.

    Args:
        source_id: One of the ids defined in config/sources.json
            (e.g. "hawaii", "marianas", "samoa", "prias").

    Raises:
        KeyError: If the source_id is not found.
    """
    sources = _ensure_loaded()
    if source_id not in sources:
        available = ", ".join(sorted(sources.keys()))
        raise KeyError(
            f"Unknown source '{source_id}'. Available: {available}"
        )
    return sources[source_id]


def list_sources() -> list[str]:
    """Return a sorted list of all available source ids."""
    return sorted(_ensure_loaded().keys())
