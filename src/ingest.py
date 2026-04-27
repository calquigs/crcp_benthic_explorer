"""Ingest module – query NOAA ERDDAP for CRCP benthic cover point data."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from erddapy import ERDDAP

from src.config import get_source, SourceConfig

logger = logging.getLogger(__name__)

VARIABLES = [
    "latitude",
    "longitude",
    "missionid",
    "region_name",
    "island",
    "site",
    "reef_zone",
    "survey_type",
    "depth_bin",
    "min_depth",
    "max_depth",
    "date_",
    "image_name",
    "image_url",
    "obs_year",
    "rep",
    "photoid",
    "analyst",
    "tier_1",
    "category_name",
    "tier_2",
    "subcategory_name",
    "tier_3",
    "genera_name",
]


def _build_client(cfg: SourceConfig) -> ERDDAP:
    """Construct an erddapy client from a SourceConfig."""
    client = ERDDAP(
        server=cfg.erddap_server,
        protocol="tabledap",
    )
    client.dataset_id = cfg.dataset_id
    client.variables = VARIABLES
    return client


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Post-process the raw ERDDAP DataFrame.

    erddapy may return a units row or column-name suffixes.  This function
    normalises column names, drops the units row if present, and casts types.
    """
    # erddapy's to_pandas often appends units to column names like
    # "obs_year (years)".  Strip everything after the first space/paren.
    rename_map = {}
    for col in df.columns:
        base = col.split(" (")[0].split(" [")[0].strip()
        rename_map[col] = base
    df = df.rename(columns=rename_map)

    # Drop any row where obs_year is literally the string "years" (units row)
    if df["obs_year"].dtype == object:
        df = df[df["obs_year"] != "years"]

    numeric_cols = ["latitude", "longitude", "obs_year", "min_depth", "max_depth", "photoid"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["obs_year"] = df["obs_year"].astype("Int64")

    # Normalise string columns
    str_cols = [
        "region_name", "island", "site", "reef_zone", "depth_bin",
        "tier_1", "tier_2", "tier_3", "category_name",
        "subcategory_name", "genera_name",
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    df = df.reset_index(drop=True)
    return df


def fetch_source(
    source_id: str,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
) -> pd.DataFrame:
    """Query ERDDAP for all point-level annotations for a given source.

    Args:
        source_id: Key from config/sources.json (e.g. "hawaii").
        min_year: If provided, only include obs_year >= min_year.
        max_year: If provided, only include obs_year <= max_year.

    Returns:
        DataFrame with one row per annotation point.
    """
    cfg = get_source(source_id)
    client = _build_client(cfg)

    constraints: dict = {}
    if min_year is not None:
        constraints["obs_year>="] = min_year
    if max_year is not None:
        constraints["obs_year<="] = max_year
    client.constraints = constraints

    logger.info(
        "Fetching %s (dataset=%s) with constraints=%s",
        cfg.display_name,
        cfg.dataset_id,
        constraints or "none",
    )

    df = client.to_pandas()
    df = _clean_dataframe(df)

    logger.info("Fetched %d rows for source '%s'", len(df), source_id)
    return df


def fetch_source_incremental(source_id: str, since_year: int) -> pd.DataFrame:
    """Query only data from *since_year* onward (for annual updates).

    Args:
        source_id: Key from config/sources.json.
        since_year: Minimum obs_year to fetch.

    Returns:
        DataFrame of point-level annotations from since_year onward.
    """
    return fetch_source(source_id, min_year=since_year)
