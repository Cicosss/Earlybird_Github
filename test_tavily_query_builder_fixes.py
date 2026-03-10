#!/usr/bin/env python3
"""
Test script for TavilyQueryBuilder V7.1 fixes

Tests the following fixes:
1. Python 3.9 compatibility (Optional[list[str]] syntax)
2. Error handling in parse_batched_response()
3. Error handling in split_long_query()
"""

import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add src to path
sys.path.insert(0, 'src')

from src.ingestion.tavily_query_builder import TavilyQueryBuilder


class MockTavilyResult:
    """Mock TavilyResult for testing"""
    def __init__(self, content):
        self.content = content


class MockTavilyResponse:
    """Mock TavilyResponse for testing"""
    def __init__(self, answer=None, results=None):
        self.answer = answer
        self.results = results or []


def test_python_39_compatibility():
    """Test that the code uses Optional[list[str]] syntax compatible with Python 3.9"""
    print("\n" + "="*80)
    print("TEST 1: Python 3.9 Compatibility")
    print("="*80)
    
    try:
        # Test build_match_enrichment_query with Optional[list[str]]
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="Team A",
            away_team="Team B",
            match_date="2024-01-01",
            questions=None  # Test None value
        )
        assert query == "Team A vs Team B 2024-01-01: Recent team news and injuries | Head-to-head history | Current form and standings | Key player availability"
        print("✅ build_match_enrichment_query with questions=None: PASSED")
        
        # Test with empty list
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="Team A",
            away_team="Team B",
            match_date="2024-01-01",
            questions=[]
        )
        assert query == "Team A vs Team B 2024-01-01"
        print("✅ build_match_enrichment_query with questions=[]: PASSED")
        
        # Test with custom questions
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="Team A",
            away_team="Team B",
            match_date="2024-01-01",
            questions=["Question 1", "Question 2"]
        )
        assert query == "Team A vs Team B 2024-01-01: Question 1 | Question 2"
        print("✅ build_match_enrichment_query with custom questions: PASSED")
        
        # Test build_twitter_recovery_query with Optional[list[str]]
        query = TavilyQueryBuilder.build_twitter_recovery_query(
            handle="@user",
            keywords=None
        )
        assert query == "Twitter @user recent tweets"
        print("✅ build_twitter_recovery_query with keywords=None: PASSED")
        
        query = TavilyQueryBuilder.build_twitter_recovery_query(
            handle="@user",
            keywords=["keyword1", "keyword2"]
        )
        assert query == "Twitter @user recent tweets keyword1 keyword2"
        print("✅ build_twitter_recovery_query with keywords: PASSED")
        
        print("\n✅ TEST 1: Python 3.9 Compatibility - ALL PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 1: Python 3.9 Compatibility - FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_parse_batched_response_error_handling():
    """Test error handling in parse_batched_response()"""
    print("\n" + "="*80)
    print("TEST 2: Error Handling in parse_batched_response()")
    print("="*80)
    
    try:
        # Test 1: None response
        answers = TavilyQueryBuilder.parse_batched_response(None, 3)
        assert answers == ["", "", ""]
        print("✅ parse_batched_response with None response: PASSED")
        
        # Test 2: Response with missing 'answer' attribute
        class ResponseWithoutAnswer:
            def __init__(self):
                self.results = []
        
        response = ResponseWithoutAnswer()
        answers = TavilyQueryBuilder.parse_batched_response(response, 3)
        assert answers == ["", "", ""]
        print("✅ parse_batched_response with missing 'answer' attribute: PASSED")
        
        # Test 3: Response with missing 'results' attribute
        class ResponseWithoutResults:
            def __init__(self):
                self.answer = "Test answer"
        
        response = ResponseWithoutResults()
        answers = TavilyQueryBuilder.parse_batched_response(response, 3)
        # Should use the answer for all questions
        assert len(answers) == 3
        assert all(a == "Test answer" for a in answers)
        print("✅ parse_batched_response with missing 'results' attribute: PASSED")
        
        # Test 4: Response with results missing 'content' attribute
        class ResultWithoutContent:
            pass
        
        response = MockTavilyResponse(
            answer=None,
            results=[ResultWithoutContent(), ResultWithoutContent()]
        )
        answers = TavilyQueryBuilder.parse_batched_response(response, 2)
        assert answers == ["", ""]
        print("✅ parse_batched_response with results missing 'content' attribute: PASSED")
        
        # Test 5: Response with valid numbered list format
        response = MockTavilyResponse(
            answer="1. Answer one 2. Answer two 3. Answer three",
            results=[]
        )
        answers = TavilyQueryBuilder.parse_batched_response(response, 3)
        assert answers == ["Answer one", "Answer two", "Answer three"]
        print("✅ parse_batched_response with numbered list format: PASSED")
        
        # Test 6: Response with pipe separator format
        response = MockTavilyResponse(
            answer="Answer one | Answer two | Answer three",
            results=[]
        )
        answers = TavilyQueryBuilder.parse_batched_response(response, 3)
        assert answers == ["Answer one", "Answer two", "Answer three"]
        print("✅ parse_batched_response with pipe separator format: PASSED")
        
        # Test 7: Response with valid results
        response = MockTavilyResponse(
            answer=None,
            results=[
                MockTavilyResult("Content 1"),
                MockTavilyResult("Content 2"),
                MockTavilyResult("Content 3")
            ]
        )
        answers = TavilyQueryBuilder.parse_batched_response(response, 3)
        assert answers == ["Content 1", "Content 2", "Content 3"]
        print("✅ parse_batched_response with valid results: PASSED")
        
        # Test 8: Response with more results than questions
        response = MockTavilyResponse(
            answer=None,
            results=[
                MockTavilyResult("Content 1"),
                MockTavilyResult("Content 2"),
                MockTavilyResult("Content 3"),
                MockTavilyResult("Content 4")
            ]
        )
        answers = TavilyQueryBuilder.parse_batched_response(response, 3)
        assert answers == ["Content 1", "Content 2", "Content 3"]
        print("✅ parse_batched_response with more results than questions: PASSED")
        
        # Test 9: Response with fewer results than questions
        response = MockTavilyResponse(
            answer=None,
            results=[
                MockTavilyResult("Content 1"),
                MockTavilyResult("Content 2")
            ]
        )
        answers = TavilyQueryBuilder.parse_batched_response(response, 3)
        assert answers == ["Content 1", "Content 2", ""]
        print("✅ parse_batched_response with fewer results than questions: PASSED")
        
        print("\n✅ TEST 2: Error Handling in parse_batched_response() - ALL PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 2: Error Handling in parse_batched_response() - FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_split_long_query_error_handling():
    """Test error handling in split_long_query()"""
    print("\n" + "="*80)
    print("TEST 3: Error Handling in split_long_query()")
    print("="*80)
    
    try:
        # Test 1: None input
        queries = TavilyQueryBuilder.split_long_query(None)
        assert queries == []
        print("✅ split_long_query with None input: PASSED")
        
        # Test 2: Empty string
        queries = TavilyQueryBuilder.split_long_query("")
        assert queries == []
        print("✅ split_long_query with empty string: PASSED")
        
        # Test 3: Whitespace only
        queries = TavilyQueryBuilder.split_long_query("   ")
        assert queries == []
        print("✅ split_long_query with whitespace only: PASSED")
        
        # Test 4: Short query (no split needed)
        queries = TavilyQueryBuilder.split_long_query("Short query")
        assert queries == ["Short query"]
        print("✅ split_long_query with short query: PASSED")
        
        # Test 5: Long query with pipe separator
        long_query = "Team A vs Team B: Question 1 | Question 2 | Question 3 | Question 4 | Question 5 | Question 6"
        queries = TavilyQueryBuilder.split_long_query(long_query, max_length=50)
        assert len(queries) > 1
        assert all(len(q) <= 50 for q in queries)
        print(f"✅ split_long_query with long query (split into {len(queries)} parts): PASSED")
        
        # Test 6: Very long query without separator
        very_long_query = " ".join(["word"] * 100)
        queries = TavilyQueryBuilder.split_long_query(very_long_query, max_length=50)
        assert len(queries) > 1
        assert all(len(q) <= 50 for q in queries)
        print(f"✅ split_long_query with very long query (split into {len(queries)} parts): PASSED")
        
        # Test 7: Query with colon but no pipe separator
        query = "Team A vs Team B: This is a very long query that needs to be split into multiple parts"
        queries = TavilyQueryBuilder.split_long_query(query, max_length=50)
        assert len(queries) > 1
        assert all(len(q) <= 50 for q in queries)
        print(f"✅ split_long_query with colon but no separator (split into {len(queries)} parts): PASSED")
        
        print("\n✅ TEST 3: Error Handling in split_long_query() - ALL PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 3: Error Handling in split_long_query() - FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """Test integration scenarios"""
    print("\n" + "="*80)
    print("TEST 4: Integration Scenarios")
    print("="*80)
    
    try:
        # Test 1: Build query and split it
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="Team A",
            away_team="Team B",
            match_date="2024-01-01",
            questions=["Question 1", "Question 2", "Question 3", "Question 4", "Question 5"]
        )
        queries = TavilyQueryBuilder.split_long_query(query, max_length=50)
        assert len(queries) > 1
        print(f"✅ Integration test: Built query and split into {len(queries)} parts: PASSED")
        
        # Test 2: Parse response from batched query
        response = MockTavilyResponse(
            answer="1. Answer one 2. Answer two 3. Answer three",
            results=[]
        )
        answers = TavilyQueryBuilder.parse_batched_response(response, 3)
        assert len(answers) == 3
        print("✅ Integration test: Parsed batched response: PASSED")
        
        print("\n✅ TEST 4: Integration Scenarios - ALL PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 4: Integration Scenarios - FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("TAVILY QUERY BUILDER V7.1 FIXES - TEST SUITE")
    print("="*80)
    
    results = []
    
    results.append(("Python 3.9 Compatibility", test_python_39_compatibility()))
    results.append(("Error Handling in parse_batched_response()", test_parse_batched_response_error_handling()))
    results.append(("Error Handling in split_long_query()", test_split_long_query_error_handling()))
    results.append(("Integration Scenarios", test_integration()))
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("="*80)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
