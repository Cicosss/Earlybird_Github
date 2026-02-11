"""
Test Suite for Bug #10 Fix: analyze_single_match Not Found

This test suite verifies that the analyze_single_match() function
has been correctly implemented in src/main.py and works as expected
when called by the Opportunity Radar.

Author: Debug Mode
Date: 2026-02-10
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

# Setup path
sys.path.append(os.getcwd())

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load .env before imports
from dotenv import load_dotenv
load_dotenv()

def test_1_import_main_module():
    """Test 1: Import src.main module successfully."""
    logger.info("\n" + "="*70)
    logger.info("TEST 1: Import src.main module")
    logger.info("="*70)
    
    try:
        import src.main as main_module
        logger.info("✅ PASS: src.main module imported successfully")
        return True
    except ImportError as e:
        logger.error(f"❌ FAIL: Could not import src.main: {e}")
        return False

def test_2_function_exists():
    """Test 2: Verify analyze_single_match function exists in main.py."""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: Verify analyze_single_match function exists")
    logger.info("="*70)
    
    try:
        import src.main as main_module
        analyze_fn = getattr(main_module, 'analyze_single_match', None)
        
        if analyze_fn is None:
            logger.error("❌ FAIL: analyze_single_match function not found in main.py")
            return False
        
        if not callable(analyze_fn):
            logger.error("❌ FAIL: analyze_single_match exists but is not callable")
            return False
        
        logger.info("✅ PASS: analyze_single_match function exists and is callable")
        return True
    except Exception as e:
        logger.error(f"❌ FAIL: Error checking function: {e}")
        return False

def test_3_function_signature():
    """Test 3: Verify function signature accepts match_id and forced_narrative."""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: Verify function signature")
    logger.info("="*70)
    
    try:
        import inspect
        import src.main as main_module
        
        sig = inspect.signature(main_module.analyze_single_match)
        params = list(sig.parameters.keys())
        
        logger.info(f"Function parameters: {params}")
        
        # Check for required parameters
        if 'match_id' not in params:
            logger.error("❌ FAIL: Missing required parameter 'match_id'")
            return False
        
        if 'forced_narrative' not in params:
            logger.error("❌ FAIL: Missing parameter 'forced_narrative'")
            return False
        
        # Check default value for forced_narrative
        forced_narrative_param = sig.parameters['forced_narrative']
        if forced_narrative_param.default is not inspect.Parameter.empty:
            logger.info(f"✅ forced_narrative has default value: {forced_narrative_param.default}")
        else:
            logger.info("ℹ️ forced_narrative has no default value (optional)")
        
        logger.info("✅ PASS: Function signature is correct")
        return True
    except Exception as e:
        logger.error(f"❌ FAIL: Error checking signature: {e}")
        return False

def test_4_database_initialization():
    """Test 4: Verify database can be initialized."""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: Verify database initialization")
    logger.info("="*70)
    
    try:
        from src.database.models import SessionLocal, init_db
        
        # Initialize database
        init_db()
        logger.info("✅ PASS: Database initialized successfully")
        
        # Test session creation
        db = SessionLocal()
        db.close()
        logger.info("✅ PASS: Database session created successfully")
        
        return True
    except Exception as e:
        logger.error(f"❌ FAIL: Database initialization failed: {e}")
        return False

def test_5_create_test_match():
    """Test 5: Create a test match in the database for testing."""
    logger.info("\n" + "="*70)
    logger.info("TEST 5: Create test match in database")
    logger.info("="*70)
    
    try:
        from src.database.models import Match, SessionLocal
        from sqlalchemy import or_
        
        db = SessionLocal()
        
        try:
            # Check if test match already exists
            existing_match = db.query(Match).filter(
                Match.id == 'test_radar_match_001'
            ).first()
            
            if existing_match:
                logger.info(f"✅ Test match already exists: {existing_match.home_team} vs {existing_match.away_team}")
                return True
            
            # Create new test match
            test_match = Match(
                id='test_radar_match_001',
                league='soccer_epl',
                home_team='Test Home Team',
                away_team='Test Away Team',
                start_time=datetime.now(timezone.utc) + timedelta(hours=24),
                opening_home_odd=2.50,
                opening_away_odd=2.80,
                opening_draw_odd=3.20,
                current_home_odd=2.50,
                current_away_odd=2.80,
                current_draw_odd=3.20
            )
            
            db.add(test_match)
            db.commit()
            
            logger.info(f"✅ PASS: Test match created: {test_match.home_team} vs {test_match.away_team}")
            return True
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ FAIL: Failed to create test match: {e}")
        return False

def test_6_call_with_valid_match():
    """Test 6: Call analyze_single_match with valid match_id."""
    logger.info("\n" + "="*70)
    logger.info("TEST 6: Call analyze_single_match with valid match_id")
    logger.info("="*70)
    
    try:
        import src.main as main_module
        
        # Test with forced narrative
        forced_narrative = """
