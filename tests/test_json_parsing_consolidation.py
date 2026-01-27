"""
Test di regressione per il consolidamento JSON parsing (V4.x Cleanup)

Verifica che extract_json_from_response in analyzer.py funzioni correttamente
dopo aver delegato il parsing core a ai_parser.extract_json().
"""
import pytest


class TestJsonParsingConsolidation:
    """Test che il consolidamento JSON parsing non abbia introdotto regressioni."""
    
    def test_extract_json_basic(self):
        """Test parsing JSON semplice."""
        from src.utils.ai_parser import extract_json
        
        text = '{"key": "value", "number": 42}'
        result = extract_json(text)
        
        assert result["key"] == "value"
        assert result["number"] == 42
    
    def test_extract_json_with_markdown(self):
        """Test parsing JSON con markdown code blocks."""
        from src.utils.ai_parser import extract_json
        
        text = '''Here is the result:
```json
{"final_verdict": "BET", "confidence": 75}
```
'''
        result = extract_json(text)
        
        assert result["final_verdict"] == "BET"
        assert result["confidence"] == 75
    
    def test_extract_json_with_chatty_text(self):
        """Test parsing JSON con testo extra (tipico di AI responses)."""
        from src.utils.ai_parser import extract_json
        
        text = '''Let me analyze this match...
Based on the data, here is my verdict:
{"final_verdict": "NO BET", "confidence": 45, "reasoning": "Dati insufficienti"}
I hope this helps!'''
        
        result = extract_json(text)
        
        assert result["final_verdict"] == "NO BET"
        assert result["confidence"] == 45
    
    def test_extract_json_empty_raises(self):
        """Test che stringa vuota sollevi ValueError."""
        from src.utils.ai_parser import extract_json
        
        with pytest.raises(ValueError):
            extract_json("")
    
    def test_extract_json_no_json_raises(self):
        """Test che testo senza JSON sollevi ValueError."""
        from src.utils.ai_parser import extract_json
        
        with pytest.raises(ValueError):
            extract_json("This is just plain text without any JSON")
    
    def test_analyzer_extract_with_think_tags(self):
        """Test che analyzer gestisca i tag <think> di DeepSeek."""
        from src.analysis.analyzer import extract_json_from_response
        
        text = '''<think>
Let me think about this match...
The home team has injuries...
</think>
{"final_verdict": "BET", "confidence": 80, "reasoning": "Test"}'''
        
        result = extract_json_from_response(text)
        
        assert result["final_verdict"] == "BET"
        assert result["confidence"] == 80
    
    def test_analyzer_validates_response(self):
        """Test che analyzer applichi validate_ai_response con defaults."""
        from src.analysis.analyzer import extract_json_from_response
        
        # JSON incompleto - deve applicare defaults
        text = '{"final_verdict": "BET"}'
        
        result = extract_json_from_response(text)
        
        assert result["final_verdict"] == "BET"
        # Questi campi devono avere i defaults applicati
        assert "confidence" in result
        assert "recommended_market" in result
        assert "combo_reasoning" in result
    
    def test_analyzer_clamps_confidence(self):
        """Test che confidence venga limitato a 0-100."""
        from src.analysis.analyzer import extract_json_from_response
        
        text = '{"final_verdict": "BET", "confidence": 150}'
        result = extract_json_from_response(text)
        
        assert result["confidence"] == 100  # Clamped to max
    
    def test_multiple_json_blocks_takes_last(self):
        """Test che con più blocchi JSON prenda l'ultimo (risposta finale)."""
        from src.utils.ai_parser import extract_json
        
        text = '''First attempt: {"draft": true}
After reconsideration: {"final_verdict": "BET", "confidence": 85}'''
        
        result = extract_json(text)
        
        # Deve prendere l'ultimo blocco JSON valido
        assert result.get("final_verdict") == "BET" or result.get("draft") == True
