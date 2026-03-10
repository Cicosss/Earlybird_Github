# Architecture Snapshot - Ground Truth for V10.5

**Generated:** 2026-02-20T22:37:17.186044+00:00
**Purpose:** Single Source of Truth for Claude-Mem Integration
**Method:** AST-based code analysis

---

## 📋 Metadata

- **Tool:** Native Python AST Mapper
- **Scanned Directories:** `src/`, `config/`
- **Analysis Method:** Abstract Syntax Tree (AST) parsing
- **Extraction:** Classes and Functions definitions

---

## 🏗️ Architecture Map

### config

#### `settings.py`

**Functions:**
- `def _inject_default_env_vars()`
- `def get_home_advantage()`
- `def get_news_decay_lambda()`
- `def get_source_decay_modifier()`
- `def get_team_fotmob_ids()`
- `def is_config_valid()`
- `def validate_config()`


#### `twitter_intel_accounts.py`

**Classes:**
- `class AccountType`
- `class LeagueTier`
- `class TwitterIntelAccount`

**Functions:**
- `def build_gemini_twitter_extraction_prompt()`
- `def find_account_by_handle()`
- `def get_account_count()`
- `def get_all_twitter_handles()`
- `def get_handles_by_tier()`
- `def get_twitter_intel_accounts()`


### src

#### `main.py`

**Functions:**
- `def _cleanup_background_workers()`
- `def analyze_single_match()`
- `def check_biscotto_suspects()`
- `def check_odds_drops()`
- `def cleanup_on_exit()`
- `def get_news_sources_with_fallback()`
- `def get_social_sources_with_fallback()`
- `def is_biscotto_suspect()`
- `def is_case_closed()`
- `def is_intelligence_only_league()`
- `def load_local_mirror()`
- `def on_high_priority_discovery()`
- `def parse_args()`
- `def process_intelligence_queue()`
- `def refresh_twitter_intel_sync()`
- `def run_browser_monitor_loop()`
- `def run_continuous()`
- `def run_nightly_settlement()`
- `def run_opportunity_radar()`
- `def run_pipeline()`
- `def should_run_radar()`
- `def should_run_settlement()`
- `def show_system_status()`
- `def signal_handler()`
- `def test_main_configuration()`


### src/alerting

#### `health_monitor.py`

**Classes:**
- `class HealthMonitor`
- `class HealthStats`

**Functions:**
- `def get_health_monitor()`


#### `notifier.py`

**Functions:**
- `def _build_bet_section()`
- `def _build_confidence_breakdown_section()`
- `def _build_convergence_section()`
- `def _build_date_line()`
- `def _build_injury_section()`
- `def _build_referee_section()`
- `def _build_twitter_section()`
- `def _build_verification_section()`
- `def _clean_ai_text()`
- `def _send_plain_text_fallback()`
- `def _send_telegram_document_request()`
- `def _send_telegram_request()`
- `def _truncate_message_if_needed()`
- `def calculate_odds_movement()`
- `def extract_combo_from_summary()`
- `def normalize_unicode()`
- `def send_alert()`
- `def send_alert_wrapper()`
- `def send_biscotto_alert()`
- `def send_document()`
- `def send_status_message()`
- `def strip_html_links()`
- `def truncate_utf8()`


### src/analysis


#### `analyzer.py`

**Functions:**
- `def _format_team_stats()`
- `def _json_loads()`
- `def _normalize_signal_type()`
- `def _parse_twitter_intel()`
- `def analyze_biscotto()`
- `def analyze_relevance()`
- `def analyze_with_triangulation()`
- `def basic_keyword_analysis()`
- `def batch_analyze()`
- `def call_deepseek()`
- `def check_biscotto_keywords()`
- `def detect_cross_source_convergence()`
- `def enrich_with_player_data()`
- `def extract_json_from_response()`
- `def extract_player_names()`
- `def extract_reasoning_from_response()`
- `def get_ai_response_stats()`
- `def get_match_attr()`
- `def normalize_unicode()`
- `def reset_ai_response_stats()`
- `def safe_injuries_list()`
- `def truncate_utf8()`
- `def validate_ai_response()`


#### `biscotto_engine.py`

**Classes:**
- `class BiscottoAnalysis`
- `class BiscottoPattern`
- `class BiscottoSeverity`
- `class ClassificaContext`

