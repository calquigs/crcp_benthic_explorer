"""Publish module – push Feature Layers to ArcGIS Online."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Literal, Optional

import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)

Mode = Literal["create", "overwrite", "append"]

FIELD_ALIASES: dict[str, str] = {
    # Tier-1 mean cover
    "mean_t1_CORAL": "Coral (mean %)",
    "mean_t1_TURF": "Turf (mean %)",
    "mean_t1_MA": "Macroalgae (mean %)",
    "mean_t1_CCA": "CCA (mean %)",
    "mean_t1_SED": "Sediment (mean %)",
    "mean_t1_Other": "Other (mean %)",
    "mean_t1_I": "Invertebrate (mean %)",
    "mean_t1_SC": "Soft Coral (mean %)",
    "mean_t1_MF": "Microfilm (mean %)",
    # Tier-1 std cover
    "std_t1_CORAL": "Coral (std %)",
    "std_t1_TURF": "Turf (std %)",
    "std_t1_MA": "Macroalgae (std %)",
    "std_t1_CCA": "CCA (std %)",
    "std_t1_SED": "Sediment (std %)",
    "std_t1_Other": "Other (std %)",
    "std_t1_I": "Invertebrate (std %)",
    "std_t1_SC": "Soft Coral (std %)",
    "std_t1_MF": "Microfilm (std %)",
    # Metadata fields
    "obs_year": "Observation Year",
    "obs_date": "Survey Date",
    "n_images": "Number of Images",
    "min_depth": "Min Depth (m)",
    "max_depth": "Max Depth (m)",
    "reef_zone": "Reef Zone",
    "depth_bin": "Depth Bin",
    "region_name": "Region",
    "island": "Island",
    "site": "Site",
    "representative_image_url": "Representative Image URL",
}


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


def _find_existing_item(gis, title: str, item_type: str = "Feature Service"):
    """Find a single existing item by title and type. Returns the first match or None."""
    owner = gis.properties.user.username
    query = f'title:"{title}" AND type:"{item_type}" AND owner:{owner}'
    results = gis.content.search(query=query, max_items=10)
    matches = [r for r in results if r.title == title]
    return matches[0] if matches else None


def _write_geojson(gdf: gpd.GeoDataFrame, title: str, tmp_dir: str) -> Path:
    """Write a GeoDataFrame to a temporary GeoJSON file."""
    path = Path(tmp_dir) / f"{title}.geojson"
    gdf.to_file(path, driver="GeoJSON")
    return path


def _create_feature_layer(gis, gdf, title, tags, description, folder):
    """Create a new Feature Layer from scratch (deletes any existing item)."""
    existing = _find_existing_items(gis, title)
    for item in existing:
        logger.info(
            "Deleting existing item: %s (%s, type=%s)",
            item.title, item.id, item.type,
        )
        item.delete()

    if folder:
        existing_folders = {f.name for f in gis.users.me.folders}
        if folder not in existing_folders:
            gis.content.create_folder(folder)
            logger.info("Created AGOL folder: %s", folder)

    with tempfile.TemporaryDirectory() as tmp:
        geojson_path = _write_geojson(gdf, title, tmp)

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


def _overwrite_feature_layer(gis, gdf, title):
    """Overwrite all data in an existing Feature Layer, preserving the item ID.

    Symbology, popups, and web map / Experience Builder references are retained.
    The schema (field names and types) must match the existing layer.
    """
    from arcgis.features import FeatureLayerCollection

    item = _find_existing_item(gis, title, "Feature Service")
    if item is None:
        raise ValueError(
            f"No existing Feature Service '{title}' found. "
            "Use mode='create' to publish a new layer first."
        )

    flc = FeatureLayerCollection.fromitem(item)
    with tempfile.TemporaryDirectory() as tmp:
        geojson_path = _write_geojson(gdf, title, tmp)
        flc.manager.overwrite(str(geojson_path))
        logger.info("Overwrote Feature Layer in place: %s (id=%s)", item.title, item.id)

    return item


def _append_to_feature_layer(gis, gdf, title):
    """Append new rows to an existing Feature Layer.

    Uploads a temporary GeoJSON item, appends its features, then cleans up.
    """
    from arcgis.features import FeatureLayerCollection

    item = _find_existing_item(gis, title, "Feature Service")
    if item is None:
        raise ValueError(
            f"No existing Feature Service '{title}' found. "
            "Use mode='create' to publish a new layer first."
        )

    with tempfile.TemporaryDirectory() as tmp:
        geojson_path = _write_geojson(gdf, title, tmp)

        geojson_item = gis.content.add(
            item_properties={
                "title": f"{title}_append_temp",
                "type": "GeoJson",
            },
            data=str(geojson_path),
        )

    try:
        flc = FeatureLayerCollection.fromitem(item)
        flc.manager.append(
            item_id=geojson_item.id,
            upload_format="geojson",
        )
        logger.info(
            "Appended %d features to %s (id=%s)",
            len(gdf), item.title, item.id,
        )
    finally:
        geojson_item.delete()
        logger.info("Cleaned up temporary GeoJSON item")

    return item


def _enable_time(item, time_field: str = "obs_date") -> None:
    """Enable time settings on a Feature Layer so Map Viewer shows a time slider."""
    fl = item.layers[0]

    field_type = None
    for field in fl.properties.fields:
        if field["name"] == time_field:
            field_type = field["type"]
            break

    if field_type is None:
        logger.warning(
            "Time field '%s' not found on layer %s – skipping time enablement",
            time_field, item.title,
        )
        return

    time_info = {
        "timeInfo": {
            "startTimeField": time_field,
            "endTimeField": None,
            "timeInterval": 1,
            "timeIntervalUnits": "esriTimeUnitsDays",
        }
    }
    fl.manager.update_definition(time_info)
    logger.info("Enabled time on field '%s' for %s", time_field, item.title)


def _apply_field_aliases(item, aliases: dict[str, str]) -> None:
    """Update field aliases on a published Feature Layer item."""
    fl = item.layers[0]
    existing_fields = fl.properties.fields

    updates = []
    for field in existing_fields:
        name = field["name"]
        if name in aliases:
            updates.append({"name": name, "alias": aliases[name]})

    if updates:
        fl.manager.update_definition({"fields": updates})
        logger.info("Applied %d field aliases to %s", len(updates), item.title)


def publish_feature_layer(
    gdf: gpd.GeoDataFrame,
    title: str,
    tags: list[str],
    description: str = "",
    folder: Optional[str] = None,
    mode: Mode = "create",
) -> object:
    """Publish or update a GeoDataFrame as a Hosted Feature Layer on ArcGIS Online.

    Uploads as GeoJSON to avoid the shapefile 10-character column name limit.

    Args:
        gdf: GeoDataFrame to publish (must have geometry and CRS set).
        title: Title for the Feature Layer item.
        tags: List of tags for discoverability.
        description: Item description / abstract.
        folder: AGOL folder to publish into (created if needed).
        mode: Publishing strategy:
            "create"    – delete any existing layer and publish fresh.
            "overwrite" – replace all rows in place (preserves item ID,
                          symbology, popups, and web map references).
                          Schema must match the existing layer.
            "append"    – add new rows to the existing layer.

    Returns:
        The published/updated arcgis Feature Layer item.
    """
    gis = _get_gis()

    if mode == "create":
        return _create_feature_layer(gis, gdf, title, tags, description, folder)
    elif mode == "overwrite":
        return _overwrite_feature_layer(gis, gdf, title)
    elif mode == "append":
        return _append_to_feature_layer(gis, gdf, title)
    else:
        raise ValueError(f"Invalid mode '{mode}'. Use 'create', 'overwrite', or 'append'.")


def publish_site_summary(
    gdf: gpd.GeoDataFrame,
    source_id: str,
    folder: Optional[str] = "CRCP_Benthic_Explorer",
    mode: Mode = "create",
) -> str:
    """Publish the site-year summary layer for a specific source.

    This is the primary entry point for the publish step.

    Args:
        gdf: Site-year GeoDataFrame from the spatial module.
        source_id: Source key (e.g. "hawaii") for naming.
        folder: AGOL folder name.
        mode: "create", "overwrite", or "append" (see publish_feature_layer).

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

    gdf = gdf.copy()
    gdf["obs_date"] = pd.to_datetime(gdf["date_"]).dt.normalize()
    gdf = gdf.drop(columns=["date_"])

    item = publish_feature_layer(
        gdf=gdf,
        title=title,
        tags=tags,
        description=description,
        folder=folder,
        mode=mode,
    )

    _apply_field_aliases(item, FIELD_ALIASES)
    _enable_time(item, time_field="obs_date")

    return item.url
