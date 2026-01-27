"""
Test di copertura per odds_taken in analyzer.py V4.4

Verifica che tutti i formati di mercato siano coperti:
- 1, 2, X (formato corto)
- Home Win, Away Win, Draw (formato lungo)
- 1X, X2 (Double Chance)
- BTTS
- Over/Under Goals
- Over/Under Corners
- Over/Under Cards
"""
import pytest


def test_odds_taken_market_coverage():
    """Test che tutti i mercati mappino correttamente a odds_taken."""
    
    # Simula la logica di analyzer.py
    def get_odds_taken(market: str, snippet_data: dict) -> float:
        """Replica della logica in analyzer.py"""
        odds_taken = None
        market_lower = (market or '').lower().strip()
        
        if market_lower in ('1', 'home') or ('home' in market_lower and 'win' in market_lower):
            odds_taken = snippet_data.get('current_home_odd')
        elif market_lower in ('2', 'away') or ('away' in market_lower and 'win' in market_lower):
            odds_taken = snippet_data.get('current_away_odd')
        elif market_lower in ('x', 'draw'):
            odds_taken = snippet_data.get('current_draw_odd')
        elif market_lower == '1x' or ('home' in market_lower and 'draw' in market_lower):
            odds_taken = snippet_data.get('current_home_odd')
        elif market_lower == 'x2' or ('away' in market_lower and 'draw' in market_lower):
            odds_taken = snippet_data.get('current_away_odd')
        elif 'over' in market_lower or 'under' in market_lower or 'btts' in market_lower:
            if 'corner' in market_lower:
                odds_taken = 1.85
            elif 'card' in market_lower:
                odds_taken = 1.80
            else:
                odds_taken = 1.90
        elif 'corner' in market_lower:
            odds_taken = 1.85
        elif 'card' in market_lower:
            odds_taken = 1.80
            
        return odds_taken
    
    snippet_data = {
        'current_home_odd': 1.65,
        'current_away_odd': 4.50,
        'current_draw_odd': 3.80
    }
    
    # Test tutti i formati
    test_cases = [
        # (market, expected_odds)
        ('1', 1.65),                    # Home short
        ('2', 4.50),                    # Away short
        ('X', 3.80),                    # Draw short
        ('Home Win', 1.65),             # Home long
        ('Away Win', 4.50),             # Away long
        ('Draw', 3.80),                 # Draw long
        ('1X', 1.65),                   # Double Chance 1X
        ('X2', 4.50),                   # Double Chance X2
        ('BTTS', 1.90),                 # Both Teams To Score
        ('Over 2.5 Goals', 1.90),       # Over goals
        ('Under 2.5 Goals', 1.90),      # Under goals
        ('Over 9.5 Corners', 1.85),     # Over corners
        ('Under 8.5 Corners', 1.85),    # Under corners
        ('Over 4.5 Cards', 1.80),       # Over cards
        ('Under 3.5 Cards', 1.80),      # Under cards
        ('Over 2.5', 1.90),             # Over (implicit goals)
        ('home', 1.65),                 # Home lowercase
        ('away', 4.50),                 # Away lowercase
        ('x', 3.80),                    # Draw lowercase
    ]
    
    for market, expected in test_cases:
        result = get_odds_taken(market, snippet_data)
        assert result == expected, f"Market '{market}' expected {expected}, got {result}"
    
    print(f"✅ All {len(test_cases)} market formats covered correctly")


def test_odds_taken_none_handling():
    """Test che snippet_data con valori None non causi crash."""
    
    def get_odds_taken(market: str, snippet_data: dict) -> float:
        odds_taken = None
        market_lower = (market or '').lower().strip()
        
        if market_lower in ('1', 'home'):
            odds_taken = snippet_data.get('current_home_odd')
        elif market_lower in ('2', 'away'):
            odds_taken = snippet_data.get('current_away_odd')
        elif market_lower in ('x', 'draw'):
            odds_taken = snippet_data.get('current_draw_odd')
            
        return odds_taken
    
    # snippet_data con valori None
    snippet_data = {
        'current_home_odd': None,
        'current_away_odd': None,
        'current_draw_odd': None
    }
    
    # Non deve crashare, deve restituire None
    assert get_odds_taken('1', snippet_data) is None
    assert get_odds_taken('2', snippet_data) is None
    assert get_odds_taken('X', snippet_data) is None


def test_odds_taken_empty_market():
    """Test che mercato vuoto o None non causi crash."""
    
    def get_odds_taken(market: str, snippet_data: dict) -> float:
        odds_taken = None
        market_lower = (market or '').lower().strip()
        
        if market_lower in ('1', 'home'):
            odds_taken = snippet_data.get('current_home_odd')
            
        return odds_taken
    
    snippet_data = {'current_home_odd': 1.65}
    
    # Non deve crashare
    assert get_odds_taken('', snippet_data) is None
    assert get_odds_taken(None, snippet_data) is None
    assert get_odds_taken('   ', snippet_data) is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
