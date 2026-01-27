# Implementation Plan

- [x] 1. Create configuration and data models
  - [x] 1.1 Create `config/news_radar_sources.json` with all provided source URLs
    - Include all 40+ URLs from requirements (BBC, Flashscore, betzona.ru, etc.)
    - Set appropriate priorities and navigation modes
    - Configure betzona.ru with `navigation_mode: "paginated"`
    - _Requirements: 8.1, 8.4_
  - [x] 1.2 Create `src/services/news_radar.py` with RadarSource and RadarAlert dataclasses
    - Define RadarSource with url, name, priority, scan_interval, navigation_mode, link_selector
    - Define RadarAlert with source_name, source_url, affected_team, category, summary, confidence
    - Define AnalysisResult for internal use
    - _Requirements: 1.1, 6.2_
  - [x] 1.3 Write property test for config loading
    - **Property 1: Config Loading Correctness**
    - **Validates: Requirements 1.1, 8.1**

- [x] 2. Implement ContentCache for deduplication
  - [x] 2.1 Create ContentCache class with hash-based deduplication
    - Compute SHA256 hash from first 1000 characters
    - Store hash with timestamp, implement LRU eviction
    - Implement is_cached(), add(), evict_expired() methods
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] 2.2 Write property test for content deduplication round-trip
    - **Property 7: Content Deduplication Round-Trip**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

- [x] 3. Implement ExclusionFilter
  - [x] 3.1 Create ExclusionFilter class with multilingual keyword lists
    - Define EXCLUDED_SPORTS (basket, basketball, nba, euroleague, pallacanestro, etc.)
    - Define EXCLUDED_CATEGORIES (women, ladies, femminile, femenino, kobiet, etc.)
    - Define EXCLUDED_YOUTH (primavera, u19, u21, youth, academy, giovanili, etc.)
    - Define EXCLUDED_OTHER_SPORTS (nfl, rugby, handball, volleyball, futsal, etc.)
    - Implement is_excluded() with case-insensitive matching
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - [x] 3.2 Write property test for exclusion filter completeness
    - **Property 3: Exclusion Filter Completeness**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [x] 4. Implement RelevanceAnalyzer
  - [x] 4.1 Create RelevanceAnalyzer class with multilingual relevance keywords
    - Define INJURY_KEYWORDS (injury, infortunio, lesión, kontuzja, sakatlık, etc.)
    - Define SUSPENSION_KEYWORDS (suspended, squalificato, sancionado, zawieszony, etc.)
    - Define NATIONAL_TEAM_KEYWORDS (national team, nazionale, selección, milli takım, etc.)
    - Define CUP_ABSENCE_KEYWORDS (cup, coppa, copa, puchar, kupa, etc.)
    - Implement analyze() returning AnalysisResult with category, confidence, summary
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [x] 4.2 Write property test for relevance detection accuracy
    - **Property 4: Relevance Detection Accuracy**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
  - [x] 4.3 Write property test for confidence threshold routing
    - **Property 5: Confidence Threshold Routing**
    - **Validates: Requirements 4.5, 5.1**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement CircuitBreaker (copy from browser_monitor.py)
  - [x] 6.1 Copy and adapt CircuitBreaker class from browser_monitor.py
    - Implement CLOSED, OPEN, HALF_OPEN states
    - Configure failure_threshold and recovery_timeout
    - Implement can_execute(), record_success(), record_failure()
    - _Requirements: 1.4_
  - [x] 6.2 Write property test for circuit breaker activation
    - **Property 2: Circuit Breaker Activation**
    - **Validates: Requirements 1.4**

- [x] 7. Implement ContentExtractor
  - [x] 7.1 Create ContentExtractor class with hybrid HTTP/Playwright extraction
    - Implement HTTP extraction with Trafilatura (primary)
    - Implement Playwright fallback with stealth mode
    - Copy resource blocking patterns from browser_monitor.py
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 7.2 Implement paginated navigation mode
    - Extract links using CSS selector from config
    - Visit each linked page with configurable delay
    - Apply same extraction pipeline to each page
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - [x] 7.3 Write property test for graceful error continuation
    - **Property 10: Graceful Error Continuation**
    - **Validates: Requirements 2.4, 10.2**

- [x] 8. Implement DeepSeekFallback
  - [x] 8.1 Create DeepSeekFallback class with rate limiting
    - Use OpenRouter API (same as browser_monitor.py)
    - Implement rate limiting (min 2 seconds between calls)
    - Build relevance analysis prompt with exclusion filters
    - Parse JSON response with safe defaults
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [x] 8.2 Write property test for DeepSeek rate limiting
    - **Property 6: DeepSeek Rate Limiting**
    - **Validates: Requirements 5.4**

- [x] 9. Implement TelegramAlerter
  - [x] 9.1 Create TelegramAlerter class with distinct alert format
    - Use 🔔 RADAR emoji prefix to distinguish from main bot (🚨 EARLYBIRD)
    - Format message with source_name, affected_team, category, summary, URL
    - Implement retry with exponential backoff (max 3 attempts)
    - Use existing TELEGRAM_TOKEN and TELEGRAM_CHAT_ID from .env
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [x] 9.2 Write property test for alert content completeness
    - **Property 8: Alert Content Completeness**
    - **Validates: Requirements 6.1, 6.2**

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement NewsRadarMonitor main class
  - [x] 11.1 Create NewsRadarMonitor class with lifecycle methods
    - Implement __init__ with config loading
    - Implement start() with Playwright initialization
    - Implement stop() with graceful shutdown
    - Implement is_running() status check
    - _Requirements: 1.1, 10.1, 10.3_
  - [x] 11.2 Implement scan_cycle() with priority ordering
    - Sort sources by priority (descending)
    - Iterate sources, check circuit breaker, extract, filter, analyze
    - Route to DeepSeek for ambiguous content (0.5-0.7 confidence)
    - Send alerts for confirmed relevant news
    - _Requirements: 1.2, 1.3, 8.4_
  - [x] 11.3 Write property test for priority-based scan ordering
    - **Property 9: Priority-Based Scan Ordering**
    - **Validates: Requirements 8.4**
  - [x] 11.4 Implement config hot-reload
    - Monitor config file modification time
    - Reload sources when file changes
    - _Requirements: 8.2, 8.3_

- [x] 12. Create launcher script
  - [x] 12.1 Create `run_news_radar.py` standalone launcher
    - Parse command line arguments (config file path)
    - Initialize NewsRadarMonitor
    - Handle SIGINT/SIGTERM for graceful shutdown
    - Log startup and shutdown messages
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 13. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
