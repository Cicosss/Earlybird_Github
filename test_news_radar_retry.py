#!/usr/bin/env python3
"""
Test script to verify News Radar's DeepSeek retry logic with exponential backoff.

This test simulates network timeout scenarios to ensure the retry mechanism
works correctly and doesn't cause permanent failures.
"""
import asyncio
import os
import sys
import time
from unittest.mock import patch, AsyncMock, MagicMock
import requests

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from services.news_radar import DeepSeekFallback


async def test_retry_logic_on_timeout():
    """Test that DeepSeekFallback retries on timeout with exponential backoff."""
    print("\n" + "="*70)
    print("TEST 1: Retry Logic on Timeout")
    print("="*70)
    
    # Mock environment variables
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    os.environ["OPENROUTER_MODEL"] = "deepseek/deepseek-chat-v3-0324"
    
    # Create DeepSeekFallback instance
    fallback = DeepSeekFallback(min_interval=0.1)  # Short interval for testing
    
    # Track retry attempts and timing
    retry_attempts = []
    call_times = []
    
    def mock_post_with_timeout(*args, **kwargs):
        """Mock requests.post that times out on first 2 attempts, succeeds on 3rd."""
        call_times.append(time.time())
        attempt = len(call_times)
        
        if attempt <= 2:
            # First 2 attempts: timeout
            print(f"  ↳ Attempt #{attempt}: Simulating timeout...")
            raise requests.Timeout("Connection timed out")
        else:
            # 3rd attempt: success
            print(f"  ↳ Attempt #{attempt}: Simulating success...")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": '{"is_high_value": true, "team": "Test Team", "category": "INJURY", "betting_impact": "HIGH", "confidence": 0.9}'
                    }
                }]
            }
            return mock_response
    
    # Patch requests.post and asyncio.to_thread
    with patch('requests.post', side_effect=mock_post_with_timeout):
        start_time = time.time()
        result = await fallback.analyze_v2("Test content", timeout=5, max_retries=2)
        total_time = time.time() - start_time
    
    # Verify results
    print(f"\n  📊 Results:")
    print(f"     - Total attempts: {len(call_times)}")
    print(f"     - Expected attempts: 3 (1 initial + 2 retries)")
    print(f"     - Total time: {total_time:.2f}s")
    print(f"     - Result: {'SUCCESS' if result else 'FAILURE'}")
    
    # Verify retry timing (exponential backoff: 1s, 2s)
    if len(call_times) >= 3:
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        print(f"     - Delay 1->2: {delay1:.2f}s (expected ~1s)")
        print(f"     - Delay 2->3: {delay2:.2f}s (expected ~2s)")
    
    # Assertions
    assert len(call_times) == 3, f"Expected 3 attempts, got {len(call_times)}"
    assert result is not None, "Expected result to be non-None after retries"
    assert result.get('is_high_value') == True, "Expected is_high_value to be True"
    assert total_time >= 3, f"Expected total time >= 3s (1s + 2s backoff), got {total_time:.2f}s"
    
    print("\n  ✅ TEST 1 PASSED: Retry logic works correctly with exponential backoff")
    return True


async def test_retry_logic_on_network_error():
    """Test that DeepSeekFallback retries on network errors."""
    print("\n" + "="*70)
    print("TEST 2: Retry Logic on Network Error")
    print("="*70)
    
    # Mock environment variables
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    os.environ["OPENROUTER_MODEL"] = "deepseek/deepseek-chat-v3-0324"
    
    # Create DeepSeekFallback instance
    fallback = DeepSeekFallback(min_interval=0.1)
    
    call_count = [0]
    
    def mock_post_with_network_error(*args, **kwargs):
        """Mock requests.post that fails with network error on first attempt, succeeds on 2nd."""
        call_count[0] += 1
        attempt = call_count[0]
        
        if attempt == 1:
            # First attempt: network error
            print(f"  ↳ Attempt #{attempt}: Simulating network error...")
            raise requests.RequestException("Network error: Connection refused")
        else:
            # 2nd attempt: success
            print(f"  ↳ Attempt #{attempt}: Simulating success...")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": '{"is_high_value": true, "team": "Test Team", "category": "SUSPENSION", "betting_impact": "HIGH", "confidence": 0.85}'
                    }
                }]
            }
            return mock_response
    
    # Patch requests.post
    with patch('requests.post', side_effect=mock_post_with_network_error):
        result = await fallback.analyze_v2("Test content", timeout=5, max_retries=2)
    
    # Verify results
    print(f"\n  📊 Results:")
    print(f"     - Total attempts: {call_count[0]}")
    print(f"     - Expected attempts: 2 (1 initial + 1 retry)")
    print(f"     - Result: {'SUCCESS' if result else 'FAILURE'}")
    
    # Assertions
    assert call_count[0] == 2, f"Expected 2 attempts, got {call_count[0]}"
    assert result is not None, "Expected result to be non-None after retry"
    assert result.get('is_high_value') == True, "Expected is_high_value to be True"
    
    print("\n  ✅ TEST 2 PASSED: Retry logic works correctly for network errors")
    return True