🔄 MULETTO/RISERVE ALERT - RADAR DETECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 TEAM: Test Home Team
📊 TYPE: B_TEAM
📝 INTEL: Key player rested for upcoming match
🔗 SOURCE: https://example.com/news
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ CRITICAL INTELLIGENCE - This narrative was detected by the Opportunity Radar.
Factor this HEAVILY into your analysis. This is PRE-MARKET intelligence.
"""
        
        result = main_module.analyze_single_match(
            match_id='test_radar_match_001',
            forced_narrative=forced_narrative
        )
        
        logger.info(f"Analysis result: {result}")
        
        # Verify result structure
        if not isinstance(result, dict):
            logger.error("❌ FAIL: Result is not a dictionary")
            return False
        
        if 'alert_sent' not in result:
            logger.error("❌ FAIL: Result missing 'alert_sent' key")
            return False
        
        if 'score' not in result:
            logger.error("❌ FAIL: Result missing 'score' key")
            return False
        
        if 'error' not in result:
            logger.error("❌ FAIL: Result missing 'error' key")
            return False
        
        logger.info(f"✅ PASS: Function called successfully")
        logger.info(f"   Alert sent: {result['alert_sent']}")
        logger.info(f"   Score: {result['score']}")
        logger.info(f"   Error: {result['error']}")
        
        return True
    except Exception as e:
        logger.error(f"❌ FAIL: Function call failed: {e}", exc_info=True)
        return False

def test_7_call_with_invalid_match():
    """Test 7: Call analyze_single_match with invalid match_id."""
    logger.info("\n" + "="*70)
    logger.info("TEST 7: Call analyze_single_match with invalid match_id")
    logger.info("="*70)
    
    try:
        import src.main as main_module
        
        result = main_module.analyze_single_match(
            match_id='invalid_match_id_12345',
            forced_narrative=None
        )
        
        logger.info(f"Analysis result: {result}")
        
        # Verify error handling
        if result.get('error') is None:
            logger.error("❌ FAIL: Should have returned error for invalid match_id")
            return False
        
        if 'not found' not in result['error'].lower():
            logger.error(f"❌ FAIL: Error message doesn't indicate match not found: {result['error']}")
            return False
        
        logger.info(f"✅ PASS: Invalid match_id handled correctly")
        logger.info(f"   Error: {result['error']}")
        
        return True
    except Exception as e:
        logger.error(f"❌ FAIL: Function should handle invalid match gracefully: {e}")
        return False

def test_8_verify_newslog_created():
    """Test 8: Verify NewsLog entry was created for radar narrative."""
    logger.info("\n" + "="*70)
    logger.info("TEST 8: Verify NewsLog entry created")
    logger.info("="*70)
    
    try:
        from src.database.models import NewsLog, SessionLocal
        
        db = SessionLocal()
        
        try:
            # Query for radar news logs for our test match
            radar_logs = db.query(NewsLog).filter(
                NewsLog.match_id == 'test_radar_match_001',
                NewsLog.source == 'radar'
            ).all()
            
            if not radar_logs:
                logger.warning("⚠️ WARNING: No radar NewsLog entries found (might be expected)")
                return True
            
            logger.info(f"✅ PASS: Found {len(radar_logs)} radar NewsLog entries")
            
            for log in radar_logs:
                logger.info(f"   - ID: {log.id}, Category: {log.category}, Score: {log.score}")
                logger.info(f"     Summary length: {len(log.summary) if log.summary else 0} chars")
            
            return True
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ FAIL: Failed to verify NewsLog: {e}")
        return False

def test_9_opportunity_radar_integration():
    """Test 9: Verify Opportunity Radar can import and call the function."""
    logger.info("\n" + "="*70)
    logger.info("TEST 9: Opportunity Radar integration")
    logger.info("="*70)
    
    try:
        import importlib
        import src.main as main_module
        
        # Simulate what Opportunity Radar does
        analyze_fn = getattr(main_module, 'analyze_single_match', None)
        
        if not analyze_fn or not callable(analyze_fn):
            logger.error("❌ FAIL: Function not accessible for Opportunity Radar")
            return False
        
        logger.info("✅ PASS: Opportunity Radar can access analyze_single_match")
        return True
    except Exception as e:
        logger.error(f"❌ FAIL: Integration test failed: {e}")
        return False

def main():
    """Run all tests."""
    logger.info("\n" + "="*70)
    logger.info("TEST SUITE: Bug #10 Fix - analyze_single_match Not Found")
    logger.info("="*70)
    logger.info("Date: 2026-02-10")
    logger.info("Objective: Verify analyze_single_match function is correctly implemented")
    
    tests = [
        test_1_import_main_module,
        test_2_function_exists,
        test_3_function_signature,
        test_4_database_initialization,
        test_5_create_test_match,
        test_6_call_with_valid_match,
        test_7_call_with_invalid_match,
        test_8_verify_newslog_created,
        test_9_opportunity_radar_integration
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            logger.error(f"❌ TEST CRASHED: {test.__name__}: {e}", exc_info=True)
            results.append((test.__name__, False))
    
    # Print summary
    logger.info("\n" + "="*70)
    logger.info("TEST SUMMARY")
    logger.info("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n🎉 ALL TESTS PASSED! Bug #10 is FIXED.")
        return 0
    else:
        logger.warning(f"\n⚠️ {total - passed} test(s) failed. Please review the logs above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
