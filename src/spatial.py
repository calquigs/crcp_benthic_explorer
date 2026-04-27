"""Spatial module – construct GeoDataFrames and validate coordinates."""

from __future__ import annotations

import logging
from typing import Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from src.config import get_source, SourceConfig

logger = logging.getLogger(__name__)

CRS_WGS84 = "EPSG:4326"


def build_site_geodataframe(sites_df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Convert a site-year summary DataFrame to a GeoDataFrame.

    Args:
        sites_df: Output of ``transform.images_to_sites`` or
            ``transform.run_full_transform``, containing ``latitude``
            and ``longitude`` columns.

    Returns:
        GeoDataFrame with Point geometry in WGS 84 (EPSG:4326).

    Raises:
        ValueError: If latitude or longitude columns are missing.
    """
    for col in ("latitude", "longitude"):
        if col not in sites_df.columns:
            raise ValueError(f"Missing required column: {col}")

    geometry = [
        Point(row.longitude, row.latitude)
        if pd.notna(row.latitude) and pd.notna(row.longitude)
        else None
        for row in sites_df.itertuples()
    ]

    gdf = gpd.GeoDataFrame(sites_df, geometry=geometry, crs=CRS_WGS84)

    null_geom = gdf.geometry.isna().sum()
    if null_geom > 0:
        logger.warning("%d features have null geometry (missing coordinates)", null_geom)

    logger.info(
        "Built GeoDataFrame with %d features (CRS=%s)",
        len(gdf),
        CRS_WGS84,
    )
    return gdf


def validate_coordinates(
    gdf: gpd.GeoDataFrame,
    source_id: str,
) -> list[str]:
    """Check that all coordinates fall within the expected bounding box.

    Args:
        gdf: GeoDataFrame produced by ``build_site_geodataframe``.
        source_id: Source key used to look up expected_bounds.

    Returns:
        List of warning messages.  Empty list means all coordinates pass.
    """
    cfg = get_source(source_id)
    bounds = cfg.expected_bounds
    warnings: list[str] = []

    if bounds is None:
        warnings.append(
            f"No expected_bounds configured for source '{source_id}'; skipping."
        )
        return warnings

    valid = gdf[gdf.geometry.notna()].copy()
    if valid.empty:
        warnings.append("No features with valid geometry to check.")
        return warnings

    lats = valid.geometry.y
    lons = valid.geometry.x

    out_lat = valid[
        (lats < bounds["min_lat"]) | (lats > bounds["max_lat"])
    ]
    out_lon = valid[
        (lons < bounds["min_lon"]) | (lons > bounds["max_lon"])
    ]

    if not out_lat.empty:
        sites = out_lat["site"].tolist()
        warnings.append(
            f"{len(out_lat)} feature(s) outside latitude bounds "
            f"[{bounds['min_lat']}, {bounds['max_lat']}]: {sites[:5]}"
        )

    if not out_lon.empty:
        sites = out_lon["site"].tolist()
        warnings.append(
            f"{len(out_lon)} feature(s) outside longitude bounds "
            f"[{bounds['min_lon']}, {bounds['max_lon']}]: {sites[:5]}"
        )

    if not warnings:
        logger.info("All %d features pass coordinate bounds check.", len(valid))
    else:
        for w in warnings:
            logger.warning(w)

    return warnings
