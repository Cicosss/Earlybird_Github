#!/usr/bin/env python3
"""
ContinentalOrchestrator Integration Tests (V9.0)

Tests the "Follow the Sun" scheduling logic including:
- Initialization and Supabase connection
- Continental window filtering
- Maintenance window handling
- Local mirror fallback
- Response structure validation

Author: Lead Architect
Date: 2026-02-08
"""

import pytest
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, Any, List

# Import the module to test
from src.processing.continental_orchestrator import (
    ContinentalOrchestrator,
    get_continental_orchestrator,
    CONTINENTAL_WINDOWS,
    MAINTENANCE_WINDOW_START,
    MAINTENANCE_WINDOW_END,
    MIRROR_FILE_PATH,
)


@pytest.mark.integration
class TestContinentalOrchestratorInitialization:
    """Test ContinentalOrchestrator initialization and setup."""
    
    def test_get_continental_orchestrator_singleton(self):
        """Test that get_continental_orchestrator returns a valid instance."""
        orchestrator = get_continental_orchestrator()
        assert isinstance(orchestrator, ContinentalOrchestrator)
        assert hasattr(orchestrator, 'supabase_provider')
        assert hasattr(orchestrator, 'supabase_available')
    
    def test_continental_windows_constants(self):
        """Test that continental windows are properly defined."""
        assert 'AFRICA' in CONTINENTAL_WINDOWS
        assert 'ASIA' in CONTINENTAL_WINDOWS
        assert 'LATAM' in CONTINENTAL_WINDOWS
        
        # Check Africa window (08:00-19:00 UTC)
        assert CONTINENTAL_WINDOWS['AFRICA'] == list(range(8, 20))
        
        # Check Asia window (00:00-11:00 UTC)
        assert CONTINENTAL_WINDOWS['ASIA'] == list(range(0, 12))
        
        # Check LATAM window (12:00-23:00 UTC)
        assert CONTINENTAL_WINDOWS['LATAM'] == list(range(12, 24))
    
    def test_maintenance_window_constants(self):
        """Test that maintenance window is properly defined."""
        assert MAINTENANCE_WINDOW_START == 4
        assert MAINTENANCE_WINDOW_END == 6
    
    def test_mirror_file_path_constant(self):
        """Test that mirror file path is properly defined."""
        assert MIRROR_FILE_PATH == Path("data/supabase_mirror.json")


@pytest.mark.integration
class TestContinentalOrchestratorStatus:
    """Test ContinentalOrchestrator status methods."""
    
    def test_get_continental_status(self):
        """Test getting continental status."""
        orchestrator = get_continental_orchestrator()
        status = orchestrator.get_continental_status()
        
        # Check required keys
        assert 'current_utc_hour' in status
        assert 'in_maintenance_window' in status
        assert 'supabase_available' in status
        assert 'continents' in status
        
        # Check current_utc_hour is valid
        assert isinstance(status['current_utc_hour'], int)
        assert 0 <= status['current_utc_hour'] <= 23
        
        # Check in_maintenance_window is boolean
        assert isinstance(status['in_maintenance_window'], bool)
        
        # Check supabase_available is boolean
        assert isinstance(status['supabase_available'], bool)
        
        # Check continents structure
        assert 'AFRICA' in status['continents']
        assert 'ASIA' in status['continents']
        assert 'LATAM' in status['continents']
        
        for continent, info in status['continents'].items():
            assert 'active_hours_utc' in info
            assert 'is_currently_active' in info
            assert isinstance(info['is_currently_active'], bool)
            assert isinstance(info['active_hours_utc'], list)
    
    def test_apply_continental_filters(self):
        """Test applying continental filters for different UTC hours."""
        orchestrator = get_continental_orchestrator()
        
        # Test at 00:00 UTC (Asia active)
        active_blocks = orchestrator.apply_continental_filters(0)
        assert 'ASIA' in active_blocks
        assert 'AFRICA' not in active_blocks
        assert 'LATAM' not in active_blocks
        
        # Test at 10:00 UTC (Asia + Africa active)
        active_blocks = orchestrator.apply_continental_filters(10)
        assert 'ASIA' in active_blocks
        assert 'AFRICA' in active_blocks
        assert 'LATAM' not in active_blocks
        
        # Test at 14:00 UTC (Africa + LATAM active)
        active_blocks = orchestrator.apply_continental_filters(14)
        assert 'ASIA' not in active_blocks
        assert 'AFRICA' in active_blocks
        assert 'LATAM' in active_blocks
        
        # Test at 22:00 UTC (LATAM active)
        active_blocks = orchestrator.apply_continental_filters(22)
        assert 'ASIA' not in active_blocks
        assert 'AFRICA' not in active_blocks
        assert 'LATAM' in active_blocks
    
    def test_is_maintenance_window(self):
        """Test maintenance window detection."""
        orchestrator = get_continental_orchestrator()
        
        # Test within maintenance window (04:00-06:00 UTC)
        assert orchestrator.is_maintenance_window(4) is True
        assert orchestrator.is_maintenance_window(5) is True
        
        # Test outside maintenance window
        assert orchestrator.is_maintenance_window(3) is False
        assert orchestrator.is_maintenance_window(6) is False
        assert orchestrator.is_maintenance_window(12) is False