**Functions:**
- `def _estimate_matches_remaining_from_date()`
- `def analyze_biscotto()`
- `def analyze_classifica_context()`
- `def calculate_implied_probability()`
- `def calculate_severity()`
- `def calculate_zscore()`
- `def check_mutual_benefit()`
- `def detect_odds_pattern()`
- `def format_biscotto_context()`
- `def get_draw_threshold_for_league()`
- `def get_enhanced_biscotto_analysis()`
- `def is_minor_league_biscotto_risk()`


#### `clv_tracker.py`

**Classes:**
- `class CLVStats`
- `class CLVTracker`
- `class StrategyEdgeReport`

**Functions:**
- `def _tavily_verify_line_movement()`
- `def get_clv_tracker()`


#### `enhanced_verifier.py`

**Classes:**
- `class DataDiscrepancy`
- `class EnhancedFinalVerifier`

**Functions:**
- `def get_enhanced_final_verifier()`


#### `fatigue_engine.py`

**Classes:**
- `class FatigueAnalysis`
- `class FatigueDifferential`

**Functions:**
- `def analyze_fatigue_differential()`
- `def analyze_team_fatigue()`
- `def calculate_fatigue_index()`
- `def calculate_late_game_risk()`
- `def format_fatigue_context()`
- `def get_enhanced_fatigue_context()`
- `def get_fatigue_level()`
- `def get_squad_depth_score()`


#### `final_alert_verifier.py`

**Classes:**
- `class FinalAlertVerifier`

**Functions:**
- `def get_final_verifier()`
- `def is_final_verifier_available()`


#### `image_ocr.py`

**Functions:**
- `def _is_valid_ocr_text()`
- `def extract_player_names()`
- `def process_squad_image()`


#### `injury_impact_engine.py`

**Classes:**
- `class InjuryDifferential`
- `class PlayerImpact`
- `class PlayerPosition`
- `class PlayerRole`
- `class TeamInjuryImpact`

**Functions:**
- `def _build_player_info_map()`
- `def _calculate_score_adjustment()`
- `def _generate_differential_summary()`
- `def analyze_match_injuries()`
- `def calculate_injury_differential()`
- `def calculate_player_impact()`
- `def calculate_team_injury_impact()`
- `def detect_position_from_group()`
- `def detect_position_from_player_data()`
- `def estimate_player_role()`


#### `intelligent_modification_logger.py`

**Classes:**
- `class FeedbackDecision`
- `class IntelligentModificationLogger`
- `class ModificationPlan`
- `class ModificationPriority`
- `class ModificationType`
- `class SuggestedModification`

**Functions:**
- `def get_intelligent_modification_logger()`


#### `market_intelligence.py`

**Classes:**
- `class MarketIntelligence`
- `class OddsSnapshot`
- `class RLMSignalV2`
- `class ReverseLineSignal`
- `class SteamMoveSignal`

**Functions:**
- `def _estimate_rlm_time_window()`
- `def _get_freshness_tag_from_minutes()`
- `def analyze_market_intelligence()`
- `def apply_news_decay()`
- `def apply_news_decay_v2()`
- `def calculate_news_freshness_multiplier()`
- `def cleanup_old_snapshots()`
- `def detect_reverse_line_movement()`
- `def detect_rlm_v2()`
- `def detect_steam_move()`
- `def get_odds_history()`
- `def get_steam_window_for_league()`
- `def init_market_intelligence_db()`
- `def save_odds_snapshot()`


#### `math_engine.py`

**Classes:**
- `class EdgeResult`
- `class MathPredictor`
- `class PoissonResult`

**Functions:**
- `def calculate_btts_trend()`
- `def format_math_context()`
- `def quick_poisson()`


#### `news_scorer.py`

**Classes:**
- `class NewsScore`

**Functions:**
- `def _determine_primary_driver()`
- `def _determine_tier()`
- `def _score_content()`
- `def _score_freshness()`
- `def _score_source()`
- `def _score_specificity()`
- `def format_batch_score_for_prompt()`
- `def format_news_score_for_prompt()`
- `def score_news_batch()`
- `def score_news_item()`


#### `optimizer.py`

**Classes:**
- `class OptimizerState`
- `class OptimizerWeightCache`
- `class StrategyOptimizer`

**Functions:**
- `def calc_max_drawdown()`
- `def calc_sharpe()`
- `def calc_sortino()`
- `def calculate_advanced_weight()`
- `def categorize_market()`
- `def get_dynamic_alert_threshold()`
- `def get_optimizer()`
- `def get_optimizer_state()`


#### `player_intel.py`

