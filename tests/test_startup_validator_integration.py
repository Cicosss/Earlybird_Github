#!/usr/bin/env python3
"""
Test Suite for Startup Validator Integration

Verifies that is_feature_disabled() is correctly integrated across all modules
that use optional features.

V1.0: Initial test suite for intelligent feature detection

Run with: python -m pytest tests/test_startup_validator_integration.py -v
"""

import os
import sys
from unittest.mock import patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestStartupValidatorFeatureDetection:
    """Test that is_feature_disabled is correctly integrated."""

    def test_startup_validator_exports_is_feature_disabled(self):
        """Verify that is_feature_disabled is exported from startup_validator."""
        from src.utils.startup_validator import is_feature_disabled

        assert callable(is_feature_disabled)

    def test_startup_validator_exports_get_validation_report(self):
        """Verify that get_validation_report is exported from startup_validator."""
        from src.utils.startup_validator import get_validation_report

        assert callable(get_validation_report)

    def test_is_feature_disabled_returns_false_when_no_report(self):
        """Test that is_feature_disabled returns False when no validation has run."""
        # Reset global report
        import src.utils.startup_validator as validator_module
        from src.utils.startup_validator import is_feature_disabled

        validator_module._global_validation_report = None

        result = is_feature_disabled("telegram_monitor")
        assert result is False

    def test_is_feature_disabled_returns_true_when_feature_disabled(self):
        """Test that is_feature_disabled returns True when feature is in disabled_features."""
        import src.utils.startup_validator as validator_module
        from src.utils.startup_validator import (
            StartupValidationReport,
            ValidationStatus,
            is_feature_disabled,
        )

        # Create a mock report with disabled features
        mock_report = StartupValidationReport(
            critical_results=[],
            optional_results=[],
            overall_status=ValidationStatus.READY,
            summary="Test",
            api_connectivity_results=[],
            config_file_results=[],
            disabled_features={"telegram_monitor", "perplexity_fallback"},
            timestamp="2024-01-01 00:00:00 UTC",
        )

        # Set global report
        validator_module._global_validation_report = mock_report

        # Test
        assert is_feature_disabled("telegram_monitor") is True
        assert is_feature_disabled("perplexity_fallback") is True
        assert is_feature_disabled("tavily_enrichment") is False

        # Cleanup
        validator_module._global_validation_report = None


class TestIntelligenceRouterIntegration:
    """Test that IntelligenceRouter correctly uses is_feature_disabled."""

    def test_intelligence_router_imports_is_feature_disabled(self):
        """Verify that intelligence_router imports is_feature_disabled."""
        from src.services import intelligence_router

        assert hasattr(intelligence_router, "is_feature_disabled")
        assert hasattr(intelligence_router, "_STARTUP_VALIDATOR_AVAILABLE")

    @patch("src.services.intelligence_router._STARTUP_VALIDATOR_AVAILABLE", True)
    @patch("src.services.intelligence_router.is_feature_disabled")
    def test_tavily_enrich_match_respects_disabled_feature(self, mock_is_disabled):
        """Test that _tavily_enrich_match skips when tavily_enrichment is disabled."""
        mock_is_disabled.return_value = True

        from src.services.intelligence_router import IntelligenceRouter

        router = IntelligenceRouter()

        # Call _tavily_enrich_match
        result = router._tavily_enrich_match("Home", "Away", "2024-01-01", "League")

        # Should return None when disabled
        assert result is None
        mock_is_disabled.assert_called_with("tavily_enrichment")


class TestVerificationLayerIntegration:
    """Test that VerificationLayer correctly uses is_feature_disabled."""

    def test_verification_layer_imports_is_feature_disabled(self):
        """Verify that verification_layer imports is_feature_disabled."""
        from src.analysis import verification_layer

        assert hasattr(verification_layer, "is_feature_disabled")
        assert hasattr(verification_layer, "_STARTUP_VALIDATOR_AVAILABLE")


class TestPlayerIntelIntegration:
    """Test that player_intel correctly uses is_feature_disabled."""

    def test_player_intel_imports_is_feature_disabled(self):
        """Verify that player_intel imports is_feature_disabled."""
        from src.analysis import player_intel

        assert hasattr(player_intel, "is_feature_disabled")
        assert hasattr(player_intel, "_STARTUP_VALIDATOR_AVAILABLE")


class TestTelegramListenerIntegration:
    """Test that telegram_listener correctly uses is_feature_disabled."""

    def test_telegram_listener_imports_is_feature_disabled(self):
        """Verify that telegram_listener imports is_feature_disabled."""
        from src.processing import telegram_listener

        assert hasattr(telegram_listener, "is_feature_disabled")
        assert hasattr(telegram_listener, "_STARTUP_VALIDATOR_AVAILABLE")


class TestTelegramMonitorIntegration:
    """Test that run_telegram_monitor correctly uses is_feature_disabled."""

    def test_telegram_monitor_imports_is_feature_disabled(self):
        """Verify that run_telegram_monitor imports is_feature_disabled."""
        # This is a script, so we need to check the source
        import run_telegram_monitor

        assert hasattr(run_telegram_monitor, "is_feature_disabled")
        assert hasattr(run_telegram_monitor, "_STARTUP_VALIDATOR_AVAILABLE")


