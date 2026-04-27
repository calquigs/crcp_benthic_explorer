"""Tests for the transform module."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.transform import points_to_images, images_to_sites, run_full_transform

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_points() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "sample_points.csv")


class TestPointsToImages:
    """Tests for Stage A: point → image aggregation."""

    def test_output_row_count(self, sample_points):
        """Fixture has 3 images; result should have 3 rows."""
        result = points_to_images(sample_points)
        assert len(result) == 3

    def test_tw_excluded(self, sample_points):
        """TW points should be removed before computing cover."""
        result = points_to_images(sample_points)
        tw_cols = [c for c in result.columns if "TW" in c]
        assert len(tw_cols) == 0

    def test_uc_renamed_to_other(self, sample_points):
        result = points_to_images(sample_points)
        assert "t1_Other" in result.columns
        assert "t1_UC" not in result.columns

    def test_cover_sums_to_100(self, sample_points):
        """After TW exclusion and renormalization, tier_1 covers should sum to 100."""
        result = points_to_images(sample_points)
        t1_cols = [c for c in result.columns if c.startswith("t1_")]
        row_sums = result[t1_cols].sum(axis=1)
        for s in row_sums:
            assert abs(s - 100.0) < 0.1, f"tier_1 sum = {s}, expected ~100"

    def test_all_coral_image(self):
        """An image where all 10 points are CORAL should yield 100% coral."""
        rows = []
        for i in range(10):
            rows.append({
                "latitude": 21.0, "longitude": -158.0,
                "site": "TEST-001", "island": "Test",
                "region_name": "Test Region", "obs_year": 2020,
                "reef_zone": "Forereef", "depth_bin": "Shallow",
                "min_depth": 10.0, "max_depth": 20.0,
                "image_name": "TEST_01.JPG", "image_url": "https://example.com/test.jpg",
                "date_": "2020-01-01",
                "tier_1": "CORAL", "category_name": "Coral",
                "tier_2": "MASS", "subcategory_name": "Massive hard coral",
                "tier_3": "POMA", "genera_name": "Porites massive",
            })
        df = pd.DataFrame(rows)
        result = points_to_images(df)
        assert result.iloc[0]["t1_CORAL"] == 100.0

    def test_n_points_column_present(self, sample_points):
        result = points_to_images(sample_points)
        assert "n_points" in result.columns
        # Image 1 had 10 points (9 non-TW after exclusion), but n_points
        # reflects the count AFTER TW exclusion.
        assert (result["n_points"] > 0).all()

    def test_metadata_carried_forward(self, sample_points):
        result = points_to_images(sample_points)
        assert "site" in result.columns
        assert "island" in result.columns
        assert "image_url" in result.columns


class TestImagesToSites:
    """Tests for Stage B: image → site-year aggregation."""

    def test_output_row_count(self, sample_points):
        """Fixture has 2 sites (OAH-100, MAU-200), each in 1 year → 2 rows."""
        images = points_to_images(sample_points)
        sites = images_to_sites(images)
        assert len(sites) == 2

    def test_n_images_correct(self, sample_points):
        images = points_to_images(sample_points)
        sites = images_to_sites(images)
        oah = sites[sites["site"] == "OAH-100"].iloc[0]
        assert oah["n_images"] == 2

        mau = sites[sites["site"] == "MAU-200"].iloc[0]
        assert mau["n_images"] == 1

    def test_mean_cover_columns_present(self, sample_points):
        images = points_to_images(sample_points)
        sites = images_to_sites(images)
        mean_cols = [c for c in sites.columns if c.startswith("mean_t1_")]
        std_cols = [c for c in sites.columns if c.startswith("std_t1_")]
        assert len(mean_cols) > 0
        assert len(std_cols) > 0

    def test_representative_image_url(self, sample_points):
        images = points_to_images(sample_points)
        sites = images_to_sites(images)
        assert (sites["representative_image_url"].str.startswith("https://")).all()

    def test_coordinates_present(self, sample_points):
        images = points_to_images(sample_points)
        sites = images_to_sites(images)
        assert sites["latitude"].notna().all()
        assert sites["longitude"].notna().all()


class TestRunFullTransform:
    """Tests for the end-to-end pipeline."""

    def test_returns_dataframe(self, sample_points):
        result = run_full_transform(sample_points)
        assert isinstance(result, pd.DataFrame)

    def test_output_has_expected_sites(self, sample_points):
        result = run_full_transform(sample_points)
        assert set(result["site"]) == {"OAH-100", "MAU-200"}
