"""Validation module – QA checks at each pipeline stage."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Issue:
    severity: Severity
    message: str
    count: int = 0


@dataclass
class ValidationReport:
    stage: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    def summary(self) -> str:
        n_problems = sum(
            1 for i in self.issues if i.severity != Severity.INFO
        )
        lines = [f"Validation [{self.stage}]: {n_problems} issue(s)"]
        for issue in self.issues:
            lines.append(f"  [{issue.severity.value.upper()}] {issue.message}")
        return "\n".join(lines)


# ── Point-level checks ──────────────────────────────────────────────────────

def validate_points(df: pd.DataFrame) -> ValidationReport:
    """Validate raw point-level data from ERDDAP.

    Checks:
    - No null tier_1 values
    - No null coordinates
    """
    report = ValidationReport(stage="points")

    # Null tier_1
    null_t1 = df["tier_1"].isna().sum() + (df["tier_1"] == "").sum()
    if null_t1 > 0:
        report.issues.append(Issue(
            Severity.WARNING,
            f"{null_t1} point(s) have null or empty tier_1",
            count=null_t1,
        ))

    # Null coordinates
    null_coords = df["latitude"].isna().sum() + df["longitude"].isna().sum()
    if null_coords > 0:
        report.issues.append(Issue(
            Severity.ERROR,
            f"{null_coords} null coordinate value(s)",
            count=null_coords,
        ))

    if not report.issues:
        report.issues.append(Issue(Severity.INFO, "All point-level checks passed."))

    logger.info(report.summary())
    return report


# ── Image-level checks ──────────────────────────────────────────────────────

def validate_images(df: pd.DataFrame) -> ValidationReport:
    """Validate image-level aggregation output.

    Checks:
    - tier_1 cover columns sum to ~100% per image
    - No null image metadata
    """
    report = ValidationReport(stage="images")

    t1_cols = [c for c in df.columns if c.startswith("t1_")]
    if t1_cols:
        row_sums = df[t1_cols].sum(axis=1)
        bad_sums = row_sums[~np.isclose(row_sums, 100.0, atol=1.0)]
        if not bad_sums.empty:
            report.issues.append(Issue(
                Severity.WARNING,
                f"{len(bad_sums)} image(s) have tier_1 cover not summing to ~100% "
                f"(range: {bad_sums.min():.1f}-{bad_sums.max():.1f})",
                count=len(bad_sums),
            ))

    null_site = df["site"].isna().sum()
    if null_site > 0:
        report.issues.append(Issue(
            Severity.ERROR,
            f"{null_site} image(s) missing site identifier",
            count=null_site,
        ))

    null_year = df["obs_year"].isna().sum()
    if null_year > 0:
        report.issues.append(Issue(
            Severity.ERROR,
            f"{null_year} image(s) missing obs_year",
            count=null_year,
        ))

    if not report.issues:
        report.issues.append(Issue(Severity.INFO, "All image-level checks passed."))

    logger.info(report.summary())
    return report


# ── Site-level checks ────────────────────────────────────────────────────────

def validate_sites(
    gdf: gpd.GeoDataFrame,
    expected_images: Optional[int] = None,
) -> ValidationReport:
    """Validate site-year summary GeoDataFrame.

    Checks:
    - No null geometry
    - n_images > 0 for all sites
    - Total images match expected count (if provided)
    """
    report = ValidationReport(stage="sites")

    null_geom = gdf.geometry.isna().sum()
    if null_geom > 0:
        report.issues.append(Issue(
            Severity.ERROR,
            f"{null_geom} site(s) have null geometry",
            count=null_geom,
        ))

    zero_imgs = (gdf["n_images"] <= 0).sum() if "n_images" in gdf.columns else 0
    if zero_imgs > 0:
        report.issues.append(Issue(
            Severity.ERROR,
            f"{zero_imgs} site(s) have n_images <= 0",
            count=zero_imgs,
        ))

    if expected_images is not None and "n_images" in gdf.columns:
        actual = gdf["n_images"].sum()
        if actual != expected_images:
            report.issues.append(Issue(
                Severity.WARNING,
                f"Total images ({actual}) differs from expected ({expected_images}). "
                "Possible data loss during aggregation.",
                count=abs(actual - expected_images),
            ))

    if not report.issues:
        report.issues.append(Issue(Severity.INFO, "All site-level checks passed."))

    logger.info(report.summary())
    return report
