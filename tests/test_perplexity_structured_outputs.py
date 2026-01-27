"""
Test suite for Perplexity Structured Outputs V1.0

Tests Pydantic models and parsing logic for Deep Dive and Betting Stats schemas.
Validates that new structured outputs work correctly and handle edge cases.

V1.0: Initial test suite for DeepDiveResponse and BettingStatsResponse models.
"""
import pytest
from pydantic import ValidationError

from src.schemas.perplexity_schemas import (
    DeepDiveResponse,
    BettingStatsResponse,
    DEEP_DIVE_JSON_SCHEMA,
    BETTING_STATS_JSON_SCHEMA
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
            "table_context": "2nd vs 5th, 6 points gap"
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
            "table_context": "Valid context"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            DeepDiveResponse(**invalid_data)
        
        assert "internal_crisis" in str(exc_info.value)
        assert "High/Medium/Low/Unknown" in str(exc_info.value)
    
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
            "table_context": "Valid context"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            DeepDiveResponse(**invalid_data)
        
        assert "referee_intel" in str(exc_info.value)
        assert "Strict/Lenient/Unknown" in str(exc_info.value)
    
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
            "table_context": "Valid context"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            DeepDiveResponse(**invalid_data)
        
        assert "biscotto_potential" in str(exc_info.value)
        assert "Yes/No/Unknown" in str(exc_info.value)
    
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
            "home_cards_avg": 1.8,
            "away_cards_avg": 2.1,
            "cards_total_avg": 3.9,
            "cards_signal": "Medium",
            "cards_reasoning": "Away team more aggressive, home disciplined",
            "referee_name": "Maurizio Mariani",
            "referee_cards_avg": 4.2,
            "referee_strictness": "Medium",
            "match_intensity": "High",
            "is_derby": False,
            "recommended_corner_line": "Over 9.5 Corners",
            "recommended_cards_line": "Over 3.5 Cards",
            "data_confidence": "High",
            "sources_found": "Serie A official stats, SofaScore"
        }
        
        response = BettingStatsResponse(**valid_data)
        assert response.home_form_wins == 3
        assert response.home_corners_avg == 5.2
        assert response.corners_signal == "High"
        assert response.cards_signal == "Medium"
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
            "cards_signal": "Unknown",
            "referee_strictness": "Unknown",
            "match_intensity": "Unknown",
            "is_derby": False,
            "recommended_corner_line": "No bet",
            "recommended_cards_line": "No bet",
            "data_confidence": "Low",
            "sources_found": ""
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
            "cards_signal": "Medium",
            "referee_strictness": "Medium",
            "match_intensity": "High",
            "is_derby": False,
            "recommended_corner_line": "No bet",
            "recommended_cards_line": "No bet",
            "data_confidence": "High",
            "sources_found": "Test"
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
            "sources_found": "Test"
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
            "cards_signal": "Medium",
            "referee_strictness": "Medium",
            "match_intensity": "High",
            "is_derby": False,
            "recommended_corner_line": "No bet",
            "recommended_cards_line": "No bet",
            "data_confidence": "High",
            "sources_found": "Test"
        }
        
        # This should not raise ValidationError due to the validator that converts to Unknown
        response = BettingStatsResponse(**invalid_data)
        assert response.corners_signal == "Unknown"
    
    def test_json_schema_structure(self):
        """Test that JSON schema is properly generated."""
        schema = BETTING_STATS_JSON_SCHEMA
        
        assert "properties" in schema
        assert "home_form_wins" in schema["properties"]
        assert "home_corners_avg" in schema["properties"]
        assert "corners_signal" in schema["properties"]
        assert "cards_signal" in schema["properties"]
        assert "referee_strictness" in schema["properties"]
        assert "match_intensity" in schema["properties"]
        assert "is_derby" in schema["properties"]
        assert "data_confidence" in schema["properties"]
        
        # Check field types
        assert schema["properties"]["home_form_wins"]["type"] == "integer"
        assert schema["properties"]["home_corners_avg"]["type"] == "number"
        assert schema["properties"]["is_derby"]["type"] == "boolean"


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
            "table_context": "1st vs 4th, 8 points gap"
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
            "cards_signal": "Medium",
            "referee_strictness": "Strict",
            "match_intensity": "High",
            "is_derby": True,
            "data_confidence": "Medium"
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
            "injury_impact": "None reported",
            "btts_impact": "Neutral - Full squads",
            "motivation_home": "Medium - Safe position",
            "motivation_away": "Medium - Safe position",
            "table_context": "8th vs 10th, mid-table"
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
            "cards_signal": "Disciplined",
            "referee_strictness": "Lenient",
            "match_intensity": "Low",
            "is_derby": False,
            "data_confidence": "Low"
        }
        
        betting = BettingStatsResponse(**betting_data)
        betting_json = betting.model_dump_json()
        
        # Parse back from JSON
        parsed_betting = json.loads(betting_json)
        betting_restored = BettingStatsResponse(**parsed_betting)
        
        assert betting.corners_signal == betting_restored.corners_signal


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
