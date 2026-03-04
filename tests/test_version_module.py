#!/usr/bin/env python3
"""
Test Suite for Centralized Version Module (V11.1)

Tests the src.version module to ensure:
1. Version constants are correctly defined
2. Version functions return expected values
3. Historical versions are preserved
4. Version comparison utilities work correctly

Author: Lead Architect
Date: 2026-02-23
"""

import pytest
from src.version import (
    VERSION,
    VERSION_MAJOR,
    VERSION_MINOR,
    VERSION_PATCH,
    VERSION_DATE,
    VERSION_NAME,
    VERSION_DESCRIPTION,
    get_version,
    get_version_tuple,
    get_version_dict,
    get_version_with_module,
    get_version_info,
    HISTORICAL_MODULE_VERSIONS,
    get_historical_version,
    version_matches,
    is_at_least,
)


class TestVersionConstants:
    """Test version constants are correctly defined."""

    def test_version_string(self):
        """Test VERSION string is correctly formatted."""
        assert VERSION == "V11.1"
        assert VERSION.startswith("V")
        assert "." in VERSION

    def test_version_components(self):
        """Test version components are integers."""
        assert isinstance(VERSION_MAJOR, int)
        assert isinstance(VERSION_MINOR, int)
        assert isinstance(VERSION_PATCH, int)
        assert VERSION_MAJOR == 11
        assert VERSION_MINOR == 1
        assert VERSION_PATCH == 0

    def test_version_metadata(self):
        """Test version metadata is correctly defined."""
        assert isinstance(VERSION_DATE, str)
        assert isinstance(VERSION_NAME, str)
        assert isinstance(VERSION_DESCRIPTION, str)
        assert "2026-02-23" in VERSION_DATE
        assert len(VERSION_NAME) > 0
        assert len(VERSION_DESCRIPTION) > 0


class TestVersionFunctions:
    """Test version functions return expected values."""

    def test_get_version(self):
        """Test get_version returns correct version string."""
        version = get_version()
        assert version == "V11.1"
        assert isinstance(version, str)

    def test_get_version_tuple(self):
        """Test get_version_tuple returns correct tuple."""
        version_tuple = get_version_tuple()
        assert version_tuple == (11, 1, 0)
        assert isinstance(version_tuple, tuple)
        assert len(version_tuple) == 3

    def test_get_version_dict(self):
        """Test get_version_dict returns correct dictionary."""
        version_dict = get_version_dict()
        assert isinstance(version_dict, dict)
        assert version_dict["version"] == "V11.1"
        assert version_dict["major"] == 11
        assert version_dict["minor"] == 1
        assert version_dict["patch"] == 0
        assert "date" in version_dict
        assert "name" in version_dict
        assert "description" in version_dict

    def test_get_version_with_module(self):
        """Test get_version_with_module returns correct string."""
        version = get_version_with_module("Test Module")
        assert version == "Test Module V11.1"
        assert "Test Module" in version
        assert "V11.1" in version

    def test_get_version_info(self):
        """Test get_version_info returns human-readable string."""
        info = get_version_info()
        assert isinstance(info, str)
        assert "V11.1" in info
        assert "2026-02-23" in info
        assert len(info) > 50  # Should be a multi-line string


class TestHistoricalVersions:
    """Test historical module versions are preserved."""

    def test_historical_versions_dict(self):
        """Test HISTORICAL_MODULE_VERSIONS is a dictionary."""
        assert isinstance(HISTORICAL_MODULE_VERSIONS, dict)
        assert len(HISTORICAL_MODULE_VERSIONS) > 0

    def test_historical_version_getter(self):
        """Test get_historical_version returns correct values."""
        # Test known historical versions
        assert get_historical_version("Global Orchestrator") == "V11.0"
        assert get_historical_version("Launcher") == "V3.7"
        assert get_historical_version("Analysis Engine") == "V1.0"
        assert get_historical_version("Notifier") == "V8.2"

        # Test unknown module returns None
        assert get_historical_version("Unknown Module") is None


class TestVersionComparison:
    """Test version comparison utilities."""

    def test_version_matches_exact(self):
        """Test version_matches with exact version."""
        assert version_matches("V11.1") is True
        assert version_matches("11.1") is True
        assert version_matches("11.1.0") is True

    def test_version_matches_different(self):
        """Test version_matches with different version."""
        assert version_matches("V11.0") is False
        assert version_matches("V10.0") is False
        assert version_matches("V12.0") is False

    def test_version_matches_invalid(self):
        """Test version_matches with invalid input."""
        assert version_matches("") is False
        assert version_matches("invalid") is False
        assert version_matches("V") is False

    def test_is_at_least_equal(self):
        """Test is_at_least with equal version."""
        assert is_at_least(11, 1, 0) is True

    def test_is_at_least_lower(self):
        """Test is_at_least with lower version."""
        assert is_at_least(11, 0, 0) is True
        assert is_at_least(10, 0, 0) is True
        assert is_at_least(11) is True

    def test_is_at_least_higher(self):
        """Test is_at_least with higher version."""
        assert is_at_least(11, 2, 0) is False
        assert is_at_least(12, 0, 0) is False
        assert is_at_least(12) is False


class TestVersionIntegration:
    """Test version module integration with other modules."""

    def test_version_importable(self):
        """Test version module can be imported by other modules."""
        # This test ensures the version module is importable
        from src.version import get_version

        version = get_version()
        assert version == "V11.1"

    def test_version_consistency(self):
        """Test version consistency across different functions."""
        version_str = get_version()
        version_tuple = get_version_tuple()
        version_dict = get_version_dict()

        # All should represent the same version
        assert version_str == f"V{version_tuple[0]}.{version_tuple[1]}"
        assert version_dict["version"] == version_str
        assert version_dict["major"] == version_tuple[0]
        assert version_dict["minor"] == version_tuple[1]
        assert version_dict["patch"] == version_tuple[2]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