**Functions:**
- `def check_player_status()`
- `def clear_cache()`
- `def extract_lastname()`
- `def get_player_role()`
- `def get_team_players_with_stats()`
- `def is_key_player()`
- `def match_player()`
- `def normalize_name()`
- `def resolve_player_in_team()`
- `def similarity()`


#### `reporter.py`

**Functions:**
- `def _ensure_output_dir()`
- `def _format_match_string()`
- `def _format_match_time()`
- `def _format_odds()`
- `def _get_pronostico()`
- `def _is_match_finished()`
- `def export_bet_history()`
- `def export_bet_history_batch()`
- `def get_daily_summary()`


#### `settler.py`

**Functions:**
- `def _tavily_post_match_search()`
- `def calculate_clv()`
- `def evaluate_bet()`
- `def evaluate_combo_bet()`
- `def evaluate_over_under()`
- `def get_league_performance()`
- `def get_match_result()`
- `def safe_int()`
- `def settle_pending_bets()`


#### `squad_analyzer.py`

**Functions:**
- `def analyze_squad_list()`
- `def get_top_key_players()`


#### `stats_drawer.py`

**Functions:**
- `def draw_dashboard()`
- `def generate_dashboard()`
- `def get_stats_data()`
- `def get_text_summary()`


#### `step_by_step_feedback.py`

**Classes:**
- `class ComponentCommunicator`
- `class StepByStepFeedbackLoop`

**Functions:**
- `def get_step_by_step_feedback_loop()`


#### `telegram_trust_score.py`

**Classes:**
- `class ChannelMetrics`
- `class MessageValidation`
- `class TrustLevel`

**Functions:**
- `def _get_text_hash()`
- `def _normalize_text_for_echo()`
- `def calculate_timestamp_lag()`
- `def calculate_trust_score()`
- `def check_echo_chamber()`
- `def detect_red_flags()`
- `def get_channel_trust_metrics()`
- `def get_first_odds_drop_time()`
- `def track_odds_correlation()`
- `def validate_telegram_message()`


#### `verification_layer.py`

**Classes:**
- `class ConfidenceLevel`
- `class FormStats`
- `class H2HStats`
- `class InjurySeverity`
- `class LogicValidator`
- `class OptimizedQueryBuilder`
- `class OptimizedResponseParser`
- `class PerplexityVerifier`
- `class PlayerImpact`
- `class RefereeStats`
- `class RefereeStrictness`
- `class TavilyVerifier`
- `class VerificationOrchestrator`
- `class VerificationRequest`
- `class VerificationResult`
- `class VerificationStatus`
- `class VerifiedData`

**Functions:**
- `def _calculate_injury_severity()`
- `def build_italian_reasoning()`
- `def create_fallback_result()`
- `def create_rejection_result()`
- `def create_skip_result()`
- `def create_verification_request_from_match()`
- `def get_logic_validator()`
- `def get_verification_orchestrator()`
- `def market_value_to_impact()`
- `def parse_ai_json()`
- `def parse_number()`
- `def should_verify_alert()`
- `def verify_alert()`


#### `verifier_integration.py`

**Functions:**
- `def build_alert_data_for_verifier()`
- `def build_context_data_for_verifier()`
- `def build_news_source_verification()`
- `def extract_domain_from_url()`
- `def verify_alert_before_telegram()`


### src/core

#### `analysis_engine.py`

**Classes:**
- `class AnalysisEngine`

**Functions:**
- `def get_analysis_engine()`


#### `betting_quant.py`

**Classes:**
- `class BettingDecision`
- `class BettingQuant`
- `class VetoReason`

**Functions:**
- `def get_betting_quant()`


#### `settlement_service.py`

**Classes:**
- `class SettlementService`

**Functions:**
- `def get_settlement_service()`
- `def safe_int()`


### src/database

#### `db.py`

**Functions:**
- `def _ensure_alias()`
- `def get_db_context()`
- `def get_upcoming_matches()`
- `def init_db()`
- `def normalize_unicode()`
- `def save_analysis()`
- `def save_matches()`


#### `maintenance.py`

**Functions:**
- `def emergency_cleanup()`
- `def get_db_stats()`
- `def prune_old_data()`


#### `migration.py`

**Functions:**
- `def check_and_migrate()`
- `def get_schema_version()`
- `def get_table_columns()`


#### `migration_v73.py`

**Functions:**
- `def migrate_v73()`


#### `migration_v83_odds_fix.py`

**Functions:**
- `def migrate()`
- `def rollback()`


#### `models.py`

**Classes:**
- `class Match`
- `class NewsLog`
- `class TeamAlias`

