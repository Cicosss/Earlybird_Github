"""
Comprehensive tests for ModificationType enum and related functionality.

Tests cover:
- ModificationType enum values (ensuring COMBO_MODIFICATION is removed)
- Parser methods for each modification type
- Apply methods for each modification type
- Database validation triggers for modification_type column
- Edge cases and error handling

Created: 2026-03-13
Purpose: Verify ModificationType implementation works correctly after dead code removal
"""

from datetime import datetime, timezone

import pytest

from src.analysis.intelligent_modification_logger import (
    IntelligentModificationLogger,
    ModificationPriority,
    ModificationType,
    SuggestedModification,
)
from src.analysis.step_by_step_feedback import StepByStepFeedbackLoop
from src.database.models import ModificationHistory, NewsLog


class TestModificationTypeEnum:
    """Test ModificationType enum functionality."""

    def test_enum_has_only_valid_values(self):
        """Test that ModificationType has only 4 valid values."""
        valid_types = {
            ModificationType.MARKET_CHANGE,
            ModificationType.SCORE_ADJUSTMENT,
            ModificationType.DATA_CORRECTION,
            ModificationType.REASONING_UPDATE,
        }

        # Get all enum values
        all_types = set(ModificationType)

        # Verify only valid types exist
        assert all_types == valid_types, f"Unexpected enum values: {all_types - valid_types}"

    def test_combo_modification_removed(self):
        """Test that COMBO_MODIFICATION has been removed from enum."""
        with pytest.raises(AttributeError):
            _ = ModificationType.COMBO_MODIFICATION

    def test_enum_values_are_strings(self):
        """Test that all enum values are strings."""
        for mod_type in ModificationType:
            assert isinstance(mod_type.value, str), f"{mod_type} value is not a string"

    def test_enum_values_match_expected(self):
        """Test that enum values match expected strings."""
        assert ModificationType.MARKET_CHANGE.value == "market_change"
        assert ModificationType.SCORE_ADJUSTMENT.value == "score_adjustment"
        assert ModificationType.DATA_CORRECTION.value == "data_correction"
        assert ModificationType.REASONING_UPDATE.value == "reasoning_update"