class TestFeatureFlagConstants:
    """Test that all feature flags are consistently defined."""

    def test_optional_keys_disable_features_exist(self):
        """Verify that all OPTIONAL_KEYS have corresponding disable_feature values."""
        from src.utils.startup_validator import StartupValidator

        validator = StartupValidator()

        # Get all disable_feature values
        disable_features = set()
        for key, config in validator.OPTIONAL_KEYS.items():
            if "disable_feature" in config:
                disable_features.add(config["disable_feature"])

        # Expected features based on OPTIONAL_KEYS
        expected_features = {
            "telegram_monitor",  # TELEGRAM_API_ID + TELEGRAM_API_HASH
            "perplexity_fallback",  # PERPLEXITY_API_KEY
            "player_intelligence",  # API_FOOTBALL_KEY
            "tavily_enrichment",  # TAVILY_API_KEY
        }

        assert expected_features == disable_features


class TestStartupValidationReport:
    """Test StartupValidationReport dataclass."""

    def test_startup_validation_report_has_disabled_features(self):
        """Verify that StartupValidationReport has disabled_features field."""
        from src.utils.startup_validator import (
            StartupValidationReport,
            ValidationStatus,
        )

        report = StartupValidationReport(
            critical_results=[],
            optional_results=[],
            overall_status=ValidationStatus.READY,
            summary="Test",
            api_connectivity_results=[],
            config_file_results=[],
            disabled_features={"test_feature"},
            timestamp="2024-01-01 00:00:00 UTC",
        )

        assert hasattr(report, "disabled_features")
        assert isinstance(report.disabled_features, set)
        assert "test_feature" in report.disabled_features


class TestConfigFileValidationResult:
    """Test ConfigFileValidationResult dataclass."""

    def test_config_file_validation_result_structure(self):
        """Verify ConfigFileValidationResult has correct fields."""
        from src.utils.startup_validator import (
            ConfigFileValidationResult,
            ValidationStatus,
        )

        result = ConfigFileValidationResult(
            file_path=".env",
            status=ValidationStatus.READY,
            file_size_bytes=1000,
            last_modified="2024-01-01 00:00:00",
            error_message=None,
        )

        assert result.file_path == ".env"
        assert result.status == ValidationStatus.READY
        assert result.file_size_bytes == 1000
        assert result.last_modified == "2024-01-01 00:00:00"
        assert result.error_message is None

    def test_config_file_validation_result_with_error(self):
        """Verify ConfigFileValidationResult handles errors correctly."""
        from src.utils.startup_validator import (
            ConfigFileValidationResult,
            ValidationStatus,
        )

        result = ConfigFileValidationResult(
            file_path="config/missing.json",
            status=ValidationStatus.FAIL,
            file_size_bytes=0,
            last_modified=None,
            error_message="File not found",
        )

        assert result.status == ValidationStatus.FAIL
        assert result.error_message == "File not found"
        assert result.file_size_bytes == 0
        assert result.last_modified is None

    def test_config_file_validation_result_warn_status(self):
        """Verify ConfigFileValidationResult handles WARN status correctly."""
        from src.utils.startup_validator import (
            ConfigFileValidationResult,
            ValidationStatus,
        )

        result = ConfigFileValidationResult(
            file_path="config/small_file.json",
            status=ValidationStatus.WARN,
            file_size_bytes=50,
            last_modified="2024-01-01 00:00:00",
            error_message="File size below minimum threshold",
        )

        assert result.status == ValidationStatus.WARN
        assert result.file_size_bytes == 50
        assert "threshold" in result.error_message

    def test_config_file_validation_result_all_statuses(self):
        """Verify ConfigFileValidationResult works with all ValidationStatus values."""
        from src.utils.startup_validator import (
            ConfigFileValidationResult,
            ValidationStatus,
        )

        # Test all three statuses
        for status in [ValidationStatus.READY, ValidationStatus.FAIL, ValidationStatus.WARN]:
            result = ConfigFileValidationResult(
                file_path="test.json",
                status=status,
                file_size_bytes=100,
                last_modified=None,
                error_message=None,
            )
            assert result.status == status


class TestAPIConnectivityResult:
    """Test APIConnectivityResult dataclass."""

    def test_api_connectivity_result_structure(self):
        """Verify APIConnectivityResult has correct fields."""
        from src.utils.startup_validator import (
            APIConnectivityResult,
            ValidationStatus,
        )

        result = APIConnectivityResult(
            api_name="Test API",
            status=ValidationStatus.READY,
            response_time_ms=100.0,
            quota_info="100 remaining",
            error_message=None,
        )

        assert result.api_name == "Test API"
        assert result.status == ValidationStatus.READY
        assert result.response_time_ms == 100.0
        assert result.quota_info == "100 remaining"
        assert result.error_message is None

    def test_api_connectivity_result_with_error(self):
        """Verify APIConnectivityResult handles errors correctly."""
        from src.utils.startup_validator import (
            APIConnectivityResult,
            ValidationStatus,
        )

        result = APIConnectivityResult(
            api_name="Test API",
            status=ValidationStatus.FAIL,
            response_time_ms=None,
            quota_info=None,
            error_message="Connection refused",
        )

        assert result.status == ValidationStatus.FAIL
        assert result.error_message == "Connection refused"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
