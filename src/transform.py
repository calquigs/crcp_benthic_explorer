"""Transform module – aggregate point-level annotations to site-year summaries.

Pipeline stages:
    Stage A  points_to_images   Point-level → image-level percent cover
    Stage B  images_to_sites    Image-level → site-year-level summaries
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

EXCLUDE_TIER1 = {"TW"}
RENAME_TIER1 = {"UC": "Other"}

# Columns carried from points through to images
_IMAGE_META_COLS = [
    "site",
    "island",
    "region_name",
    "obs_year",
    "reef_zone",
    "depth_bin",
    "min_depth",
    "max_depth",
    "latitude",
    "longitude",
    "image_url",
    "date_",
]


# ── Stage A: Points → Images ────────────────────────────────────────────────

def _exclude_and_rename(df: pd.DataFrame) -> pd.DataFrame:
    """Remove TW rows and rename UC → Other in tier_1."""
    before = len(df)
    df = df[~df["tier_1"].isin(EXCLUDE_TIER1)].copy()
    logger.info("Excluded %d TW points (%d → %d)", before - len(df), before, len(df))

    df["tier_1"] = df["tier_1"].replace(RENAME_TIER1)
    df["category_name"] = df["category_name"].where(
        df["tier_1"] != "Other", "Other"
    )
    return df


def _compute_cover(group: pd.DataFrame, column: str) -> pd.Series:
    """Compute percent cover for each unique value in *column* within a group.

    Returns a Series indexed by the unique values with percent cover (0-100).
    """
    counts = group[column].value_counts()
    total = counts.sum()
    if total == 0:
        return pd.Series(dtype=float)
    return (counts / total * 100.0)


def points_to_images(points_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate point-level data to image-level percent cover.

    For each image, computes percent cover at tier_1, tier_2, and tier_3
    levels after excluding TW points and renormalising.

    Args:
        points_df: Raw point-level DataFrame from ingest.

    Returns:
        DataFrame with one row per image and cover columns for every
        observed tier_1, tier_2, and tier_3 value.
    """
    df = _exclude_and_rename(points_df.copy())

    # Get unique tier_1, tier_2, tier_3 values for column creation
    tier1_vals = sorted(df["tier_1"].unique())
    tier2_vals = sorted(df["tier_2"].dropna().unique())
    tier3_vals = sorted(df["tier_3"].dropna().unique())
    # Remove empty strings
    tier2_vals = [v for v in tier2_vals if v and v != "nan"]
    tier3_vals = [v for v in tier3_vals if v and v != "nan"]

    records = []
    for image_name, grp in df.groupby("image_name"):
        meta = grp[_IMAGE_META_COLS].iloc[0].to_dict()
        meta["image_name"] = image_name
        meta["n_points"] = len(grp)

        # Tier 1 cover
        t1_cover = _compute_cover(grp, "tier_1")
        for val in tier1_vals:
            meta[f"t1_{val}"] = t1_cover.get(val, 0.0)

        # Tier 2 cover
        t2_cover = _compute_cover(grp, "tier_2")
        for val in tier2_vals:
            meta[f"t2_{val}"] = t2_cover.get(val, 0.0)

        # Tier 3 cover
        t3_cover = _compute_cover(grp, "tier_3")
        for val in tier3_vals:
            meta[f"t3_{val}"] = t3_cover.get(val, 0.0)

        records.append(meta)

    images_df = pd.DataFrame(records)
    logger.info(
        "Aggregated %d points into %d image records",
        len(df),
        len(images_df),
    )
    return images_df


# ── Stage B: Images → Site-Year ─────────────────────────────────────────────

def _mode(series: pd.Series) -> Optional[str]:
    """Return the most common value, or None for empty series."""
    if series.empty:
        return None
    return series.mode().iloc[0] if not series.mode().empty else None


def _pick_representative_image(group: pd.DataFrame) -> str:
    """Select the image whose coral cover is closest to the site mean.

    This gives a visually "typical" photo for the popup thumbnail.
    """
    coral_col = "t1_CORAL"
    if coral_col not in group.columns or group[coral_col].isna().all():
        return group["image_url"].iloc[0]

    site_mean = group[coral_col].mean()
    idx = (group[coral_col] - site_mean).abs().idxmin()
    return group.loc[idx, "image_url"]


def images_to_sites(images_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate image-level data to site-year summaries.

    For each (site, obs_year) combination, computes mean and standard
    deviation of every cover column, along with metadata.

    Args:
        images_df: Output of ``points_to_images``.

    Returns:
        DataFrame with one row per site-year.
    """
    cover_cols = [c for c in images_df.columns if c.startswith(("t1_", "t2_", "t3_"))]

    records = []
    for (site, year), grp in images_df.groupby(["site", "obs_year"]):
        rec: dict = {
            "site": site,
            "obs_year": int(year),
            "island": _mode(grp["island"]),
            "region_name": _mode(grp["region_name"]),
            "reef_zone": _mode(grp["reef_zone"]),
            "depth_bin": _mode(grp["depth_bin"]),
            "min_depth": grp["min_depth"].min(),
            "max_depth": grp["max_depth"].max(),
            "latitude": grp["latitude"].median(),
            "longitude": grp["longitude"].median(),
            "n_images": len(grp),
            "representative_image_url": _pick_representative_image(grp),
        }

        for col in cover_cols:
            rec[f"mean_{col}"] = grp[col].mean()
            rec[f"std_{col}"] = grp[col].std(ddof=1) if len(grp) > 1 else 0.0

        records.append(rec)

    sites_df = pd.DataFrame(records)

    # Round cover values for cleaner output
    cover_result_cols = [c for c in sites_df.columns if c.startswith(("mean_", "std_"))]
    sites_df[cover_result_cols] = sites_df[cover_result_cols].round(2)

    logger.info(
        "Aggregated %d images into %d site-year records",
        len(images_df),
        len(sites_df),
    )
    return sites_df


# ── Full pipeline ────────────────────────────────────────────────────────────

def run_full_transform(points_df: pd.DataFrame) -> pd.DataFrame:
    """Run both aggregation stages end-to-end.

    Args:
        points_df: Raw point-level DataFrame from ingest.

    Returns:
        Site-year summary DataFrame ready for spatial conversion.
    """
    images_df = points_to_images(points_df)
    sites_df = images_to_sites(images_df)
    return sites_df
