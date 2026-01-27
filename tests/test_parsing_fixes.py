"""
Regression Tests for Parsing Fixes (ContextDeep Audit)

Tests for:
1. extract_json() - Multiple JSON blocks handling
2. fuzzy_match_team() - Abbreviation matching (Man Utd → Manchester United)
"""
import pytest


class TestExtractJsonFix:
    """Tests for extract_json fix - should capture LAST valid JSON block."""
    
    def test_multiple_json_blocks_returns_last(self):
        """REGRESSION: Input with 2 JSON blocks should return the LAST valid one."""
        from src.utils.ai_parser import extract_json
        
        # This input has 2 JSON blocks - old code would fail with invalid JSON
        text = 'Example: {"a":1} ... Real answer: {"b":2}'
        
        result = extract_json(text)
        
        # Should return the LAST valid JSON, not concatenate them
        assert result == {"b": 2}
    
    def test_nested_json_preserved(self):
        """Nested JSON structures should be parsed correctly."""
        from src.utils.ai_parser import extract_json
        
        text = '```json\n{"outer": {"inner": "value"}, "list": [1,2,3]}\n```'
        
        result = extract_json(text)
        
        assert result["outer"]["inner"] == "value"
        assert result["list"] == [1, 2, 3]
    
    def test_markdown_fences_stripped(self):
        """Markdown code fences should be handled."""
        from src.utils.ai_parser import extract_json
        
        text = 'Here is the result:\n```json\n{"verdict": "BET"}\n```\nDone.'
        
        result = extract_json(text)
        
        assert result == {"verdict": "BET"}
    
    def test_empty_input_raises(self):
        """Empty input should raise ValueError."""
        from src.utils.ai_parser import extract_json
        
        with pytest.raises(ValueError, match="Empty response"):
            extract_json("")
        
        with pytest.raises(ValueError, match="Empty response"):
            extract_json(None)
    
    def test_no_json_raises(self):
        """Input without JSON should raise ValueError."""
        from src.utils.ai_parser import extract_json
        
        with pytest.raises(ValueError):
            extract_json("This is just plain text without any JSON")


class TestFuzzyMatchTeamFix:
    """Tests for fuzzy_match_team fix - should handle abbreviations."""
    
    def test_man_utd_matches_manchester_united(self):
        """REGRESSION: 'Man Utd' should match 'Manchester United'."""
        from src.ingestion.data_provider import fuzzy_match_team
        
        candidates = ["Manchester United", "Manchester City", "Liverpool"]
        
        result = fuzzy_match_team("Man Utd", candidates, threshold=0.5)
        
        # Old code: SequenceMatcher ratio ~0.48 → None (FAIL)
        # New code: token_set_ratio ~0.70 → "Manchester United" (PASS)
        assert result == "Manchester United"
    
    def test_exact_match_priority(self):
        """Exact match should be returned immediately."""
        from src.ingestion.data_provider import fuzzy_match_team
        
        candidates = ["Liverpool", "Liverpool FC", "Everton"]
        
        result = fuzzy_match_team("Liverpool", candidates)
        
        assert result == "Liverpool"
    
    def test_token_overlap_fc_prefix(self):
        """'FC Barcelona' should match 'Barcelona FC'."""
        from src.ingestion.data_provider import fuzzy_match_team
        
        candidates = ["Barcelona FC", "Real Madrid", "Atletico Madrid"]
        
        result = fuzzy_match_team("FC Barcelona", candidates, threshold=0.5)
        
        assert result == "Barcelona FC"
    
    def test_empty_candidates_returns_none(self):
        """Empty candidates list should return None safely."""
        from src.ingestion.data_provider import fuzzy_match_team
        
        result = fuzzy_match_team("Any Team", [])
        
        assert result is None
    
    def test_none_search_name_returns_none(self):
        """None search name should return None safely."""
        from src.ingestion.data_provider import fuzzy_match_team
        
        result = fuzzy_match_team(None, ["Team A", "Team B"])
        
        assert result is None
    
    def test_none_in_candidates_skipped(self):
        """None values in candidates should be skipped safely."""
        from src.ingestion.data_provider import fuzzy_match_team
        
        candidates = ["Liverpool", None, "Everton", "", "Arsenal"]
        
        result = fuzzy_match_team("Liverpool", candidates)
        
        assert result == "Liverpool"
    
    def test_below_threshold_returns_none(self):
        """Matches below threshold should return None."""
        from src.ingestion.data_provider import fuzzy_match_team
        
        candidates = ["Juventus", "Inter Milan", "AC Milan"]
        
        # "XYZ Team" has no similarity with Italian teams
        result = fuzzy_match_team("XYZ Team", candidates, threshold=0.6)
        
        assert result is None


class TestExtractJsonFromResponseFix:
    """Tests for analyzer.py extract_json_from_response fix."""
    
    def test_multiple_json_in_deepseek_response(self):
        """DeepSeek response with multiple JSON should return last valid."""
        from src.analysis.analyzer import extract_json_from_response
        
        # Simulated DeepSeek response with example + real answer
        content = '''
        Here's an example format: {"example": true}
        
        Now here's my actual analysis:
        {"final_verdict": "BET", "confidence": 75}
        '''
        
        result = extract_json_from_response(content)
        
        assert result["final_verdict"] == "BET"
        assert result["confidence"] == 75
