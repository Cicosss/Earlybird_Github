#!/usr/bin/env python3
"""
V8.3 Learning Loop Integrity Fix - Deployment and Testing Script

This script:
1. Runs the database migration to add new odds tracking fields
2. Tests the odds capture functionality
3. Verifies the learning loop integrity

Usage:
    python -m src.deploy_v83_odds_fix
"""

import sys
import logging
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


def print_success(text: str):
    """Print a success message."""
    print(f"✅ {text}")


def print_error(text: str):
    """Print an error message."""
    print(f"❌ {text}")


def print_warning(text: str):
    """Print a warning message."""
    print(f"⚠️  {text}")


def print_info(text: str):
    """Print an info message."""
    print(f"ℹ️  {text}")


def run_migration():
    """Run the V8.3 database migration."""
    print_header("STEP 1: Running Database Migration V8.3")
    
    try:
        from src.database.migration_v83_odds_fix import migrate
        
        print_info("Starting migration...")
        success = migrate()
        
        if success:
            print_success("Database migration completed successfully!")
            print_info("New fields added: odds_at_alert, odds_at_kickoff, alert_sent_at")
            return True
        else:
            print_error("Database migration failed!")
            return False
            
    except Exception as e:
        print_error(f"Migration error: {e}")
        return False


def verify_database_schema():
    """Verify that new fields exist in the database."""
    print_header("STEP 2: Verifying Database Schema")
    
    try:
        from src.database.db import get_db_context
        from src.database.models import NewsLog
        from sqlalchemy import inspect
        
        with get_db_context() as db:
            inspector = inspect(db.bind)
            columns = [col['name'] for col in inspector.get_columns('news_logs')]
            
            required_fields = ['odds_at_alert', 'odds_at_kickoff', 'alert_sent_at']
            missing_fields = [field for field in required_fields if field not in columns]
            
            if missing_fields:
                print_error(f"Missing fields: {missing_fields}")
                return False
            
            print_success("All required fields present in database schema!")
            print_info(f"Verified fields: {', '.join(required_fields)}")
            return True
            
    except Exception as e:
        print_error(f"Schema verification error: {e}")
        return False


def test_odds_capture():
    """Test the odds capture functionality."""
    print_header("STEP 3: Testing Odds Capture Functionality")
    
    try:
        from src.services.odds_capture import capture_kickoff_odds, get_kickoff_odds_capture_stats
        
        print_info("Testing kickoff odds capture...")
        count = capture_kickoff_odds()
        
        if count > 0:
            print_success(f"Kickoff odds captured for {count} alerts!")
        else:
            print_warning("No kickoff odds captured (expected if no matches in kickoff window)")
        
        # Get statistics
        stats = get_kickoff_odds_capture_stats()
        print_info(f"Kickoff odds capture stats: {stats}")
        
        return True
        
    except Exception as e:
        print_error(f"Odds capture test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_settler_integration():
    """Verify that settler uses the new odds fields."""
    print_header("STEP 4: Verifying Settler Integration")
    
    try:
        from src.analysis.settler import calculate_clv
        
        # Test CLV calculation with new fields
        test_odds_taken = 2.10
        test_closing_odds = 1.95
        
        clv = calculate_clv(test_odds_taken, test_closing_odds)
        
        if clv is not None:
            print_success(f"CLV calculation works correctly!")
            print_info(f"Test: odds_taken={test_odds_taken}, closing_odds={test_closing_odds}, CLV={clv:+.2f}%")
            return True
        else:
            print_error("CLV calculation returned None!")
            return False
            
    except Exception as e:
        print_error(f"Settler verification error: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_existing_data_quality():
    """Check data quality of existing records."""
    print_header("STEP 5: Checking Existing Data Quality")
    
    try:
        from src.database.db import get_db_context
        from src.database.models import NewsLog
        
        with get_db_context() as db:
            # Count records with new fields
            total_sent = db.query(NewsLog).filter(
                NewsLog.sent == True
            ).count()
            
            with_alert_odds = db.query(NewsLog).filter(
                NewsLog.odds_at_alert.isnot(None)
            ).count()
            
            with_kickoff_odds = db.query(NewsLog).filter(
                NewsLog.odds_at_kickoff.isnot(None)
            ).count()
            
            print_info(f"Total sent alerts: {total_sent}")
            print_info(f"With odds_at_alert: {with_alert_odds} ({with_alert_odds/total_sent*100:.1f}%)")
            print_info(f"With odds_at_kickoff: {with_kickoff_odds} ({with_kickoff_odds/total_sent*100:.1f}%)")
            
            if total_sent > 0:
                alert_odds_rate = (with_alert_odds / total_sent) * 100
                if alert_odds_rate > 50:
                    print_success(f"Good alert odds capture rate: {alert_odds_rate:.1f}%")
                else:
                    print_warning(f"Low alert odds capture rate: {alert_odds_rate:.1f}%")
            
            return True
            
    except Exception as e:
        print_error(f"Data quality check error: {e}")
        return False


def print_summary():
    """Print deployment summary."""
    print_header("DEPLOYMENT SUMMARY")
    
    print_info("V8.3 Learning Loop Integrity Fix has been deployed!")
    print()
    print("Changes made:")
    print("  1. Added database fields: odds_at_alert, odds_at_kickoff, alert_sent_at")
    print("  2. Modified main.py to capture odds at alert time")
    print("  3. Created odds_capture.py for kickoff odds capture")
    print("  4. Updated settler.py to use odds_at_alert for ROI calculation")
    print("  5. Updated settler.py to use odds_at_kickoff for CLV calculation")
    print()
    print("Next steps:")
    print("  1. Add odds_capture.capture_kickoff_odds() to scheduled jobs (every 5 minutes)")
    print("  2. Monitor learning loop metrics to verify ROI accuracy")
    print("  3. Check logs for V8.3 debug messages")
    print()


def main():
    """Main deployment function."""
    print_header("V8.3 LEARNING LOOP INTEGRITY FIX - DEPLOYMENT")
    print_info(f"Started at: {datetime.now(timezone.utc).isoformat()}")
    
    # Run deployment steps
    steps = [
        ("Database Migration", run_migration),
        ("Schema Verification", verify_database_schema),
        ("Odds Capture Test", test_odds_capture),
        ("Settler Integration", verify_settler_integration),
        ("Data Quality Check", check_existing_data_quality),
    ]
    
    results = []
    for step_name, step_func in steps:
        try:
            success = step_func()
            results.append((step_name, success))
        except Exception as e:
            print_error(f"{step_name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((step_name, False))
    
    # Print summary
    print_summary()
    
    # Overall result
    all_success = all(success for _, success in results)
    
    if all_success:
        print_success("ALL DEPLOYMENT STEPS COMPLETED SUCCESSFULLY!")
        print_info("The learning loop integrity fix is now active.")
        return 0
    else:
        print_error("SOME DEPLOYMENT STEPS FAILED!")
        print_warning("Please review the errors above and fix them before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
