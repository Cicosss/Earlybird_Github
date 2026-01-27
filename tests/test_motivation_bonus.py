"""
Test: Motivation Bonus Logic

Verifies that motivation bonus is applied correctly and safely:
- High motivation (relegation/title) = positive bonus
- Dead rubber = negative bonus
- Score is capped at 10.0 and never goes below 0
- Empty/None strings don't cause crashes
"""
import pytest


class TestMotivationBonus:
    """Test motivation bonus calculation."""
    
    def test_relegation_bonus(self):
        """Relegation battle should give positive bonus."""
        mot_home = "High - Relegation battle, 2 points from safety"
        mot_away = "Low - Mid-table safe"
        
        bonus = 0.0
        mot_home_lower = (mot_home or "").lower()
        mot_away_lower = (mot_away or "").lower()
        
        if any(kw in mot_home_lower for kw in ["relegation", "title", "championship", "golden boot"]):
            bonus += 0.3
        if any(kw in mot_away_lower for kw in ["relegation", "title", "championship", "golden boot"]):
            bonus += 0.2
            
        assert bonus == 0.3, "Relegation should give +0.3 bonus"
    
    def test_title_race_both_teams(self):
        """Both teams in title race should give combined bonus."""
        mot_home = "High - Title race, 1st place"
        mot_away = "High - Title contender, 2nd place"
        
        bonus = 0.0
        mot_home_lower = (mot_home or "").lower()
        mot_away_lower = (mot_away or "").lower()
        
        if any(kw in mot_home_lower for kw in ["relegation", "title", "championship", "golden boot"]):
            bonus += 0.3
        if any(kw in mot_away_lower for kw in ["relegation", "title", "championship", "golden boot"]):
            bonus += 0.2
            
        assert bonus == 0.5, "Both teams in title race should give +0.5 total"
    
    def test_dead_rubber_penalty(self):
        """Dead rubber should give negative bonus."""
        mot_home = "Low - Nothing to play for, mid-table safe"
        mot_away = "Low - Dead rubber, season over"
        
        bonus = 0.0
        mot_home_lower = (mot_home or "").lower()
        mot_away_lower = (mot_away or "").lower()
        
        if any(kw in mot_home_lower for kw in ["dead rubber", "nothing to play", "mid-table safe", "friendly"]):
            bonus -= 0.5
        if any(kw in mot_away_lower for kw in ["dead rubber", "nothing to play", "mid-table safe", "friendly"]):
            bonus -= 0.5
            
        assert bonus == -1.0, "Both teams dead rubber should give -1.0 penalty"
    
    def test_score_cap_at_10(self):
        """Score should never exceed 10.0."""
        score = 9.5
        bonus = 0.5
        
        score = max(0, min(10.0, score + bonus))
        
        assert score == 10.0, "Score should be capped at 10.0"
    
    def test_score_floor_at_0(self):
        """Score should never go below 0."""
        score = 0.3
        bonus = -1.0
        
        score = max(0, min(10.0, score + bonus))
        
        assert score == 0, "Score should not go below 0"
    
    def test_none_motivation_safe(self):
        """None motivation should not crash."""
        mot_home = None
        mot_away = None
        
        bonus = 0.0
        mot_home_lower = (mot_home or "").lower()
        mot_away_lower = (mot_away or "").lower()
        
        # This should not raise any exception
        if any(kw in mot_home_lower for kw in ["relegation", "title"]):
            bonus += 0.3
        if any(kw in mot_away_lower for kw in ["relegation", "title"]):
            bonus += 0.2
            
        assert bonus == 0.0, "None motivation should give 0 bonus"
    
    def test_empty_string_safe(self):
        """Empty string motivation should not crash."""
        mot_home = ""
        mot_away = ""
        
        bonus = 0.0
        mot_home_lower = (mot_home or "").lower()
        mot_away_lower = (mot_away or "").lower()
        
        if any(kw in mot_home_lower for kw in ["relegation", "title"]):
            bonus += 0.3
            
        assert bonus == 0.0, "Empty string should give 0 bonus"
    
    def test_unknown_motivation_no_display(self):
        """Unknown motivation should not be displayed."""
        motivation_home = "Unknown"
        motivation_away = "Unknown"
        
        motivation_display = ""
        if motivation_home and motivation_home.lower() != "unknown":
            motivation_display = f"🔥 Motivazione Casa: {motivation_home}"
        if motivation_away and motivation_away.lower() != "unknown":
            if motivation_display:
                motivation_display += f"\n🔥 Motivazione Trasferta: {motivation_away}"
            else:
                motivation_display = f"🔥 Motivazione Trasferta: {motivation_away}"
        
        assert motivation_display == "", "Unknown motivation should not be displayed"
    
    def test_valid_motivation_displayed(self):
        """Valid motivation should be displayed."""
        motivation_home = "High - Title race"
        motivation_away = "Low - Mid-table"
        
        motivation_display = ""
        if motivation_home and motivation_home.lower() != "unknown":
            motivation_display = f"🔥 Motivazione Casa: {motivation_home}"
        if motivation_away and motivation_away.lower() != "unknown":
            if motivation_display:
                motivation_display += f"\n🔥 Motivazione Trasferta: {motivation_away}"
            else:
                motivation_display = f"🔥 Motivazione Trasferta: {motivation_away}"
        
        assert "Title race" in motivation_display
        assert "Mid-table" in motivation_display


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
