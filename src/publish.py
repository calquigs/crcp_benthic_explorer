"""Publish module – push Feature Layers to ArcGIS Online."""

from __future__ import annotations

import logging
import os
from typing import Optional

import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)


def _get_gis():
    """Authenticate to ArcGIS Online.

    Reads credentials from environment variables:
        AGOL_URL      – Portal URL (default: https://www.arcgis.com)
        AGOL_USERNAME – ArcGIS Online username
        AGOL_PASSWORD – ArcGIS Online password

    Returns:
        An authenticated arcgis.GIS instance.
    """
    from arcgis.gis import GIS

    url = os.environ.get("AGOL_URL", "https://www.arcgis.com")
    username = os.environ.get("AGOL_USERNAME")
    password = os.environ.get("AGOL_PASSWORD")

    if not username or not password:
        raise EnvironmentError(
            "AGOL_USERNAME and AGOL_PASSWORD environment variables must be set. "
            "See README.md for setup instructions."
        )

    gis = GIS(url, username, password)
    logger.info("Authenticated to %s as %s", url, gis.properties.user.username)
    return gis


def _find_existing_item(gis, title: str, folder: Optional[str]) -> Optional[object]:
    """Search for an existing Feature Layer item by title."""
    query = f'title:"{title}" AND type:"Feature Service" AND owner:{gis.properties.user.username}'
    results = gis.content.search(query=query, max_items=10)
    for item in results:
        if item.title == title:
            return item
    return None


def publish_feature_layer(
    gdf: gpd.GeoDataFrame,
    title: str,
    tags: list[str],
    description: str = "",
    folder: Optional[str] = None,
    overwrite: bool = True,
) -> object:
    """Publish a GeoDataFrame as a Hosted Feature Layer on ArcGIS Online.

    Args:
        gdf: GeoDataFrame to publish (must have geometry and CRS set).
        title: Title for the Feature Layer item.
        tags: List of tags for discoverability.
        description: Item description / abstract.
        folder: AGOL folder to publish into (created if needed).
        overwrite: If True and a layer with the same title exists,
            overwrite it. Otherwise raise an error.

    Returns:
        The published arcgis FeatureLayer item.
    """
    from arcgis.features import GeoAccessor

    gis = _get_gis()

    existing = _find_existing_item(gis, title, folder)
    if existing and overwrite:
        logger.info("Overwriting existing item: %s (%s)", existing.title, existing.id)
        existing.delete()
    elif existing and not overwrite:
        raise ValueError(
            f"Item '{title}' already exists (id={existing.id}). "
            "Set overwrite=True to replace it."
        )

    # Convert GeoDataFrame to Esri-compatible Spatially Enabled DataFrame
    sdf = pd.DataFrame.spatial.from_geodataframe(gdf)

    item = sdf.spatial.to_featurelayer(
        title=title,
        gis=gis,
        folder=folder,
        tags=tags,
    )

    # Update item metadata
    item.update(item_properties={
        "description": description,
        "snippet": f"CRCP benthic cover site summaries – {title}",
        "accessInformation": "NOAA Coral Reef Conservation Program (CRCP)",
        "licenseInfo": "Public domain – U.S. Government Work",
    })

    logger.info("Published Feature Layer: %s (id=%s)", item.title, item.id)
    return item


def publish_site_summary(
    gdf: gpd.GeoDataFrame,
    source_id: str,
    folder: Optional[str] = "CRCP_Benthic_Explorer",
    overwrite: bool = True,
) -> str:
    """Publish the site-year summary layer for a specific source.

    This is the primary entry point for the publish step.

    Args:
        gdf: Site-year GeoDataFrame from the spatial module.
        source_id: Source key (e.g. "hawaii") for naming.
        folder: AGOL folder name.
        overwrite: Whether to replace an existing layer.

    Returns:
        URL of the published Feature Layer.
    """
    from src.config import get_source

    cfg = get_source(source_id)
    title = f"CRCP Benthic Cover – {cfg.display_name}"
    tags = [
        "CRCP",
        "benthic cover",
        "coral reef",
        cfg.display_name,
        "NOAA",
        "ERDDAP",
    ]
    description = (
        f"Site-year summary of benthic cover derived from NOAA CRCP "
        f"stratified random survey annotations for the {cfg.display_name}. "
        f"Source ERDDAP dataset: {cfg.dataset_id}. "
        f"Processed by the CRCP Benthic Explorer pipeline."
    )

    item = publish_feature_layer(
        gdf=gdf,
        title=title,
        tags=tags,
        description=description,
        folder=folder,
        overwrite=overwrite,
    )

    return item.url