**Functions:**
- `def decorator()`
- `def get_db()`
- `def get_db_session()`
- `def get_db_stats()`
- `def init_db()`
- `def set_sqlite_pragma()`
- `def vacuum_db()`
- `def with_db_retry()`
- `def wrapper()`


#### `supabase_provider.py`

**Classes:**
- `class SupabaseProvider`

**Functions:**
- `def create_local_mirror()`
- `def fetch_continents()`
- `def fetch_countries()`
- `def fetch_hierarchical_map()`
- `def fetch_leagues()`
- `def fetch_sources()`
- `def get_supabase()`
- `def refresh_mirror()`


#### `telegram_channel_model.py`

**Classes:**
- `class TelegramChannel`
- `class TelegramMessageLog`

**Functions:**
- `def cleanup_old_message_logs()`
- `def get_blacklisted_channels()`
- `def get_channel_metrics()`
- `def get_or_create_channel()`
- `def get_trusted_channels()`
- `def init_telegram_tracking_db()`
- `def log_telegram_message()`
- `def update_channel_metrics()`


### src/entrypoints

#### `launcher.py`

**Functions:**
- `def check_and_restart()`
- `def check_component_health()`
- `def discover_processes()`
- `def main()`
- `def parse_args()`
- `def show_process_status()`
- `def signal_handler()`
- `def start_process()`
- `def stop_process()`


#### `run_bot.py`

**Functions:**
- `def debug_handler()`
- `def help_handler()`
- `def is_admin()`
- `def main()`
- `def parse_args()`
- `def ping_handler()`
- `def report_handler()`
- `def resume_handler()`
- `def settle_handler()`
- `def setup_handlers()`
- `def start_handler()`
- `def stat_handler()`
- `def status_handler()`
- `def stop_handler()`
- `def test_bot_configuration()`


### src/ingestion

#### `aleague_scraper.py`

**Classes:**
- `class ALeagueScraper`

**Functions:**
- `def _extract_team_mentions()`
- `def _get_article_hash()`
- `def _has_injury_content()`
- `def _is_article_seen()`
- `def _is_ins_outs_article()`
- `def _mark_scraped()`
- `def _should_scrape()`
- `def get_aleague_scraper()`
- `def is_aleague_scraper_available()`
- `def scrape_aleague_news_list()`
- `def scrape_article_content()`
- `def search_aleague_news()`


#### `base_budget_manager.py`

**Classes:**
- `class BaseBudgetManager`
- `class BudgetStatus`


#### `brave_budget.py`

**Classes:**
- `class BudgetManager`

**Functions:**
- `def get_brave_budget_manager()`
- `def reset_brave_budget_manager()`


#### `brave_key_rotator.py`

**Classes:**
- `class BraveKeyRotator`

**Functions:**
- `def get_brave_key_rotator()`
- `def reset_brave_key_rotator()`


#### `brave_provider.py`

**Classes:**
- `class BraveSearchProvider`

**Functions:**
- `def get_brave_provider()`
- `def reset_brave_provider()`


#### `data_provider.py`

**Classes:**
- `class FotMobProvider`

**Functions:**
- `def fetch_match_lineup()`
- `def fetch_team_details()`
- `def fuzzy_match_team()`
- `def get_data_provider()`
- `def get_random_user_agent()`
- `def log_fotmob_cache_metrics()`
- `def normalize_unicode()`


#### `deepseek_intel_provider.py`

**Classes:**
- `class DeepSeekIntelProvider`

**Functions:**
- `def get_deepseek_provider()`
- `def safe_bool()`
- `def safe_float()`
- `def safe_int()`
- `def safe_list()`
- `def safe_str()`


#### `fotmob_team_mapping.py`

**Functions:**
- `def add_team_mapping()`
- `def get_fotmob_league_id()`
- `def get_fotmob_team_id()`


#### `ingest_fixtures.py`

**Functions:**
- `def _close_session()`
- `def _ensure_utc_aware()`
- `def _get_current_odds_key()`
- `def _get_session()`
- `def _reset_odds_key_rotation()`
- `def _rotate_odds_key()`
- `def check_quota_status()`
- `def clean_team_name()`
- `def extract_h2h_odds()`
- `def extract_sharp_odds_analysis()`
- `def extract_totals_odds()`
- `def get_optimized_regions()`
- `def ingest_fixtures()`
- `def should_update_league()`
- `def update_team_aliases()`


#### `league_manager.py`

