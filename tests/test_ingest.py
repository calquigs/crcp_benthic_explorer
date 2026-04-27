"""Tests for the ingest module."""

from pathlib import Path

import pandas as pd
import pytest

from src.config import get_source
from src.ingest import _clean_dataframe

FIXTURES = Path(__file__).parent / "fixtures"


class TestCleanDataframe:
    """Tests for _clean_dataframe post-processing."""

    def _load_fixture(self) -> pd.DataFrame:
        return pd.read_csv(FIXTURES / "sample_points.csv")

    def test_returns_dataframe(self):
        df = self._load_fixture()
        result = _clean_dataframe(df)
        assert isinstance(result, pd.DataFrame)

    def test_numeric_columns_cast(self):
        df = self._load_fixture()
        result = _clean_dataframe(df)
        assert result["latitude"].dtype in ("float64", "Float64")
        assert result["longitude"].dtype in ("float64", "Float64")
        assert result["obs_year"].dtype == "Int64"

    def test_strips_units_row(self):
        """Simulate a units row like ERDDAP returns and verify it's removed."""
        df = self._load_fixture()
        units_row = {col: "units" for col in df.columns}
        units_row["obs_year"] = "years"
        units_row["latitude"] = "degrees_north"
        df = pd.concat([pd.DataFrame([units_row]), df], ignore_index=True)

        result = _clean_dataframe(df)
        assert (result["obs_year"] != "years").all()
        assert len(result) == 30  # fixture has 30 real rows

    def test_string_columns_stripped(self):
        df = self._load_fixture()
        df.loc[0, "island"] = "  Oahu  "
        result = _clean_dataframe(df)
        assert result.loc[0, "island"] == "Oahu"


class TestSourceConfig:
    """Tests for source configuration loading."""

    def test_get_known_source(self):
        cfg = get_source("hawaii")
        assert cfg.dataset_id == "CRCP_Benthic_Cover_Hawaii"

    def test_get_unknown_source_raises(self):
        with pytest.raises(KeyError, match="Unknown source"):
            get_source("nonexistent")

    def test_all_sources_have_bounds(self):
        from src.config import list_sources

        for sid in list_sources():
            cfg = get_source(sid)
            assert cfg.expected_bounds is not None, f"Source {sid} missing bounds"
