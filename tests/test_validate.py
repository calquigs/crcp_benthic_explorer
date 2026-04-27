"""Tests for the validation module."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from src.validate import (
    Severity,
    validate_images,
    validate_points,
    validate_sites,
)
from src.transform import points_to_images, run_full_transform
from src.spatial import build_site_geodataframe

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_points() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "sample_points.csv")


class TestValidatePoints:
    def test_clean_data_passes(self, sample_points):
        report = validate_points(sample_points)
        assert not report.has_errors

    def test_detects_null_coords(self, sample_points):
        df = sample_points.copy()
        df.loc[0, "latitude"] = np.nan
        report = validate_points(df)
        assert report.has_errors
        assert any("null coordinate" in i.message for i in report.issues)

    def test_detects_null_tier1(self, sample_points):
        df = sample_points.copy()
        df.loc[0, "tier_1"] = ""
        report = validate_points(df)
        assert any("null or empty tier_1" in i.message for i in report.issues)


class TestValidateImages:
    def test_clean_data_passes(self, sample_points):
        images = points_to_images(sample_points)
        report = validate_images(images)
        assert not report.has_errors

    def test_detects_bad_cover_sum(self, sample_points):
        images = points_to_images(sample_points)
        t1_cols = [c for c in images.columns if c.startswith("t1_")]
        images.loc[0, t1_cols[0]] = 200.0  # break the sum
        report = validate_images(images)
        assert any("not summing to ~100%" in i.message for i in report.issues)

    def test_detects_missing_site(self, sample_points):
        images = points_to_images(sample_points)
        images.loc[0, "site"] = None
        report = validate_images(images)
        assert report.has_errors


class TestValidateSites:
    def test_clean_data_passes(self, sample_points):
        sites = run_full_transform(sample_points)
        gdf = build_site_geodataframe(sites)
        report = validate_sites(gdf)
        assert not report.has_errors

    def test_detects_null_geometry(self, sample_points):
        sites = run_full_transform(sample_points)
        gdf = build_site_geodataframe(sites)
        gdf.loc[gdf.index[0], "geometry"] = None
        report = validate_sites(gdf)
        assert report.has_errors

    def test_image_count_mismatch(self, sample_points):
        sites = run_full_transform(sample_points)
        gdf = build_site_geodataframe(sites)
        report = validate_sites(gdf, expected_images=9999)
        assert report.has_warnings
