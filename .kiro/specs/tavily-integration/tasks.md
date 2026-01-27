# Implementation Plan

- [x] 1. Set up Tavily configuration and environment
  - [x] 1.1 Add Tavily API keys to config/settings.py
    - Add TAVILY_API_KEY_1 through TAVILY_API_KEY_7 environment variables
    - Add TAVILY_ENABLED flag for feature toggle
    - Add TAVILY_RATE_LIMIT_SECONDS = 1.0 constant
    - Add TAVILY_CACHE_TTL_SECONDS = 1800 constant
    - _Requirements: 1.1, 11.1_
  - [x] 1.2 Update .env.example with Tavily keys template
    - Add placeholder entries for all 7 API keys
    - Add documentation comments explaining rotation
    - _Requirements: 11.1_

- [x] 2. Implement TavilyKeyRotator
  - [x] 2.1 Create src/ingestion/tavily_key_rotator.py
    - Implement TavilyKeyRotator class with key loading from env
    - Implement get_current_key() method
    - Implement rotate_to_next() method
    - Implement mark_exhausted() method
    - Implement record_call() method
    - Implement reset_all() method for monthly reset
    - Implement get_status() for monitoring
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
  - [x] 2.2 Write property test for key rotation
    - **Property 2: Key Rotation on 429**
    - **Validates: Requirements 1.4, 11.2**

- [x] 3. Implement TavilyProvider core
  - [x] 3.1 Create src/ingestion/tavily_provider.py
    - Implement TavilyProvider class with TavilyKeyRotator integration
    - Implement is_available() method
    - Implement _apply_rate_limit() method (1 req/sec)
    - Implement _check_cache() and _update_cache() methods
    - Implement search() method with caching and rate limiting
    - Implement search_news() method for news-specific queries
    - Implement get_budget_status() method
    - Add singleton get_tavily_provider() function
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - [x] 3.2 Write property test for rate limiting
    - **Property 3: Rate Limiting Enforcement**
    - **Validates: Requirements 1.2**
  - [x] 3.3 Write property test for cache round-trip
    - **Property 4: Cache Round-Trip**
    - **Validates: Requirements 1.3**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement TavilyQueryBuilder
  - [x] 5.1 Create src/ingestion/tavily_query_builder.py
    - Implement build_match_enrichment_query() with batching
    - Implement build_news_verification_query()
    - Implement build_biscotto_query()
    - Implement build_twitter_recovery_query()
    - Implement parse_batched_response() for answer extraction
    - Implement _split_long_query() for queries > 500 chars
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 5.2 Write property test for query batching round-trip
    - **Property 5: Query Batching Round-Trip**
    - **Validates: Requirements 2.1, 2.2, 2.3**
  - [x] 5.3 Write property test for query splitting
    - **Property 6: Query Splitting**
    - **Validates: Requirements 2.4**

- [x] 6. Implement BudgetManager
  - [x] 6.1 Create src/ingestion/tavily_budget.py
    - Implement BudgetStatus dataclass
    - Implement BudgetManager class with per-key tracking
    - Implement can_call() method with component allocation
    - Implement record_call() method
    - Implement get_status() method
    - Implement reset_monthly() method
    - Implement _check_thresholds() for degraded/disabled modes
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - [x] 6.2 Write property test for budget tracking
    - **Property 10: Budget Tracking Consistency**
    - **Validates: Requirements 9.1, 9.2, 11.2**

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Integrate Tavily into Intelligence Router
  - [x] 8.1 Modify src/services/intelligence_router.py
    - Import TavilyProvider and TavilyQueryBuilder
    - Add _tavily instance to IntelligenceRouter.__init__()
    - Implement _tavily_enrich_match() helper method
    - Modify enrich_match_context() to call Tavily before DeepSeek
    - Implement _merge_tavily_context() for result merging
    - Add Tavily to confirm_biscotto() flow
    - Add Tavily to verify_news_batch() as pre-filter
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 8.2 Write property test for content merging
    - **Property 7: Content Merging Preservation**
    - **Validates: Requirements 3.2, 4.2, 5.2**

- [x] 9. Integrate Tavily into News Radar
  - [x] 9.1 Modify src/services/news_radar.py
    - Import TavilyProvider
    - Add _tavily instance to NewsRadarMonitor.__init__()
    - Implement _tavily_enrich() async method
    - Modify _analyze_content() to call Tavily for confidence 0.5-0.7
    - Implement confidence boost logic (+0.15 on confirmation)
    - Add fallback handling when Tavily unavailable
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [x] 9.2 Write property test for confidence adjustment
    - **Property 8: Confidence Adjustment Bounds**
    - **Validates: Requirements 4.3**

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Integrate Tavily into Browser Monitor
  - [x] 11.1 Modify src/services/browser_monitor.py
    - Import TavilyProvider
    - Add _tavily instance to BrowserMonitor.__init__()
    - Implement _tavily_expand_short_content() method
    - Modify content analysis to call Tavily for content < 500 chars
    - Implement snippet merging logic
    - Add skip logic when Tavily returns no results
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 12. Integrate Tavily into Telegram Monitor
  - [x] 12.1 Modify src/processing/telegram_listener.py
    - Import TavilyProvider
    - Add _tavily instance to TelegramListener.__init__()
    - Implement _tavily_verify_intel() method
    - Modify intel processing for trust score 0.4-0.7
    - Implement trust score adjustment logic (+0.2/-0.1/0)
    - Add warning flag on contradiction
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [x] 12.2 Write property test for trust score adjustment
    - **Property 9: Trust Score Adjustment**
    - **Validates: Requirements 6.2, 6.3, 6.4**

- [x] 13. Integrate Tavily into Settlement and CLV
  - [x] 13.1 Modify src/analysis/settler.py
    - Import TavilyProvider
    - Add _tavily instance to Settler.__init__()
    - Implement _tavily_post_match_search() method
    - Modify settlement processing to search post-match reports
    - Store Tavily insights in settlement reason field
    - _Requirements: 7.1, 7.2, 7.4_
  - [x] 13.2 Modify src/analysis/clv_tracker.py
    - Import TavilyProvider
    - Add _tavily instance to CLVTracker.__init__()
    - Implement _tavily_verify_line_movement() method
    - Add Tavily verification to CLV analysis
    - _Requirements: 7.3_

- [x] 14. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Integrate Tavily into Twitter Intel Recovery
  - [x] 15.1 Modify src/services/twitter_intel_cache.py
    - Import TavilyProvider and TavilyQueryBuilder
    - Add _tavily instance to TwitterIntelCache.__init__()
    - Implement _tavily_recover_tweets() method
    - Modify Nitter fallback to use Tavily recovery
    - Implement tweet format normalization from Tavily results
    - Add freshness decay for tweets > 24h
    - Mark account unavailable when Tavily returns no results
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 16. Implement fallback and resilience
  - [x] 16.1 Add fallback logic to TavilyProvider
    - Implement _fallback_to_brave() method
    - Implement _fallback_to_ddg() method
    - Add circuit breaker for consecutive failures
    - Implement recovery attempt logic (every 60s)
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - [x] 16.2 Write property test for fallback activation
    - **Property 12: Fallback Activation on Exhaustion**
    - **Validates: Requirements 1.5, 10.2, 11.4**

- [x] 17. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