**Functions:**
- `def _check_daily_reset()`
- `def _close_session()`
- `def _fetch_tier1_from_supabase()`
- `def _fetch_tier2_from_supabase()`
- `def _get_continental_fallback()`
- `def _get_current_odds_key()`
- `def _get_session()`
- `def _reset_odds_key_rotation()`
- `def _rotate_odds_key()`
- `def fetch_all_sports()`
- `def get_active_leagues_for_continental_blocks()`
- `def get_active_niche_leagues()`
- `def get_elite_leagues()`
- `def get_fallback_leagues()`
- `def get_league_priority()`
- `def get_league_tier()`
- `def get_leagues_for_cycle()`
- `def get_quota_status()`
- `def get_regions_for_league()`
- `def get_tier1_leagues()`
- `def get_tier2_fallback_batch()`
- `def get_tier2_fallback_status()`
- `def get_tier2_for_cycle()`
- `def get_tier2_leagues()`
- `def increment_cycle()`
- `def is_asia_league()`
- `def is_australia_league()`
- `def is_elite_league()`
- `def is_europe_league()`
- `def is_latam_league()`
- `def is_niche_league()`
- `def is_tier1_league()`
- `def is_tier2_league()`
- `def record_tier2_activation()`
- `def reset_daily_tier2_stats()`
- `def should_activate_tier2_fallback()`


#### `mediastack_budget.py`

**Classes:**
- `class MediaStackBudget`

**Functions:**
- `def get_mediastack_budget()`


#### `mediastack_key_rotator.py`

**Classes:**
- `class MediaStackKeyRotator`

**Functions:**
- `def get_mediastack_key_rotator()`


#### `mediastack_provider.py`

**Classes:**
- `class CacheEntry`
- `class CircuitBreaker`
- `class CircuitBreakerState`
- `class MediastackProvider`

**Functions:**
- `def _clean_query_for_mediastack()`
- `def _matches_exclusion()`
- `def get_mediastack_provider()`


#### `mediastack_query_builder.py`

**Classes:**
- `class MediaStackQueryBuilder`


#### `opportunity_radar.py`

**Classes:**
- `class OpportunityRadar`

**Functions:**
- `def get_radar()`
- `def run_radar_scan()`


#### `perplexity_provider.py`

**Classes:**
- `class PerplexityProvider`

**Functions:**
- `def get_perplexity_provider()`
- `def is_perplexity_available()`
- `def safe_bool()`
- `def safe_int()`
- `def safe_list()`
- `def safe_str()`


#### `prompts.py`

**Functions:**
- `def build_betting_stats_prompt()`
- `def build_biscotto_confirmation_prompt()`
- `def build_deep_dive_prompt()`
- `def build_match_context_enrichment_prompt()`
- `def build_news_verification_prompt()`
- `def normalize_unicode()`
- `def truncate_utf8()`


#### `search_provider.py`

**Classes:**
- `class SearchProvider`

**Functions:**
- `def _fetch_news_sources_from_supabase()`
- `def _get_league_id_from_key()`
- `def get_news_domains_for_league()`
- `def get_search_provider()`
- `def search_insider()`
- `def search_local()`
- `def search_news()`
- `def search_twitter()`


#### `tavily_budget.py`

**Classes:**
- `class BudgetManager`

**Functions:**
- `def get_budget_manager()`


#### `tavily_key_rotator.py`

**Classes:**
- `class TavilyKeyRotator`

**Functions:**
- `def get_tavily_key_rotator()`


#### `tavily_provider.py`

**Classes:**
- `class BudgetStatus`
- `class CacheEntry`
- `class CircuitBreaker`
- `class CircuitBreakerState`
- `class TavilyProvider`
- `class TavilyResponse`
- `class TavilyResult`

**Functions:**
- `def get_tavily_provider()`


#### `tavily_query_builder.py`

**Classes:**
- `class TavilyQueryBuilder`


#### `weather_provider.py`

**Functions:**
- `def analyze_weather_impact()`
- `def get_match_weather()`
- `def get_weather_forecast()`
- `def safe_get()`
- `def validate_coordinates()`


### src/models

#### `schemas.py`

**Classes:**
- `class GeminiResponse`
- `class MatchAlert`
- `class OddsMovement`


### src/processing

#### `global_orchestrator.py`

**Classes:**
- `class GlobalOrchestrator`

**Functions:**
- `def get_continental_orchestrator()`
- `def get_global_orchestrator()`


#### `news_hunter.py`