class TestModificationParserMethods:
    """Test parser methods for each modification type."""

    @pytest.fixture
    def logger(self):
        """Create IntelligentModificationLogger instance."""
        return IntelligentModificationLogger()

    @pytest.fixture
    def sample_verification_result(self):
        """Sample verification result for testing."""
        return {
            "suggested_modifications": "Consider under instead of over market",
            "data_discrepancies": [
                {
                    "field": "home_goals",
                    "impact": "HIGH",
                    "fotmob_value": "2",
                    "intelligence_value": "3",
                    "description": "Goal count mismatch",
                }
            ],
            "confidence_level": "HIGH",
            "key_weaknesses": ["Insufficient injury analysis"],
        }

    @pytest.fixture
    def sample_alert_data(self):
        """Sample alert data for testing."""
        return {
            "recommended_market": "Over 2.5 Goals",
            "score": 8,
            "reasoning": "Original reasoning text",
        }

    def test_parse_market_change_success(
        self, logger, sample_verification_result, sample_alert_data
    ):
        """Test successful parsing of market change modification."""
        result = logger._parse_market_change(
            sample_verification_result["suggested_modifications"],
            sample_alert_data,
            sample_verification_result,
        )

        assert result is not None
        assert result.type == ModificationType.MARKET_CHANGE
        assert result.original_value == "Over 2.5 Goals"
        assert "Under" in result.suggested_value
        assert result.priority == ModificationPriority.HIGH

    def test_parse_market_change_no_pattern(self, logger, sample_alert_data):
        """Test parsing when no market change pattern is found."""
        result = logger._parse_market_change(
            "No market change here", sample_alert_data, {"confidence_level": "HIGH"}
        )

        assert result is None

    def test_parse_score_adjustment_reduce(self, logger, sample_alert_data):
        """Test parsing of score reduction modification."""
        result = logger._parse_score_adjustment(
            "Reduce the score", sample_alert_data, {"confidence_level": "HIGH"}
        )

        assert result is not None
        assert result.type == ModificationType.SCORE_ADJUSTMENT
        assert result.original_value == 8
        assert result.suggested_value == 6  # max(5, 8-2)
        assert result.priority == ModificationPriority.MEDIUM

    def test_parse_score_adjustment_increase(self, logger, sample_alert_data):
        """Test parsing of score increase modification."""
        sample_alert_data["score"] = 5
        result = logger._parse_score_adjustment(
            "Increase the score", sample_alert_data, {"confidence_level": "HIGH"}
        )

        assert result is not None
        assert result.type == ModificationType.SCORE_ADJUSTMENT
        assert result.original_value == 5
        assert result.suggested_value == 6  # min(10, 5+1)

    def test_parse_data_correction_high_impact(
        self, logger, sample_verification_result, sample_alert_data
    ):
        """Test parsing of data correction with HIGH impact."""
        discrepancy = sample_verification_result["data_discrepancies"][0]
        result = logger._parse_data_correction(
            discrepancy, sample_alert_data, sample_verification_result
        )

        assert result is not None
        assert result.type == ModificationType.DATA_CORRECTION
        assert result.original_value == "2"
        assert result.suggested_value == "3"
        assert result.priority == ModificationPriority.CRITICAL
        assert result.confidence == 0.9

    def test_parse_data_correction_low_impact(self, logger, sample_alert_data):
        """Test parsing of data correction with LOW impact."""
        discrepancy = {
            "field": "away_possession",
            "impact": "LOW",
            "fotmob_value": "45%",
            "intelligence_value": "47%",
            "description": "Minor possession difference",
        }
        result = logger._parse_data_correction(
            discrepancy, sample_alert_data, {"confidence_level": "HIGH"}
        )

        assert result is not None
        assert result.type == ModificationType.DATA_CORRECTION
        assert result.priority == ModificationPriority.LOW
        assert result.confidence == 0.6

    def test_parse_data_correction_dict_object(self, logger, sample_alert_data):
        """Test that both dict and object discrepancies are handled."""
        # Test with dict
        discrepancy_dict = {
            "field": "test_field",
            "impact": "MEDIUM",
            "fotmob_value": "val1",
            "intelligence_value": "val2",
            "description": "Test",
        }
        result_dict = logger._parse_data_correction(
            discrepancy_dict, sample_alert_data, {"confidence_level": "HIGH"}
        )
        assert result_dict is not None

        # Test with object-like dict (using getattr)
        class DataDiscrepancy:
            field = "test_field"
            impact = "MEDIUM"
            fotmob_value = "val1"
            intelligence_value = "val2"
            description = "Test"

        result_obj = logger._parse_data_correction(
            DataDiscrepancy(), sample_alert_data, {"confidence_level": "HIGH"}
        )
        assert result_obj is not None

    def test_parse_reasoning_update_success(
        self, logger, sample_verification_result, sample_alert_data
    ):
        """Test successful parsing of reasoning update modification."""
        result = logger._parse_reasoning_update(sample_verification_result, sample_alert_data)

        assert result is not None
        assert result.type == ModificationType.REASONING_UPDATE
        assert result.original_value == "Original reasoning text"
        assert "Insufficient injury analysis" in result.suggested_value
        assert result.priority == ModificationPriority.MEDIUM

    def test_parse_reasoning_update_no_weaknesses(self, logger, sample_alert_data):
        """Test parsing when no key weaknesses are present."""
        result = logger._parse_reasoning_update({"key_weaknesses": []}, sample_alert_data)

        assert result is None


