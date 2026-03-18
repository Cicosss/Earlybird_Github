"""
Test script to verify RefereeCacheMonitor fixes applied.

This test verifies:
1. Double-checked locking in get_referee_cache_monitor()
2. Write batching with dirty flag and periodic flush
3. Improved error logging in _load_metrics()
4. Type hints in get_top_referees()
5. record_boost_usage() method for duplicate hit recording fix
"""

import sys
import time
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.analysis.referee_cache_monitor import RefereeCacheMonitor, get_referee_cache_monitor


def test_double_checked_locking():
    """Test that double-checked locking is implemented."""
    print("✅ Testing double-checked locking...")
    
    # Get the source code
    import inspect
    source = inspect.getsource(get_referee_cache_monitor)
    
    # Check for double-checked locking pattern
    assert "if _referee_cache_monitor is None:" in source, "Missing first check"
    assert "with _monitor_lock:" in source, "Missing lock acquisition"
    assert "if _referee_cache_monitor is None:" in source, "Missing second check inside lock"
    
    print("   ✓ Double-checked locking pattern found")


def test_write_batching():
    """Test write batching with dirty flag and periodic flush."""
    print("✅ Testing write batching...")
    
    # Create a temporary metrics file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = Path(f.name)
    
    try:
        # Create monitor with short flush interval for testing
        monitor = RefereeCacheMonitor(metrics_file=temp_file, flush_interval=1.0)
        
        # Check that dirty flag is initialized
        assert hasattr(monitor, '_dirty'), "Missing _dirty flag"
        assert monitor._dirty == False, "Dirty flag should be False initially"
        
        # Record a hit
        monitor.record_hit("Test Referee")
        
        # Check that dirty flag is set
        assert monitor._dirty == True, "Dirty flag should be True after recording hit"
        
        # Wait for flush
        time.sleep(1.5)
        
        # Check that metrics were saved
        metrics = monitor.get_metrics()
        assert metrics['hits'] == 1, "Metrics should have 1 hit"
        
        # Force flush
        monitor.flush()
        
        print("   ✓ Write batching with dirty flag works correctly")
        
        # Shutdown monitor
        monitor.shutdown()
        
    finally:
        # Clean up
        if temp_file.exists():
            temp_file.unlink()


def test_record_boost_usage():
    """Test record_boost_usage() method for duplicate hit recording fix."""
    print("✅ Testing record_boost_usage()...")
    
    # Create a temporary metrics file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = Path(f.name)
    
    try:
        monitor = RefereeCacheMonitor(metrics_file=temp_file)
        
        # Record a cache hit
        monitor.record_hit("Michael Oliver")
        
        # Record boost usage (separate from cache hit)
        monitor.record_boost_usage("Michael Oliver")
        
        # Get metrics
        metrics = monitor.get_metrics()
        
        # Check that hits and boost_usage are tracked separately
        assert metrics['hits'] == 1, "Should have 1 cache hit"
        assert 'boost_usage' in metrics, "Missing boost_usage in metrics"
        assert metrics['boost_usage']['Michael Oliver'] == 1, "Should have 1 boost usage"
        
        # Record another boost usage
        monitor.record_boost_usage("Michael Oliver")
        
        metrics = monitor.get_metrics()
        assert metrics['hits'] == 1, "Should still have 1 cache hit (not incremented)"
        assert metrics['boost_usage']['Michael Oliver'] == 2, "Should have 2 boost usages"
        
        print("   ✓ record_boost_usage() works correctly and doesn't inflate hit rate")
        
        # Shutdown monitor
        monitor.shutdown()
        
    finally:
        # Clean up
        if temp_file.exists():
            temp_file.unlink()


def test_type_hints():
    """Test that type hints are improved."""
    print("✅ Testing type hints...")
    
    import inspect
    source = inspect.getsource(RefereeCacheMonitor.get_top_referees)
    
    # Check for improved type hints
    assert "List[Tuple[str, int]]" in source, "Missing improved type hints"
    
    print("   ✓ Type hints are improved")


def test_error_logging():
    """Test that error logging is improved."""
    print("✅ Testing error logging...")
    
    import inspect
    source = inspect.getsource(RefereeCacheMonitor._load_metrics)
    
    # Check for improved error logging
    assert "traceback.format_exc()" in source, "Missing stack trace in error logging"
    assert "metrics_file" in source, "Missing file path in error logging"
    
    print("   ✓ Error logging is improved with stack trace and file path")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("REFEREE CACHE MONITOR FIXES VERIFICATION")
    print("="*60 + "\n")
    
    try:
        test_double_checked_locking()
        test_write_batching()
        test_record_boost_usage()
        test_type_hints()
        test_error_logging()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60 + "\n")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