**Functions:**
- `def _apply_intelligence_gate_to_news()`
- `def _apply_news_decay()`
- `def _get_search_backend()`
- `def _is_brave_available()`
- `def _is_ddg_available()`
- `def _legacy_store_discovery()`
- `def build_dynamic_search_query()`
- `def cleanup_expired_browser_monitor_discoveries()`
- `def clear_browser_monitor_discoveries()`
- `def extract_country_from_league()`
- `def get_beat_writers_from_supabase()`
- `def get_browser_monitor_news()`
- `def get_browser_monitor_stats()`
- `def get_country_code()`
- `def get_freshness_tag()`
- `def get_native_keywords()`
- `def get_news_sources_from_supabase()`
- `def get_search_strategy()`
- `def get_social_sources_from_supabase()`
- `def register_browser_monitor_discovery()`
- `def run_hunter_for_match()`
- `def search_beat_writers()`
- `def search_beat_writers_priority()`
- `def search_dynamic_country()`
- `def search_exotic_league()`
- `def search_insiders()`
- `def search_news()`
- `def search_news_generic()`
- `def search_news_local()`
- `def search_twitter_rumors()`


#### `sources_config.py`

**Classes:**
- `class BeatWriter`
- `class SourceTier`

**Functions:**
- `def _initialize_white_list()`
- `def build_site_dork_query()`
- `def get_all_telegram_channels()`
- `def get_beat_writer_by_handle()`
- `def get_beat_writer_handles()`
- `def get_beat_writers()`
- `def get_country_from_league()`
- `def get_insider_handles()`
- `def get_keywords_for_league()`
- `def get_source_weight()`
- `def get_sources_for_league()`
- `def get_telegram_channels()`
- `def get_trust_score()`


#### `telegram_listener.py`

**Functions:**
- `def _safe_int_env()`
- `def _tavily_verify_intel()`
- `def extract_team_names_from_text()`
- `def fetch_squad_images()`
- `def get_channel_entity_safe()`
- `def has_upcoming_match()`
- `def is_message_fresh()`
- `def monitor_channels_for_squads()`
- `def normalize_datetime()`
- `def run_telegram_monitor()`
- `def should_process_message()`


### src/schemas

#### `perplexity_schemas.py`

**Classes:**
- `class BTTSImpact`
- `class BettingStatsResponse`
- `class BiscottoPotential`
- `class CardsSignal`
- `class DataConfidence`
- `class DeepDiveResponse`
- `class InjuryImpact`
- `class MatchIntensity`
- `class RefereeStrictness`
- `class RiskLevel`
- `class SignalLevel`


### src/services

#### `browser_monitor.py`

**Classes:**
- `class BrowserMonitor`
- `class CircuitBreaker`
- `class ContentCache`
- `class DiscoveredNews`
- `class GlobalSettings`
- `class MonitorConfig`
- `class MonitoredSource`

**Functions:**
- `def abort_route()`
- `def get_browser_monitor()`
- `def get_memory_usage_percent()`
- `def get_sources_for_league()`
- `def is_valid_html()`
- `def load_config()`
- `def record_extraction()`


#### `intelligence_router.py`

**Classes:**
- `class IntelligenceRouter`

**Functions:**
- `def get_intelligence_router()`
- `def is_intelligence_available()`


#### `news_radar.py`

**Classes:**
- `class CircuitBreaker`
- `class ContentCache`
- `class ContentExtractor`
- `class DeepSeekFallback`
- `class GlobalRadarMonitor`
- `class GlobalSettings`
- `class NewsRadarMonitor`
- `class RadarAlert`
- `class RadarConfig`
- `class RadarSource`
- `class TelegramAlerter`

**Functions:**
- `def extract_single()`
- `def get_global_radar_monitor()`
- `def load_config()`


#### `nitter_fallback_scraper.py`

**Classes:**
- `class InstanceHealth`
- `class NitterCache`
- `class NitterFallbackScraper`
- `class ScrapedTweet`

**Functions:**
- `def build_flash_analysis_prompt()`
- `def clear_nitter_intel_cache()`
- `def get_nitter_fallback_scraper()`
- `def get_nitter_intel_for_match()`
- `def parse_flash_analysis_response()`
- `def passes_native_gate()`
- `def scrape_twitter_intel_fallback()`
- `def test_scraper()`


#### `nitter_pool.py`

**Classes:**
- `class CircuitBreaker`
- `class CircuitState`
- `class InstanceHealth`
- `class NitterPool`

**Functions:**
- `def get_nitter_pool()`
- `def reset_nitter_pool()`


#### `odds_capture.py`

**Functions:**
- `def capture_kickoff_odds()`
- `def get_kickoff_odds_capture_stats()`


