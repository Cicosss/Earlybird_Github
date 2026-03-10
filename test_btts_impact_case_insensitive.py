"""
Test suite for BTTSImpact case-insensitive validation fix.

Verifies that validate_btts_impact() now handles case variations correctly,
consistent with validate_referee_strictness() behavior.

This test validates the fix for the case sensitivity inconsistency identified
in COVE_BTTSIMPACT_DOUBLE_VERIFICATION_REPORT.md.
"""

import pytest
from pydantic import ValidationError

from src.schemas.perplexity_schemas import DeepDiveResponse


class TestBTTSImpactCaseInsensitive:
    """Test suite for case-insensitive BTTS impact validation."""

    def test_positive_lowercase(self):
        """Test that 'positive' (lowercase) is accepted and normalized."""
        data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "positive - Key defender missing",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        response = DeepDiveResponse(**data)
        # Should be normalized to "Positive - Key defender missing"
        assert response.btts_impact == "Positive - Key defender missing"

    def test_negative_uppercase(self):
        """Test that 'NEGATIVE' (uppercase) is accepted and normalized."""
        data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "NEGATIVE - Strong defensive setup",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        response = DeepDiveResponse(**data)
        # Should be normalized to "Negative - Strong defensive setup"
        assert response.btts_impact == "Negative - Strong defensive setup"

    def test_neutral_mixed_case(self):
        """Test that 'NeUtRaL' (mixed case) is accepted and normalized."""
        data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "NeUtRaL - Balanced teams",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        response = DeepDiveResponse(**data)
        # Should be normalized to "Neutral - Balanced teams"
        assert response.btts_impact == "Neutral - Balanced teams"

    def test_unknown_various_cases(self):
        """Test that 'Unknown' in various cases is accepted and normalized."""
        test_cases = [
            "unknown - No clear trend",
            "UNKNOWN - Insufficient data",
            "UnKnOwN - Analysis inconclusive",
        ]

        for btts_value in test_cases:
            data = {
                "internal_crisis": "Low - Valid",
                "turnover_risk": "Medium - Valid",
                "referee_intel": "Strict - Valid",
                "biscotto_potential": "No - Valid",
                "injury_impact": "Manageable - Valid",
                "btts_impact": btts_value,
                "motivation_home": "High - Valid",
                "motivation_away": "Medium - Valid",
                "table_context": "Valid context",
            }

            response = DeepDiveResponse(**data)
            # Should be normalized to "Unknown - ..."
            assert response.btts_impact.startswith("Unknown -")

    def test_explanation_preserved(self):
        """Test that the explanation part is preserved exactly as provided."""
        data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "positive - Key defender injured, backup is inexperienced",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        response = DeepDiveResponse(**data)
        # The explanation should be preserved exactly
        assert response.btts_impact == "Positive - Key defender injured, backup is inexperienced"

    def test_invalid_value_still_rejected(self):
        """Test that truly invalid values are still rejected."""
        data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "Invalid - Not a valid impact level",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        with pytest.raises(ValidationError) as exc_info:
            DeepDiveResponse(**data)

        assert "btts_impact" in str(exc_info.value)
        assert "Positive, Negative, Neutral, Unknown" in str(exc_info.value)

    def test_exact_case_still_works(self):
        """Test that exact case matching still works (backward compatibility)."""
        data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "Positive - Exact case",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        response = DeepDiveResponse(**data)
        assert response.btts_impact == "Positive - Exact case"

    def test_consistency_with_referee_intel(self):
        """
        Test that btts_impact behaves consistently with referee_intel.

        Both validators should handle the same pattern of validation.
        Note: referee_intel is case-sensitive, btts_impact is now case-insensitive.
        """
        # Test btts_impact with lowercase (should work now)
        deep_dive_data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "positive - Test",  # lowercase - should now work
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        deep_dive_response = DeepDiveResponse(**deep_dive_data)
        # Should be normalized to "Positive - Test"
        assert deep_dive_response.btts_impact == "Positive - Test"

        # Test that referee_intel is still case-sensitive (as expected)
        deep_dive_data2 = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "strict - Valid",  # lowercase - should fail
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "Positive - Test",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        with pytest.raises(ValidationError) as exc_info:
            DeepDiveResponse(**deep_dive_data2)

        assert "referee_intel" in str(exc_info.value)

    def test_all_enum_values_case_insensitive(self):
        """Test that all BTTSImpact enum values work with case variations."""
        test_cases = [
            ("positive - Test", "Positive - Test"),
            ("NEGATIVE - Test", "Negative - Test"),
            ("neutral - Test", "Neutral - Test"),
            ("UNKNOWN - Test", "Unknown - Test"),
            ("PoSiTiVe - Test", "Positive - Test"),
            ("NeGaTiVe - Test", "Negative - Test"),
            ("nEuTrAl - Test", "Neutral - Test"),
            ("uNkNoWn - Test", "Unknown - Test"),
        ]

        for input_value, expected_output in test_cases:
            data = {
                "internal_crisis": "Low - Valid",
                "turnover_risk": "Medium - Valid",
                "referee_intel": "Strict - Valid",
                "biscotto_potential": "No - Valid",
                "injury_impact": "Manageable - Valid",
                "btts_impact": input_value,
                "motivation_home": "High - Valid",
                "motivation_away": "Medium - Valid",
                "table_context": "Valid context",
            }

            response = DeepDiveResponse(**data)
            assert response.btts_impact == expected_output, f"Failed for input: {input_value}"

    def test_edge_case_empty_explanation(self):
        """Test edge case where explanation is empty."""
        data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "positive",  # No explanation
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }

        response = DeepDiveResponse(**data)
        # Should be normalized to "Positive" (no space since no explanation)
        assert response.btts_impact == "Positive"

    def test_edge_case_only_dash(self):
        """Test edge case where explanation is just a dash."""
        data = {
            "internal_crisis": "Low - Valid",
            "turnover_risk": "Medium - Valid",
            "referee_intel": "Strict - Valid",
            "biscotto_potential": "No - Valid",
            "injury_impact": "Manageable - Valid",
            "btts_impact": "positive -",
            "motivation_home": "High - Valid",
            "motivation_away": "Medium - Valid",
            "table_context": "Valid context",
        }
        
        response = DeepDiveResponse(**data)
        # Should be normalized to "Positive -"
        assert response.btts_impact == "Positive -"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
