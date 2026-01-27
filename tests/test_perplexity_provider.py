"""
Test suite per PerplexityProvider V4.2

Verifica:
- Parsing risposte JSON
- format_for_prompt allineato con Gemini (incluso btts_impact)
- Edge cases (None, empty, malformed responses)
"""
import pytest


class TestPerplexityFormatForPrompt:
    """Test format_for_prompt - deve essere allineato con Gemini."""
    
    def test_format_includes_btts_impact(self):
        """CRITICAL: btts_impact deve essere incluso (bug fix V4.2)."""
        from src.ingestion.perplexity_provider import PerplexityProvider
        
        provider = PerplexityProvider()
        
        deep_dive = {
            "internal_crisis": "Low - No issues",
            "btts_impact": "Positive - Key defender missing",
        }
        
        result = provider.format_for_prompt(deep_dive)
        
        assert "BTTS TACTICAL" in result
        assert "Positive" in result
    
    def test_format_skips_unknown_btts(self):
        """btts_impact='Unknown' non deve apparire."""
        from src.ingestion.perplexity_provider import PerplexityProvider
        
        provider = PerplexityProvider()
        deep_dive = {"btts_impact": "Unknown"}
        
        result = provider.format_for_prompt(deep_dive)
        assert "BTTS" not in result
    
    def test_format_none_returns_empty(self):
        """Edge case: deep_dive None."""
        from src.ingestion.perplexity_provider import PerplexityProvider
        
        provider = PerplexityProvider()
        assert provider.format_for_prompt(None) == ""
    
    def test_format_empty_dict(self):
        """Edge case: deep_dive vuoto (falsy) restituisce stringa vuota."""
        from src.ingestion.perplexity_provider import PerplexityProvider
        
        provider = PerplexityProvider()
        result = provider.format_for_prompt({})
        # {} è falsy in Python, quindi restituisce ""
        assert result == ""



class TestAiParserDefaults:
    """Test che parse_ai_json abbia default allineati con normalize."""

    def test_parse_ai_json_includes_btts_impact_default(self):
        """btts_impact deve essere nei default di parse_ai_json."""
        from src.utils.ai_parser import parse_ai_json

        # Simula risposta malformata che forza uso dei default
        result = parse_ai_json("not valid json at all")

        # btts_impact deve esistere con valore default
        assert "btts_impact" in result
        assert result["btts_impact"] == "Unknown"

    def test_parse_ai_json_preserves_btts_from_response(self):
        """btts_impact dalla risposta AI deve essere preservato."""
        from src.utils.ai_parser import parse_ai_json

        response = '{"btts_impact": "Positive - Defender out"}'
        result = parse_ai_json(response)

        assert result["btts_impact"] == "Positive - Defender out"