class TestModificationApplyMethods:
    """Test apply methods for each modification type."""

    @pytest.fixture
    def feedback_loop(self):
        """Create StepByStepFeedbackLoop instance."""
        return StepByStepFeedbackLoop()

    @pytest.fixture
    def sample_analysis(self):
        """Create sample NewsLog for testing."""
        analysis = NewsLog()
        analysis.id = 1
        analysis.recommended_market = "Over 2.5 Goals"
        analysis.score = 8
        analysis.reasoning = "Original reasoning"
        return analysis

    @pytest.fixture
    def sample_alert_data(self):
        """Sample alert data for testing."""
        return {
            "recommended_market": "Over 2.5 Goals",
            "score": 8,
            "reasoning": "Original reasoning",
        }

    @pytest.fixture
    def sample_context_data(self):
        """Sample context data for testing."""
        return {}

    def test_apply_market_change(
        self, feedback_loop, sample_analysis, sample_alert_data, sample_context_data
    ):
        """Test applying market change modification."""
        modification = SuggestedModification(
            id="test_market_change",
            type=ModificationType.MARKET_CHANGE,
            priority=ModificationPriority.HIGH,
            original_value="Over 2.5 Goals",
            suggested_value="Under 2.5 Goals",
            reason="Market direction corrected",
            confidence=0.9,
            impact_assessment="HIGH",
            verification_context={},
        )

        result = feedback_loop._apply_market_change(
            modification, sample_analysis, sample_alert_data, sample_context_data
        )

        assert result["success"] is True
        assert sample_analysis.recommended_market == "Under 2.5 Goals"
        assert sample_alert_data["recommended_market"] == "Under 2.5 Goals"
        assert "market_modification" in sample_context_data
        assert "MARKET MODIFIED" in sample_analysis.reasoning

    def test_apply_score_adjustment(
        self, feedback_loop, sample_analysis, sample_alert_data, sample_context_data
    ):
        """Test applying score adjustment modification."""
        modification = SuggestedModification(
            id="test_score_adjust",
            type=ModificationType.SCORE_ADJUSTMENT,
            priority=ModificationPriority.MEDIUM,
            original_value=8,
            suggested_value=6,
            reason="Score reduced based on verification",
            confidence=0.7,
            impact_assessment="MEDIUM",
            verification_context={},
        )

        result = feedback_loop._apply_score_adjustment(
            modification, sample_analysis, sample_alert_data, sample_context_data
        )

        assert result["success"] is True
        assert sample_analysis.score == 6
        assert sample_alert_data["score"] == 6
        assert "score_modification" in sample_context_data

    def test_apply_data_correction(
        self, feedback_loop, sample_analysis, sample_alert_data, sample_context_data
    ):
        """Test applying data correction modification."""
        modification = SuggestedModification(
            id="data_correction_home_goals",
            type=ModificationType.DATA_CORRECTION,
            priority=ModificationPriority.CRITICAL,
            original_value="2",
            suggested_value="3",
            reason="Correct home goals data",
            confidence=0.9,
            impact_assessment="HIGH",
            verification_context={},
        )

        result = feedback_loop._apply_data_correction(
            modification, sample_analysis, sample_alert_data, sample_context_data
        )

        assert result["success"] is True
        assert "corrected_data_correction_home_goals" in sample_context_data
        assert sample_context_data["corrected_data_correction_home_goals"]["original"] == "2"
        assert sample_context_data["corrected_data_correction_home_goals"]["corrected"] == "3"

    def test_apply_reasoning_update(
        self, feedback_loop, sample_analysis, sample_alert_data, sample_context_data
    ):
        """Test applying reasoning update modification."""
        modification = SuggestedModification(
            id="test_reasoning_update",
            type=ModificationType.REASONING_UPDATE,
            priority=ModificationPriority.MEDIUM,
            original_value="Original reasoning",
            suggested_value="Updated reasoning addressing: weakness1, weakness2",
            reason="Reasoning updated based on verifier feedback",
            confidence=0.6,
            impact_assessment="MEDIUM",
            verification_context={},
        )

        result = feedback_loop._apply_reasoning_update(
            modification, sample_analysis, sample_alert_data, sample_context_data
        )

        assert result["success"] is True
        assert sample_analysis.reasoning == "Updated reasoning addressing: weakness1, weakness2"
        assert (
            sample_alert_data["reasoning"] == "Updated reasoning addressing: weakness1, weakness2"
        )

    def test_apply_modification_unknown_type(
        self, feedback_loop, sample_analysis, sample_alert_data, sample_context_data
    ):
        """Test applying modification with unknown type."""
        # Create a mock modification with invalid type
        modification = SuggestedModification(
            id="test_invalid",
            type="invalid_type",  # This will be caught by type checking
            priority=ModificationPriority.MEDIUM,
            original_value="orig",
            suggested_value="new",
            reason="test",
            confidence=0.5,
            impact_assessment="LOW",
            verification_context={},
        )

        result = feedback_loop._apply_modification(
            modification, sample_analysis, sample_alert_data, sample_context_data
        )

        assert result["success"] is False
        assert "error" in result