#### `tweet_relevance_filter.py`

**Classes:**
- `class TweetRelevanceFilter`

**Functions:**
- `def get_tweet_relevance_filter()`


#### `twitter_intel_cache.py`

**Classes:**
- `class CachedTweet`
- `class IntelRelevance`
- `class TwitterIntelCache`
- `class TwitterIntelCacheEntry`

**Functions:**
- `def _get_cache_lock()`
- `def _get_tweet_relevance_filter()`
- `def get_social_sources_from_supabase()`
- `def get_twitter_intel_cache()`
- `def test_cache()`


### src/testing

#### `mocks.py`

**Classes:**
- `class Match`


### src/utils

#### `admin_tools.py`

**Functions:**
- `def format_debug_output()`
- `def generate_report()`
- `def generate_stats_dashboard()`
- `def get_report_summary()`
- `def get_stats_text_summary()`
- `def read_last_error_lines()`


#### `ai_parser.py`

**Functions:**
- `def _json_loads()`
- `def extract_json()`
- `def normalize_deep_dive_response()`
- `def parse_ai_json()`


#### `article_reader.py`

**Classes:**
- `class ArticleResult`

**Functions:**
- `def apply_deep_dive_to_results()`
- `def fetch_full_article()`
- `def should_deep_dive()`


#### `browser_fingerprint.py`

**Classes:**
- `class BrowserFingerprint`
- `class BrowserProfile`

**Functions:**
- `def get_fingerprint()`
- `def reset_fingerprint()`
- `def validate_header_consistency()`


#### `check_apis.py`

**Functions:**
- `def main()`
- `def print_err()`
- `def print_ok()`
- `def print_warn()`
- `def test_brave_api()`
- `def test_continental_orchestrator()`
- `def test_odds_api()`
- `def test_openrouter_api()`
- `def test_perplexity_api()`
- `def test_supabase_api()`
- `def test_tavily_api()`


#### `check_leagues.py`

**Functions:**
- `def main()`


#### `content_analysis.py`

**Classes:**
- `class AnalysisResult`
- `class ExclusionFilter`
- `class PositiveNewsFilter`
- `class RelevanceAnalyzer`

**Functions:**
- `def get_exclusion_filter()`
- `def get_positive_news_filter()`
- `def get_relevance_analyzer()`
- `def is_non_latin()`


#### `contracts.py`

**Classes:**
- `class Contract`
- `class ContractViolation`
- `class FieldSpec`

**Functions:**
- `def _is_valid_score()`
- `def _is_valid_url()`
- `def assert_contract()`
- `def get_contract()`
- `def validate_contract()`


#### `debug_funnel.py`

**Functions:**
- `def calculate_kelly_criterion()`
- `def check_active_continent()`
- `def check_market_veto()`
- `def main()`
- `def trace_match_pipeline()`


#### `discovery_queue.py`

**Classes:**
- `class DiscoveryItem`
- `class DiscoveryQueue`

**Functions:**
- `def get_discovery_queue()`
- `def reset_discovery_queue()`


#### `freshness.py`

**Classes:**
- `class FreshnessResult`

**Functions:**
- `def calculate_decay_multiplier()`
- `def calculate_minutes_old()`
- `def get_freshness_category()`
- `def get_freshness_tag()`
- `def get_full_freshness()`
- `def get_league_aware_freshness()`
- `def get_league_decay_rate()`
- `def parse_relative_time()`


#### `high_value_detector.py`

**Classes:**
- `class GarbageFilter`
- `class HighSignalDetector`
- `class SignalResult`
- `class SignalType`
- `class StructuredAnalysis`

**Functions:**
- `def get_garbage_filter()`
- `def get_high_signal_detector()`
- `def get_signal_detector()`


#### `http_client.py`

**Classes:**
- `class EarlyBirdHTTPClient`
- `class FallbackHTTPClient`
- `class RateLimiter`

**Functions:**
- `def get_http_client()`
- `def is_httpx_available()`
- `def is_requests_available()`
- `def reset_http_client()`


#### `inspect_fotmob.py`

**Functions:**
- `def get_match_details()`
- `def get_team_last_match()`
- `def inspect_stats()`
- `def main()`
- `def search_team()`


#### `intelligence_gate.py`

**Functions:**
- `def apply_intelligence_gate()`
- `def build_level_2_prompt()`
- `def get_keyword_count()`
- `def get_supported_languages()`
- `def level_1_keyword_check()`
- `def level_1_keyword_check_with_details()`
- `def level_2_translate_and_classify()`
- `def level_3_deep_reasoning()`
- `def parse_level_2_response()`
- `def print_gate_stats()`
- `def should_use_level_3()`