async def test_retry_logic_on_empty_response():
    """Test that DeepSeekFallback retries on empty responses."""
    print("\n" + "="*70)
    print("TEST 3: Retry Logic on Empty Response")
    print("="*70)
    
    # Mock environment variables
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    os.environ["OPENROUTER_MODEL"] = "deepseek/deepseek-chat-v3-0324"
    
    # Create DeepSeekFallback instance
    fallback = DeepSeekFallback(min_interval=0.1)
    
    call_count = [0]
    
    def mock_post_with_empty_response(*args, **kwargs):
        """Mock requests.post that returns empty response on first attempt, valid on 2nd."""
        call_count[0] += 1
        attempt = call_count[0]
        
        print(f"  ↳ Attempt #{attempt}: Returning response...")
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        if attempt == 1:
            # First attempt: empty response
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": ""
                    }
                }]
            }
        else:
            # 2nd attempt: valid response
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": '{"is_high_value": true, "team": "Test Team", "category": "COACH_CHANGE", "betting_impact": "HIGH", "confidence": 0.88}'
                    }
                }]
            }
        
        return mock_response
    
    # Patch requests.post
    with patch('requests.post', side_effect=mock_post_with_empty_response):
        result = await fallback.analyze_v2("Test content", timeout=5, max_retries=2)
    
    # Verify results
    print(f"\n  📊 Results:")
    print(f"     - Total attempts: {call_count[0]}")
    print(f"     - Expected attempts: 2 (1 initial + 1 retry)")
    print(f"     - Result: {'SUCCESS' if result else 'FAILURE'}")
    
    # Assertions
    assert call_count[0] == 2, f"Expected 2 attempts, got {call_count[0]}"
    assert result is not None, "Expected result to be non-None after retry"
    assert result.get('is_high_value') == True, "Expected is_high_value to be True"
    
    print("\n  ✅ TEST 3 PASSED: Retry logic works correctly for empty responses")
    return True


async def test_max_retries_exhausted():
    """Test that DeepSeekFallback returns None after max retries are exhausted."""
    print("\n" + "="*70)
    print("TEST 4: Max Retries Exhausted")
    print("="*70)
    
    # Mock environment variables
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    os.environ["OPENROUTER_MODEL"] = "deepseek/deepseek-chat-v3-0324"
    
    # Create DeepSeekFallback instance
    fallback = DeepSeekFallback(min_interval=0.1)
    
    call_count = [0]
    
    def mock_post_always_timeout(*args, **kwargs):
        """Mock requests.post that always times out."""
        call_count[0] += 1
        print(f"  ↳ Attempt #{call_count[0]}: Simulating timeout...")
        raise requests.Timeout("Connection timed out")
    
    # Patch requests.post
    with patch('requests.post', side_effect=mock_post_always_timeout):
        start_time = time.time()
        result = await fallback.analyze_v2("Test content", timeout=5, max_retries=2)
        total_time = time.time() - start_time
    
    # Verify results
    print(f"\n  📊 Results:")
    print(f"     - Total attempts: {call_count[0]}")
    print(f"     - Expected attempts: 3 (1 initial + 2 retries)")
    print(f"     - Total time: {total_time:.2f}s")
    print(f"     - Result: {'NONE (expected)' if result is None else 'UNEXPECTED'}")
    
    # Assertions
    assert call_count[0] == 3, f"Expected 3 attempts (1 + 2 retries), got {call_count[0]}"
    assert result is None, "Expected result to be None after all retries exhausted"
    assert total_time >= 3, f"Expected total time >= 3s (1s + 2s backoff), got {total_time:.2f}s"
    
    print("\n  ✅ TEST 4 PASSED: Returns None after max retries exhausted")
    return True


async def test_backward_compatibility():
    """Test that calling analyze_v2 without new parameters uses defaults."""
    print("\n" + "="*70)
    print("TEST 5: Backward Compatibility")
    print("="*70)
    
    # Mock environment variables
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    os.environ["OPENROUTER_MODEL"] = "deepseek/deepseek-chat-v3-0324"
    
    # Create DeepSeekFallback instance
    fallback = DeepSeekFallback(min_interval=0.1)
    
    def mock_post_success(*args, **kwargs):
        """Mock requests.post that succeeds immediately."""
        print(f"  ↳ Attempt #1: Simulating success...")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"is_high_value": true, "team": "Test Team", "category": "INJURY", "betting_impact": "HIGH", "confidence": 0.92}'
                }
            }]
        }
        return mock_response
    
    # Patch requests.post
    with patch('requests.post', side_effect=mock_post_success):
        # Call without new parameters (backward compatibility)
        result = await fallback.analyze_v2("Test content")
    
    # Verify results
    print(f"\n  📊 Results:")
    print(f"     - Result: {'SUCCESS' if result else 'FAILURE'}")
    print(f"     - Uses default timeout=60 and max_retries=2")
    
    # Assertions
    assert result is not None, "Expected result to be non-None"
    assert result.get('is_high_value') == True, "Expected is_high_value to be True"
    
    print("\n  ✅ TEST 5 PASSED: Backward compatibility maintained")
    return True


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("🧪 NEWS RADAR RETRY LOGIC TEST SUITE")
    print("="*70)
    print("\nTesting the fix for Bug #5: News Radar - DeepSeek Network Timeout")
    print("Verifying retry logic with exponential backoff implementation")
    
    tests = [
        test_retry_logic_on_timeout,
        test_retry_logic_on_network_error,
        test_retry_logic_on_empty_response,
        test_max_retries_exhausted,
        test_backward_compatibility,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            await test()
            passed += 1
        except AssertionError as e:
            print(f"\n  ❌ TEST FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n  ❌ TEST ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*70)
    print(f"📊 TEST SUMMARY: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("="*70)
    
    if failed == 0:
        print("\n✅ ALL TESTS PASSED! The retry logic fix is working correctly.")
        return 0
    else:
        print(f"\n❌ {failed} TEST(S) FAILED! Please review the implementation.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