class TestDatabaseValidationTriggers:
    """Test database validation triggers for modification_type column."""

    def test_valid_modification_type_insert(self, isolated_db_with_triggers):
        """Test that valid modification_type values can be inserted."""
        # Create a test entry with valid modification_type
        mod_history = ModificationHistory(
            alert_id=1,
            match_id="test_match",
            modification_type="market_change",  # Valid value
            original_value="Over",
            suggested_value="Under",
            reason="Test",
            priority="high",
            confidence=0.9,
            impact_assessment="HIGH",
            applied=True,
            success=True,
        )

        try:
            isolated_db_with_triggers.add(mod_history)
            isolated_db_with_triggers.flush()  # Flush to trigger validation without committing
            # If we get here, validation passed
            assert True
        except Exception as e:
            pytest.fail(f"Valid modification_type should not raise error: {e}")
        finally:
            isolated_db_with_triggers.rollback()

    @pytest.mark.parametrize(
        "invalid_type",
        [
            "combo_modification",  # Removed dead code
            "invalid_type",
            "market",
            "score",
            "",
            None,
        ],
    )
    def test_invalid_modification_type_insert(self, isolated_db_with_triggers, invalid_type):
        """Test that invalid modification_type values are rejected by trigger."""
        # Create a test entry with invalid modification_type
        mod_history = ModificationHistory(
            alert_id=1,
            match_id="test_match",
            modification_type=invalid_type,  # Invalid value
            original_value="Over",
            suggested_value="Under",
            reason="Test",
            priority="high",
            confidence=0.9,
            impact_assessment="HIGH",
            applied=True,
            success=True,
        )

        try:
            isolated_db_with_triggers.add(mod_history)
            isolated_db_with_triggers.flush()  # Flush to trigger validation
            pytest.fail(f"Invalid modification_type '{invalid_type}' should raise error")
        except Exception as e:
            # Expected: trigger should reject invalid values
            assert "Invalid modification_type value" in str(e) or "constraint" in str(e).lower()
        finally:
            isolated_db_with_triggers.rollback()

    def test_valid_modification_type_update(self, isolated_db_with_triggers):
        """Test that valid modification_type values can be updated."""
        # Create entry with one valid type
        mod_history = ModificationHistory(
            alert_id=1,
            match_id="test_match",
            modification_type="market_change",
            original_value="Over",
            suggested_value="Under",
            reason="Test",
            priority="high",
            confidence=0.9,
            impact_assessment="HIGH",
            applied=True,
            success=True,
        )

        try:
            isolated_db_with_triggers.add(mod_history)
            isolated_db_with_triggers.flush()

            # Update to another valid type
            mod_history.modification_type = "score_adjustment"
            isolated_db_with_triggers.flush()

            # If we get here, validation passed
            assert True
        except Exception as e:
            pytest.fail(f"Valid modification_type update should not raise error: {e}")
        finally:
            isolated_db_with_triggers.rollback()

    def test_invalid_modification_type_update(self, isolated_db_with_triggers):
        """Test that invalid modification_type values are rejected on update."""
        # Create entry with valid type
        mod_history = ModificationHistory(
            alert_id=1,
            match_id="test_match",
            modification_type="market_change",
            original_value="Over",
            suggested_value="Under",
            reason="Test",
            priority="high",
            confidence=0.9,
            impact_assessment="HIGH",
            applied=True,
            success=True,
        )

        try:
            isolated_db_with_triggers.add(mod_history)
            isolated_db_with_triggers.flush()

            # Try to update to invalid type
            mod_history.modification_type = "combo_modification"
            isolated_db_with_triggers.flush()

            pytest.fail("Invalid modification_type update should raise error")
        except Exception as e:
            # Expected: trigger should reject invalid values
            assert "Invalid modification_type value" in str(e) or "constraint" in str(e).lower()
        finally:
            isolated_db_with_triggers.rollback()


class TestSuggestedModificationDataclass:
    """Test SuggestedModification dataclass functionality."""

    def test_initialization(self):
        """Test basic SuggestedModification initialization."""
        mod = SuggestedModification(
            id="test_id",
            type=ModificationType.MARKET_CHANGE,
            priority=ModificationPriority.HIGH,
            original_value="Over",
            suggested_value="Under",
            reason="Test reason",
            confidence=0.9,
            impact_assessment="HIGH",
            verification_context={"test": "data"},
        )

        assert mod.id == "test_id"
        assert mod.type == ModificationType.MARKET_CHANGE
        assert mod.priority == ModificationPriority.HIGH
        assert mod.original_value == "Over"
        assert mod.suggested_value == "Under"
        assert mod.reason == "Test reason"
        assert mod.confidence == 0.9
        assert mod.impact_assessment == "HIGH"
        assert mod.verification_context == {"test": "data"}
        assert isinstance(mod.timestamp, datetime)

    def test_timestamp_defaults_to_utc(self):
        """Test that timestamp defaults to UTC timezone."""
        mod = SuggestedModification(
            id="test_id",
            type=ModificationType.MARKET_CHANGE,
            priority=ModificationPriority.HIGH,
            original_value="Over",
            suggested_value="Under",
            reason="Test",
            confidence=0.9,
            impact_assessment="HIGH",
            verification_context={},
        )

        assert mod.timestamp.tzinfo == timezone.utc


class TestModificationPriorityEnum:
    """Test ModificationPriority enum functionality."""

    def test_enum_values(self):
        """Test that ModificationPriority has all expected values."""
        expected_values = {
            ModificationPriority.CRITICAL,
            ModificationPriority.HIGH,
            ModificationPriority.MEDIUM,
            ModificationPriority.LOW,
        }
        assert set(ModificationPriority) == expected_values

    def test_enum_values_are_strings(self):
        """Test that all enum values are strings."""
        for priority in ModificationPriority:
            assert isinstance(priority.value, str)

    def test_enum_values_match_expected(self):
        """Test that enum values match expected strings."""
        assert ModificationPriority.CRITICAL.value == "critical"
        assert ModificationPriority.HIGH.value == "high"
        assert ModificationPriority.MEDIUM.value == "medium"
        assert ModificationPriority.LOW.value == "low"
