"""
Test suite for Perplexity Structured Outputs V1.0

Tests Pydantic models and parsing logic for Deep Dive and Betting Stats schemas.
Validates that new structured outputs work correctly and handle edge cases.

V1.0: Initial test suite for DeepDiveResponse and BettingStatsResponse models.
"""

import pytest
from pydantic import ValidationError

from src.schemas.perplexity_schemas import (
    BETTING_STATS_JSON_SCHEMA,
    DEEP_DIVE_JSON_SCHEMA,
    BettingStatsResponse,
    DeepDiveResponse,
)


class TestDeepDiveResponse:
    """Test suite for DeepDiveResponse Pydantic model."""

    def test_valid_deep_dive_response(self):
        """Test that a valid Deep Dive response passes validation."""
        valid_data = {
            "internal_crisis": "Low - No internal issues reported",
            "turnover_risk": "Medium - Manager may rotate for Cup match",
            "referee_intel": "Strict - Avg 3.8 yellow cards per game",
            "biscotto_potential": "No - Both teams need win for title race",
            "injury_impact": "Manageable - Missing bench player, adequate replacements",
            "btts_impact": "Neutral - No key defensive or attacking absences",
            "motivation_home": "High - Title race, 3 points behind leaders",
            "motivation_away": "Medium - European spots still achievable",
            "table_context": "2nd vs 5th, 6 points gap",
        }

        response = DeepDiveResponse(**valid_data)
        assert response.internal_crisis == "Low - No internal issues reported"
        assert response.turnover_risk == "Medium - Manager may rotate for Cup match"
        assert response.referee_intel == "Strict - Avg 3.8 yellow cards per game"
        assert response.biscotto_potential == "No - Both teams need win for title race"
        assert response.injury_impact == "Manageable - Missing bench player, adequate replacements"
        assert response.btts_impact == "Neutral - No key defensive or attacking absences"
        assert response.motivation_home == "High - Title race, 3 points behind leaders"
        assert response.motivation_away == "Medium - European spots still achievable"
        assert response.table_context == "2nd vs 5th, 6 points gap"

    def test_invalid_risk_levels(self):
        """Test that invalid risk levels raise ValidationError."""
        invalid_data = {
            "internal_crisis": "Invalid - Some explanation",  # Should start with High/Medium/Low/Unknown
            "turnover_risk": "Medium - Valid explanation",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "Neutral - Valid",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        with pytest.raises(ValidationError) as exc_info:
            DeepDiveResponse(**invalid_data)

        assert "internal_crisis" in str(exc_info.value)
        # Pydantic V2 uses commas in enum listing
        assert "High, Medium, Low, Unknown" in str(exc_info.value)

    def test_invalid_referee_strictness(self):
        """Test that invalid referee strictness raises ValidationError."""
        invalid_data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Invalid - Should start with Strict/Lenient/Unknown",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "Neutral - Valid",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        with pytest.raises(ValidationError) as exc_info:
            DeepDiveResponse(**invalid_data)

        assert "referee_intel" in str(exc_info.value)
        # Pydantic V2 uses commas
        assert "Strict, Medium, Lenient, Unknown" in str(exc_info.value)

    def test_invalid_biscotto_potential(self):
        """Test that invalid biscotto potential raises ValidationError."""
        invalid_data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "Invalid - Should start with Yes/No/Unknown",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "Neutral - Valid",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        with pytest.raises(ValidationError) as exc_info:
            DeepDiveResponse(**invalid_data)

        assert "biscotto_potential" in str(exc_info.value)
        # Pydantic V2 uses commas
        assert "Yes, No, Unknown" in str(exc_info.value)

    def test_json_schema_structure(self):
        """Test that JSON schema is properly generated."""
        schema = DEEP_DIVE_JSON_SCHEMA

        assert "properties" in schema
        assert "internal_crisis" in schema["properties"]
        assert "turnover_risk" in schema["properties"]
        assert "referee_intel" in schema["properties"]
        assert "biscotto_potential" in schema["properties"]
        assert "injury_impact" in schema["properties"]
        assert "btts_impact" in schema["properties"]
        assert "motivation_home" in schema["properties"]
        assert "motivation_away" in schema["properties"]
        assert "table_context" in schema["properties"]

        # Check field types
        assert schema["properties"]["internal_crisis"]["type"] == "string"
        assert schema["properties"]["turnover_risk"]["type"] == "string"


class TestBettingStatsResponse:
    """Test suite for BettingStatsResponse Pydantic model."""

    def test_valid_betting_stats_response(self):
        """Test that a valid Betting Stats response passes validation."""
        valid_data = {
            "home_form_wins": 3,
            "home_form_draws": 1,
            "home_form_losses": 1,
            "home_goals_scored_last5": 8,
            "home_goals_conceded_last5": 4,
            "away_form_wins": 2,
            "away_form_draws": 2,
            "away_form_losses": 1,
            "away_goals_scored_last5": 6,
            "away_goals_conceded_last5": 5,
            "home_corners_avg": 5.2,
            "away_corners_avg": 4.1,
            "corners_total_avg": 9.3,
            "corners_signal": "High",
            "corners_reasoning": "Home team attacks wide, high crossing volume",
            "referee_name": "Maurizio Mariani",
            "referee_cards_avg": 4.2,
            "referee_strictness": "Medium",
            "match_intensity": "High",
            "is_derby": False,
            "recommended_corner_line": "Over 9.5 Corners",
            "data_confidence": "High",
            "sources_found": "Serie A official stats, SofaScore",
        }

        response = BettingStatsResponse(**valid_data)
        assert response.home_form_wins == 3
        assert response.home_corners_avg == 5.2
        assert response.corners_signal == "High"
        assert response.referee_strictness == "Medium"
        assert response.match_intensity == "High"
        assert response.is_derby is False
        assert response.data_confidence == "High"

    def test_optional_fields_null(self):
        """Test that optional fields can be null."""
        data_with_nulls = {
            "home_form_wins": None,
            "home_corners_avg": None,
            "referee_cards_avg": None,
            "corners_signal": "Unknown",
            "referee_strictness": "Unknown",
            "match_intensity": "Unknown",
            "is_derby": False,
            "recommended_corner_line": "No bet",
            "data_confidence": "Low",
            "sources_found": "",
        }

        response = BettingStatsResponse(**data_with_nulls)
        assert response.home_form_wins is None
        assert response.home_corners_avg is None
        assert response.referee_cards_avg is None
        assert response.corners_signal == "Unknown"
        assert response.data_confidence == "Low"

    def test_invalid_form_values(self):
        """Test that invalid form values raise ValidationError."""
        invalid_data = {
            "home_form_wins": 6,  # Should be 0-5
            "home_form_draws": 1,
            "home_form_losses": 1,
            "corners_signal": "High",
            "referee_strictness": "Medium",
            "match_intensity": "High",
            "is_derby": False,
            "recommended_corner_line": "No bet",
            "data_confidence": "High",
            "sources_found": "Test",
        }

        with pytest.raises(ValidationError) as exc_info:
            BettingStatsResponse(**invalid_data)

        assert "home_form_wins" in str(exc_info.value)

    def test_negative_values(self):
        """Test that negative values raise ValidationError."""
        invalid_data = {
            "home_form_wins": -1,  # Should be >= 0
            "home_corners_avg": -2.0,  # Should be >= 0
            "corners_signal": "High",
            "cards_signal": "Medium",
            "referee_strictness": "Medium",
            "match_intensity": "High",
            "is_derby": False,
            "recommended_corner_line": "No bet",
            "recommended_cards_line": "No bet",
            "data_confidence": "High",
            "sources_found": "Test",
        }

        with pytest.raises(ValidationError) as exc_info:
            BettingStatsResponse(**invalid_data)

        # Should catch both negative values
        error_msg = str(exc_info.value)
        assert "home_form_wins" in error_msg or "home_corners_avg" in error_msg

    def test_enum_validation(self):
        """Test that enum fields validate correctly."""
        invalid_data = {
            "corners_signal": "InvalidSignal",  # Should be High/Medium/Low/Unknown
            "referee_strictness": "Medium",
            "match_intensity": "High",
            "is_derby": False,
            "recommended_corner_line": "No bet",
            "data_confidence": "High",
            "sources_found": "Test",
        }

        # V8.3: Pydantic V2 is strict by default for Enums.
        # Unless a pre-validator is added, this raises ValidationError.
        # Updating test to match current strict behavior.
        with pytest.raises(ValidationError) as exc_info:
            BettingStatsResponse(**invalid_data)

        assert "corners_signal" in str(exc_info.value)

    def test_json_schema_structure(self):
        """Test that JSON schema is properly generated."""
        schema = BETTING_STATS_JSON_SCHEMA

        assert "properties" in schema
        assert "home_form_wins" in schema["properties"]
        assert "home_corners_avg" in schema["properties"]
        assert "corners_signal" in schema["properties"]
        assert "referee_strictness" in schema["properties"]
        assert "match_intensity" in schema["properties"]
        assert "is_derby" in schema["properties"]
        assert "data_confidence" in schema["properties"]

        # Check field existence (types can be complex in V2, e.g. anyOf)
        assert "home_form_wins" in schema["properties"]
        assert "home_corners_avg" in schema["properties"]
        assert "is_derby" in schema["properties"]


class TestModelIntegration:
    """Integration tests for the complete structured outputs system."""

    def test_deep_dive_serialization_roundtrip(self):
        """Test that DeepDiveResponse can serialize and deserialize correctly."""
        original_data = {
            "internal_crisis": "Low - No issues",
            "turnover_risk": "Medium - Rotation possible",
            "referee_intel": "Strict - 3.8 cards avg",
            "biscotto_potential": "No - Competitive match",
            "injury_impact": "Critical - Key striker out",
            "btts_impact": "Negative - Missing goalscorer",
            "motivation_home": "High - Title race",
            "motivation_away": "Medium - European spot",
            "table_context": "1st vs 4th, 8 points gap",
        }

        # Create model
        response = DeepDiveResponse(**original_data)

        # Serialize to dict
        serialized = response.model_dump()

        # Create new model from serialized data
        response2 = DeepDiveResponse(**serialized)

        # Should be identical
        assert response.internal_crisis == response2.internal_crisis
        assert response.turnover_risk == response2.turnover_risk
        assert response.injury_impact == response2.injury_impact

    def test_betting_stats_serialization_roundtrip(self):
        """Test that BettingStatsResponse can serialize and deserialize correctly."""
        original_data = {
            "home_form_wins": 3,
            "home_form_draws": 1,
            "home_form_losses": 1,
            "home_corners_avg": 5.5,
            "corners_signal": "High",
            "referee_strictness": "Strict",
            "match_intensity": "High",
            "is_derby": True,
            "data_confidence": "Medium",
        }

        # Create model
        response = BettingStatsResponse(**original_data)

        # Serialize to dict
        serialized = response.model_dump()

        # Create new model from serialized data
        response2 = BettingStatsResponse(**serialized)

        # Should be identical
        assert response.home_form_wins == response2.home_form_wins
        assert response.corners_signal == response2.corners_signal
        assert response.is_derby == response2.is_derby

    def test_json_serialization_compatibility(self):
        """Test that models can serialize to JSON and back."""
        import json

        # Test DeepDiveResponse
        deep_dive_data = {
            "internal_crisis": "Low - Stable",
            "turnover_risk": "Low - No rotation",
            "referee_intel": "Lenient - 2.1 cards avg",
            "biscotto_potential": "Unknown - Unclear motives",
            "injury_impact": "Unknown - None reported",  # Must start with valid Enum value
            "btts_impact": "Neutral - Full squads",
            "motivation_home": "Medium - Safe position",
            "motivation_away": "Medium - Safe position",
            "table_context": "8th vs 10th, mid-table",
        }

        deep_dive = DeepDiveResponse(**deep_dive_data)
        deep_dive_json = deep_dive.model_dump_json()

        # Parse back from JSON
        parsed_data = json.loads(deep_dive_json)
        deep_dive_restored = DeepDiveResponse(**parsed_data)

        assert deep_dive.internal_crisis == deep_dive_restored.internal_crisis

        # Test BettingStatsResponse
        betting_data = {
            "corners_signal": "Low",
            "referee_strictness": "Lenient",
            "match_intensity": "Low",
            "is_derby": False,
            "data_confidence": "Low",
        }

        betting = BettingStatsResponse(**betting_data)
        betting_json = betting.model_dump_json()

        # Parse back from JSON
        parsed_betting = json.loads(betting_json)
        betting_restored = BettingStatsResponse(**parsed_betting)

        assert betting.corners_signal == betting_restored.corners_signal


class TestCaseSensitivityFixes:
    """Test suite for case-sensitivity fixes (COVE Double Verification)."""

    def test_risk_levels_case_insensitive(self):
        """Test that risk levels are case-insensitive."""
        # Test lowercase
        data_lower = {
            "internal_crisis": "high - Player unrest",
            "turnover_risk": "medium - Squad rotation",
            "referee_intel": "strict - High card rate",
            "biscotto_potential": "no - Both need win",
            "injury_impact": "manageable - Minor injuries",
            "btts_impact": "positive - Attacking matchup",
            "motivation_home": "high - Title race",
            "motivation_away": "low - Safe from relegation",
            "table_context": "Valid context",
        }

        response = DeepDiveResponse(**data_lower)
        # Should normalize to proper case
        assert response.internal_crisis == "High - Player unrest"
        assert response.turnover_risk == "Medium - Squad rotation"
        assert response.referee_intel == "Strict - High card rate"
        assert response.biscotto_potential == "No - Both need win"
        assert response.injury_impact == "Manageable - Minor injuries"
        assert response.btts_impact == "Positive - Attacking matchup"
        assert response.motivation_home == "High - Title race"
        assert response.motivation_away == "Low - Safe from relegation"

    def test_risk_levels_uppercase(self):
        """Test that risk levels work with uppercase."""
        data_upper = {
            "internal_crisis": "HIGH - Crisis",
            "turnover_risk": "MEDIUM - Risk",
            "referee_intel": "STRICT - Strict",
            "biscotto_potential": "YES - Yes",
            "injury_impact": "CRITICAL - Critical",
            "btts_impact": "NEGATIVE - Negative",
            "motivation_home": "HIGH - High",
            "motivation_away": "MEDIUM - Medium",
            "table_context": "Valid",
        }

        response = DeepDiveResponse(**data_upper)
        # Should normalize to proper case
        assert response.internal_crisis == "High - Crisis"
        assert response.turnover_risk == "Medium - Risk"
        assert response.referee_intel == "Strict - Strict"
        assert response.biscotto_potential == "Yes - Yes"
        assert response.injury_impact == "Critical - Critical"
        assert response.btts_impact == "Negative - Negative"
        assert response.motivation_home == "High - High"
        assert response.motivation_away == "Medium - Medium"

    def test_risk_levels_mixed_case(self):
        """Test that risk levels work with mixed case."""
        data_mixed = {
            "internal_crisis": "HiGh - Mixed case",
            "turnover_risk": "MeDiUm - Mixed",
            "referee_intel": "StRiCt - Mixed",
            "biscotto_potential": "UnKnOwN - Unknown",
            "injury_impact": "MaNaGeAbLe - Mixed",
            "btts_impact": "NeUtRaL - Mixed",
            "motivation_home": "LoW - Mixed",
            "motivation_away": "UnKnOwN - Unknown",
            "table_context": "Valid",
        }

        response = DeepDiveResponse(**data_mixed)
        # Should normalize to proper case
        assert response.internal_crisis == "High - Mixed case"
        assert response.turnover_risk == "Medium - Mixed"
        assert response.referee_intel == "Strict - Mixed"
        assert response.biscotto_potential == "Unknown - Unknown"
        assert response.injury_impact == "Manageable - Mixed"
        assert response.btts_impact == "Neutral - Mixed"
        assert response.motivation_home == "Low - Mixed"
        assert response.motivation_away == "Unknown - Unknown"

    def test_unknown_with_explanation(self):
        """Test that 'Unknown' with explanation works correctly."""
        data = {
            "internal_crisis": "Unknown - No data available",
            "turnover_risk": "Unknown - Insufficient info",
            "referee_intel": "Unknown - New referee",
            "biscotto_potential": "Unknown - Uncertain",
            "injury_impact": "Unknown - No injury report",
            "btts_impact": "Unknown - No tactical data",
            "motivation_home": "Unknown - Early season",
            "motivation_away": "Unknown - Unclear stakes",
            "table_context": "Valid context",
        }

        response = DeepDiveResponse(**data)
        assert response.internal_crisis == "Unknown - No data available"
        assert response.turnover_risk == "Unknown - Insufficient info"
        assert response.referee_intel == "Unknown - New referee"
        assert response.biscotto_potential == "Unknown - Uncertain"
        assert response.injury_impact == "Unknown - No injury report"
        assert response.btts_impact == "Unknown - No tactical data"
        assert response.motivation_home == "Unknown - Early season"
        assert response.motivation_away == "Unknown - Unclear stakes"


class TestFormatForPrompt:
    """Test suite for format_for_prompt case-sensitivity fixes."""

    def test_format_for_prompt_ignores_lowercase_unknown(self):
        """Test that format_for_prompt ignores lowercase 'unknown' values."""
        from src.ingestion.deepseek_intel_provider import DeepSeekIntelProvider

        provider = DeepSeekIntelProvider()

        # Test with lowercase 'unknown'
        deep_dive = {
            "internal_crisis": "unknown - No data",
            "turnover_risk": "High - Risk",
            "referee_intel": "unknown - No referee data",
            "biscotto_potential": "No - No biscotto",
            "injury_impact": "Critical - Key injuries",
            "btts_impact": "unknown - No data",
            "motivation_home": "High - Motivated",
            "motivation_away": "unknown - No data",
            "table_context": "Valid",
        }

        formatted = provider.format_for_prompt(deep_dive)

        # Should not include 'unknown' fields
        assert "INTERNAL CRISIS" not in formatted
        assert "REFEREE" not in formatted
        assert "BTTS TACTICAL" not in formatted
        assert "MOTIVATION AWAY" not in formatted

        # Should include non-unknown fields
        assert "TURNOVER RISK" in formatted
        assert "BISCOTTO" in formatted
        assert "INJURY IMPACT" in formatted
        assert "MOTIVATION HOME" in formatted
        assert "TABLE" in formatted

    def test_format_for_prompt_ignores_uppercase_unknown(self):
        """Test that format_for_prompt ignores uppercase 'Unknown' values."""
        from src.ingestion.deepseek_intel_provider import DeepSeekIntelProvider

        provider = DeepSeekIntelProvider()

        deep_dive = {
            "internal_crisis": "Unknown - No data",
            "turnover_risk": "High - Risk",
            "referee_intel": "Unknown - No referee data",
            "biscotto_potential": "No - No biscotto",
            "injury_impact": "Critical - Key injuries",
            "btts_impact": "Unknown - No data",
            "motivation_home": "High - Motivated",
            "motivation_away": "Unknown - No data",
            "table_context": "Valid",
        }

        formatted = provider.format_for_prompt(deep_dive)

        # Should not include 'Unknown' fields
        assert "INTERNAL CRISIS" not in formatted
        assert "REFEREE" not in formatted
        assert "BTTS TACTICAL" not in formatted
        assert "MOTIVATION AWAY" not in formatted

        # Should include non-unknown fields
        assert "TURNOVER RISK" in formatted
        assert "BISCOTTO" in formatted
        assert "INJURY IMPACT" in formatted
        assert "MOTIVATION HOME" in formatted
        assert "TABLE" in formatted


class TestNormalizeDeepDiveResponse:
    """Test suite for normalize_deep_dive_response normalization."""

    def test_normalize_lowercase_values(self):
        """Test that normalize_deep_dive_response normalizes lowercase values."""
        from src.utils.ai_parser import normalize_deep_dive_response

        data = {
            "internal_crisis": "high - Crisis",
            "turnover_risk": "medium - Risk",
            "referee_intel": "strict - Strict",
            "biscotto_potential": "no - No",
            "injury_impact": "manageable - Manageable",
            "btts_impact": "positive - Positive",
            "motivation_home": "high - High",
            "motivation_away": "low - Low",
            "table_context": "Valid",
        }

        normalized = normalize_deep_dive_response(data)

        # Should normalize to proper case
        assert normalized["internal_crisis"] == "High - Crisis"
        assert normalized["turnover_risk"] == "Medium - Risk"
        assert normalized["referee_intel"] == "Strict - Strict"
        assert normalized["biscotto_potential"] == "No - No"
        assert normalized["injury_impact"] == "Manageable - Manageable"
        assert normalized["btts_impact"] == "Positive - Positive"
        assert normalized["motivation_home"] == "High - High"
        assert normalized["motivation_away"] == "Low - Low"
        assert normalized["table_context"] == "Valid"

    def test_normalize_handles_none_input(self):
        """Test that normalize_deep_dive_response handles None input."""
        from src.utils.ai_parser import normalize_deep_dive_response

        result = normalize_deep_dive_response(None)
        assert result == {}

    def test_normalize_handles_empty_dict(self):
        """Test that normalize_deep_dive_response handles empty dict."""
        from src.utils.ai_parser import normalize_deep_dive_response

        result = normalize_deep_dive_response({})
        assert result == {}

    def test_normalize_provides_defaults(self):
        """Test that normalize_deep_dive_response provides defaults for missing fields."""
        from src.utils.ai_parser import normalize_deep_dive_response

        data = {"internal_crisis": "High - Crisis"}
        normalized = normalize_deep_dive_response(data)

        # Should provide defaults for missing fields
        assert normalized["internal_crisis"] == "High - Crisis"
        assert normalized["turnover_risk"] == "Unknown"
        assert normalized["referee_intel"] == "Unknown"
        assert normalized["biscotto_potential"] == "Unknown"
        assert normalized["injury_impact"] == "None reported"
        assert normalized["btts_impact"] == "Unknown"
        assert normalized["motivation_home"] == "Unknown"
        assert normalized["motivation_away"] == "Unknown"
        assert normalized["table_context"] == "Unknown"


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
