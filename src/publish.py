"""Publish module – push Feature Layers to ArcGIS Online."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import geopandas as gpd

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


def _find_existing_items(gis, title: str) -> list:
    """Search for existing items (Feature Service and GeoJSON) by title."""
    owner = gis.properties.user.username
    items = []
    for item_type in ("Feature Service", "GeoJson"):
        query = f'title:"{title}" AND type:"{item_type}" AND owner:{owner}'
        results = gis.content.search(query=query, max_items=10)
        items.extend(r for r in results if r.title == title)
    return items


def publish_feature_layer(
    gdf: gpd.GeoDataFrame,
    title: str,
    tags: list[str],
    description: str = "",
    folder: Optional[str] = None,
    overwrite: bool = True,
) -> object:
    """Publish a GeoDataFrame as a Hosted Feature Layer on ArcGIS Online.

    Uploads as GeoJSON to avoid the shapefile 10-character column name limit.

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
    gis = _get_gis()

    existing = _find_existing_items(gis, title)
    if existing and overwrite:
        for item in existing:
            logger.info("Deleting existing item: %s (%s, type=%s)", item.title, item.id, item.type)
            item.delete()
    elif existing and not overwrite:
        raise ValueError(
            f"Item '{title}' already exists ({len(existing)} item(s)). "
            "Set overwrite=True to replace."
        )

    if folder:
        existing_folders = {f.name for f in gis.users.me.folders}
        if folder not in existing_folders:
            gis.content.create_folder(folder)
            logger.info("Created AGOL folder: %s", folder)

    with tempfile.TemporaryDirectory() as tmp:
        geojson_path = Path(tmp) / f"{title}.geojson"
        gdf.to_file(geojson_path, driver="GeoJSON")

        geojson_item = gis.content.add(
            item_properties={
                "title": title,
                "type": "GeoJson",
                "tags": ",".join(tags),
                "description": description,
                "snippet": f"CRCP benthic cover site summaries – {title}",
                "accessInformation": "NOAA Coral Reef Conservation Program (CRCP)",
                "licenseInfo": "Public domain – U.S. Government Work",
            },
            data=str(geojson_path),
            folder=folder,
        )
        logger.info("Uploaded GeoJSON item: %s (%s)", geojson_item.title, geojson_item.id)

        item = geojson_item.publish()
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