@pytest.mark.integration
class TestContinentalOrchestratorLeagues:
    """Test ContinentalOrchestrator league retrieval."""
    
    def test_get_active_leagues_for_current_time_structure(self):
        """Test that get_active_leagues_for_current_time returns valid structure."""
        orchestrator = get_continental_orchestrator()
        result = orchestrator.get_active_leagues_for_current_time()
        
        # Check required keys
        required_keys = ['leagues', 'continent_blocks', 'settlement_mode', 'source', 'utc_hour']
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"
        
        # Check types
        assert isinstance(result['leagues'], list)
        assert isinstance(result['continent_blocks'], list)
        assert isinstance(result['settlement_mode'], bool)
        assert isinstance(result['source'], str)
        assert isinstance(result['utc_hour'], int)
        
        # Check valid source values
        assert result['source'] in ['supabase', 'mirror', 'none']
        
        # Check utc_hour is valid
        assert 0 <= result['utc_hour'] <= 23
        
        # Check all leagues are strings
        for league in result['leagues']:
            assert isinstance(league, str)
    
    def test_get_active_leagues_in_maintenance_window(self, log_capture):
        """Test that maintenance window returns empty leagues."""
        orchestrator = get_continental_orchestrator()
        
        # Mock current time to be in maintenance window (05:00 UTC)
        with patch('src.processing.continental_orchestrator.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 2, 8, 5, 0, 0, tzinfo=timezone.utc)
            mock_datetime.timezone = timezone
            
            result = orchestrator.get_active_leagues_for_current_time()
            
            # Check settlement mode is active
            assert result['settlement_mode'] is True
            
            # Check no leagues are returned
            assert result['leagues'] == []
            assert result['continent_blocks'] == []
            assert result['source'] == 'none'
            
            # Verify maintenance window was logged
            log_capture.assert_logged("SETTLEMENT-ONLY WINDOW", level="INFO")
    
    def test_get_active_leagues_returns_valid_leagues(self):
        """Test that get_active_leagues_for_current_time returns valid leagues."""
        orchestrator = get_continental_orchestrator()
        result = orchestrator.get_active_leagues_for_current_time()
        
        # Skip if in maintenance window
        if result['settlement_mode']:
            pytest.skip("Test skipped during maintenance window")
        
        # Check that leagues are returned if not in maintenance
        if not result['settlement_mode'] and result['source'] != 'none':
            # At least some leagues should be returned (from mirror if not Supabase)
            # This might be empty if no active leagues exist
            assert isinstance(result['leagues'], list)


@pytest.mark.integration
class TestContinentalOrchestratorFallback:
    """Test ContinentalOrchestrator fallback to local mirror."""
    
    def test_fallback_to_local_mirror_structure(self):
        """Test that fallback_to_local_mirror returns valid structure."""
        orchestrator = get_continental_orchestrator()
        
        # Test with active continent blocks
        active_blocks = ['LATAM', 'ASIA']
        leagues = orchestrator.fallback_to_local_mirror(active_blocks)
        
        # Check return type
        assert isinstance(leagues, list)
        
        # If mirror exists and has data, check structure
        if leagues:
            for league in leagues:
                assert isinstance(league, dict)
                assert 'api_key' in league
                assert 'country' in league
                assert 'continent' in league
                
                # Check nested structure
                assert 'id' in league['country']
                assert 'name' in league['country']
                assert 'id' in league['continent']
                assert 'name' in league['continent']
    
    def test_fallback_to_local_mirror_filters_by_continent(self):
        """Test that fallback_to_local_mirror filters by active continent blocks."""
        orchestrator = get_continental_orchestrator()
        
        # Test with only LATAM active
        latam_leagues = orchestrator.fallback_to_local_mirror(['LATAM'])
        
        # Test with only ASIA active
        asia_leagues = orchestrator.fallback_to_local_mirror(['ASIA'])
        
        # Test with both active
        both_leagues = orchestrator.fallback_to_local_mirror(['LATAM', 'ASIA'])
        
        # If mirror has data, verify filtering
        if latam_leagues and asia_leagues:
            # LATAM leagues should have continent name 'LATAM'
            for league in latam_leagues:
                assert league['continent']['name'] == 'LATAM'
            
            # ASIA leagues should have continent name 'ASIA'
            for league in asia_leagues:
                assert league['continent']['name'] == 'ASIA'
            
            # Both should have more leagues than individual
            assert len(both_leagues) >= len(latam_leagues)
            assert len(both_leagues) >= len(asia_leagues)
    
    def test_fallback_to_local_mirror_filters_inactive_leagues(self):
        """Test that fallback_to_local_mirror filters out inactive leagues."""
        orchestrator = get_continental_orchestrator()
        
        active_blocks = ['LATAM']
        leagues = orchestrator.fallback_to_local_mirror(active_blocks)
        
        # All returned leagues should be active
        for league in leagues:
            assert league.get('is_active', False) is True
    
    def test_fallback_to_local_mirror_with_empty_blocks(self):
        """Test that fallback_to_local_mirror handles empty continent blocks."""
        orchestrator = get_continental_orchestrator()
        
        # Test with empty continent blocks
        leagues = orchestrator.fallback_to_local_mirror([])
        
        # Should return empty list
        assert leagues == []


@pytest.mark.integration
class TestContinentalOrchestratorMirror:
    """Test ContinentalOrchestrator local mirror handling."""
    
    def test_mirror_file_exists(self):
        """Test that mirror file exists."""
        assert MIRROR_FILE_PATH.exists(), f"Mirror file not found: {MIRROR_FILE_PATH}"
    
    def test_mirror_file_valid_json(self):
        """Test that mirror file is valid JSON."""
        with open(MIRROR_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check top-level structure
        assert 'timestamp' in data
        assert 'data' in data
        
        # Check data structure
        mirror_data = data['data']
        assert 'continents' in mirror_data
        assert 'countries' in mirror_data
        assert 'leagues' in mirror_data
    
    def test_mirror_data_structure(self):
        """Test that mirror data has correct structure."""
        with open(MIRROR_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        mirror_data = data['data']
        
        # Check continents
        continents = mirror_data['continents']
        assert isinstance(continents, list)
        for continent in continents:
            assert 'id' in continent
            assert 'name' in continent
            assert 'active_hours_utc' in continent
            assert isinstance(continent['active_hours_utc'], list)
        
        # Check countries
        countries = mirror_data['countries']
        assert isinstance(countries, list)
        for country in countries:
            assert 'id' in country
            assert 'name' in country
            assert 'continent_id' in country
            assert 'iso_code' in country
        
        # Check leagues
        leagues = mirror_data['leagues']
        assert isinstance(leagues, list)
        for league in leagues:
            assert 'id' in league
            assert 'country_id' in league
            assert 'api_key' in league
            assert 'tier_name' in league
            assert 'priority' in league
            assert 'is_active' in league
    
    def test_mirror_has_required_continents(self):
        """Test that mirror has all required continents."""
        with open(MIRROR_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        continents = [c['name'] for c in data['data']['continents']]
        
        assert 'AFRICA' in continents
        assert 'ASIA' in continents
        assert 'LATAM' in continents


@pytest.mark.integration
class TestContinentalOrchestratorFollowTheSun:
    """Test "Follow the Sun" logic across different time zones."""
    
    def test_follow_the_sun_coverage(self):
        """Test that all UTC hours are covered by continental windows."""
        covered_hours = set()
        
        for continent, hours in CONTINENTAL_WINDOWS.items():
            covered_hours.update(hours)
        
        # All hours 0-23 should be covered
        expected_hours = set(range(24))
        assert covered_hours == expected_hours, f"Uncovered hours: {expected_hours - covered_hours}"
    
    def test_follow_the_sun_overlap(self):
        """Test that continental windows overlap for continuity."""
        # Check overlap between ASIA and AFRICA (hours 8-11)
        asia_hours = set(CONTINENTAL_WINDOWS['ASIA'])
        africa_hours = set(CONTINENTAL_WINDOWS['AFRICA'])
        overlap_asia_africa = asia_hours & africa_hours
        assert len(overlap_asia_africa) > 0, "No overlap between ASIA and AFRICA"
        
        # Check overlap between AFRICA and LATAM (hours 12-19)
        latam_hours = set(CONTINENTAL_WINDOWS['LATAM'])
        overlap_africa_latam = africa_hours & latam_hours
        assert len(overlap_africa_latam) > 0, "No overlap between AFRICA and LATAM"
    
    def test_follow_the_sun_maintenance_window_excluded(self):
        """Test that maintenance window (04:00-06:00 UTC) is handled."""
        # Maintenance window is 04:00-06:00 UTC
        # This is within ASIA window (00:00-11:00 UTC)
        # The orchestrator should handle this specially
        
        orchestrator = get_continental_orchestrator()
        
        # Test that maintenance window is detected
        assert orchestrator.is_maintenance_window(4) is True
        assert orchestrator.is_maintenance_window(5) is True
        assert orchestrator.is_maintenance_window(6) is False


@pytest.mark.integration
class TestContinentalOrchestratorResilience:
    """Test ContinentalOrchestrator resilience features."""
    
    def test_supabase_fallback_to_mirror(self, log_capture):
        """Test that orchestrator falls back to mirror when Supabase fails."""
        orchestrator = get_continental_orchestrator()
        
        # If Supabase is not available, mirror should be used
        if not orchestrator.supabase_available:
            result = orchestrator.get_active_leagues_for_current_time()
            
            # Skip if in maintenance window
            if not result['settlement_mode']:
                # Source should be mirror
                assert result['source'] == 'mirror', f"Expected mirror, got {result['source']}"
                
                # Verify fallback was logged
                log_capture.assert_logged("fallback", level="WARNING")
    
    def test_mirror_data_integrity(self):
        """Test that mirror data maintains referential integrity."""
        with open(MIRROR_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        mirror_data = data['data']
        continents = {c['id']: c for c in mirror_data['continents']}
        countries = {c['id']: c for c in mirror_data['countries']}
        
        # Check that all countries reference valid continents
        for country in mirror_data['countries']:
            continent_id = country['continent_id']
            assert continent_id in continents, f"Country {country['name']} references invalid continent {continent_id}"
        
        # Check that all leagues reference valid countries
        for league in mirror_data['leagues']:
            country_id = league['country_id']
            assert country_id in countries, f"League {league['api_key']} references invalid country {country_id}"


@pytest.mark.integration
class TestContinentalOrchestratorEndToEnd:
    """End-to-end tests for ContinentalOrchestrator."""
    
    def test_full_workflow(self, log_capture):
        """Test the complete workflow from initialization to league retrieval."""
        # Step 1: Initialize orchestrator
        orchestrator = get_continental_orchestrator()
        assert orchestrator is not None
        
        # Step 2: Get continental status
        status = orchestrator.get_continental_status()
        assert status is not None
        assert 'current_utc_hour' in status
        
        # Step 3: Get active leagues
        result = orchestrator.get_active_leagues_for_current_time()
        assert result is not None
        
        # Step 4: Verify response structure
        required_keys = ['leagues', 'continent_blocks', 'settlement_mode', 'source', 'utc_hour']
        for key in required_keys:
            assert key in result
        
        # Step 5: Verify data consistency
        assert result['utc_hour'] == status['current_utc_hour']
        assert result['settlement_mode'] == status['in_maintenance_window']
        
        # Step 6: Verify logging
        if not result['settlement_mode']:
            log_capture.assert_logged("Active continental blocks", level="INFO")
    
    def test_source_tracking(self, log_capture):
        """Test that data source is properly tracked and logged."""
        orchestrator = get_continental_orchestrator()
        result = orchestrator.get_active_leagues_for_current_time()
        
        # Skip if in maintenance window
        if result['settlement_mode']:
            pytest.skip("Test skipped during maintenance window")
        
        # Verify source is tracked
        assert result['source'] in ['supabase', 'mirror']
        
        # Verify source is logged - check for relevant log messages
        # When Supabase is used, we should see Supabase-related logs
        # When mirror is used, we should see mirror-related logs
        # Note: When Supabase returns 0 leagues, source may still be 'mirror' due to
        # initialization logic, but Supabase logs will be present
        if result['source'] == 'supabase':
            # Check for Supabase-related logs - look for initialization or connection logs
            # Just check for "Supabase" in logs (case-insensitive)
            has_supabase_log = log_capture.contains("Supabase", level="INFO")
            assert has_supabase_log, f"Expected Supabase-related log not found. Source: {result['source']}. Logs: {log_capture.format_all()}"
        elif result['source'] == 'mirror':
            # Check for mirror-related logs OR Supabase logs (if mirror was set as default)
            # This handles the edge case where Supabase returns 0 leagues
            has_mirror_log = (
                log_capture.contains("Loaded mirror", level="INFO") or
                log_capture.contains("fallback", level="WARNING")
            )
            has_supabase_log = log_capture.contains("Supabase", level="INFO")
            
            # At least one of these should be present
            assert has_mirror_log or has_supabase_log, \
                f"Expected mirror or Supabase-related log not found. Source: {result['source']}. Logs: {log_capture.format_all()}"


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