#### `odds_utils.py`

**Functions:**
- `def get_market_odds()`


#### `parallel_enrichment.py`

**Classes:**
- `class EnrichmentResult`

**Functions:**
- `def enrich_match_parallel()`


#### `radar_cross_validator.py`

**Classes:**
- `class CrossSourceValidator`
- `class PendingAlert`

**Functions:**
- `def get_cross_validator()`
- `def reset_cross_validator()`


#### `radar_enrichment.py`

**Classes:**
- `class EnrichmentContext`
- `class RadarLightEnricher`

**Functions:**
- `def enrich_radar_alert_async()`
- `def get_radar_enricher()`


#### `radar_odds_check.py`

**Classes:**
- `class OddsCheckResult`
- `class OddsMovementStatus`
- `class RadarOddsChecker`

**Functions:**
- `def check_odds_for_alert_async()`
- `def get_radar_odds_checker()`


#### `radar_prompts.py`

**Functions:**
- `def build_analysis_prompt_v2()`
- `def build_quick_check_prompt()`


#### `shared_cache.py`

**Classes:**
- `class SharedContentCache`

**Functions:**
- `def compute_content_hash()`
- `def compute_simhash()`
- `def get_shared_cache()`
- `def hamming_distance()`
- `def normalize_unicode()`
- `def normalize_url()`
- `def reset_shared_cache()`


#### `smart_cache.py`

**Classes:**
- `class CacheEntry`
- `class CacheMetrics`
- `class SmartCache`

**Functions:**
- `def cached_with_match_time()`
- `def clear_all_caches()`
- `def decorator()`
- `def get_all_cache_stats()`
- `def get_match_cache()`
- `def get_search_cache()`
- `def get_team_cache()`
- `def log_cache_stats()`
- `def refresh_worker()`
- `def wrapper()`


#### `startup_validator.py`

**Classes:**
- `class APIConnectivityResult`
- `class ConfigFileValidationResult`
- `class StartupValidationReport`
- `class StartupValidator`
- `class ValidationResult`
- `class ValidationStatus`

**Functions:**
- `def validate_startup()`
- `def validate_startup_detailed()`
- `def validate_startup_or_exit()`


#### `text_normalizer.py`

**Functions:**
- `def find_team_in_text()`
- `def fold_accents()`
- `def fuzzy_match_player()`
- `def fuzzy_match_team()`
- `def get_multilang_form_pattern()`
- `def get_team_aliases()`
- `def get_value_patterns()`
- `def normalize_for_matching()`
- `def normalize_unicode()`


#### `trafilatura_extractor.py`

**Classes:**
- `class ExtractionStats`

**Functions:**
- `def _clean_html_to_text()`
- `def _extract_raw_text()`
- `def _extract_with_regex()`
- `def extract_with_fallback()`
- `def extract_with_trafilatura()`
- `def get_extraction_stats()`
- `def get_extractor()`
- `def has_article_structure()`
- `def is_valid_html()`
- `def record_extraction()`


#### `url_normalizer.py`

**Classes:**
- `class NewsDeduplicator`

**Functions:**
- `def are_articles_similar()`
- `def extract_content_signature()`
- `def extract_key_words()`
- `def get_deduplicator()`
- `def get_proper_nouns()`
- `def get_url_hash()`
- `def normalize_url()`


#### `validators.py`

**Classes:**
- `class ValidationResult`

**Functions:**
- `def assert_valid_alert()`
- `def assert_valid_analysis()`
- `def assert_valid_news_item()`
- `def assert_valid_verification_request()`
- `def assert_valid_verification_result()`
- `def ensure_dict()`
- `def ensure_list()`
- `def fail()`
- `def ok()`
- `def safe_dict_get()`
- `def safe_get()`
- `def safe_list_get()`
- `def validate_alert_payload()`
- `def validate_analysis_result()`
- `def validate_batch()`
- `def validate_dict_has_keys()`
- `def validate_in_list()`
- `def validate_in_range()`
- `def validate_list_not_empty()`
- `def validate_news_item()`
- `def validate_non_empty_string()`
- `def validate_positive_number()`
- `def validate_verification_request()`
- `def validate_verification_result()`


---

## 📊 Statistics

- **Directories scanned:** 14
- **Python files analyzed:** 107
- **Total classes:** 197
- **Total functions:** 654

---

**End of Architecture Snapshot**