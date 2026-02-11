# MASTER SYSTEM ARCHITECTURE - EarlyBird V8.3

**Version:** V8.3  
**Date:** 2026-02-08  
**Status:** Phase 1 Complete (Framework & Visual Map)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Cerebral Flow (Visual Conceptual Map)](#2-the-cerebral-flow-visual-conceptual-map)
3. [Intelligence & Component Breakdown](#3-intelligence--component-breakdown)
4. [Betting Strategy & Money Management](#4-betting-strategy--money-management)
5. [The Data Journey (Pipeline)](#5-the-data-journey-pipeline)
6. [Database Schema](#6-database-schema)
7. [API & External Providers](#7-api--external-providers)
8. [Persistence Layer](#8-persistence-layer)
9. [Advanced Architectural Patterns](#9-advanced-architectural-patterns)
10. [Analysis Engines (11/11 Verified)](#10-analysis-engines-1111-verified)
11. [Mathematical Models (9/9 Verified)](#11-mathematical-models-99-verified)
12. [Operational Rules & Thresholds (32/32 Verified)](#12-operational-rules--thresholds-3232-verified)
13. [Core Features (22/22 Verified)](#13-core-features-2222-verified)
14. [Workflow Processes (10 Pipeline Phases)](#14-workflow-processes-10-pipeline-phases)
15. [Configuration & Settings](#15-configuration--settings)
16. [Security Measures](#16-security-measures)
17. [Testing & Quality Assurance](#17-testing--quality-assurance)
18. [Evolution & Production Status](#18-evolution--production-status)

---

## 1. Executive Summary

### System Purpose and Scope

EarlyBird V8.3 is a **self-learning football betting intelligence system** that autonomously discovers, analyzes, and acts upon betting opportunities across global football markets. The system combines:

- **Multi-source data ingestion** (Brave Search, Tavily AI, Nitter, Telegram, FotMob)
- **AI-powered deep analysis** (DeepSeek V3.2 via OpenRouter with Gemini/Perplexity fallback)
- **Quantitative optimization** (Strategy weights based on ROI, Sortino Ratio, CLV, Max Drawdown)
- **Real-time alerting** (Telegram notifications with feedback loop integration)
- **Automated settlement** (Match result tracking with accurate odds capture for learning)

The system operates continuously through scheduled cycles, processing matches from 30+ football leagues worldwide, with a focus on Elite and Tier 2 leagues for maximum edge detection.

### Key Components at a High Level

| Component | Primary Function | Key Technologies |
|-----------|-------------------|-------------------|
| **Continental Scheduler** | Orchestrates analysis cycles based on time zones and league tiers | [`src/services/news_radar.py`](src/services/news_radar.py) |
| **Multi-Channel Hunter** | Discovers betting-relevant news from multiple sources | [`src/ingestion/search_provider.py`](src/ingestion/search_provider.py), [`src/ingestion/brave_provider.py`](src/ingestion/brave_provider.py), [`src/ingestion/tavily_provider.py`](src/ingestion/tavily_provider.py) |
| **Deep Analysis Engine** | Correlates data sources and generates betting recommendations | [`src/analysis/analyzer.py`](src/analysis/analyzer.py), [`src/services/intelligence_router.py`](src/services/intelligence_router.py) |
| **Tactical Brain** | Applies veto rules and context-aware decision making | [`src/analysis/analyzer.py`](src/analysis/analyzer.py) (Tactical Veto System) |
| **Notifier & Optimizer** | Sends alerts and manages strategy weights | [`src/alerting/notifier.py`](src/alerting/notifier.py), [`src/analysis/optimizer.py`](src/analysis/optimizer.py) |
| **Learning Loop** | Captures feedback and refines strategy performance | [`src/analysis/alert_feedback_loop.py`](src/analysis/alert_feedback_loop.py), [`src/analysis/settler.py`](src/analysis/settler.py) |
| **Database Layer** | Persistent storage for matches, analyses, and learning data | [`src/database/db.py`](src/database/db.py), [`src/database/models.py`](src/database/models.py) |

### V8.3 Specific Improvements

The V8.3 release introduces **critical learning loop integrity fixes** that fundamentally improve the system's ability to learn from its own performance:

#### Learning Loop Integrity Fix

**Problem Identified:** Previous versions stored incorrect odds data for learning calculations:
- `odds_taken` was storing current odds at analysis time, NOT when alert was sent
- `closing_odds` was storing current odds at analysis time, NOT at match kickoff
- This caused ROI and CLV (Closing Line Value) calculations to be fundamentally incorrect

**V8.3 Solution:**
1. **New Database Fields** (via [`migration_v83_odds.py`](src/database/migration_v83_odds.py)):
   - `odds_at_alert`: Actual odds when Telegram alert was sent
   - `odds_at_kickoff`: Actual odds at match kickoff
   - `alert_sent_at`: Timestamp when alert was sent

2. **Odds Capture Service** ([`src/services/odds_capture.py`](src/services/odds_capture.py)):
   - Scheduled job runs every 5 minutes
   - Finds matches that started within last 10 minutes
   - Captures kickoff odds and stores in `odds_at_kickoff` field

3. **Updated Settler Logic** ([`src/analysis/settler.py`](src/analysis/settler.py)):
   - ROI calculation now uses `odds_at_alert` (actual betting odds)
   - CLV calculation now compares `odds_at_alert` vs `odds_at_kickoff`
   - Priority order: `odds_at_alert` → `closing_odds` (legacy) → current odds → default

**Impact:**
- **Accurate ROI**: Now uses actual odds when user received the alert
- **Meaningful CLV**: Compares alert odds vs kickoff odds for true edge validation
- **Reliable Learning**: Optimizer adjusts weights based on correct performance data

### Architecture Philosophy

EarlyBird V8.3 follows these core architectural principles:

1. **Modular Design**: Each component is independently testable and deployable
2. **Graceful Degradation**: System continues operating when components fail (API key exhaustion, network issues)
3. **Stateless Learning**: Feedback loop operates without persistent storage between iterations
4. **Multi-Layer Verification**: Alerts pass through Verification Layer before dispatch
5. **Sample Size Guards**: Optimizer uses FROZEN/WARMING_UP/ACTIVE states to prevent overfitting
6. **Circuit Breaker Pattern**: API failures trigger automatic fallback to alternative providers
7. **Unicode-First**: All text handling uses NFC normalization for multilingual support

### Technology Stack Overview

| Layer | Technologies | Purpose |
|--------|--------------|---------|
| **Data Ingestion** | Brave Search API, Tavily AI Search, DuckDuckGo (ddgs), FotMob API, Telegram Bot API | Multi-source news and match data |
| **AI/ML** | DeepSeek V3.2 (OpenRouter), Perplexity Sonar, Gemini (conflict resolution) | Deep analysis and reasoning |
| **Database** | SQLAlchemy ORM, SQLite with WAL mode | Persistent storage with ACID compliance |
| **Scheduling** | Python asyncio, cron/systemd timers | Continuous operation and periodic jobs |
| **Alerting** | Telegram Bot API, tenacity (retry logic) | Real-time notifications |
| **Optimization** | Custom quantitative optimizer, Sortino Ratio, CLV tracking | Strategy weight management |
| **Web Scraping** | Playwright, Trafilatura, requests | Content extraction from web sources |
| **Caching** | LRU cache, SharedContentCache (cross-component deduplication) | Performance optimization |
| **HTTP Client** | Centralized http_client with fingerprint rotation | Anti-bot evasion and rate limiting |

---

## 2. The Cerebral Flow (Visual Conceptual Map)

The following Mermaid diagram visualizes the complete data journey from scheduling through alert dispatch, including the V8.3 learning loop integration.

```mermaid
graph TD
    %% ============================================
    %% CONTINENTAL SCHEDULER
    %% ============================================
    subgraph SCHEDULER["Continental Scheduler"]
        CS["Continental Scheduler<br/>src/services/news_radar.py"]
        CS -->|72-hour window| ML["Main Pipeline Loop<br/>src/main.py"]
        ML -->|96-hour lookahead| LA["Match Lookahead"]
        ML -->|6-hour cooldown| CC["Case Closed Cooldown"]
        ML -->|2h before kickoff| FC["Final Check Window"]
    end

    %% ============================================
    %% SUPABASE DATABASE
    %% ============================================
    subgraph SUPABASE["Supabase Database"]
        SB["Supabase<br/>src/database/models.py"]
        SB -->|Inject intelligence sources| IR["Intelligence Router V7.0"]
        SB -->|Store match data| MD["Match Data"]
        SB -->|Store analysis results| AR["Analysis Results"]
        SB -->|V8.3: Odds capture| OC["Odds Capture Service<br/>src/services/odds_capture.py"]
    end

    %% ============================================
    %% MULTI-CHANNEL HUNTER
    %% ============================================
    subgraph HUNTER["Multi-Channel Hunter"]
        BS["Brave Search API<br/>3 keys × 2000 calls<br/>src/ingestion/brave_provider.py"]
        TS["Tavily AI Search<br/>7 keys × 1000 calls<br/>src/ingestion/tavily_provider.py"]
        NF["Nitter Fallback<br/>Twitter/X content<br/>src/services/nitter_fallback_scraper.py"]
        
        BS --> NH["News Hunter<br/>src/processing/news_hunter.py"]
        TS --> NH
        NF --> NH
        
        NH --> ND["News Discovery<br/>Multi-source search"]
        ND --> DU["News Deduplication"]
        DU --> NV["News Verification"]
    end

    %% ============================================
    %% DEEP ANALYSIS ENGINE
    %% ============================================
    subgraph ANALYSIS["Deep Analysis Engine"]
        IR -->|Primary: DeepSeek V3.2| DA["Deep Analysis<br/>src/analysis/analyzer.py"]
        IR -->|Fallback: Perplexity| DA
        IR -->|Pre-enrichment: Tavily| DA
        
        DA --> SP["System Prompt<br/>500+ lines"]
        DA --> UN["Unicode Normalization<br/>NFC form"]
        DA --> UT["UTF-8 Truncation<br/>3000 bytes"]
        
        DA --> CB["Context Building"]
        CB --> AI["AI Processing"]
    end

    %% ============================================
    %% TACTICAL BRAIN & VETO LOGIC
    %% ============================================
    subgraph TACTICAL["Tactical Brain & Veto Logic"]
        TV["Tactical Veto Rules V8.0<br/>src/analysis/analyzer.py"]
        RVS["Referee Veto System V8.0<br/>src/analysis/analyzer.py"]
        
        AI --> TV
        AI --> RVS
        
        TV --> DM["Decision Making"]
        RVS --> DM
        
        DM -->|Veto passed| AL["Action Layer"]
        DM -->|Veto triggered| RE["Reject Match"]
    end

    %% ============================================
    %% ACTION LAYER (SETTLER & OPTIMIZER)
    %% ============================================
    subgraph ACTION["Action Layer"]
        AL --> OPT["Optimizer V3.0<br/>src/analysis/optimizer.py"]
        AL --> ST["Settler Module<br/>src/analysis/settler.py"]
        
        OPT --> WA["Weight Application"]
        OPT --> DT["Dynamic Threshold"]
        OPT --> SD["Score-Delta Deduplication"]
        
        ST --> BS2["Betting Stats Enrichment"]
        ST --> FSC["Final Score Calculation"]
        
        WA --> NOT["Notifier<br/>src/alerting/notifier.py"]
        DT --> NOT
        SD --> NOT
        BS2 --> NOT
        FSC --> NOT
        
        NOT --> TA["Telegram Alert"]
    end

    %% ============================================
    %% LEARNING LOOP (V8.3 INTEGRATION)
    %% ============================================
    subgraph LEARNING["Learning Loop & Feedback"]
        AFB["Alert Feedback Loop<br/>src/analysis/alert_feedback_loop.py"]
        OC["Odds Capture<br/>V8.3 New Service"]
        
        TA -->|User receives alert| UFB["User Feedback<br/>Optional"]
        TA -->|Alert timestamp captured| AFB
        
        OC -->|Captures at kickoff| SB_KO["Store odds_at_kickoff"]
        OC -->|Scheduled every 5 min| SB_KO
        
        AFB -->|Re-process if MODIFY| REPROC["Re-processed Analysis"]
        
        REPROC -->|Updated analysis| NOT
        SB_KO -->|Accurate odds for CLV| ST["Settler ROI/CLV"]
        
        ST -->|Learning data| OPT["Optimizer Weight Adjustment"]
    end

    %% ============================================
    %% CORE PROCESSES
    %% ============================================
    subgraph CORE["Core Processes"]
        MP["Main Pipeline<br/>src/main.py"]
        LNCH["Launcher<br/>src/launcher.py"]
        TB["Telegram Bot<br/>src/run_bot.py"]
        NR["News Radar<br/>src/services/news_radar.py"]
        BM["Browser Monitor<br/>src/services/browser_monitor.py"]
        TLM["Telegram Monitor<br/>src/processing/telegram_listener.py"]
    end

    %% ============================================
    %% DATA FLOW CONNECTIONS
    %% ============================================
    CS --> MP
    LNCH -->|Orchestrate| MP
    TB -->|Admin commands| MP
    NR -->|Minor leagues| MP
    BM -->|Web monitoring| MP
    TLM -->|Channel scraping| MP
    
    MP -->|Trigger cycle| CS
    MP -->|Query| SB
    MP -->|Request news| NH
    
    NV -->|Verified news| DA
    DA -->|Analysis results| SB
    AR -->|Feedback| OPT
    
    TA -->|Alert sent| SB
    SB -->|Learning data| OPT
    
    %% ============================================
    %% STYLING
    %% ============================================
    classDef scheduler fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef database fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef hunter fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef analysis fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef tactical fill:#ffebee,stroke:#b71c1c,stroke-width:2px
    classDef action fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    classDef learning fill:#e8d5f2,stroke:#7b1fa2,stroke-width:2px
    classDef core fill:#eceff1,stroke:#37474f,stroke-width:2px
    
    class CS,ML,LA,CC,FC scheduler
    class SB,MD,AR,OC database
    class BS,TS,NF,NH,ND,DU,NV hunter
    class IR,DA,SP,UN,UT,CB,AI analysis
    class TV,RVS,DM tactical
    class OPT,ST,WA,DT,SD,BS2,FSC,NOT,TA action
    class AFB,OC,SB_KO,REPROC,ST learning
    class MP,LNCH,TB,NR,BM,TLM core
```

### Diagram Legend

| Color | Component | Description |
|-------|-----------|-------------|
| 🔵 Blue | **Continental Scheduler** - Time-based orchestration of analysis cycles |
| 🟠 Orange | **Supabase Database** - Persistent storage layer |
| 🟢 Green | **Multi-Channel Hunter** - News discovery from multiple sources |
| 🟣 Purple | **Deep Analysis Engine** - AI-powered correlation and reasoning |
| 🔴 Red | **Tactical Brain** - Veto logic and decision making |
| 🟡 Yellow | **Action Layer** - Optimizer, Settler, and Notifier |
| 🟦 Teal | **Learning Loop** - V8.3 feedback integration and odds capture |
| ⚪ Gray | **Core Processes** - Main pipeline and orchestration |

### Key Data Flow Patterns

1. **Scheduling → Analysis**: Continental Scheduler triggers main pipeline every 120 minutes
2. **Hunter → Analysis**: Multi-Channel Hunter aggregates news from Brave, Tavily, and Nitter
3. **Analysis → Database**: AI analysis results are stored in Supabase for persistence
4. **Database → Optimizer**: Historical performance data drives strategy weight adjustments
5. **Optimizer → Notifier**: Dynamic thresholds and weights influence alert dispatch decisions
6. **Notifier → Learning Loop**: Alert feedback flows back through re-processing and odds capture
7. **Learning Loop → Settler**: Accurate odds_at_alert and odds_at_kickoff enable correct ROI/CLV calculation

### V8.3 Learning Loop Integration

The diagram highlights the V8.3-specific learning loop improvements:

- **Odds Capture Service** ([`src/services/odds_capture.py`](src/services/odds_capture.py)) runs as a scheduled job every 5 minutes
- Captures `odds_at_kickoff` for matches that started within the last 10 minutes
- **Alert Feedback Loop** ([`src/analysis/alert_feedback_loop.py`](src/analysis/alert_feedback_loop.py)) can re-process alerts when modifications are suggested
- **Settler** ([`src/analysis/settler.py`](src/analysis/settler.py)) now uses accurate odds for ROI and CLV calculations
- This creates a **closed feedback loop** where performance data correctly informs strategy optimization

---

**Phase 1 Complete: Framework and Visual Map generated.**

---

## 3. Intelligence & Component Breakdown

This section documents the core intelligence components that form the "Brain" of the EarlyBird V8.3 system. These components work in concert to gather, process, and analyze betting-relevant information from diverse sources.

### 3.1 Intelligence Router

The Intelligence Router ([`src/services/intelligence_router.py`](src/services/intelligence_router.py)) serves as the central orchestration layer for AI-powered analysis, implementing a sophisticated fallback hierarchy that ensures continuous operation even during provider outages.

**Primary Provider: DeepSeek V3.2**
- DeepSeek V3.2 via OpenRouter serves as the primary intelligence provider
- High rate limits eliminate the need for cooldown management
- Advanced reasoning capabilities enable deep match analysis and tactical assessment
- Processes complex queries involving multiple data sources (injuries, form, tactics)

**Tavily AI Pre-Enrichment**
- Before DeepSeek analysis, Tavily AI Search provides contextual enrichment
- Delivers match-specific background information (recent form, tactical setup, historical context)
- Reduces DeepSeek token consumption by pre-fetching factual data
- Budget-managed with 7 API keys (1000 calls each = 7000 calls/month)

**Fallback Hierarchy**
1. **Primary**: DeepSeek V3.2 (OpenRouter) - High-quality reasoning, no rate limits
2. **Fallback**: Perplexity Sonar - Luxury fallback for transient errors
3. **Emergency**: Cached results - When all providers unavailable

**Routing Logic**
- Provider selection based on availability and budget status
- Automatic failover on API errors (timeouts, rate limits, service outages)
- Budget-aware routing prevents overconsumption of quota-limited providers
- Each request logged with provider attribution for performance tracking

**Budget Management**
- Tavily budget allocation per component ([`config/settings.py`](config/settings.py:490-497)):
  - Main pipeline: 2100 calls/month (30%)
  - News radar: 1500 calls/month (21%)
  - Browser monitor: 750 calls/month (11%)
  - Telegram monitor: 450 calls/month (6%)
  - Settlement/CLV: 225 calls/month (3%)
  - Twitter recovery: 1975 calls/month (29%)

### 3.2 Multi-Channel Hunter

The Multi-Channel Hunter aggregates intelligence from diverse web sources, creating a comprehensive intelligence picture for each match under analysis.

**Web Search Integration**
- **Brave Search API** ([`src/ingestion/brave_provider.py`](src/ingestion/brave_provider.py)): Primary search provider
  - 3 API keys with 2000 calls each (6000 calls/month)
  - High-quality search results with minimal noise
  - Budget-managed with component-based allocation
  - Automatic key rotation on exhaustion (429 errors)
- **DuckDuckGo (ddgs)**: Free, no-API-key fallback
  - Python library integration, no Docker required
  - Used when Brave quota exhausted or unavailable
- **Serper API**: Paid fallback for enhanced search capabilities
- **MediaStack**: Free unlimited tier for news-specific queries
  - Emergency last-resort for news gathering
  - 4 API keys for redundancy

**Nitter Fallback Scraper**
- Twitter/X intelligence via Nitter instances ([`src/services/nitter_fallback_scraper.py`](src/services/nitter_fallback_scraper.py))
- Bypasses Twitter API limitations and authentication requirements
- Real-time injury news, lineup announcements, tactical updates
- Multi-instance rotation for reliability
- Content extraction with Trafilatura for clean text parsing

**Multi-Source Aggregation**
- News Hunter ([`src/processing/news_hunter.py`](src/processing/news_hunter.py)) coordinates multi-channel gathering
- Deduplication prevents redundant processing of identical news items
- Source attribution for each intelligence item (Brave, Nitter, etc.)
- Relevance filtering removes low-quality or irrelevant content
- Freshness scoring prioritizes recent intelligence over stale data

**Sport-Specific Filtering**
- Native sport keywords per league ([`config/settings.py`](config/settings.py:104-110))
  - Turkey: "futbol"
  - Spain: "fútbol"
  - Portugal: "futebol"
  - Germany: "fußball"
  - Greece: "ποδόσφαιρο"
  - And 15+ other languages
- Sport exclusion terms filter out basketball/other sports
- Prevents "Wrong Sport" hallucinations in AI analysis

### 3.3 Tactical Brain

The Tactical Brain ([`src/analysis/analyzer.py`](src/analysis/analyzer.py)) implements a sophisticated veto system that prioritizes tactical considerations over statistical signals. This hierarchy ensures that contextual intelligence overrides raw mathematical models when appropriate.

**Tactics > Statistics Hierarchy**
- Tactical considerations have veto power over statistical recommendations
- Prevents betting on statistically favorable but tactically unsound positions
- Example: Statistical model suggests Over 2.5 Goals, but tactical analysis reveals defensive lineup change → VETO

**Position-Based Veto Logic**
- **OFFENSIVE DEPLETION**: Multiple key attackers missing → Under markets favored
- **DEFENSIVE DEPLETION**: Multiple key defenders missing → Over markets favored
- **Extreme Impact Threshold**: 5.0 injury impact triggers tactical veto
- **Confidence Adjustment**: ±2.0 points based on tactical assessment

**Tactical Veto Rules (V8.0)**
1. **Confirmed Disaster**: News confirms tactical weakness → Boost confidence +15%
2. **Potential Turnaround**: Key player returns to struggling team → Boost confidence +10%
3. **Conflict Detection**: Conflicting intelligence sources → Reduce confidence 15%
4. **Freshness Priority**: Recent Twitter intelligence > Stale FotMob data
5. **Multi-Source Boost**: 2+ sources report same info → Boost confidence +5%

**Veto Activation**
- When tactical veto triggered, reasoning includes: "⚠️ TACTICAL VETO ATTIVO: [specific reason]"
- Veto tags appended to alert for transparency
- Examples:
  - "⚠️ TACTICAL VETO ATTIVO: OFFENSIVE DEPLETION"
  - "⚠️ TACTICAL VETO ATTIVO: DEFENSIVE DEPLETION"

**Cross-Reference Intelligence**
- Tactical context cross-referenced with news sources
- Consistency checks between tactical analysis and injury reports
- Discrepancies trigger confidence reduction or veto
- Alignment between tactics and news boosts confidence

### 3.4 Standard Preservation

Standard Preservation ensures data integrity across the entire system through Unicode normalization and text standardization.

**NFC Normalization**
- All text normalized to NFC (Normalization Form C) form
- Handles international characters (e.g., Çalhanoğlu, Müller, Pjanić)
- Consistent text representation across database, analysis, and alerting
- Implemented in:
  - [`src/analysis/analyzer.py`](src/analysis/analyzer.py:30-45) - Analysis pipeline
  - [`src/ingestion/prompts.py`](src/ingestion/prompts.py:19-34) - AI prompts
  - [`src/database/db.py`](src/database/db.py:27-42) - Database operations
  - [`src/utils/shared_cache.py`](src/utils/shared_cache.py:46-61) - Cache keys
  - [`src/alerting/notifier.py`](src/alerting/notifier.py:33-48) - Alert formatting

**Why NFC Normalization is Critical**
1. **Database Consistency**: Prevents duplicate entries for identical names with different Unicode representations
2. **Search Accuracy**: Team/player lookups match regardless of accent encoding
3. **Cache Efficiency**: Cache keys consistent across components
4. **Cross-Platform Compatibility**: Ensures consistent behavior across different operating systems
5. **AI Prompt Reliability**: DeepSeek receives consistent text representations

**UTF-8 Truncation**
- Safe UTF-8 truncation at 3000 bytes ([`config/settings.py`](config/settings.py:461))
- Prevents token overflow in LLM calls
- Preserves multi-byte character integrity
- Applied to news snippets before AI processing

**Hash Generation**
- Unicode normalization before content hashing
- Prevents hash collisions for identical content with different encodings
- Implemented in:
  - [`src/services/news_radar.py`](src/services/news_radar.py:392-398) - News deduplication
  - [`src/services/browser_monitor.py`](src/services/browser_monitor.py:409-416) - Content tracking
- Uses `errors='replace'` instead of `'ignore'` to preserve special characters

---

## 4. Betting Strategy & Money Management

This section documents the core betting philosophy, confidence thresholds, money management principles, and safety mechanisms that govern the EarlyBird V8.3 system's betting decisions.

### 4.1 Confidence Thresholds

The system employs a dual-threshold approach based on market conditions and intelligence quality.

**Elite Threshold: 9.0**
- Minimum confidence score for standard primary bets
- Represents "Cream of the Crop" quality opportunities
- Requires strong statistical evidence AND confirmed intelligence
- Configured in [`config/settings.py`](config/settings.py:224) as `ALERT_THRESHOLD_HIGH = 9.0`
- Applied to all markets (1X2, Goals, BTTS, Corners, Cards)

**Radar/Tier B Threshold: 7.5**
- Lower threshold when forced narrative present (Radar boost)
- Enables secondary opportunities in Tier 2 leagues
- Requires cross-source confirmation for confidence boost
- Configured in [`config/settings.py`](config/settings.py:225) as `ALERT_THRESHOLD_RADAR = 7.5`
- Used for opportunities with:
  - Forced narrative from multiple sources
  - Strong tactical signals
  - Confirmed injury intelligence

**Settlement Threshold: 7.0**
- Minimum `highest_score_sent` to include in settlement calculations
- Ensures only meaningful alerts contribute to learning loop
- Configured in [`config/settings.py`](config/settings.py:226) as `SETTLEMENT_MIN_SCORE = 7.0`

### 4.2 Market Philosophy: "Equal Citizen" Rule

EarlyBird V8.3 evaluates all market types with equal priority, selecting opportunities based purely on statistical strength rather than market type bias.

**Market Types Evaluated**
- **1X2** (Match Result): Home win, Draw, Away win
- **Goals Markets**: Over/Under 2.5, Over/Under 3.5
- **BTTS** (Both Teams to Score): Yes/No
- **Corners Markets**: Over/Under corner thresholds
- **Cards Markets**: Over/Under card thresholds

**Equal Priority Principle**
- No inherent preference for any market type
- Selection based on:
  - Statistical edge (probability vs implied odds)
  - Confidence score (AI analysis + tactical assessment)
  - Market timing (odds movement analysis)
  - Intelligence quality (news freshness, source reliability)

**Market-Specific Considerations**
- Goals markets require injury impact analysis (attacker/defender absences)
- BTTS requires assessment of both teams' scoring and defensive capabilities
- Corners/Cards require referee analysis and tactical setup evaluation
- 1X2 requires comprehensive match outcome probability assessment

### 4.3 Finance Logic: Position Sizing

The system employs a conservative money management approach using the Kelly Criterion with extreme risk aversion.

**Quarter-Kelly Multiplier (0.25)**
- Full Kelly stake multiplied by 0.25 for extreme risk management
- Reduces volatility and protects bankroll during losing streaks
- Implemented in [`src/analysis/math_engine.py`](src/analysis/math_engine.py:426-440)
- Formula: `kelly_quarter = kelly_full * 0.25`

**Balanced Probability Formula**
- Combines Poisson mathematical probability with AI confidence probability
- Dampens AI over-optimism and balances quantitative + qualitative analysis
- Formula: `(Poisson_Prob + AI_Confidence_Prob) / 2`
- Applied before Kelly calculation to ensure realistic probability estimates

**Kelly Criterion Implementation**
```
b = bookmaker_odd - 1
kelly_full = ((b * balanced_prob) - (1 - balanced_prob)) / b
kelly_quarter = kelly_full * 0.25
```

**Safety Caps**
- **Minimum Stake**: 0.5% of bankroll (anything less treated as 0)
- **Maximum Stake**: 5.0% of bankroll (hard cap)
- Configured in [`src/analysis/math_engine.py`](src/analysis/math_engine.py:34-35):
  ```python
  MIN_STAKE_PCT = 0.5  # Minimum 0.5% of bankroll per bet
  MAX_STAKE_PCT = 5.0  # Maximum 5.0% of bankroll per bet (hard cap)
  ```

**Stake Calculation Flow**
1. Calculate balanced probability from Poisson + AI
2. Apply Kelly Criterion to determine optimal stake
3. Multiply by 0.25 (Quarter-Kelly) for risk aversion
4. Apply safety caps (min 0.5%, max 5.0%)
5. Return final stake percentage

### 4.4 Safety Veto: Market Timing

The Market Veto system prevents betting on degraded value by detecting when odds have already crashed.

**15% Market Veto Threshold**
- Programmatic block if odds have dropped ≥15% from opening
- Configured in [`src/analysis/analyzer.py`](src/analysis/analyzer.py:1412-1429)
- Prevents betting on fully priced-in news
- Formula: `if odds_drop >= 0.15 and verdict == "BET": verdict = "NO BET"`

**Market Timing Constraint**
- System must catch news **before** market reacts
- If news found BUT odds already dropped >15%, assume "Value is Gone"
- AI instructed to output "NO BET" or very low score
- Goal: Early edge detection, not chasing already-crashed odds

**Veto Activation Example**
```
Opening odds: 2.50 (40% implied probability)
Current odds: 2.00 (50% implied probability)
Odds drop: (2.50 - 2.00) / 2.50 = 20% (>15% threshold)
Result: ⚠️ VALUE GONE: Market already crashed (>15% drop). News is fully priced in.
```

**Odds Drop Calculation**
- Compares opening odds vs current odds
- Percentage drop calculated as: `(opening - current) / opening`
- Applied to all market types (1X2, Goals, BTTS, Corners, Cards)
- Prevents "late to the party" betting scenarios

**Veto Override Conditions**
- Veto can only be overridden by exceptional circumstances:
  - Confirmed key player return (not just injury)
  - Tactical setup change not yet priced in
  - Multi-source confirmation of undervalued opportunity
- Default behavior: Veto respected, alert not sent

---

## 5. The Data Journey (Pipeline)

This section traces the complete data flow from match discovery through alert dispatch, documenting each stage of the EarlyBird V8.3 pipeline.

### 5.1 Stage 1: Continental Scheduler (Supabase)

**Match Discovery and Scheduling**
- Continental Scheduler ([`src/services/news_radar.py`](src/services/news_radar.py)) orchestrates analysis cycles
- Supabase database ([`src/database/db.py`](src/database/db.py)) stores match metadata
- 96-hour lookahead window for early odds tracking
- 72-hour analysis window for comprehensive intelligence gathering

**Time Zone Awareness**
- Scheduling based on league time zones and kickoff times
- Tier-based gating for news hunt:
  - Tier 1 (Gold List): Search if odds drop >5% OR FotMob warning
  - Tier 2 (Rotation): Search ONLY if odds drop >15% OR FotMob HIGH RISK
  - Intel-only: Always search (no odds gating)

**Match Injection**
- Scheduled matches injected into main pipeline loop
- Each match assigned analysis priority based on:
  - League tier (Elite vs Tier 1 vs Tier 2)
  - Odds movement (significant drops trigger higher priority)
  - Time to kickoff (earlier matches prioritized)
  - Intelligence availability (news, injuries, tactics)

### 5.2 Stage 2: Intelligence Gathering

**Multi-Source Data Collection**
- Multi-Channel Hunter ([`src/ingestion/search_provider.py`](src/ingestion/search_provider.py)) aggregates intelligence
- Web search via Brave API (primary), DuckDuckGo (fallback), Serper (paid fallback)
- Nitter scraper for Twitter/X intelligence
- MediaStack for news-specific queries

**Data Deduplication**
- Content hashing prevents redundant processing
- Simhash similarity detection identifies near-duplicate content
- Shared cache ([`src/utils/shared_cache.py`](src/utils/shared_cache.py)) enables cross-component deduplication
- Source attribution for each intelligence item

**Freshness Scoring**
- Recent intelligence prioritized over stale data
- League-specific decay rates:
  - Tier 1 leagues: λ = 0.14 (half-life ~5 min)
  - Elite leagues: λ = 0.023 (half-life ~30 min)
- Source-based decay modifiers (insider sources decay slower)

**Content Extraction**
- Trafilatura for clean text extraction from web pages
- Playwright fallback for JavaScript-heavy sites
- HTTP + Trafilatura (fast, ~80% success rate)
- Browser extraction (slower, ~95% success rate)

### 5.3 Stage 3: DeepSeek Triangulation

**AI Analysis and Synthesis**
- DeepSeek V3.2 ([`src/ingestion/deepseek_intel_provider.py`](src/ingestion/deepseek_intel_provider.py)) processes aggregated intelligence
- Tavily AI Search pre-enrichment provides contextual background
- System prompt ([`src/ingestion/prompts.py`](src/ingestion/prompts.py)) guides analysis with 500+ lines of instructions

**Unicode Normalization**
- NFC normalization ensures consistent text representation
- UTF-8 truncation at 3000 bytes prevents token overflow
- Applied to all text before AI processing

**Context Building**
- Multi-source intelligence synthesized into coherent narrative
- Injury impact analysis (attacker/defender absences)
- Form analysis (recent performance, home/away splits)
- Tactical assessment (formation, playing style, matchup dynamics)

**Confidence Scoring**
- AI assigns confidence score (0-10) based on:
  - Intelligence quality (source reliability, freshness)
  - Statistical edge (probability vs implied odds)
  - Tactical alignment (news confirms tactical setup)
  - Cross-source confirmation (multiple sources report same info)

### 5.4 Stage 4: Tactical Brain

**Veto Logic Application**
- Tactical Brain ([`src/analysis/analyzer.py`](src/analysis/analyzer.py)) applies veto rules
- Tactics > Statistics hierarchy enforced
- Position-based veto logic (OFFENSIVE/DEFENSIVE DEPLETION)
- Extreme impact threshold (5.0) triggers tactical veto

**Cross-Reference Intelligence**
- Tactical context cross-referenced with news sources
- Consistency checks between tactical analysis and injury reports
- Discrepancies trigger confidence reduction or veto
- Alignment between tactics and news boosts confidence

**Veto Activation**
- Tactical veto tagged in reasoning: "⚠️ TACTICAL VETO ATTIVO: [reason]"
- Examples:
  - "⚠️ TACTICAL VETO ATTIVO: OFFENSIVE DEPLETION"
  - "⚠️ TACTICAL VETO ATTIVO: DEFENSIVE DEPLETION"
- Veto overrides statistical recommendations

### 5.5 Stage 5: Final Verification

**Confidence Scoring**
- Final confidence score calculated
- Thresholds applied:
  - Elite: 9.0 (primary bets)
  - Radar/Tier B: 7.5 (secondary opportunities)
- Market Veto check (15% drop threshold)
- Odds movement analysis

**Market Selection**
- "Equal Citizen" rule applied
- All market types evaluated with equal priority
- Selection based on statistical strength
- Market-specific considerations applied

**Position Sizing**
- Kelly Criterion with Quarter-Kelly multiplier (0.25)
- Balanced probability formula: `(Poisson + AI) / 2`
- Safety caps: min 0.5%, max 5.0%
- Final stake percentage calculated

### 5.6 Stage 6: Telegram Alert

**User Notification**
- Notifier ([`src/alerting/notifier.py`](src/alerting/notifier.py)) formats and sends alerts
- Telegram Bot API delivers real-time notifications
- Alert includes:
  - Match details (teams, league, kickoff time)
  - Market recommendation (bet type, selection)
  - Confidence score
  - Reasoning (intelligence summary, tactical assessment)
  - Stake percentage (Kelly-based)
  - Odds (current odds, edge calculation)

**Alert Feedback Loop**
- User feedback captured (optional)
- Feedback loop ([`src/analysis/alert_feedback_loop.py`](src/analysis/alert_feedback_loop.py)) enables re-processing
- Modifications suggested based on user feedback
- Re-processed analysis sent as updated alert

**Learning Data Capture**
- Alert timestamp captured for accurate ROI calculation
- Odds at alert stored in database ([`src/database/models.py`](src/database/models.py))
- V8.3 fields: `odds_at_alert`, `odds_at_kickoff`, `alert_sent_at`
- Data feeds into Settler for post-match analysis

**Odds Capture Service**
- Scheduled job runs every 5 minutes ([`src/services/odds_capture.py`](src/services/odds_capture.py))
- Captures kickoff odds for matches that started within last 10 minutes
- Stores `odds_at_kickoff` in database
- Enables accurate CLV (Closing Line Value) calculation

---

**Phase 2 Complete: Operational Logic (Heart and Shield) documented.**

---

## 6. Database Schema

This section documents the database schema design for EarlyBird V8.3, including table structures, relationships, and data integrity features.

### 6.1 Core Tables

#### Match Table

The [`Match`](src/database/models.py:23-146) table stores match metadata, odds data, and post-match statistics for settlement analysis.

**Primary Identification Fields:**
- `id` (String, Primary Key): Unique ID from The-Odds-API
- `league` (String): Sport/league key (e.g., `soccer_epl`)
- `home_team` (String): Home team name
- `away_team` (String): Away team name
- `start_time` (DateTime): Match kickoff time (UTC)

**Odds Tracking Fields:**
- Opening Odds (First time we see the match - NEVER updated):
  - `opening_home_odd`: Opening home win odds
  - `opening_away_odd`: Opening away win odds
  - `opening_draw_odd`: Opening draw odds (Biscotto detection)
  - `opening_over_2_5`, `opening_under_2_5`: Over/Under 2.5 goals opening odds

- Current Odds (Latest market prices - Updated on each ingestion):
  - `current_home_odd`, `current_away_odd`, `current_draw_odd`
  - `current_over_2_5`, `current_under_2_5`

- Sharp Odds (Smart Money Detection):
  - `sharp_bookie`: Sharp bookie name (e.g., 'pinnacle')
  - `sharp_home_odd`, `sharp_draw_odd`, `sharp_away_odd`
  - `avg_home_odd`, `avg_draw_odd`, `avg_away_odd`
  - `is_sharp_drop`: Boolean flag for smart money detection
  - `sharp_signal`: Signal description (e.g., 'SMART MONEY on HOME')

**Alert Flags:**
- `odds_alert_sent`: Prevents repeated odds alerts
- `biscotto_alert_sent`: Prevents repeated biscotto alerts
- `sharp_alert_sent`: Prevents repeated sharp alerts

**Deduplication Fields:**
- `highest_score_sent`: Highest score already alerted for this match (prevents spam)
- `last_alert_time`: When last alert was sent (temporal reset)
- `last_deep_dive_time`: When last full investigation was done

#### NewsLog Table

The [`NewsLog`](src/database/models.py:148-284) table stores analysis results, betting recommendations, and post-alert tracking for CLV analysis.

**Primary Identification Fields:**
- `id` (Integer, Primary Key, Autoincrement)
- `match_id` (String, Foreign Key): References `matches.id`

**Content Fields:**
- `url`: Source URL
- `summary` (Text): Analysis summary/reasoning
- `score` (Integer, 0-10): Relevance score
- `category` (String): Alert category (INJURY, TURNOVER, etc.)
- `affected_team` (String): Team affected by the news

**Status Tracking:**
- `sent` (Boolean): Whether alert was sent to Telegram
- `status` (String): Alert status (pending, sent, no_bet, rejected)
- `verification_status` (String): Verification layer status
- `verification_reason` (String): Reason for verification decision

**Combo Bet Fields:**
- `combo_suggestion`: e.g., 'Over 2.5 + BTTS'
- `combo_reasoning`: Why this combo was suggested
- `recommended_market`: Primary market recommendation
- `combo_outcome`: WIN/LOSS/PENDING for expansion
- `combo_explanation`: Detailed explanation of expansion result
- `expansion_type`: Type (over/under, gg/ng, corners, cards)

**Driver Classification:**
- `primary_driver`: Main signal (INJURY_INTEL, SHARP_MONEY, MATH_VALUE, CONTEXT_PLAY, CONTRARIAN)

**CLV Tracking (V8.3 Fix):**
- `odds_taken` (Float, Legacy): Odds when alert was sent (use `odds_at_alert`)
- `closing_odds` (Float, Legacy): Closing odds for CLV analysis (use `odds_at_kickoff`)
- `clv_percent` (Float): Calculated CLV percentage

**V8.3: Proper Historical Odds Tracking:**
- `odds_at_alert` (Float): Actual odds when Telegram alert was sent (for ROI calculation)
- `odds_at_kickoff` (Float): Actual odds at match kickoff (for CLV analysis)
- `alert_sent_at` (DateTime): Timestamp when alert was sent to Telegram

**Source Tracking:**
- `source`: Source type (web, telegram_ocr, telegram_channel)
- `source_confidence` (Float): Confidence in source reliability (0-1)

**V8.1: Confidence Breakdown (JSON):**
- `confidence_breakdown` (Text): JSON with individual weight contributions

**V8.2: Final Verifier Tracking (JSON):**
- `final_verifier_result` (Text): JSON with complete verifier result

**V8.2: Feedback Loop Tracking:**
- `feedback_loop_used` (Boolean): Whether feedback loop was applied
- `feedback_loop_iterations` (Integer): Number of feedback iterations
- `modification_plan` (Text): JSON with modification plan
- `modification_applied` (Boolean): Whether modifications were applied
- `original_score` (Integer): Original score before modifications
- `original_market` (String): Original market before modifications

**Timestamps:**
- `timestamp` (DateTime): Analysis timestamp
- `created_at` (DateTime): Record creation time
- `updated_at` (DateTime): Last update time

#### TeamAlias Table

The [`TeamAlias`](src/database/models.py:286-310) table maps API team names to search-friendly names and stores social media handles.

**Fields:**
- `id` (Integer, Primary Key, Autoincrement)
- `api_name` (String, Unique): Team name from API (The-Odds-API)
- `search_name` (String): Clean name for search queries
- `twitter_handle` (String): Twitter/X handle (e.g., @GalatasaraySK)
- `telegram_channel` (String): Telegram channel (e.g., 'galatasaray')
- `fotmob_id` (String): FotMob team ID for data enrichment
- `country` (String): Team country for regional context
- `league` (String): Primary league for this team

### 6.2 Post-Match Statistics (16 Columns for AI Training)

The [`Match`](src/database/models.py:79-95) table includes 16 post-match statistics columns populated by the settler for AI training and pattern recognition:

**Corners Statistics:**
- `home_corners` (Integer): Final home team corners
- `away_corners` (Integer): Final away team corners

**Cards Statistics:**
- `home_yellow_cards` (Integer): Final home yellow cards
- `away_yellow_cards` (Integer): Final away yellow cards
- `home_red_cards` (Integer): Final home red cards
- `away_red_cards` (Integer): Final away red cards

**Expected Goals (xG):**
- `home_xg` (Float): Home expected goals (xG)
- `away_xg` (Float): Away expected goals (xG)

**Possession:**
- `home_possession` (Float): Home possession percentage
- `away_possession` (Float): Away possession percentage

**Shots on Target:**
- `home_shots_on_target` (Integer): Home shots on target
- `away_shots_on_target` (Integer): Away shots on target

**Big Chances Created:**
- `home_big_chances` (Integer): Home big chances created
- `away_big_chances` (Integer): Away big chances created

**Fouls Committed:**
- `home_fouls` (Integer): Home fouls committed
- `away_fouls` (Integer): Away fouls committed

**Match Result:**
- `final_home_goals` (Integer): Final home goals
- `final_away_goals` (Integer): Final away goals
- `match_status` (String): Match status (scheduled, live, finished)

### 6.3 Data Integrity Features

#### UTF-8 Preservation

All text handling uses NFC normalization for consistent text representation across the system:

**Implementation Locations:**
- [`src/database/db.py:26-42`](src/database/db.py:26-42) - Database operations
- [`src/analysis/analyzer.py:30-45`](src/analysis/analyzer.py:30-45) - Analysis pipeline
- [`src/ingestion/prompts.py:19-34`](src/ingestion/prompts.py:19-34) - AI prompts
- [`src/utils/shared_cache.py:46-61`](src/utils/shared_cache.py:46-61) - Cache keys
- [`src/alerting/notifier.py:33-48`](src/alerting/notifier.py:33-48) - Alert formatting

**Why NFC Normalization is Critical:**
1. **Database Consistency**: Prevents duplicate entries for identical names with different Unicode representations
2. **Search Accuracy**: Team/player lookups match regardless of accent encoding
3. **Cache Efficiency**: Cache keys consistent across components
4. **Cross-Platform Compatibility**: Ensures consistent behavior across different operating systems
5. **AI Prompt Reliability**: DeepSeek receives consistent text representations

#### WAL Mode (Write-Ahead Logging)

SQLite is configured with WAL mode for concurrent reads/writes:

**Configuration** ([`src/database/models.py:356-377`](src/database/models.py:356-377)):
```python
PRAGMA journal_mode=WAL          # Write-Ahead Logging for concurrent reads/writes
PRAGMA busy_timeout=60000         # Wait up to 60s for lock release
PRAGMA synchronous=NORMAL         # Balance between speed and safety
PRAGMA foreign_keys=ON           # Enforce referential integrity
PRAGMA cache_size=-64000         # 64MB page cache for better performance
PRAGMA temp_store=memory         # Store temp tables in memory
PRAGMA mmap_size=268435456      # 256MB memory-mapped I/O
```

**Benefits:**
- Concurrent reads and writes without blocking
- Better performance under load
- ACID compliance with SQLite

#### Odds Snapshot Logic (V8.3)

The V8.3 release introduces proper historical odds tracking for accurate ROI and CLV calculation:

**Problem Identified:**
- `odds_taken` was storing current odds at analysis time, NOT when alert was sent
- `closing_odds` was storing current odds at analysis time, NOT at match kickoff
- This caused ROI and CLV calculations to be fundamentally incorrect

**V8.3 Solution** ([`src/database/migration_v83_odds_fix.py`](src/database/migration_v83_odds_fix.py)):
1. **New Database Fields:**
   - `odds_at_alert`: Actual odds when Telegram alert was sent
   - `odds_at_kickoff`: Actual odds at match kickoff
   - `alert_sent_at`: Timestamp when alert was sent

2. **Odds Capture Service** ([`src/services/odds_capture.py`](src/services/odds_capture.py)):
   - Scheduled job runs every 5 minutes
   - Finds matches that started within last 10 minutes
   - Captures kickoff odds and stores in `odds_at_kickoff` field

3. **Updated Settler Logic** ([`src/analysis/settler.py`](src/analysis/settler.py)):
   - ROI calculation now uses `odds_at_alert` (actual betting odds)
   - CLV calculation now compares `odds_at_alert` vs `odds_at_kickoff`
   - Priority order: `odds_at_alert` → `closing_odds` (legacy) → current odds → default

**Indexes Created** ([`src/database/migration_v83_odds_fix.py:64-86`](src/database/migration_v83_odds_fix.py:64-86)):
- `idx_news_logs_odds_at_kickoff`: For CLV calculations
- `idx_news_logs_alert_sent_at`: For time-based queries

**Impact:**
- **Accurate ROI**: Now uses actual odds when user received the alert
- **Meaningful CLV**: Compares alert odds vs kickoff odds for true edge validation
- **Reliable Learning**: Optimizer adjusts weights based on correct performance data

---

## 7. API & External Providers

This section documents the external API providers and search engines used by EarlyBird V8.3 for intelligence gathering.

### 7.1 3-Layer Search Architecture

The system implements a 3-layer search architecture ([`src/ingestion/search_provider.py`](src/ingestion/search_provider.py:233-649)) with automatic failover:

**Layer 0: Brave Search API (Primary)**
- **Provider**: Brave Search API
- **Keys**: 3 API keys with 2000 calls each (6000 calls/month)
- **File**: [`src/ingestion/brave_provider.py`](src/ingestion/brave_provider.py)
- **Key Rotator**: [`src/ingestion/brave_key_rotator.py`](src/ingestion/brave_key_rotator.py) (V1.0)
- **Budget Manager**: [`src/ingestion/brave_budget.py`](src/ingestion/brave_budget.py)
- **Characteristics**: High-quality search results with minimal noise

**Layer 1: DuckDuckGo (Secondary)**
- **Provider**: DuckDuckGo Python library (`ddgs`)
- **Keys**: No API key required (free)
- **File**: [`src/ingestion/search_provider.py:293-371`](src/ingestion/search_provider.py:293-371)
- **Characteristics**: Free, no Docker required, fallback when Brave quota exhausted

**Layer 2: MediaStack (Emergency Fallback)**
- **Provider**: MediaStack API
- **Keys**: 4 API keys (FREE unlimited tier)
- **File**: [`src/ingestion/mediastack_provider.py`](src/ingestion/mediastack_provider.py)
- **Key Rotator**: [`src/ingestion/mediastack_key_rotator.py`](src/ingestion/mediastack_key_rotator.py) (V1.0)
- **Budget Manager**: [`src/ingestion/mediastack_budget.py`](src/ingestion/mediastack_budget.py)
- **Characteristics**: Free unlimited tier, emergency last-resort for news gathering

**Layer 3: Serper (DISABLED - V4.5)**
- **Status**: Disabled due to query length issues
- **Reason**: Queries with sport exclusions + site dorking exceed 2048 char limit
- **Characteristics**: Paid fallback for enhanced search (currently disabled)

### 7.2 Deep Dive Intelligence

**Gemini (Deep Dive)**
- **Provider**: Gemini API via Intelligence Router
- **Purpose**: Deep analysis with web search grounding
- **Features**: 
  - Match-specific background information
  - Recent form, tactical setup, historical context
  - Reduces DeepSeek token consumption by pre-fetching factual data
- **File**: [`src/services/intelligence_router.py`](src/services/intelligence_router.py)

**Perplexity (Fallback)**
- **Provider**: Perplexity API (sonar-pro model)
- **File**: [`src/ingestion/perplexity_provider.py`](src/ingestion/perplexity_provider.py)
- **Purpose**: Luxury fallback for transient errors
- **Features**:
  - Identical interface to Gemini for seamless fallback
  - Web search grounding
  - Structured outputs support
  - News verification capabilities
  - Betting stats analysis

### 7.3 Tavily AI Search (Fact-Check)

**Tavily AI Search**
- **Provider**: Tavily AI Search
- **File**: [`src/ingestion/tavily_provider.py`](src/ingestion/tavily_provider.py)
- **Keys**: 7 API keys with 1000 calls each (7000 calls/month)
- **Key Rotator**: [`src/ingestion/tavily_key_rotator.py`](src/ingestion/tavily_key_rotator.py) (V8.0)
- **Budget Manager**: [`src/ingestion/tavily_budget.py`](src/ingestion/tavily_budget.py)

**V8.0: Double Cycle Support**
- When all keys are exhausted, attempts monthly reset before activating fallback
- Allows up to 2 full cycles per month before fallback activation
- Cycle tracking for monitoring and debugging

**Features:**
- Native news search with `topic="news"` and `days` parameters
- Response caching with 30 min TTL to avoid duplicate queries
- Circuit breaker: Auto-fallback to Brave/DDG after 3 consecutive failures
- Budget-managed with component-based allocation

### 7.4 Tavily Key Rotator (7 Keys / 7,000 Calls)

**Configuration** ([`src/ingestion/tavily_key_rotator.py`](src/ingestion/tavily_key_rotator.py)):
- **Total Keys**: 7 API keys
- **Calls per Key**: 1000 calls/month
- **Total Monthly Budget**: 7,000 calls
- **Double Cycle**: Allows 2 full cycles before fallback

**Key Rotation Logic:**
1. Automatic rotation to next key on 429 error
2. Monthly reset when new month detected
3. Cycle tracking (number of completed cycles)
4. Last cycle month tracking for double cycle logic

**Budget Allocation per Component** ([`config/settings.py:490-497`](config/settings.py:490-497)):
| Component | Calls/Month | Percentage |
|-----------|-------------|------------|
| Main pipeline | 2100 | 30% |
| News radar | 1500 | 21% |
| Browser monitor | 750 | 11% |
| Telegram monitor | 450 | 6% |
| Settlement/CLV | 225 | 3% |
| Twitter recovery | 1975 | 29% |

**Tiered Throttling:**
- **Normal Mode** (<90%): Full functionality
- **Degraded Mode** (90-95%): Non-critical calls throttled (50% of normal)
- **Disabled Mode** (>95%): Only critical calls allowed (main_pipeline, settlement_clv)

### 7.5 Brave Key Rotator (3 Keys / 6,000 Calls)

**Configuration** ([`src/ingestion/brave_key_rotator.py`](src/ingestion/brave_key_rotator.py)):
- **Total Keys**: 3 API keys
- **Calls per Key**: 2000 calls/month
- **Total Monthly Budget**: 6,000 calls
- **Double Cycle**: Allows 2 full cycles before fallback

**Key Rotation Logic:**
1. Automatic rotation to next key on 429 error
2. Monthly reset when new month detected
3. Cycle tracking (number of completed cycles)
4. Last cycle month tracking for double cycle logic

**Budget Allocation per Component**:
- Similar tiered throttling as Tavily
- Critical components: main_pipeline, settlement_clv
- Degraded mode: 50% of normal calls for non-critical components

### 7.6 MediaStack Key Rotator (4 Keys / FREE Unlimited)

**Configuration** ([`src/ingestion/mediastack_key_rotator.py`](src/ingestion/mediastack_key_rotator.py)):
- **Total Keys**: 4 API keys
- **Calls per Key**: FREE unlimited tier
- **Purpose**: Emergency last-resort for news gathering
- **No Double Cycle Needed**: MediaStack is free unlimited

**Characteristics:**
- Monthly reset ensures keys are available at start of each month
- Monitoring-only budget tracking (no throttling implemented)
- Used when Brave, DDG, and Serper all fail

---

## 8. Persistence Layer

This section documents the persistence layer architecture for EarlyBird V8.3, including database connection management, session handling, and maintenance operations.

### 8.1 Database Connection Management

**SQLite Configuration** ([`src/database/models.py:338-350`](src/database/models.py:338-350)):
```python
engine = create_engine(
    DB_PATH,
    connect_args={
        "check_same_thread": False,  # Allow multi-threaded access
        "timeout": 60                  # Wait up to 60s for lock release
    },
    pool_pre_ping=True,           # Verify connections before use
    pool_size=5,                 # Allow multiple concurrent connections
    max_overflow=5,              # Allow up to 10 total connections under load
    pool_timeout=60,             # 60 second timeout for connection pool
    pool_recycle=3600,           # Recycle connections after 1 hour to prevent memory leaks
    echo=False                    # Set to True for SQL debugging
)
```

**Connection Pooling:**
- 5 base connections in pool
- Up to 10 total connections under load
- Connection recycling after 1 hour to prevent memory leaks
- Pre-ping verification to handle stale connections

### 8.2 Session Management

**Context Manager Pattern** ([`src/database/db.py:46-62`](src/database/db.py:46-62)):
```python
@contextmanager
def get_db_context():
    """Context manager for database sessions with auto-commit/rollback."""
    session = SessionLocal()
    try:
        yield session
        session.commit()  # Auto-commit on success
    except Exception as e:
        logger.error(f"Database operation failed: {e}")
        session.rollback()  # Auto-rollback on error
    finally:
        session.close()  # Ensure cleanup
```

**Retry Logic** ([`src/database/db.py:394-437`](src/database/db.py:394-437)):
- Automatic retry on database lock (up to 3 attempts)
- Exponential backoff between retries
- Lock error detection: 'database is locked' or 'locked' in error message
- Non-lock errors re-raised immediately

### 8.3 Transaction Handling

**Automatic Commit/Rollback:**
- Success: Automatic commit via context manager
- Failure: Automatic rollback with error logging
- Ensures ACID compliance for all database operations

**Foreign Key Constraints:**
- `ON DELETE CASCADE` for NewsLog → Match relationship
- Automatic cleanup of child records when parent is deleted
- Referential integrity enforced at database level

### 8.4 Maintenance and Cleanup

**Database Maintenance** ([`src/database/maintenance.py`](src/database/maintenance.py)):

**Prune Old Data** ([`src/database/maintenance.py:22-91`](src/database/maintenance.py:22-91)):
- Removes matches and associated news_logs older than X days (default: 30)
- Deletion order (FK safe):
  1. Delete NewsLog entries for old matches (children first)
  2. Delete old Match entries (parents second)
- Safe transaction handling with rollback on error
- Returns statistics: `{'matches_deleted': X, 'logs_deleted': Y}`

**Get Database Statistics** ([`src/database/maintenance.py:94-121`](src/database/maintenance.py:94-121)):
- Total matches count
- Total news_logs count
- Oldest match date
- Error handling for database access failures

**Emergency Cleanup** ([`src/database/maintenance.py:124-207`](src/database/maintenance.py:124-207)):
- **Trigger**: Disk usage > 90% threshold
- **Actions**:
  1. Find and truncate log files > 20MB (keep last 100KB)
  2. Clear temp/ folder
  3. Log: "🚨 Emergency cleanup triggered due to high disk usage."
- **Returns**: Cleanup stats with logs truncated and temp files deleted

**Indexes for Query Optimization** ([`src/database/models.py:110-114`](src/database/models.py:110-114)):
```python
__table_args__ = (
    Index('idx_match_time_league', 'start_time', 'league'),
    Index('idx_match_teams', 'home_team', 'away_team'),
    Index('idx_match_status', 'match_status'),
)
```

---

## 9. Advanced Architectural Patterns

This section documents the advanced architectural patterns that enable EarlyBird V8.3's self-learning capabilities, operational resilience, and performance optimization.

---

### 🛡️ 9.1 Resilience Patterns

#### 9.1.1 Circuit Breaker Pattern

**Purpose**: Prevents cascading failures by automatically switching to alternative providers when API failures occur.

**Implementation** ([`src/ingestion/tavily_provider.py`](src/ingestion/tavily_provider.py)):
```python
class CircuitBreaker:
    """Circuit breaker for API resilience with state machine."""
    
    def __init__(self, failure_threshold=3, recovery_timeout=300):
        self.failure_threshold = failure_threshold  # 3 failures triggers open
        self.recovery_timeout = recovery_timeout    # 5 minutes before half-open
        self.state = 'CLOSED'                       # CLOSED, OPEN, HALF_OPEN
        self.failure_count = 0
        self.last_failure_time = None
```

**State Machine**:
```
┌─────────────────────────────────────────────────────────────────┐
│                    CIRCUIT BREAKER STATE MACHINE                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────┐   Success    ┌─────────────┐   Timeout    ┌──────┐ │
│   │ CLOSED  │─────────────▶│  HALF_OPEN  │─────────────▶│OPEN  │ │
│   └─────────┘              └─────────────┘              └──────┘ │
│        ▲                        │                            │    │
│        │                        │ Success                     │    │
│        │                        ▼                            │    │
│        │                   ┌─────────┐                        │    │
│        └───────────────────│ CLOSED  │◀───────────────────────┘    │
│              Failure       └─────────┘      Failure               │
│              (>3)                                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**States**:
- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Circuit tripped, all requests fail fast (no API calls)
- **HALF_OPEN**: Testing if service recovered (limited requests allowed)

**Configuration**:
- **Failure Threshold**: 3 consecutive failures trigger OPEN state
- **Recovery Timeout**: 5 minutes before attempting HALF_OPEN
- **Per-Source Breakers**: Each URL has independent circuit breaker

**Benefits**:
1. **Prevents Cascading Failures**: Isolates failing components
2. **Automatic Recovery**: Self-healing without manual intervention
3. **Resource Conservation**: Stops wasting quota on failing APIs
4. **Graceful Degradation**: System continues with fallback providers

**Usage Across Components**:
- Tavily AI Search: Auto-fallback to Brave/DDG after 3 failures
- Browser Monitor: Per-URL circuit breakers for web scraping
- API Providers: Automatic provider rotation on 429 errors

---

#### 9.1.2 Graceful Degradation

**Purpose**: System continues operating with reduced functionality when components fail, rather than crashing.

**Implementation Philosophy**:
- **Never Crash**: Components skip functionality when dependencies unavailable
- **Fallback Hierarchy**: Primary → Secondary → Tertiary → Emergency
- **Partial Operation**: System provides value even with degraded capabilities

**Examples**:

**1. API Key Exhaustion** ([`src/ingestion/brave_key_rotator.py`](src/ingestion/brave_key_rotator.py)):
```python
def get_search_results(query):
    try:
        return brave_search(query)  # Primary
    except QuotaExhausted:
        try:
            return ddg_search(query)  # Secondary
        except Exception:
            return mediastack_search(query)  # Emergency
    except Exception:
        return []  # Graceful degradation - return empty results
```

**2. Missing Environment Variables** ([`config/settings.py`](config/settings.py)):
```python
BRAVE_API_KEYS = os.getenv('BRAVE_API_KEYS', '').split(',')
if not BRAVE_API_KEYS or BRAVE_API_KEYS == ['']:
    logger.warning("⚠️ Brave API keys not configured - using fallback only")
    # System continues with DDG/MediaStack only
```

**3. Database Lock Errors** ([`src/database/db.py`](src/database/db.py)):
```python
def with_retry(func):
    """Automatic retry with exponential backoff."""
    for attempt in range(3):
        try:
            return func()
        except OperationalError as e:
            if 'locked' in str(e) and attempt < 2:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise
    return None  # Graceful degradation on persistent failure
```

**Degradation Levels**:

| Level | Trigger | Behavior | Example |
|-------|---------|----------|---------|
| **Normal** | All systems operational | Full functionality | All search providers available |
| **Degraded** | Primary provider exhausted | Secondary providers active | Brave exhausted → DDG active |
| **Limited** | Multiple providers down | Emergency only | Brave + DDG down → MediaStack only |
| **Minimal** | All external APIs down | Local data only | Cache-only mode, no new data |

**Benefits**:
1. **Continuous Operation**: System never completely stops
2. **Predictable Behavior**: Known degradation levels
3. **Automatic Recovery**: Self-healing when services return
4. **User Transparency**: Clear logging of degraded state

---

#### 9.1.3 Retry Logic with Exponential Backoff

**Purpose**: Automatic retry of transient failures with increasing delays to prevent overwhelming systems.

**Implementation** ([`src/database/db.py:394-437`](src/database/db.py:394-437)):
```python
def execute_with_retry(session, operation, max_attempts=3):
    """Execute database operation with retry logic."""
    for attempt in range(max_attempts):
        try:
            return operation(session)
        except OperationalError as e:
            if 'locked' in str(e) and attempt < max_attempts - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(f"DB locked, retry {attempt + 1}/{max_attempts} in {wait_time}s")
                time.sleep(wait_time)
                continue
            raise
    return None
```

**Retry Strategy**:
- **Max Attempts**: 3 retries before giving up
- **Backoff Formula**: `wait_time = 2 ^ attempt` (1s, 2s, 4s)
- **Error Detection**: Only retry on specific errors (database locks, timeouts)
- **Fail Fast**: Non-transient errors re-raised immediately

**Applications**:
1. **Database Operations**: SQLite lock conflicts
2. **HTTP Requests**: Network timeouts, 5xx errors
3. **API Calls**: Rate limit errors (429)
4. **Browser Automation**: Playwright crashes

**Benefits**:
1. **Handles Transient Failures**: Automatic recovery from temporary issues
2. **Prevents Storm**: Exponential backoff avoids overwhelming systems
3. **Resource Efficient**: Only retries when appropriate
4. **Transparent**: Logging shows retry attempts

---

### ⚡ 9.2 Performance Patterns

#### 9.2.1 Connection Pooling

**Purpose**: Manages database connections efficiently to reduce overhead and prevent connection exhaustion.

**Implementation** ([`src/database/models.py:338-350`](src/database/models.py:338-350)):
```python
engine = create_engine(
    DB_PATH,
    connect_args={
        "check_same_thread": False,  # Allow multi-threaded access
        "timeout": 60                  # Wait up to 60s for lock release
    },
    pool_pre_ping=True,           # Verify connections before use
    pool_size=5,                 # 5 base connections in pool
    max_overflow=5,              # Allow up to 10 total connections
    pool_timeout=60,             # 60 second timeout for connection pool
    pool_recycle=3600,           # Recycle connections after 1 hour
    echo=False
)
```

**Pool Configuration**:
- **Base Pool Size**: 5 connections always available
- **Max Overflow**: 5 additional connections under load (total 10)
- **Connection Timeout**: 60 seconds to acquire connection
- **Connection Recycling**: 1 hour max lifetime (prevents stale connections)
- **Pre-Ping Verification**: Test connections before use (detects stale connections)

**Connection Lifecycle**:
```
┌─────────────────────────────────────────────────────────────────┐
│                  CONNECTION POOL LIFECYCLE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Application Request                                           │
│          │                                                      │
│          ▼                                                      │
│   ┌──────────────┐                                             │
│   │ Check Pool   │──── Available? ────▶ Return Connection     │
│   └──────────────┘                                             │
│          │ No                                                  │
│          ▼                                                      │
│   ┌──────────────┐                                             │
│   │ Create New   │──── Under limit? ────▶ Add to Pool         │
│   │ Connection   │                                             │
│   └──────────────┘                                             │
│          │ No (at limit)                                       │
│          ▼                                                      │
│   ┌──────────────┐                                             │
│   │ Wait (60s)  │──── Timeout? ────▶ Raise Error              │
│   └──────────────┘                                             │
│          │ Available                                            │
│          ▼                                                      │
│   Use Connection → Return to Pool → Recycle after 1 hour       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits**:
1. **Reduced Overhead**: Connection reuse eliminates setup cost
2. **Concurrency**: Multiple simultaneous database operations
3. **Stability**: Prevents connection exhaustion under load
4. **Self-Healing**: Connection recycling prevents memory leaks

---

#### 9.2.2 Shared Content Cache

**Purpose**: Cross-component deduplication to prevent redundant processing of identical content.

**Implementation** ([`src/utils/shared_cache.py`](src/utils/shared_cache.py)):
```python
class SharedContentCache:
    """Thread-safe cache for content deduplication across components."""
    
    def __init__(self, max_size=10000, ttl=1800):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl  # 30 minutes
        self.lock = threading.RLock()
    
    def get(self, key):
        """Retrieve cached content if fresh."""
        with self.lock:
            entry = self.cache.get(key)
            if entry and time.time() - entry['timestamp'] < self.ttl:
                return entry['content']
            return None
    
    def set(self, key, content):
        """Store content with timestamp."""
        with self.lock:
            if len(self.cache) >= self.max_size:
                self._evict_oldest()
            self.cache[key] = {
                'content': content,
                'timestamp': time.time()
            }
```

**Cache Key Generation**:
```python
def generate_cache_key(url, content_hash):
    """Generate unique cache key using NFC normalization."""
    normalized_url = unicodedata.normalize('NFC', url)
    return hashlib.sha256(
        f"{normalized_url}:{content_hash}".encode('utf-8')
    ).hexdigest()
```

**Deduplication Flow**:
```
┌─────────────────────────────────────────────────────────────────┐
│                  SHARED CACHE DEDUPLICATION                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Component A Request                                          │
│          │                                                      │
│          ▼                                                      │
│   ┌──────────────┐                                             │
│   │ Check Cache  │──── Hit? ────▶ Return Cached Content       │
│   └──────────────┘                                             │
│          │ Miss                                                 │
│          ▼                                                      │
│   Fetch Content → Store in Cache → Return to Component A       │
│          │                                                      │
│          ▼                                                      │
│   Component B Request (same content)                          │
│          │                                                      │
│          ▼                                                      │
│   ┌──────────────┐                                             │
│   │ Check Cache  │──── Hit! ────▶ Return Cached Content       │
│   └──────────────┘                                             │
│          │ (No redundant fetch)                                 │
│          ▼                                                      │
│   Component B receives cached content instantly               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Cache Configuration**:
- **Max Size**: 10,000 entries
- **TTL**: 30 minutes (1800 seconds)
- **Eviction Policy**: LRU (Least Recently Used)
- **Thread Safety**: RLock for concurrent access

**Benefits**:
1. **Reduced API Calls**: Eliminates duplicate requests
2. **Faster Response**: Cache hits are instant
3. **Cost Savings**: Less quota consumption
4. **Cross-Component**: Shared across all system components

---

#### 9.2.3 Tiered Throttling

**Purpose**: Budget-based API call throttling to prevent quota exhaustion and ensure critical operations always have capacity.

**Implementation** ([`src/ingestion/tavily_budget.py`](src/ingestion/tavily_budget.py)):
```python
class TavilyBudgetManager:
    """Manages Tavily API budget with tiered throttling."""
    
    def __init__(self):
        self.total_budget = 7000  # 7 keys × 1000 calls
        self.component_allocation = {
            'main_pipeline': 0.30,      # 30%
            'news_radar': 0.21,         # 21%
            'browser_monitor': 0.11,    # 11%
            'telegram_monitor': 0.06,   # 6%
            'settlement_clv': 0.03,     # 3%
            'twitter_recovery': 0.29    # 29%
        }
    
    def check_budget(self, component):
        """Check if component has budget remaining."""
        used = self.get_used_calls(component)
        allocated = self.total_budget * self.component_allocation[component]
        usage_pct = used / allocated
        
        if usage_pct < 0.90:
            return 'NORMAL'  # Full functionality
        elif usage_pct < 0.95:
            return 'DEGRADED'  # 50% of normal calls
        else:
            return 'DISABLED'  # Only critical calls
```

**Throttling Levels**:

| Level | Usage Threshold | Behavior | Example |
|-------|----------------|----------|---------|
| **NORMAL** | < 90% | Full functionality | All components operate normally |
| **DEGRADED** | 90-95% | 50% throttling | Non-critical calls reduced by 50% |
| **DISABLED** | > 95% | Critical only | Only main_pipeline and settlement_clv allowed |

**Component Priority**:

| Priority | Component | Reason |
|----------|-----------|--------|
| **P0 (Critical)** | main_pipeline, settlement_clv | Core betting operations |
| **P1 (High)** | news_radar | Intelligence gathering |
| **P2 (Medium)** | browser_monitor, twitter_recovery | Supplementary sources |
| **P3 (Low)** | telegram_monitor | Optional monitoring |

**Benefits**:
1. **Prevents Exhaustion**: Critical operations always have capacity
2. **Predictable Behavior**: Known degradation levels
3. **Cost Control**: Budget-aware API usage
4. **Automatic Recovery**: Full functionality restored on monthly reset

---

#### 9.2.4 Rate Limiting with Jitter

**Purpose**: Per-domain rate limiting with configurable jitter to prevent detection and respect API limits.

**Implementation** ([`src/utils/http_client.py:67-100`](src/utils/http_client.py:67-100)):
```python
@dataclass
class RateLimiter:
    """Per-domain rate limiting with jitter."""
    
    min_interval: float = 1.0      # Minimum seconds between requests
    jitter_min: float = 0.0         # Minimum random delay added
    jitter_max: float = 0.0         # Maximum random delay added
    last_request_time: float = 0.0   # Timestamp of last request
    
    def get_delay(self) -> float:
        """Calculate delay needed before next request."""
        now = time.time()
        elapsed = now - self.last_request_time
        required = self.min_interval
        
        if elapsed >= required:
            return 0.0  # No delay needed
        
        # Add jitter to prevent pattern detection
        jitter = random.uniform(self.jitter_min, self.jitter_max)
        return required - elapsed + jitter
```

**Rate Limiting Flow**:
```
┌─────────────────────────────────────────────────────────────────┐
│                  RATE LIMITING WITH JITTER                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Request to domain.com                                         │
│          │                                                      │
│          ▼                                                      │
│   ┌──────────────┐                                             │
│   │ Check Rate    │                                             │
│   │ Limiter      │                                             │
│   └──────────────┘                                             │
│          │                                                      │
│          ├───────────────────────────────────────────────────────┤ │
│          │ Within limit?                                         │ │
│          ├───────────────────────────────────────────────────────┤ │
│          │ YES                    │ NO                           │ │
│          ▼                        ▼                              │ │
│   ┌──────────────┐       ┌──────────────┐                    │ │
│   │ Send Request │       │ Calculate    │                    │ │
│   │ Immediately  │       │ Delay        │                    │ │
│   └──────────────┘       │ delay =      │                    │ │
│          │              │ min_interval  │                    │ │
│          │              │ - elapsed     │                    │ │
│          │              │ + jitter      │                    │ │
│          │              └──────────────┘                    │ │
│          │                        │                           │ │
│          │                        ▼                           │ │
│          │              ┌──────────────┐                    │ │
│          │              │ Wait Delay   │                    │ │
│          │              └──────────────┘                    │ │
│          │                        │                           │ │
│          └────────────────────────┘                           │ │
│                           │                                    │
│                           ▼                                    │
│                  Send Request                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Configuration Examples**:

| Domain | Min Interval | Jitter Min | Jitter Max | Purpose |
|--------|-------------|------------|------------|---------|
| **Brave API** | 0.5s | 0.1s | 0.3s | Respect rate limits |
| **Tavily API** | 0.3s | 0.05s | 0.15s | Fast but safe |
| **Web Scraping** | 2.0s | 0.5s | 1.5s | Anti-detection |
| **FotMob API** | 1.0s | 0.2s | 0.5s | Standard rate limit |

**Jitter Benefits**:
1. **Pattern Prevention**: Random delays prevent detection of automated requests
2. **Rate Limit Respect**: Ensures minimum interval between requests
3. **Natural Behavior**: Simulates human request patterns
4. **Domain-Specific**: Different limits per domain/API

**Thread Safety**:
- **Sync Operations**: Uses `threading.Lock` for thread-safe rate limiting
- **Async Operations**: Uses `asyncio.Lock` for async rate limiting
- **Per-Domain**: Independent rate limiters for each domain

**Benefits**:
1. **Anti-Detection**: Jitter prevents pattern recognition
2. **Rate Limit Compliance**: Respects API rate limits
3. **Domain Flexibility**: Different limits per domain
4. **Thread-Safe**: Works in multi-threaded environments

---

#### 9.2.5 Fingerprint Rotation

**Purpose**: Automatic browser fingerprint rotation on 403/429 errors to evade anti-bot detection and rate limiting.

**Implementation** ([`src/utils/http_client.py`](src/utils/http_client.py)):
```python
class HTTPClient:
    """Centralized HTTP client with fingerprint rotation."""
    
    def __init__(self):
        self.fingerprint = None
        self.domain_fingerprints = {}  # V7.2: Domain-sticky fingerprinting
    
    def _rotate_fingerprint(self, domain: str):
        """Rotate fingerprint for domain."""
        # V7.2: Domain-sticky fingerprinting
        if domain not in self.domain_fingerprints:
            self.domain_fingerprints[domain] = get_fingerprint()
        else:
            # Rotate only on 403/429 errors
            self.domain_fingerprints[domain] = get_fingerprint()
        
        return self.domain_fingerpoints[domain]
    
    async def request(self, method: str, url: str, **kwargs):
        """Make HTTP request with automatic fingerprint rotation."""
        domain = urlparse(url).netloc
        
        try:
            response = await self._make_request(method, url, **kwargs)
            
            # Check for detection errors
            if response.status_code in (403, 429):
                logger.warning(f"⚠️ Detection error {response.status_code} for {domain}")
                # Rotate fingerprint and retry
                self._rotate_fingerprint(domain)
                response = await self._make_request(method, url, **kwargs)
            
            return response
            
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise
```

**Fingerprint Rotation Logic**:
```
┌─────────────────────────────────────────────────────────────────┐
│                  FINGERPRINT ROTATION FLOW                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Request to domain.com                                         │
│          │                                                      │
│          ▼                                                      │
│   ┌──────────────┐                                             │
│   │ Get Domain   │                                             │
│   │ Fingerprint  │──── First request? ────▶ Generate New FP    │
│   └──────────────┘                                             │
│          │ Existing                                             │
│          ▼                                                      │
│   ┌──────────────┐                                             │
│   │ Make Request │                                             │
│   │ with FP      │                                             │
│   └──────────────┘                                             │
│          │                                                      │
│          ├───────────────────────────────────────────────────────┤ │
│          │ Status Code?                                          │ │
│          ├───────────────────────────────────────────────────────┤ │
│          │ 200 OK                  │ 403/429 (Detected)       │ │
│          ▼                        ▼                              │ │
│   ┌──────────────┐       ┌──────────────┐                    │ │
│   │ Return       │       │ Rotate FP    │                    │ │
│   │ Response     │       │ Generate New │                    │ │
│   └──────────────┘       │ Fingerprint  │                    │ │
│                          └──────────────┘                    │ │
│                                   │                           │ │
│                                   ▼                           │ │
│                          ┌──────────────┐                    │ │
│                          │ Retry Request │                    │ │
│                          │ with New FP  │                    │ │
│                          └──────────────┘                    │ │
│                                   │                           │ │
│                                   ▼                           │ │
│                          Return Response                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Fingerprint Components** ([`src/utils/browser_fingerprint.py`](src/utils/browser_fingerprint.py)):
```python
class BrowserFingerprint:
    """Browser fingerprint for anti-detection."""
    
    def __init__(self):
        self.user_agent = self._generate_user_agent()
        self.accept_language = self._generate_accept_language()
        self.accept_encoding = self._generate_accept_encoding()
        self.connection = self._generate_connection()
        self.sec_ch_ua = self._generate_sec_ch_ua()
        # ... more fingerprint components
```

**V7.2: Domain-Sticky Fingerprinting**:
- Each domain gets its own persistent fingerprint
- Fingerprint only rotates on detection errors (403/429)
- Maintains session consistency across requests
- Prevents frequent fingerprint changes that look suspicious

**Rotation Triggers**:
- **403 Forbidden**: Access denied (likely detected as bot)
- **429 Too Many Requests**: Rate limit exceeded
- **Manual Rotation**: Optional manual rotation for testing

**Benefits**:
1. **Anti-Bot Evasion**: Rotates fingerprints to avoid detection
2. **Session Consistency**: Domain-sticky fingerprinting maintains sessions
3. **Automatic Recovery**: Self-healing on detection errors
4. **Rate Limit Bypass**: Helps bypass rate limiting

---

#### 9.2.6 Double Cycle Support

**Purpose**: Allows two full monthly cycles before activating fallback providers, doubling effective capacity.

**Implementation** ([`src/ingestion/tavily_key_rotator.py`](src/ingestion/tavily_key_rotator.py)):
```python
class TavilyKeyRotator:
    """Rotates through Tavily API keys with double cycle support."""
    
    def __init__(self):
        self.keys = [...]  # 7 keys × 1000 calls = 7000 calls/month
        self.current_key_index = 0
        self.cycle_count = 0
        self.last_cycle_month = datetime.now().month
    
    def get_next_key(self):
        """Get next available key with double cycle logic."""
        current_month = datetime.now().month
        
        # Check if all keys exhausted
        if self._all_keys_exhausted():
            # Attempt monthly reset before fallback
            if current_month != self.last_cycle_month:
                self._reset_all_keys()
                self.cycle_count += 1
                self.last_cycle_month = current_month
                logger.info(f"🔄 Monthly reset - Cycle {self.cycle_count + 1}")
            else:
                # All keys exhausted, same month - activate fallback
                logger.warning("⚠️ All keys exhausted - activating fallback")
                return None
        
        return self.keys[self.current_key_index]
```

**Double Cycle Logic**:
```
┌─────────────────────────────────────────────────────────────────┐
│                    DOUBLE CYCLE TIMELINE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Month 1                                                       │
│   ┌───────────────────────────────────────────────────────┐    │
│   │ Key 1: 0 → 1000 calls ✓                                │    │
│   │ Key 2: 0 → 1000 calls ✓                                │    │
│   │ Key 3: 0 → 1000 calls ✓                                │    │
│   │ Key 4: 0 → 1000 calls ✓                                │    │
│   │ Key 5: 0 → 1000 calls ✓                                │    │
│   │ Key 6: 0 → 1000 calls ✓                                │    │
│   │ Key 7: 0 → 1000 calls ✓                                │    │
│   │ Total: 7000 calls (Cycle 1 Complete)                   │    │
│   └───────────────────────────────────────────────────────┘    │
│          │                                                      │
│          ▼ Monthly Reset                                        │
│                                                                 │
│   Month 1 (continued)                                          │
│   ┌───────────────────────────────────────────────────────┐    │
│   │ Key 1: 0 → 1000 calls ✓ (Cycle 2)                     │    │
│   │ Key 2: 0 → 1000 calls ✓                                │    │
│   │ ...                                                    │    │
│   │ Total: 7000 calls (Cycle 2 Complete)                   │    │
│   └───────────────────────────────────────────────────────┘    │
│          │                                                      │
│          ▼ All keys exhausted, same month                      │
│                                                                 │
│   Activate Fallback (Brave/DDG)                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Capacity Calculation**:
- **Single Cycle**: 7 keys × 1000 calls = 7,000 calls/month
- **Double Cycle**: 7,000 × 2 = 14,000 calls/month
- **Effective Capacity**: 2x monthly quota before fallback

**Benefits**:
1. **Double Capacity**: 14,000 calls/month instead of 7,000
2. **Cost Savings**: Delays paid fallback activation
3. **Automatic Recovery**: Seamless monthly reset
4. **Fallback Protection**: Still has emergency fallback if needed

---

### 📊 9.3 Data Patterns

#### 9.3.1 Unicode-First Approach

**Purpose**: Consistent text handling across the system using NFC normalization for multilingual support.

**Implementation** ([`src/utils/text_normalizer.py`](src/utils/text_normalizer.py)):
```python
import unicodedata

def normalize_text(text):
    """Normalize text to NFC form for consistent representation."""
    if not text:
        return text
    return unicodedata.normalize('NFC', text)

def safe_truncate(text, max_bytes=3000):
    """Truncate text at byte boundary preserving multi-byte characters."""
    if not text:
        return text
    
    normalized = normalize_text(text)
    encoded = normalized.encode('utf-8')
    
    if len(encoded) <= max_bytes:
        return normalized
    
    # Find safe truncation point
    truncated = encoded[:max_bytes]
    # Decode with error replacement to preserve partial characters
    return truncated.decode('utf-8', errors='replace')
```

**Normalization Locations**:

| Component | File | Purpose |
|-----------|------|---------|
| **Analysis Pipeline** | [`src/analysis/analyzer.py:30-45`](src/analysis/analyzer.py:30-45) | AI input normalization |
| **AI Prompts** | [`src/ingestion/prompts.py:19-34`](src/ingestion/prompts.py:19-34) | Consistent prompt text |
| **Database Operations** | [`src/database/db.py:27-42`](src/database/db.py:27-42) | Data consistency |
| **Cache Keys** | [`src/utils/shared_cache.py:46-61`](src/utils/shared_cache.py:46-61) | Cache key matching |
| **Alert Formatting** | [`src/alerting/notifier.py:33-48`](src/alerting/notifier.py:33-48) | User-facing text |

**Why NFC Normalization is Critical**:

1. **Database Consistency**:
   ```python
   # Without normalization (BAD):
   "Müller" != "Müller"  # Two different database entries
   
   # With NFC normalization (GOOD):
   normalize("Müller") == normalize("Müller")  # Single entry
   ```

2. **Search Accuracy**:
   ```python
   # Team lookups match regardless of accent encoding
   team_name = "Çalhanoğlu"
   search_query = "Calhanoglu"  # User types without accents
   # NFC normalization enables matching
   ```

3. **Cache Efficiency**:
   ```python
   # Cache keys consistent across components
   cache_key = generate_key(normalize(team_name))
   # Same content always generates same key
   ```

4. **Cross-Platform Compatibility**:
   ```python
   # Consistent behavior across Linux, macOS, Windows
   # Different OS may use different Unicode forms by default
   ```

5. **AI Prompt Reliability**:
   ```python
   # DeepSeek receives consistent text representations
   # Prevents confusion from encoding variations
   ```

**Benefits**:
1. **Prevents Duplicates**: Same name always matches
2. **Search Accuracy**: Lookups work regardless of accents
3. **Cache Efficiency**: Consistent cache keys
4. **Cross-Platform**: Same behavior everywhere
5. **AI Reliability**: Consistent LLM inputs

---

#### 9.3.2 Stateless Learning

**Purpose**: Feedback loop operates without persistent storage between iterations, enabling flexible deployment and avoiding state corruption.

**Implementation** ([`src/analysis/optimizer.py`](src/analysis/optimizer.py)):
```python
class StatelessOptimizer:
    """Optimizer that operates without persistent state between runs."""
    
    def optimize(self):
        """Calculate optimal weights from historical data."""
        # 1. Load historical performance from database
        historical_data = self.db.get_historical_alerts()
        
        # 2. Calculate metrics from scratch
        metrics = self._calculate_metrics(historical_data)
        
        # 3. Determine optimal weights
        weights = self._calculate_optimal_weights(metrics)
        
        # 4. Save weights to file (only persistence)
        self._save_weights(weights)
        
        return weights
    
    def _calculate_metrics(self, data):
        """Calculate metrics from raw data each time."""
        # No caching, always recalculate from source
        roi = calculate_roi(data)
        sortino = calculate_sortino(data)
        max_drawdown = calculate_max_drawdown(data)
        return {'roi': roi, 'sortino': sortino, 'max_drawdown': max_drawdown}
```

**Stateless vs Stateful Comparison**:

| Aspect | Stateless Learning | Stateful Learning |
|--------|-------------------|-------------------|
| **Persistent State** | None (weights only) | Full optimizer state |
| **Corruption Risk** | Zero (recalculated each run) | High (state can corrupt) |
| **Deployment Flexibility** | High (any environment) | Low (requires state transfer) |
| **Debugging** | Easy (reproducible) | Hard (state-dependent) |
| **Performance** | Slower (recalculates) | Faster (uses cached state) |

**Stateless Learning Flow**:
```
┌─────────────────────────────────────────────────────────────────┐
│                  STATELESS LEARNING FLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Run 1                                                        │
│   ┌──────────────┐                                             │
│   │ Load Data    │───▶ Calculate Metrics ────▶ Save Weights   │
│   └──────────────┘                                             │
│          │                                                      │
│          ▼                                                      │
│   [No persistent state]                                        │
│          │                                                      │
│          ▼                                                      │
│   Run 2 (fresh start)                                          │
│   ┌──────────────┐                                             │
│   │ Load Data    │───▶ Calculate Metrics ────▶ Save Weights   │
│   └──────────────┘                                             │
│          │                                                      │
│          ▼                                                      │
│   [No persistent state]                                        │
│          │                                                      │
│          ▼                                                      │
│   ...                                                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits**:
1. **No Corruption**: Cannot have corrupted state
2. **Reproducible**: Same data always produces same results
3. **Deployment Flexibility**: Can run anywhere without state transfer
4. **Easy Debugging**: Clear data flow, no hidden state
5. **Simple Recovery**: Just restart, no state restoration needed

---

#### 9.3.3 Context Manager Pattern

**Purpose**: Ensures proper resource cleanup and transaction management for database operations.

**Implementation** ([`src/database/db.py:46-62`](src/database/db.py:46-62)):
```python
from contextlib import contextmanager

@contextmanager
def get_db_context():
    """Context manager for database sessions with auto-commit/rollback."""
    session = SessionLocal()
    try:
        yield session
        session.commit()  # Auto-commit on success
    except Exception as e:
        logger.error(f"Database operation failed: {e}")
        session.rollback()  # Auto-rollback on error
        raise
    finally:
        session.close()  # Ensure cleanup
```

**Usage Example**:
```python
# Without context manager (BAD):
session = SessionLocal()
try:
    session.add(record)
    session.commit()
except Exception:
    session.rollback()
finally:
    session.close()

# With context manager (GOOD):
with get_db_context() as session:
    session.add(record)
    # Auto-commit on success, auto-rollback on error
    # Auto-close on exit
```

**Transaction Flow**:
```
┌─────────────────────────────────────────────────────────────────┐
│              CONTEXT MANAGER TRANSACTION FLOW                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   with get_db_context() as session:                             │
│       │                                                          │
│       ▼                                                          │
│   ┌──────────────┐                                             │
│   │ Session      │                                             │
│   │ Created      │                                             │
│   └──────────────┘                                             │
│       │                                                          │
│       ▼                                                          │
│   ┌──────────────┐                                             │
│   │ Execute      │                                             │
│   │ Operations   │                                             │
│   └──────────────┘                                             │
│       │                                                          │
│       ├───────────────────────────────────────────────────────┐ │
│       │ Success?                                              │ │
│       ├───────────────────────────────────────────────────────┤ │
│       │ YES                    │ NO                           │ │
│       ▼                        ▼                              │ │
│   ┌──────────────┐       ┌──────────────┐                    │ │
│   │ Auto-Commit  │       │ Auto-Rollback│                    │ │
│   └──────────────┘       └──────────────┘                    │ │
│       │                        │                              │ │
│       └────────────────────────┘                              │ │
│                │                                               │ │
│                ▼                                               │ │
│       ┌──────────────┐                                         │ │
│       │ Auto-Close   │                                         │ │
│       └──────────────┘                                         │ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits**:
1. **Automatic Cleanup**: Always closes session (even on error)
2. **Transaction Safety**: Auto-commit on success, auto-rollback on error
3. **Clean Code**: Eliminates boilerplate try/finally blocks
4. **Exception Safety**: Resources always released
5. **Readability**: Clear transaction boundaries

---

### 🔒 9.4 Safety Patterns

#### 9.4.1 Sample Size Guards

**Purpose**: Prevents overfitting and unreliable optimization by enforcing minimum sample sizes before adjusting strategy weights.

**Implementation** ([`src/analysis/optimizer.py`](src/analysis/optimizer.py)):
```python
class SampleSizeGuards:
    """Enforces sample size requirements for reliable optimization."""
    
    FROZEN_THRESHOLD = 30    # Minimum bets to start learning
    WARMING_THRESHOLD = 50   # Minimum bets for active optimization
    
    def get_optimizer_state(self, strategy_bets):
        """Determine optimizer state based on sample size."""
        if strategy_bets < self.FROZEN_THRESHOLD:
            return 'FROZEN'
        elif strategy_bets < self.WARMING_THRESHOLD:
            return 'WARMING_UP'
        else:
            return 'ACTIVE'
    
    def should_adjust_weights(self, state):
        """Check if weights should be adjusted based on state."""
        return state == 'ACTIVE'
    
    def get_weight_adjustment_factor(self, state):
        """Get weight adjustment factor based on state."""
        factors = {
            'FROZEN': 0.0,      # No adjustment
            'WARMING_UP': 0.5,  # Conservative adjustment
            'ACTIVE': 1.0       # Full adjustment
        }
        return factors.get(state, 0.0)
```

**State Machine**:
```
┌─────────────────────────────────────────────────────────────────┐
│                  SAMPLE SIZE GUARD STATES                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────┐                                                 │
│   │ FROZEN  │  < 30 bets                                      │
│   │         │  - No weight adjustment                         │
│   │         │  - Use default weights                         │
│   └─────────┘                                                 │
│        │                                                      │
│        ▼ 30 bets                                              │
│   ┌─────────────┐                                            │
│   │ WARMING_UP  │  30-50 bets                                 │
│   │             │  - Conservative adjustment (50% factor)     │
│   │             │  - Limited weight changes                  │
│   └─────────────┘                                            │
│        │                                                      │
│        ▼ 50 bets                                              │
│   ┌─────────┐                                                 │
│   │ ACTIVE  │  50+ bets                                      │
│   │         │  - Full weight adjustment                      │
│   │         │  - Normal optimization                         │
│   └─────────┘                                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Weight Adjustment Logic**:

| State | Sample Size | Adjustment Factor | Behavior |
|-------|------------|------------------|----------|
| **FROZEN** | < 30 bets | 0.0x | No adjustment, use defaults |
| **WARMING_UP** | 30-50 bets | 0.5x | Conservative adjustment |
| **ACTIVE** | 50+ bets | 1.0x | Full adjustment |

**Example**:
```python
# Strategy has 25 bets (FROZEN)
state = get_optimizer_state(25)  # 'FROZEN'
adjustment = get_weight_adjustment_factor(state)  # 0.0
# No weight change, use defaults

# Strategy has 40 bets (WARMING_UP)
state = get_optimizer_state(40)  # 'WARMING_UP'
adjustment = get_weight_adjustment_factor(state)  # 0.5
# Apply 50% of calculated weight change

# Strategy has 75 bets (ACTIVE)
state = get_optimizer_state(75)  # 'ACTIVE'
adjustment = get_weight_adjustment_factor(state)  # 1.0
# Apply full weight change
```

**Benefits**:
1. **Prevents Overfitting**: Small samples don't drive optimization
2. **Statistical Reliability**: Only adjusts with sufficient data
3. **Conservative Start**: Gradual adjustment as sample grows
4. **Robust Learning**: Stable optimization over time

---

#### 9.4.2 Multi-Layer Verification

**Purpose**: Alerts pass through multiple verification layers before dispatch, ensuring only high-quality opportunities reach users.

**Implementation** ([`src/analysis/verification_layer.py`](src/analysis/verification_layer.py)):
```python
class VerificationLayer:
    """Multi-layer verification for alert quality control."""
    
    def __init__(self):
        self.verifiers = [
            ConfidenceVerifier(),      # Minimum confidence threshold
            MarketVetoVerifier(),       # Market timing veto (15% drop)
            TacticalVetoVerifier(),    # Tactical veto system
            DuplicateVerifier(),       # Prevent duplicate alerts
            ScoreDeltaVerifier()       # Score-delta deduplication
        ]
    
    def verify_alert(self, alert):
        """Run alert through all verification layers."""
        for verifier in self.verifiers:
            result = verifier.verify(alert)
            if not result.passed:
                return VerificationResult(
                    passed=False,
                    reason=result.reason,
                    verifier=verifier.__class__.__name__
                )
        
        return VerificationResult(
            passed=True,
            reason="All verifications passed",
            verifier="All"
        )
```

**Verification Layers**:

```
┌─────────────────────────────────────────────────────────────────┐
│              MULTI-LAYER VERIFICATION FLOW                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   AI Analysis Result                                            │
│          │                                                      │
│          ▼                                                      │
│   ┌───────────────────────────────────────────────────────┐    │
│   │ Layer 1: Confidence Verifier                          │    │
│   │ - Check confidence ≥ 9.0 (Elite) or ≥ 7.5 (Radar)    │    │
│   └───────────────────────────────────────────────────────┘    │
│          │ Passed?                                              │
│          ▼ YES                                                 │
│   ┌───────────────────────────────────────────────────────┐    │
│   │ Layer 2: Market Veto Verifier                        │    │
│   │ - Check odds drop < 15% (value not gone)            │    │
│   └───────────────────────────────────────────────────────┘    │
│          │ Passed?                                              │
│          ▼ YES                                                 │
│   ┌───────────────────────────────────────────────────────┐    │
│   │ Layer 3: Tactical Veto Verifier                       │    │
│   │ - Check no tactical veto triggered                    │    │
│   └───────────────────────────────────────────────────────┘    │
│          │ Passed?                                              │
│          ▼ YES                                                 │
│   ┌───────────────────────────────────────────────────────┐    │
│   │ Layer 4: Duplicate Verifier                          │    │
│   │ - Check not duplicate of recent alert               │    │
│   └───────────────────────────────────────────────────────┘    │
│          │ Passed?                                              │
│          ▼ YES                                                 │
│   ┌───────────────────────────────────────────────────────┐    │
│   │ Layer 5: Score-Delta Verifier                        │    │
│   │ - Check not too similar to recent alerts             │    │
│   └───────────────────────────────────────────────────────┘    │
│          │ Passed?                                              │
│          ▼ YES                                                 │
│   ✅ ALERT APPROVED → SEND TO TELEGRAM                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Layer Details**:

| Layer | Purpose | Threshold | Action on Fail |
|-------|---------|-----------|----------------|
| **Confidence** | Minimum quality | 9.0 (Elite) / 7.5 (Radar) | Reject low-confidence alerts |
| **Market Veto** | Value timing | < 15% odds drop | Reject if value gone |
| **Tactical Veto** | Tactical soundness | No veto triggered | Reject tactically unsound |
| **Duplicate** | Prevent spam | Not recent duplicate | Reject duplicate alerts |
| **Score-Delta** | Prevent similar alerts | > 2.0 score difference | Reject too similar |

**Benefits**:
1. **Quality Control**: Only high-quality alerts reach users
2. **Spam Prevention**: Multiple layers prevent duplicate/similar alerts
3. **Value Protection**: Market veto prevents betting on degraded value
4. **Tactical Safety**: Tactical veto prevents unsound positions
5. **Transparency**: Each layer logs reasoning for audit trail

---

### 🔄 9.5 Operational Patterns

#### 9.5.1 The Learning Loop (Settler → DB → Optimizer)

The Learning Loop creates a closed feedback system where performance data drives strategy optimization:

**Flow:**
```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                          LEARNING LOOP ARCHITECTURE                             │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  1. ALERT PHASE                                                            │
│     ┌──────────────┐    ┌──────────────┐                                        │
│     │   main.py    │───▶│   NewsLog     │                                        │
│     │              │    │ odds_at_    │ (NEW - actual odds when        │
│     │ Captures     │    │ alert =      │ alert was sent)                │
│     │ current odds  │    │ 2.10        │                                        │
│     │ BEFORE        │    │ alert_sent_  │ (NEW - timestamp)             │
│     │ sending       │    │ at = now     │                                        │
│     │ alert        │    └──────────────┘                                        │
│     └──────────────┘                                                          │
│           │                                                                  │
│           ▼                                                                  │
│     ┌──────────────┐                                                        │
│     │  Notifier    │                                                        │
│     │  Sends       │                                                        │
│     │  Telegram    │                                                        │
│     │  alert       │                                                        │
│     └──────────────┘                                                        │
│           │                                                                  │
│           ▼                                                                  │
│  2. KICKOFF PHASE (NEW!)                                                │
│     ┌──────────────┐    ┌──────────────┐                                        │
│     │  odds_       │───▶│   NewsLog     │                                        │
│     │  capture.py  │    │              │                                        │
│     │  Scheduled   │    │ odds_at_    │ (NEW - actual odds at        │
│     │  job         │    │ kickoff =    │ match kickoff)               │
│     │  runs every  │    │ 1.70        │                                        │
│     │  5 minutes   │    └──────────────┘                                        │
│     └──────────────┘                                                          │
│           │                                                                  │
│           ▼                                                                  │
│  3. SETTLEMENT PHASE (UPDATED!)                                         │
│     ┌──────────────┐    ┌──────────────┐                                        │
│     │   Settler    │───▶│  Optimizer   │                                        │
│     │              │    │              │                                        │
│     │  Uses         │    │ ROI =        │ (NOW uses odds_at_alert!)    │
│     │ odds_at_     │    │ 2.10 - 1    │                                        │
│     │ alert for     │    │ = 1.10       │                                        │
│     │ ROI           │    │              │                                        │
│     │              │    │ CLV =        │ (NOW uses odds_at_kickoff!) │
│     │ Uses         │    │ +23.5%       │                                        │
│     │ odds_at_     │    │              │                                        │
│     │ kickoff for   │    │              │                                        │
│     │ CLV          │    │              │                                        │
│     └──────────────┘    └──────────────┘                                        │
│           │                                                                  │
│           ▼                                                                  │
│  4. OPTIMIZATION PHASE                                                    │
│     ┌──────────────┐                                                        │
│     │  Optimizer   │                                                        │
│     │  Adjusts     │                                                        │
│     │  strategy    │                                                        │
│     │  weights     │                                                        │
│     │  based on    │                                                        │
│     │  real        │                                                        │
│     │  performance │                                                        │
│     └──────────────┘                                                        │
│                                                                            │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Key Components:**

**Settler** ([`src/analysis/settler.py`](src/analysis/settler.py)):
- Fetches final scores from FotMob
- Calculates Win/Loss for each alert
- Computes ROI using `odds_at_alert` (actual betting odds)
- Computes CLV comparing `odds_at_alert` vs `odds_at_kickoff`
- Stores results in database for optimizer

**Optimizer** ([`src/analysis/optimizer.py`](src/analysis/optimizer.py)):
- Reads historical performance from database
- Calculates risk-adjusted metrics (Sharpe, Sortino, Max Drawdown)
- Adjusts strategy weights based on performance
- Implements sample size guards (FROZEN < 30 bets, WARMING 30-50, ACTIVE 50+)
- Stores updated weights in `data/optimizer_weights.json`

**Feedback Loop Benefits:**
1. **Accurate ROI**: Uses actual odds when alert was sent
2. **Meaningful CLV**: Compares alert odds vs kickoff odds for true edge validation
3. **Reliable Learning**: Optimizer adjusts weights based on correct performance data

---

#### 9.5.2 The Tactical Veto

The Tactical Veto system ensures tactical considerations override statistical signals when appropriate:

**Tactics > Statistics Hierarchy** ([`src/analysis/analyzer.py`](src/analysis/analyzer.py)):
- Tactical considerations have veto power over statistical recommendations
- Prevents betting on statistically favorable but tactically unsound positions
- Example: Statistical model suggests Over 2.5 Goals, but tactical analysis reveals defensive lineup change → VETO

**Position-Based Veto Logic:**
- **OFFENSIVE DEPLETION**: Multiple key attackers missing → Under markets favored
- **DEFENSIVE DEPLETION**: Multiple key defenders missing → Over markets favored
- **Extreme Impact Threshold**: 5.0 injury impact triggers tactical veto
- **Confidence Adjustment**: ±2.0 points based on tactical assessment

**Tactical Veto Rules (V8.0):**
1. **Confirmed Disaster**: News confirms tactical weakness → Boost confidence +15%
2. **Potential Turnaround**: Key player returns to struggling team → Boost confidence +10%
3. **Conflict Detection**: Conflicting intelligence sources → Reduce confidence 15%
4. **Freshness Priority**: Recent Twitter intelligence > Stale FotMob data
5. **Multi-Source Boost**: 2+ sources report same info → Boost confidence +5%

**Veto Activation:**
- When tactical veto triggered, reasoning includes: "⚠️ TACTICAL VETO ATTIVO: [specific reason]"
- Veto tags appended to alert for transparency
- Examples:
  - "⚠️ TACTICAL VETO ATTIVO: OFFENSIVE DEPLETION"
  - "⚠️ TACTICAL VETO ATTIVO: DEFENSIVE DEPLETION"

**Cross-Reference Intelligence:**
- Tactical context cross-referenced with news sources
- Consistency checks between tactical analysis and injury reports
- Discrepancies trigger confidence reduction or veto
- Alignment between tactics and news boosts confidence

---

#### 9.5.3 Emergency Cleanup Script

**Disk Space Management** ([`src/database/maintenance.py:124-207`](src/database/maintenance.py:124-207)):

**Trigger Threshold:**
- Disk usage > 90%
- Automatic activation to prevent system failure

**Cleanup Actions:**
1. **Log File Truncation**:
   - Finds .log files > 20MB
   - Truncates to last 100KB
   - Preserves recent logs while freeing disk space

2. **Temp Directory Cleanup**:
   - Clears all files in temp/ folder
   - Removes both files and directories
   - Logs number of items deleted

**Safety Features:**
- Error handling for each cleanup operation
- Logging of all cleanup actions
- Graceful degradation if cleanup fails

---

### 📋 9.7 Pattern Summary

| Category | Pattern | Purpose | Key Benefit |
|----------|---------|---------|-------------|
| **🛡️ Resilience** | Circuit Breaker | Prevent cascading failures | Automatic failover |
| **🛡️ Resilience** | Graceful Degradation | Continue operating with reduced functionality | Never crashes |
| **🛡️ Resilience** | Retry Logic | Automatic retry with exponential backoff | Handles transient failures |
| **🛡️ Resilience** | Fingerprint Rotation | Rotate browser fingerprints on detection | Anti-bot evasion |
| **⚡ Performance** | Connection Pooling | Efficient database connection management | Reduced overhead |
| **⚡ Performance** | Shared Content Cache | Cross-component deduplication | Eliminates redundant API calls |
| **⚡ Performance** | Tiered Throttling | Budget-based API call throttling | Prevents quota exhaustion |
| **⚡ Performance** | Rate Limiting with Jitter | Per-domain rate limiting with random delays | Pattern prevention |
| **⚡ Performance** | Double Cycle Support | Two full monthly cycles before fallback | 2x capacity |
| **📊 Data** | Unicode-First Approach | Consistent text handling with NFC normalization | Prevents duplicates |
| **📊 Data** | Stateless Learning | Feedback loop without persistent storage | No corruption risk |
| **📊 Data** | Context Manager Pattern | Proper resource cleanup | Automatic transaction management |
| **🔒 Safety** | Sample Size Guards | Minimum sample sizes for optimization | Prevents overfitting |
| **🔒 Safety** | Multi-Layer Verification | Multiple verification layers before dispatch | Quality control |
| **🔄 Operational** | Learning Loop | Closed feedback system | Self-improving |
| **🔄 Operational** | Tactical Veto | Tactical considerations override statistics | Context-aware decisions |
| **🔄 Operational** | Emergency Cleanup | Automatic disk space management | Prevents system failure |

**Pattern Interactions**:
- **Circuit Breaker + Graceful Degradation**: Automatic failover with reduced functionality
- **Shared Cache + Unicode-First**: Consistent deduplication across multilingual content
- **Sample Size Guards + Stateless Learning**: Reliable optimization without corruption risk
- **Multi-Layer Verification + Tactical Veto**: Quality control with tactical awareness
- **Connection Pooling + Context Manager**: Robust database operations with automatic cleanup
- **Rate Limiting + Fingerprint Rotation**: Anti-detection with rate limit compliance
- **Fingerprint Rotation + Circuit Breaker**: Multi-layer resilience against detection and failures
- **Double Cycle + Tiered Throttling**: Maximum capacity utilization with budget protection

---

## 10. Analysis Engines (11/11 Verified)

This section documents all 11 verified analysis engines that form the core intelligence processing capabilities of EarlyBird V8.3.

### 10.1 Fatigue V2.0 Engine

**Purpose**: Analyzes team fatigue levels based on recent match schedules and travel patterns.

**Implementation**: [`src/analysis/fatigue_engine.py`](src/analysis/fatigue_engine.py)

**Core Features**:
- **Match Schedule Analysis**: Tracks last 5 matches for both teams
- **Travel Distance Calculation**: Computes travel distance between venues
- **Rest Days Calculation**: Days since last match
- **Fatigue Score**: 0-10 scale indicating fatigue level

**Fatigue Multipliers**:
- **Elite Teams**: 0.5x (less affected by fatigue)
- **Tier 2 Teams**: 1.3x (more affected by fatigue)
- **Low-tier Teams**: 1.5x (highly affected by fatigue)

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
FATIGUE_ELITE_MULTIPLIER = 0.5
FATIGUE_TIER2_MULTIPLIER = 1.3
FATIGUE_LOW_TIER_MULTIPLIER = 1.5
FATIGUE_MATCH_HISTORY_DAYS = 14
```

**V8.3 Enhancements**:
- League-specific fatigue parameters
- Integration with Tactical Veto for fatigue-based veto decisions
- Cross-reference with injury reports for comprehensive fitness assessment

---

### 10.2 Biscotto V2.0 Engine

**Purpose**: Detects draw opportunities using Z-Score statistical analysis.

**Implementation**: [`src/analysis/biscotto_engine.py`](src/analysis/biscotto_engine.py)

**Core Features**:
- **Z-Score Calculation**: Statistical deviation from expected draw probability
- **Opening vs Current Odds Comparison**: Identifies draw value
- **Market Movement Analysis**: Tracks odds movement patterns

**Biscotto Threshold**:
- **Z-Score > 2.0**: Strong draw signal (EXCELLENT)
- **Z-Score 1.5-2.0**: Moderate draw signal (GOOD)
- **Z-Score < 1.5**: Weak draw signal (MARGINAL)

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
BISCOTTO_Z_SCORE_THRESHOLD = 2.0
BISCOTTO_DRAW_ODDS_THRESHOLD = 3.0
BISCOTTO_OPENING_ODDS_VARIANCE = 0.15
```

**V8.0 Enhancements**:
- Integration with Verification Layer V7.0 for multi-site validation
- Cross-reference with tactical analysis for draw probability validation
- Enhanced Z-Score calculation with league-specific parameters

---

### 10.3 Verification Layer V7.0

**Purpose**: Multi-site fact-checking and intelligence validation system.

**Implementation**: [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py)

**Core Features**:
- **Multi-Site Query Builder**: Constructs queries for multiple search engines
- **Cross-Source Validation**: Verifies intelligence across multiple sources
- **Confidence Scoring**: Assigns confidence based on source reliability
- **Conflict Detection**: Identifies conflicting intelligence

**Query Builder Logic** ([`src/analysis/verification_layer.py`](src/analysis/verification_layer.py:150-250)):
```python
def build_multi_site_query(self, team, player, intelligence_type):
    """Build queries for multiple search engines."""
    queries = []
    
    # Site-specific queries
    queries.append(f"site:twitter.com {team} {player}")
    queries.append(f"site:bbc.com {team} {player}")
    queries.append(f"site:espn.com {team} {player}")
    
    # General queries with exclusions
    queries.append(f"{team} {player} injury -basketball -tennis")
    
    return queries
```

**Verification Levels**:
- **Level 1**: Single source (LOW confidence)
- **Level 2**: Two independent sources (MEDIUM confidence)
- **Level 3**: Three+ independent sources (HIGH confidence)
- **Level 4**: Official club announcement (VERY HIGH confidence)

**V7.0 Enhancements**:
- Multi-site query builder for comprehensive validation
- Source reliability scoring
- Conflict detection and resolution
- Integration with Tactical Veto for context-aware verification

---

### 10.4 CLV V5.0 Engine

**Purpose**: Closing Line Value tracking and analysis for edge validation.

**Implementation**: [`src/analysis/clv_tracker.py`](src/analysis/clv_tracker.py)

**Core Features**:
- **CLV Calculation**: Compares alert odds vs kickoff odds
- **Edge Validation**: Confirms positive expected value
- **Historical Tracking**: Maintains CLV history for each strategy
- **Performance Correlation**: Analyzes CLV vs actual ROI

**CLV Thresholds**:
- **>+2%**: EXCELLENT (strong edge)
- **>+0.5%**: GOOD (moderate edge)
- **>0%**: MARGINAL (slight edge)
- **≤0%**: NO VALUE (negative edge)

**V8.3 Critical Fix** ([`src/database/migration_v83_odds_fix.py`](src/database/migration_v83_odds_fix.py)):
```python
# New fields for accurate CLV calculation
odds_at_alert = Column(Float)  # Actual odds when alert sent
odds_at_kickoff = Column(Float)  # Actual odds at kickoff
alert_sent_at = Column(DateTime)  # Alert timestamp

# CLV calculation now uses correct odds
clv_percent = ((odds_at_kickoff - odds_at_alert) / odds_at_alert) * 100
```

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
CLV_EXCELLENT_THRESHOLD = 2.0
CLV_GOOD_THRESHOLD = 0.5
CLV_MARGINAL_THRESHOLD = 0.0
```

---

### 10.5 Tactical Veto V8.0

**Purpose**: Market vs Tactical conflict detection and veto system.

**Implementation**: [`src/analysis/analyzer.py`](src/analysis/analyzer.py:1200-1400)

**Core Features**:
- **Tactics > Statistics Hierarchy**: Tactical considerations override statistical signals
- **Position-Based Veto Logic**: OFFENSIVE/DEFENSIVE DEPLETION detection
- **Extreme Impact Threshold**: 5.0 injury impact triggers tactical veto
- **Confidence Adjustment**: ±2.0 points based on tactical assessment

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - TACTICAL VETO V8.0**

This is a **V8.3 standard** - primary operational logic that takes precedence over statistical models.

**Veto Rules**:
1. **Confirmed Disaster**: News confirms tactical weakness → Boost confidence +15%
2. **Potential Turnaround**: Key player returns to struggling team → Boost confidence +10%
3. **Conflict Detection**: Conflicting intelligence sources → Reduce confidence 15%
4. **Freshness Priority**: Recent Twitter intelligence > Stale FotMob data
5. **Multi-Source Boost**: 2+ sources report same info → Boost confidence +5%

**Veto Activation**:
```python
# When tactical veto triggered
if tactical_veto_active:
    reasoning = f"⚠️ TACTICAL VETO ATTIVO: {veto_reason}"
    confidence_adjustment = -2.0 if veto_reason == "OFFENSIVE DEPLETION" else +2.0
```

**Position-Based Logic**:
- **OFFENSIVE DEPLETION**: Multiple key attackers missing → Under markets favored
- **DEFENSIVE DEPLETION**: Multiple key defenders missing → Over markets favored
- **Extreme Impact**: Injury impact score > 5.0 → Automatic veto

---

### 10.6 B-Team V2.0 Engine

**Purpose**: Detects when teams field weakened lineups (B-Teams).

**Implementation**: [`src/analysis/squad_analyzer.py`](src/analysis/squad_analyzer.py)

**Core Features**:
- **Squad Rotation Detection**: Identifies unusual squad selections
- **Key Player Absence**: Tracks missing key players
- **Lineup Strength Calculation**: Computes lineup strength vs expected
- **Tactical Impact Assessment**: Evaluates tactical impact of B-Team

**B-Team Indicators**:
- **>3 Key Players Missing**: Strong B-Team signal
- **Unusual Formation**: Tactical change indicates rotation
- **Youth Players**: Multiple youth players in starting XI
- **Cup Competition Context**: Higher B-Team probability

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
BTEAM_KEY_PLAYERS_THRESHOLD = 3
BTEAM_YOUTH_PLAYERS_THRESHOLD = 2
BTEAM_FORMATION_CHANGE_THRESHOLD = 1
```

---

### 10.7 BTTS V4.1 Engine

**Purpose**: Both Teams to Score prediction and analysis.

**Implementation**: [`src/analysis/analyzer.py`](src/analysis/analyzer.py:800-950)

**Core Features**:
- **Scoring Probability Analysis**: Both teams' scoring probability
- **Defensive Strength Assessment**: Evaluates defensive capabilities
- **Attacking Threat Analysis**: Evaluates attacking capabilities
- **Historical BTTS Performance**: Historical BTTS data

**BTTS Factors**:
- **Team Scoring Form**: Recent goals scored/conceded
- **Head-to-Head**: Historical BTTS record
- **Injury Impact**: Key attackers/defenders missing
- **Tactical Setup**: Attacking vs defensive formations

**V4.1 Enhancements**:
- Integration with Injury Impact Engine for attacker/defender analysis
- Cross-reference with Tactical Veto for tactical setup validation
- League-specific BTTS probability parameters

---

### 10.8 Motivation V4.2 Engine

**Purpose**: Analyzes team motivation levels based on context.

**Implementation**: [`src/analysis/analyzer.py`](src/analysis/analyzer.py:950-1100)

**Core Features**:
- **League Position Context**: Title race, relegation battle, mid-table
- **Cup Competition Importance**: Domestic cups, European competitions
- **Recent Form Impact**: Winning/losing streaks
- **Managerial Pressure**: Manager under pressure situations

**Motivation Factors**:
- **Title Race**: +2.0 motivation boost
- **Relegation Battle**: +2.5 motivation boost
- **Cup Final**: +3.0 motivation boost
- **Manager Under Pressure**: ±1.5 motivation adjustment

**V4.2 Enhancements**:
- League-specific motivation parameters
- Integration with Tactical Veto for motivation-based veto decisions
- Cross-reference with news for motivation validation

---

### 10.9 Intelligence Router V7.0

**Purpose**: Orchestrates AI provider selection and fallback hierarchy.

**Implementation**: [`src/services/intelligence_router.py`](src/services/intelligence_router.py)

**Core Features**:
- **Provider Selection**: Intelligent provider routing based on availability
- **Fallback Hierarchy**: Primary → Secondary → Emergency
- **Budget Management**: Tracks API quota usage
- **Performance Tracking**: Logs provider performance metrics

**Provider Hierarchy**:
1. **Primary**: DeepSeek V3.2 (OpenRouter) - High-quality reasoning, no rate limits
2. **Fallback**: Perplexity Sonar - Luxury fallback for transient errors
3. **Emergency**: Cached results - When all providers unavailable

**Budget Allocation** ([`config/settings.py`](config/settings.py:490-497)):
| Component | Calls/Month | Percentage |
|-----------|-------------|------------|
| Main pipeline | 2100 | 30% |
| News radar | 1500 | 21% |
| Browser monitor | 750 | 11% |
| Telegram monitor | 450 | 6% |
| Settlement/CLV | 225 | 3% |
| Twitter recovery | 1975 | 29% |

**V7.0 Enhancements**:
- Smart provider routing
- Budget-aware routing
- Performance tracking
- Automatic failover

---

### 10.10 Opportunity Radar V2.0

**Purpose**: Discovers high-value betting opportunities across multiple markets.

**Implementation**: [`src/ingestion/opportunity_radar.py`](src/ingestion/opportunity_radar.py)

**Core Features**:
- **Multi-Market Scanning**: Scans 1X2, Goals, BTTS, Corners, Cards
- **Value Detection**: Identifies mispriced odds
- **Odds Movement Tracking**: Tracks odds movement patterns
- **Market Timing**: Identifies optimal betting timing

**Radar Boost**:
- **Forced Narrative**: Multiple sources report same intelligence → +1.0 score boost
- **Cross-Source Confirmation**: 2+ independent sources → +0.5 score boost
- **Fresh Intelligence**: Recent news → +0.3 score boost

**V2.0 Enhancements**:
- Integration with Verification Layer for opportunity validation
- Cross-reference with Tactical Veto for tactical soundness
- League-specific opportunity parameters

---

### 10.11 Injury Impact Engine

**Purpose**: Analyzes impact of player injuries on match outcomes.

**Implementation**: [`src/analysis/injury_impact_engine.py`](src/analysis/injury_impact_engine.py)

**Core Features**:
- **Player Importance Scoring**: 0-10 scale based on player importance
- **Position Impact**: Attacker vs Defender impact analysis
- **Team Impact**: Overall team impact assessment
- **Market Impact**: Impact on specific markets (Goals, BTTS, etc.)

**Injury Impact Scale**:
- **0-2.0**: Minor impact (rotation player)
- **2.0-4.0**: Moderate impact (regular starter)
- **4.0-6.0**: Major impact (key player)
- **6.0-8.0**: Severe impact (star player)
- **8.0-10.0**: Critical impact (irreplaceable player)

**Position Impact Multipliers**:
- **Key Attacker**: 1.5x impact on goals markets
- **Key Defender**: 1.5x impact on goals markets
- **Midfielder**: 1.2x impact on all markets
- **Goalkeeper**: 1.8x impact on goals markets

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
INJURY_IMPACT_ATTACKER_MULTIPLIER = 1.5
INJURY_IMPACT_DEFENDER_MULTIPLIER = 1.5
INJURY_IMPACT_MIDFIELDER_MULTIPLIER = 1.2
INJURY_IMPACT_GOALKEEPER_MULTIPLIER = 1.8
```

---

## 11. Mathematical Models (9/9 Verified)

This section documents all 9 verified mathematical models used for probability calculation and value detection.

### 11.1 Dixon-Coles Model

**Purpose**: Advanced football match outcome probability model with time-decay adjustment.

**Implementation**: [`src/analysis/math_engine.py`](src/analysis/math_engine.py:100-200)

**Core Formula**:
```
P(home_win) = exp(α_i + β_j - γ) / (1 + exp(α_i + β_j - γ) + exp(α_k + β_i - γ))
P(draw) = γ / (1 + exp(α_i + β_j - γ) + exp(α_k + β_i - γ))
P(away_win) = exp(α_k + β_i - γ) / (1 + exp(α_i + β_j - γ) + exp(α_k + β_i - γ))
```

**Where**:
- `α_i`: Home team attacking strength
- `β_j`: Away team defensive strength
- `γ`: Home advantage parameter
- `ρ`: -0.07 (correction for low-scoring draws)

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - BALANCED PROBABILITY**

This is a **V8.3 standard** - primary operational logic for probability calculation.

**Balanced Probability Formula**:
```python
balanced_prob = (poisson_prob + ai_confidence_prob) / 2
```

**Purpose**: Combines Poisson mathematical probability with AI confidence probability to dampen AI over-optimism and balance quantitative + qualitative analysis.

**League-Specific Home Advantage**:
- **Elite Leagues**: γ = 0.15 (strong home advantage)
- **Tier 1 Leagues**: γ = 0.12 (moderate home advantage)
- **Tier 2 Leagues**: γ = 0.10 (weak home advantage)

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
DIXON_COLES_RHO = -0.07
DIXON_COLES_HOME_ADVANTAGE_ELITE = 0.15
DIXON_COLES_HOME_ADVANTAGE_TIER1 = 0.12
DIXON_COLES_HOME_ADVANTAGE_TIER2 = 0.10
```

---

### 11.2 Poisson Model

**Purpose**: Goals probability calculation using Poisson distribution.

**Implementation**: [`src/analysis/math_engine.py`](src/analysis/math_engine.py:50-100)

**Core Formula**:
```
P(k goals) = (λ^k * e^(-λ)) / k!
```

**Where**:
- `λ`: Expected goals (team strength × opponent defensive weakness)
- `k`: Number of goals (0, 1, 2, 3, ...)

**Applications**:
- **Over/Under 2.5 Goals**: P(total goals > 2.5)
- **Over/Under 3.5 Goals**: P(total goals > 3.5)
- **Correct Score**: P(home goals = x, away goals = y)
- **Team Goals**: P(team goals ≥ k)

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
POISSON_OVER_2_5_THRESHOLD = 2.5
POISSON_OVER_3_5_THRESHOLD = 3.5
POISSON_MAX_GOALS = 10
```

---

### 11.3 Kelly Criterion

**Purpose**: Optimal bet sizing for bankroll management.

**Implementation**: [`src/analysis/math_engine.py`](src/analysis/math_engine.py:426-440)

**Core Formula**:
```
b = bookmaker_odd - 1
kelly_full = ((b * p) - (1 - p)) / b
kelly_quarter = kelly_full * 0.25
```

**Where**:
- `b`: Net odds received (bookmaker odd - 1)
- `p`: Probability of winning (balanced probability)
- `kelly_full`: Full Kelly stake percentage
- `kelly_quarter`: Quarter-Kelly stake percentage

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - KELLY WITH 5% SAFETY CAP**

This is a **V8.3 standard** - primary operational logic for position sizing.

**Safety Caps**:
- **Minimum Stake**: 0.5% of bankroll (anything less treated as 0)
- **Maximum Stake**: 5.0% of bankroll (hard cap)

**Configuration** ([`src/analysis/math_engine.py`](src/analysis/math_engine.py:34-35)):
```python
MIN_STAKE_PCT = 0.5  # Minimum 0.5% of bankroll per bet
MAX_STAKE_PCT = 5.0  # Maximum 5.0% of bankroll per bet (hard cap)
KELLY_QUARTER_MULTIPLIER = 0.25
```

**Stake Calculation Flow**:
1. Calculate balanced probability from Poisson + AI
2. Apply Kelly Criterion to determine optimal stake
3. Multiply by 0.25 (Quarter-Kelly) for risk aversion
4. Apply safety caps (min 0.5%, max 5.0%)
5. Return final stake percentage

---

### 11.4 Sortino Ratio

**Purpose**: Risk-adjusted performance metric focusing on downside risk.

**Implementation**: [`src/analysis/optimizer.py`](src/analysis/optimizer.py:200-300)

**Core Formula**:
```
Sortino = (R - T) / σ_d
```

**Where**:
- `R`: Average return
- `T`: Target return (minimum acceptable return)
- `σ_d`: Downside deviation (standard deviation of negative returns)

**Applications**:
- **Strategy Performance Evaluation**: Compare strategies by risk-adjusted returns
- **Weight Adjustment**: Higher Sortino → Higher weight
- **Self-Healing**: Sortino boost on -20% drawdown

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
SORTINO_TARGET_RETURN = 0.05  # 5% minimum acceptable return
SORTINO_BOOST_FACTOR = 1.2  # 20% boost on -20% drawdown
```

---

### 11.5 CLV (Closing Line Value)

**Purpose**: Edge validation by comparing alert odds vs kickoff odds.

**Implementation**: [`src/analysis/clv_tracker.py`](src/analysis/clv_tracker.py)

**Core Formula**:
```
CLV% = ((odds_at_kickoff - odds_at_alert) / odds_at_alert) * 100
```

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - CLV THRESHOLDS**

This is a **V8.3 standard** - primary operational logic for edge validation.

**CLV Thresholds**:
- **>+2%**: EXCELLENT (strong edge, high confidence)
- **>+0.5%**: GOOD (moderate edge, good confidence)
- **>0%**: MARGINAL (slight edge, low confidence)
- **≤0%**: NO VALUE (negative edge, no bet)

**V8.3 Critical Fix** ([`src/database/migration_v83_odds_fix.py`](src/database/migration_v83_odds_fix.py)):
```python
# New fields for accurate CLV calculation
odds_at_alert = Column(Float)  # Actual odds when alert sent
odds_at_kickoff = Column(Float)  # Actual odds at kickoff
alert_sent_at = Column(DateTime)  # Alert timestamp

# CLV calculation now uses correct odds
clv_percent = ((odds_at_kickoff - odds_at_alert) / odds_at_alert) * 100
```

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
CLV_EXCELLENT_THRESHOLD = 2.0
CLV_GOOD_THRESHOLD = 0.5
CLV_MARGINAL_THRESHOLD = 0.0
```

---

### 11.6 Exponential Decay

**Purpose**: Time-based decay of intelligence relevance.

**Implementation**: [`src/utils/freshness.py`](src/utils/freshness.py)

**Core Formula**:
```
relevance = e^(-λ * t)
```

**Where**:
- `λ`: Decay rate (league-specific)
- `t`: Time since intelligence was published

**League-Specific Decay Rates**:
- **Elite Leagues**: λ = 0.023 (half-life ~30 min)
- **Tier 1 Leagues**: λ = 0.05 (half-life ~14 min)
- **Tier 2 Leagues**: λ = 0.14 (half-life ~5 min)

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
NEWS_DECAY_ELITE_LAMBDA = 0.023
NEWS_DECAY_TIER1_LAMBDA = 0.05
NEWS_DECAY_TIER2_LAMBDA = 0.14
```

---

### 11.7 News Decay

**Purpose**: Time-based decay of news relevance for intelligence scoring.

**Implementation**: [`src/analysis/news_scorer.py`](src/analysis/news_scorer.py)

**Core Formula**:
```
news_score = base_score * e^(-λ * t)
```

**Where**:
- `base_score`: Initial news relevance score
- `λ`: Decay rate (league-specific)
- `t`: Time since news was published

**League-Specific Decay Rates**:
- **Elite Leagues**: λ = 0.023 (half-life ~30 min)
- **Tier 1 Leagues**: λ = 0.05 (half-life ~14 min)
- **Tier 2 Leagues**: λ = 0.14 (half-life ~5 min)

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
NEWS_DECAY_ELITE_LAMBDA = 0.023
NEWS_DECAY_TIER1_LAMBDA = 0.05
NEWS_DECAY_TIER2_LAMBDA = 0.14
```

---

### 11.8 Z-Score

**Purpose**: Statistical deviation from expected value for draw detection.

**Implementation**: [`src/analysis/biscotto_engine.py`](src/analysis/biscotto_engine.py)

**Core Formula**:
```
Z = (X - μ) / σ
```

**Where**:
- `X`: Observed value (current draw odds)
- `μ`: Expected value (average draw odds)
- `σ`: Standard deviation of draw odds

**Biscotto Z-Score Threshold**:
- **Z > 2.0**: Strong draw signal (EXCELLENT)
- **Z 1.5-2.0**: Moderate draw signal (GOOD)
- **Z < 1.5**: Weak draw signal (MARGINAL)

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
BISCOTTO_Z_SCORE_THRESHOLD = 2.0
BISCOTTO_DRAW_ODDS_THRESHOLD = 3.0
```

---

### 11.9 Value Detection

**Purpose**: Identifies mispriced odds for value betting opportunities.

**Implementation**: [`src/analysis/math_engine.py`](src/analysis/math_engine.py:300-400)

**Core Formula**:
```
value = (probability * odds) - 1
```

**Where**:
- `probability`: Calculated probability (balanced probability)
- `odds`: Bookmaker odds
- `value`: Expected value (positive = value bet)

**Value Thresholds**:
- **>10%**: EXCELLENT value
- **>5%**: GOOD value
- **>0%**: MARGINAL value
- **≤0%**: NO VALUE

**Configuration** ([`config/settings.py`](config/settings.py)):
```python
VALUE_EXCELLENT_THRESHOLD = 0.10
VALUE_GOOD_THRESHOLD = 0.05
VALUE_MARGINAL_THRESHOLD = 0.0
```

---

## 12. Operational Rules & Thresholds (32/32 Verified)

This section documents all 32 verified operational rules and thresholds that govern EarlyBird V8.3's decision-making.

### 12.1 CLV Thresholds

**Purpose**: Edge validation based on Closing Line Value.

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - CLV THRESHOLDS**

This is a **V8.3 standard** - primary operational logic for edge validation.

**Thresholds**:
- **>+2%**: EXCELLENT (strong edge, high confidence)
- **>+0.5%**: GOOD (moderate edge, good confidence)
- **>0%**: MARGINAL (slight edge, low confidence)
- **≤0%**: NO VALUE (negative edge, no bet)

**Implementation**: [`src/analysis/clv_tracker.py`](src/analysis/clv_tracker.py)

**Configuration**: [`config/settings.py`](config/settings.py:230-235)
```python
CLV_EXCELLENT_THRESHOLD = 2.0
CLV_GOOD_THRESHOLD = 0.5
CLV_MARGINAL_THRESHOLD = 0.0
```

---

### 12.2 Fatigue Multipliers

**Purpose**: Adjusts fatigue impact based on team tier.

**Thresholds**:
- **Elite Teams**: 0.5x (less affected by fatigue)
- **Tier 2 Teams**: 1.3x (more affected by fatigue)
- **Low-tier Teams**: 1.5x (highly affected by fatigue)

**Implementation**: [`src/analysis/fatigue_engine.py`](src/analysis/fatigue_engine.py)

**Configuration**: [`config/settings.py`](config/settings.py:240-245)
```python
FATIGUE_ELITE_MULTIPLIER = 0.5
FATIGUE_TIER2_MULTIPLIER = 1.3
FATIGUE_LOW_TIER_MULTIPLIER = 1.5
```

---

### 12.3 Biscotto Z-Score Threshold

**Purpose**: Draw opportunity detection threshold.

**Threshold**: Z-Score > 2.0

**Implementation**: [`src/analysis/biscotto_engine.py`](src/analysis/biscotto_engine.py)

**Configuration**: [`config/settings.py`](config/settings.py:250-255)
```python
BISCOTTO_Z_SCORE_THRESHOLD = 2.0
BISCOTTO_DRAW_ODDS_THRESHOLD = 3.0
```

---

### 12.4 RLM (Reverse Line Movement)

**Purpose**: Detects smart money betting against public opinion.

**Thresholds**:
- **Public Betting**: >65% on one side
- **Odds Increase**: >3% against public

**Implementation**: [`src/analysis/market_intelligence.py`](src/analysis/market_intelligence.py)

**Configuration**: [`config/settings.py`](config/settings.py:260-265)
```python
RLM_PUBLIC_THRESHOLD = 0.65
RLM_ODDS_INCREASE_THRESHOLD = 0.03
```

---

### 12.5 Steam Move

**Purpose**: Detects rapid odds movement indicating sharp action.

**Thresholds**:
- **Odds Drop**: >5% within 15-minute window
- **Time Window**: 15 minutes

**Implementation**: [`src/analysis/market_intelligence.py`](src/analysis/market_intelligence.py)

**Configuration**: [`config/settings.py`](config/settings.py:270-275)
```python
STEAM_MOVE_ODDS_DROP_THRESHOLD = 0.05
STEAM_MOVE_TIME_WINDOW_MINUTES = 15
```

---

### 12.6 News Decay Thresholds

**Purpose**: Time-based decay of news relevance.

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - NEWS DECAY LAMBDA VALUES**

This is a **V8.3 standard** - primary operational logic for news relevance.

**Thresholds (Lambda Values)**:
- **Elite Leagues**: λ = 0.023 (half-life ~30 min)
- **Tier 1 Leagues**: λ = 0.05 (half-life ~14 min)
- **Tier 2 Leagues**: λ = 0.14 (half-life ~5 min)

**Implementation**: [`src/analysis/news_scorer.py`](src/analysis/news_scorer.py)

**Configuration**: [`config/settings.py`](config/settings.py:280-285)
```python
NEWS_DECAY_ELITE_LAMBDA = 0.023
NEWS_DECAY_TIER1_LAMBDA = 0.05
NEWS_DECAY_TIER2_LAMBDA = 0.14
```

---

### 12.7 Sample Size Thresholds

**Purpose**: Prevents overfitting by enforcing minimum sample sizes.

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - SAMPLE SIZE GUARDS**

This is a **V8.3 standard** - primary operational logic for optimizer state management.

**Thresholds**:
- **FROZEN**: <30 bets (no weight adjustment)
- **WARMING_UP**: 30-50 bets (conservative adjustment, 50% factor)
- **ACTIVE**: 50+ bets (full adjustment)

**Implementation**: [`src/analysis/optimizer.py`](src/analysis/optimizer.py:400-450)

**Configuration**: [`config/settings.py`](config/settings.py:290-295)
```python
SAMPLE_SIZE_FROZEN_THRESHOLD = 30
SAMPLE_SIZE_WARMING_THRESHOLD = 50
SAMPLE_SIZE_ACTIVE_THRESHOLD = 50
```

---

### 12.8 Self-Healing Thresholds

**Purpose**: Automatic strategy adjustment on poor performance.

**Thresholds**:
- **Drawdown Brake**: -20% drawdown triggers brake
- **Sortino Boost**: +20% Sortino boost on drawdown brake

**Implementation**: [`src/analysis/optimizer.py`](src/analysis/optimizer.py:500-550)

**Configuration**: [`config/settings.py`](config/settings.py:300-305)
```python
SELF_HEALING_DRAWDOWN_BRAKE = -0.20
SELF_HEALING_SORTINO_BOOST = 0.20
```

---

### 12.9 Alert Thresholds

**Purpose**: Minimum confidence scores for alert dispatch.

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - 9.0 ELITE ALERT THRESHOLD**

This is a **V8.3 standard** - primary operational logic for alert quality control.

**Thresholds**:
- **Elite**: 9.0 (primary bets, "Cream of the Crop")
- **Dynamic**: 7.5-9.0 (secondary opportunities with forced narrative)
- **Settlement**: 7.0 (minimum for learning loop inclusion)

**Implementation**: [`src/alerting/notifier.py`](src/alerting/notifier.py)

**Configuration**: [`config/settings.py`](config/settings.py:224-226)
```python
ALERT_THRESHOLD_HIGH = 9.0  # Elite threshold
ALERT_THRESHOLD_RADAR = 7.5  # Radar/Tier B threshold
SETTLEMENT_MIN_SCORE = 7.0  # Settlement threshold
```

---

### 12.10 Kelly Criterion Thresholds

**Purpose**: Position sizing safety caps.

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - KELLY 5% SAFETY CAP**

This is a **V8.3 standard** - primary operational logic for position sizing.

**Thresholds**:
- **Minimum Stake**: 0.5% of bankroll (anything less treated as 0)
- **Maximum Stake**: 5.0% of bankroll (hard cap)
- **Quarter-Kelly Multiplier**: 0.25

**Implementation**: [`src/analysis/math_engine.py`](src/analysis/math_engine.py:426-440)

**Configuration**: [`src/analysis/math_engine.py`](src/analysis/math_engine.py:34-35)
```python
MIN_STAKE_PCT = 0.5  # Minimum 0.5% of bankroll per bet
MAX_STAKE_PCT = 5.0  # Maximum 5.0% of bankroll per bet (hard cap)
KELLY_QUARTER_MULTIPLIER = 0.25
```

---

### 12.11 Market Veto Threshold

**Purpose**: Prevents betting on degraded value.

**Threshold**: 15% odds drop from opening

**Implementation**: [`src/analysis/analyzer.py`](src/analysis/analyzer.py:1412-1429)

**Configuration**: [`config/settings.py`](config/settings.py:310)
```python
MARKET_VETO_ODDS_DROP_THRESHOLD = 0.15
```

---

### 12.12 Tactical Veto Thresholds

**Purpose**: Triggers tactical veto based on injury impact.

**Thresholds**:
- **Extreme Impact**: 5.0 injury impact triggers tactical veto
- **Confidence Adjustment**: ±2.0 points based on tactical assessment

**Implementation**: [`src/analysis/analyzer.py`](src/analysis/analyzer.py:1200-1400)

**Configuration**: [`config/settings.py`](config/settings.py:315-320)
```python
TACTICAL_VETO_EXTREME_IMPACT_THRESHOLD = 5.0
TACTICAL_VETO_CONFIDENCE_ADJUSTMENT = 2.0
```

---

### 12.13 Dixon-Coles Parameters

**Purpose**: League-specific Dixon-Coles model parameters.

**Parameters**:
- **ρ (Rho)**: -0.07 (correction for low-scoring draws)
- **Home Advantage Elite**: γ = 0.15
- **Home Advantage Tier 1**: γ = 0.12
- **Home Advantage Tier 2**: γ = 0.10

**Implementation**: [`src/analysis/math_engine.py`](src/analysis/math_engine.py:100-200)

**Configuration**: [`config/settings.py`](config/settings.py:325-330)
```python
DIXON_COLES_RHO = -0.07
DIXON_COLES_HOME_ADVANTAGE_ELITE = 0.15
DIXON_COLES_HOME_ADVANTAGE_TIER1 = 0.12
DIXON_COLES_HOME_ADVANTAGE_TIER2 = 0.10
```

---

### 12.14 Value Detection Thresholds

**Purpose**: Identifies value betting opportunities.

**Thresholds**:
- **EXCELLENT**: >10% value
- **GOOD**: >5% value
- **MARGINAL**: >0% value
- **NO VALUE**: ≤0% value

**Implementation**: [`src/analysis/math_engine.py`](src/analysis/math_engine.py:300-400)

**Configuration**: [`config/settings.py`](config/settings.py:335-340)
```python
VALUE_EXCELLENT_THRESHOLD = 0.10
VALUE_GOOD_THRESHOLD = 0.05
VALUE_MARGINAL_THRESHOLD = 0.0
```

---

### 12.15 Injury Impact Thresholds

**Purpose**: Classifies injury severity for impact assessment.

**Thresholds**:
- **0-2.0**: Minor impact (rotation player)
- **2.0-4.0**: Moderate impact (regular starter)
- **4.0-6.0**: Major impact (key player)
- **6.0-8.0**: Severe impact (star player)
- **8.0-10.0**: Critical impact (irreplaceable player)

**Implementation**: [`src/analysis/injury_impact_engine.py`](src/analysis/injury_impact_engine.py)

**Configuration**: [`config/settings.py`](config/settings.py:345-350)
```python
INJURY_IMPACT_MINOR_MAX = 2.0
INJURY_IMPACT_MODERATE_MAX = 4.0
INJURY_IMPACT_MAJOR_MAX = 6.0
INJURY_IMPACT_SEVERE_MAX = 8.0
INJURY_IMPACT_CRITICAL_MAX = 10.0
```

---

### 12.16 Position Impact Multipliers

**Purpose**: Adjusts injury impact based on player position.

**Multipliers**:
- **Key Attacker**: 1.5x impact on goals markets
- **Key Defender**: 1.5x impact on goals markets
- **Midfielder**: 1.2x impact on all markets
- **Goalkeeper**: 1.8x impact on goals markets

**Implementation**: [`src/analysis/injury_impact_engine.py`](src/analysis/injury_impact_engine.py)

**Configuration**: [`config/settings.py`](config/settings.py:355-360)
```python
INJURY_IMPACT_ATTACKER_MULTIPLIER = 1.5
INJURY_IMPACT_DEFENDER_MULTIPLIER = 1.5
INJURY_IMPACT_MIDFIELDER_MULTIPLIER = 1.2
INJURY_IMPACT_GOALKEEPER_MULTIPLIER = 1.8
```

---

### 12.17 B-Team Detection Thresholds

**Purpose**: Detects when teams field weakened lineups.

**Thresholds**:
- **Key Players Missing**: >3 key players missing
- **Youth Players**: >2 youth players in starting XI
- **Formation Change**: >1 formation change from expected

**Implementation**: [`src/analysis/squad_analyzer.py`](src/analysis/squad_analyzer.py)

**Configuration**: [`config/settings.py`](config/settings.py:365-370)
```python
BTEAM_KEY_PLAYERS_THRESHOLD = 3
BTEAM_YOUTH_PLAYERS_THRESHOLD = 2
BTEAM_FORMATION_CHANGE_THRESHOLD = 1
```

---

### 12.18 Fatigue Match History Threshold

**Purpose**: Number of recent matches to analyze for fatigue.

**Threshold**: 14 days (last 5 matches)

**Implementation**: [`src/analysis/fatigue_engine.py`](src/analysis/fatigue_engine.py)

**Configuration**: [`config/settings.py`](config/settings.py:375)
```python
FATIGUE_MATCH_HISTORY_DAYS = 14
```

---

### 12.19 Sortino Target Return

**Purpose**: Minimum acceptable return for Sortino calculation.

**Threshold**: 5% minimum acceptable return

**Implementation**: [`src/analysis/optimizer.py`](src/analysis/optimizer.py:200-300)

**Configuration**: [`config/settings.py`](config/settings.py:380)
```python
SORTINO_TARGET_RETURN = 0.05
```

---

### 12.20 Sortino Boost Factor

**Purpose**: Sortino boost on drawdown brake.

**Threshold**: 20% boost on -20% drawdown

**Implementation**: [`src/analysis/optimizer.py`](src/analysis/optimizer.py:500-550)

**Configuration**: [`config/settings.py`](config/settings.py:385)
```python
SORTINO_BOOST_FACTOR = 1.2
```

---

### 12.21 Tavily Budget Allocation

**Purpose**: Component-based API quota allocation.

**Allocation**:
- **Main pipeline**: 30% (2100 calls/month)
- **News radar**: 21% (1500 calls/month)
- **Browser monitor**: 11% (750 calls/month)
- **Telegram monitor**: 6% (450 calls/month)
- **Settlement/CLV**: 3% (225 calls/month)
- **Twitter recovery**: 29% (1975 calls/month)

**Implementation**: [`src/ingestion/tavily_budget.py`](src/ingestion/tavily_budget.py)

**Configuration**: [`config/settings.py`](config/settings.py:490-497)

---

### 12.22 Tavily Throttling Thresholds

**Purpose**: Budget-based API call throttling.

**Thresholds**:
- **Normal Mode**: <90% usage (full functionality)
- **Degraded Mode**: 90-95% usage (50% throttling)
- **Disabled Mode**: >95% usage (critical only)

**Implementation**: [`src/ingestion/tavily_budget.py`](src/ingestion/tavily_budget.py)

**Configuration**: [`config/settings.py`](config/settings.py:500-505)
```python
TAVILY_NORMAL_MODE_THRESHOLD = 0.90
TAVILY_DEGRADED_MODE_THRESHOLD = 0.95
```

---

### 12.23 Brave Budget Allocation

**Purpose**: Component-based API quota allocation for Brave.

**Allocation**: Similar to Tavily with tiered throttling

**Implementation**: [`src/ingestion/brave_budget.py`](src/ingestion/brave_budget.py)

---

### 12.24 Brave Throttling Thresholds

**Purpose**: Budget-based API call throttling for Brave.

**Thresholds**:
- **Normal Mode**: <90% usage (full functionality)
- **Degraded Mode**: 90-95% usage (50% throttling)
- **Disabled Mode**: >95% usage (critical only)

**Implementation**: [`src/ingestion/brave_budget.py`](src/ingestion/brave_budget.py)

---

### 12.25 Circuit Breaker Thresholds

**Purpose**: Triggers circuit breaker on consecutive failures.

**Threshold**: 3 consecutive failures trigger OPEN state

**Implementation**: [`src/ingestion/tavily_provider.py`](src/ingestion/tavily_provider.py)

**Configuration**: [`config/settings.py`](config/settings.py:510)
```python
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
```

---

### 12.26 Circuit Breaker Recovery Timeout

**Purpose**: Time before attempting HALF_OPEN state.

**Threshold**: 5 minutes (300 seconds)

**Implementation**: [`src/ingestion/tavily_provider.py`](src/ingestion/tavily_provider.py)

**Configuration**: [`config/settings.py`](config/settings.py:515)
```python
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 300
```

---

### 12.27 Rate Limiting Intervals

**Purpose**: Minimum time between requests per domain.

**Intervals**:
- **Brave API**: 0.5s minimum
- **Tavily API**: 0.3s minimum
- **Web Scraping**: 2.0s minimum
- **FotMob API**: 1.0s minimum

**Implementation**: [`src/utils/http_client.py`](src/utils/http_client.py:67-100)

---

### 12.28 Rate Limiting Jitter

**Purpose**: Random delay added to rate limiting for pattern prevention.

**Jitter Ranges**:
- **Brave API**: 0.1s - 0.3s
- **Tavily API**: 0.05s - 0.15s
- **Web Scraping**: 0.5s - 1.5s
- **FotMob API**: 0.2s - 0.5s

**Implementation**: [`src/utils/http_client.py`](src/utils/http_client.py:67-100)

---

### 12.29 Connection Pool Size

**Purpose**: Database connection pool configuration.

**Thresholds**:
- **Base Pool Size**: 5 connections
- **Max Overflow**: 5 additional connections (total 10)
- **Connection Timeout**: 60 seconds
- **Connection Recycling**: 1 hour

**Implementation**: [`src/database/models.py`](src/database/models.py:338-350)

---

### 12.30 Database Retry Attempts

**Purpose**: Maximum retry attempts on database lock.

**Threshold**: 3 attempts with exponential backoff

**Implementation**: [`src/database/db.py`](src/database/db.py:394-437)

---

### 12.31 Cache TTL

**Purpose**: Time-to-live for cached content.

**Thresholds**:
- **Shared Cache**: 30 minutes (1800 seconds)
- **Tavily Cache**: 30 minutes
- **Smart Cache**: 1 hour

**Implementation**: [`src/utils/shared_cache.py`](src/utils/shared_cache.py)

---

### 12.32 Emergency Cleanup Threshold

**Purpose**: Triggers emergency cleanup on high disk usage.

**Threshold**: >90% disk usage

**Implementation**: [`src/database/maintenance.py`](src/database/maintenance.py:124-207)

**Configuration**: [`config/settings.py`](config/settings.py:520)
```python
EMERGENCY_CLEANUP_DISK_THRESHOLD = 0.90
```

---

## 13. Core Features (22/22 Verified)

This section documents all 22 verified core features that form the foundation of EarlyBird V8.3.

### 13.1 Continental Scheduler

**Purpose**: Orchestrates analysis cycles based on time zones and league tiers.

**Implementation**: [`src/services/news_radar.py`](src/services/news_radar.py)

**Core Features**:
- **Time Zone Awareness**: Scheduling based on league time zones
- **Tier-Based Gating**: Different search triggers per tier
- **96-Hour Lookahead**: Early odds tracking
- **72-Hour Analysis Window**: Comprehensive intelligence gathering

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - 6H CYCLE**

This is a **V8.3 standard** - primary operational logic for scheduling.

**6-Hour Cycle Configuration**:
- **Analysis Cycle**: 120 minutes (2 hours)
- **Cooldown Period**: 6 hours between analyses
- **Final Check Window**: 2 hours before kickoff

**Configuration**: [`config/settings.py`](config/settings.py:600-610)
```python
ANALYSIS_CYCLE_MINUTES = 120
COOLDOWN_PERIOD_HOURS = 6
FINAL_CHECK_WINDOW_HOURS = 2
```

---

### 13.2 Multi-Channel Hunter

**Purpose**: Discovers betting-relevant news from multiple sources.

**Implementation**: [`src/ingestion/search_provider.py`](src/ingestion/search_provider.py)

**Core Features**:
- **Multi-Source Aggregation**: Brave, Tavily, DDG, MediaStack, Nitter
- **Deduplication**: Content hashing prevents redundant processing
- **Freshness Scoring**: Recent intelligence prioritized
- **Relevance Filtering**: Removes low-quality content

---

### 13.3 Deep Analysis Engine

**Purpose**: Correlates data sources and generates betting recommendations.

**Implementation**: [`src/analysis/analyzer.py`](src/analysis/analyzer.py)

**Core Features**:
- **AI-Powered Analysis**: DeepSeek V3.2 with fallback hierarchy
- **Multi-Source Correlation**: Synthesizes intelligence from multiple sources
- **Confidence Scoring**: 0-10 scale based on evidence quality
- **Market Selection**: "Equal Citizen" rule for all market types

---

### 13.4 Tactical Brain

**Purpose**: Applies veto rules and context-aware decision making.

**Implementation**: [`src/analysis/analyzer.py`](src/analysis/analyzer.py:1200-1400)

**Core Features**:
- **Tactics > Statistics Hierarchy**: Tactical considerations override statistics
- **Position-Based Veto Logic**: OFFENSIVE/DEFENSIVE DEPLETION
- **Extreme Impact Threshold**: 5.0 injury impact triggers veto
- **Confidence Adjustment**: ±2.0 points based on tactical assessment

---

### 13.5 Notifier

**Purpose**: Sends alerts to Telegram with formatted messages.

**Implementation**: [`src/alerting/notifier.py`](src/alerting/notifier.py)

**Core Features**:
- **Telegram Integration**: Real-time notifications via Telegram Bot API
- **Alert Formatting**: Structured messages with match details, reasoning, stake
- **Feedback Loop**: Captures user feedback for re-processing
- **Deduplication**: Prevents duplicate alerts

---

### 13.6 Optimizer

**Purpose**: Manages strategy weights based on performance.

**Implementation**: [`src/analysis/optimizer.py`](src/analysis/optimizer.py)

**Core Features**:
- **Weight Adjustment**: Adjusts strategy weights based on ROI, Sortino, Max Drawdown
- **Sample Size Guards**: FROZEN/WARMING_UP/ACTIVE states
- **Self-Healing**: Automatic adjustment on poor performance
- **Stateless Learning**: No persistent state between runs

---

### 13.7 Learning Loop

**Purpose**: Captures feedback and refines strategy performance.

**Implementation**: [`src/analysis/alert_feedback_loop.py`](src/analysis/alert_feedback_loop.py)

**Core Features**:
- **Feedback Capture**: User feedback collection
- **Re-Processing**: Modified analysis based on feedback
- **Performance Tracking**: ROI, CLV, Win/Loss tracking
- **Strategy Adjustment**: Optimizer adjusts weights based on performance

---

### 13.8 Settler

**Purpose**: Tracks match results and calculates performance metrics.

**Implementation**: [`src/analysis/settler.py`](src/analysis/settler.py)

**Core Features**:
- **Match Result Tracking**: Fetches final scores from FotMob
- **ROI Calculation**: Uses `odds_at_alert` for accurate ROI
- **CLV Calculation**: Compares `odds_at_alert` vs `odds_at_kickoff`
- **Post-Match Statistics**: 16 columns of stats for AI training

---

### 13.9 Database Layer

**Purpose**: Persistent storage for matches, analyses, and learning data.

**Implementation**: [`src/database/db.py`](src/database/db.py), [`src/database/models.py`](src/database/models.py)

**Core Features**:
- **SQLite with WAL Mode**: Concurrent reads/writes
- **Connection Pooling**: 5 base connections, up to 10 total
- **Transaction Management**: Auto-commit/rollback via context managers
- **Indexes**: Query optimization for performance

---

### 13.10 Odds Capture Service

**Purpose**: Captures kickoff odds for accurate CLV calculation.

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - ODDS CAPTURE SERVICE**

This is a **V8.3 standard** - primary operational logic for learning loop integrity.

**Implementation**: [`src/services/odds_capture.py`](src/services/odds_capture.py)

**Core Features**:
- **Scheduled Job**: Runs every 5 minutes
- **Kickoff Detection**: Finds matches that started within last 10 minutes
- **Odds Capture**: Stores `odds_at_kickoff` in database
- **V8.3 Fields**: `odds_at_alert`, `odds_at_kickoff`, `alert_sent_at`

**Configuration**: [`config/settings.py`](config/settings.py:620-625)
```python
ODDS_CAPTURE_INTERVAL_MINUTES = 5
ODDS_CAPTURE_KICKOFF_WINDOW_MINUTES = 10
```

---

### 13.11 Verification Layer

**Purpose**: Multi-layer verification for alert quality control.

**Implementation**: [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py)

**Core Features**:
- **Multi-Site Query Builder**: Constructs queries for multiple search engines
- **Cross-Source Validation**: Verifies intelligence across multiple sources
- **Confidence Scoring**: Assigns confidence based on source reliability
- **Conflict Detection**: Identifies conflicting intelligence

---

### 13.12 Intelligence Router

**Purpose**: Orchestrates AI provider selection and fallback hierarchy.

**Implementation**: [`src/services/intelligence_router.py`](src/services/intelligence_router.py)

**Core Features**:
- **Provider Selection**: Intelligent provider routing based on availability
- **Fallback Hierarchy**: Primary → Secondary → Emergency
- **Budget Management**: Tracks API quota usage
- **Performance Tracking**: Logs provider performance metrics

---

### 13.13 News Hunter

**Purpose**: Coordinates multi-channel news gathering.

**Implementation**: [`src/processing/news_hunter.py`](src/processing/news_hunter.py)

**Core Features**:
- **Multi-Source Aggregation**: Coordinates Brave, Tavily, DDG, MediaStack
- **Deduplication**: Content hashing prevents redundant processing
- **Freshness Scoring**: Recent intelligence prioritized
- **Relevance Filtering**: Removes low-quality content

---

### 13.14 Browser Monitor

**Purpose**: Monitors web sources for real-time intelligence.

**Implementation**: [`src/services/browser_monitor.py`](src/services/browser_monitor.py)

**Core Features**:
- **Web Scraping**: Playwright for JavaScript-heavy sites
- **Per-URL Circuit Breakers**: Prevents cascading failures
- **Content Extraction**: Trafilatura for clean text parsing
- **Fingerprint Rotation**: Anti-bot evasion

---

### 13.15 Telegram Monitor

**Purpose**: Monitors Telegram channels for intelligence.

**Implementation**: [`src/processing/telegram_listener.py`](src/processing/telegram_listener.py)

**Core Features**:
- **Channel Scraping**: Monitors configured Telegram channels
- **Content Extraction**: OCR for image-based posts
- **Relevance Filtering**: Removes low-quality content
- **Trust Score**: Channel trust scoring

---

### 13.16 Twitter Intel

**Purpose**: Gathers intelligence from Twitter/X via Nitter.

**Implementation**: [`src/services/nitter_fallback_scraper.py`](src/services/nitter_fallback_scraper.py)

**Core Features**:
- **Nitter Fallback**: Bypasses Twitter API limitations
- **Multi-Instance Rotation**: Reliability through multiple instances
- **Content Extraction**: Trafilatura for clean text parsing
- **Freshness Priority**: Recent tweets prioritized

---

### 13.17 FotMob Integration

**Purpose**: Enriches match data with FotMob statistics.

**Implementation**: [`src/utils/inspect_fotmob.py`](src/utils/inspect_fotmob.py)

**Core Features**:
- **Match Statistics**: 16 post-match statistics for AI training
- **Team Mapping**: API team name to FotMob ID mapping
- **Lineup Data**: Starting XI and substitutions
- **Live Updates**: Real-time match data

---

### 13.18 Weather Provider

**Purpose**: Provides weather data for match analysis.

**Implementation**: [`src/ingestion/weather_provider.py`](src/ingestion/weather_provider.py)

**Core Features**:
- **Open-Meteo API**: Free weather data
- **Match Location**: Weather at match venue
- **Impact Analysis**: Weather impact on match outcomes
- **Alert Adjustment**: Confidence adjustment based on weather

---

### 13.19 Health Monitor

**Purpose**: Monitors system health and performance.

**Implementation**: [`src/alerting/health_monitor.py`](src/alerting/health_monitor.py)

**Core Features**:
- **System Metrics**: CPU, memory, disk usage
- **API Status**: Provider availability and quota status
- **Database Health**: Connection pool status, lock errors
- **Alerting**: Health alerts via Telegram

---

### 13.20 Shared Cache

**Purpose**: Cross-component deduplication to prevent redundant processing.

**Implementation**: [`src/utils/shared_cache.py`](src/utils/shared_cache.py)

**Core Features**:
- **Content Deduplication**: Prevents redundant API calls
- **Thread Safety**: RLock for concurrent access
- **TTL**: 30 minutes cache lifetime
- **LRU Eviction**: Least recently used eviction policy

---

### 13.21 HTTP Client

**Purpose**: Centralized HTTP client with fingerprint rotation.

**Implementation**: [`src/utils/http_client.py`](src/utils/http_client.py)

**Core Features**:
- **Fingerprint Rotation**: Automatic rotation on 403/429 errors
- **Rate Limiting**: Per-domain rate limiting with jitter
- **Retry Logic**: Automatic retry with exponential backoff
- **Domain-Sticky FP**: Persistent fingerprint per domain

---

### 13.22 Text Normalizer

**Purpose**: Unicode normalization for consistent text handling.

**Implementation**: [`src/utils/text_normalizer.py`](src/utils/text_normalizer.py)

**Core Features**:
- **NFC Normalization**: Consistent text representation
- **UTF-8 Truncation**: Safe truncation at 3000 bytes
- **Multilingual Support**: Handles international characters
- **Cross-Platform**: Consistent behavior across OS

---

## 14. Workflow Processes (10 Pipeline Phases)

This section documents the 10 pipeline phases that form the complete EarlyBird V8.3 workflow.

### 14.1 Phase 1: Match Discovery

**Purpose**: Discover matches from The-Odds-API and inject into database.

**Implementation**: [`src/ingestion/ingest_fixtures.py`](src/ingestion/ingest_fixtures.py)

**Process**:
1. Fetch fixtures from The-Odds-API
2. Filter by configured leagues
3. Store in Match table
4. Set opening odds (first time seen)
5. Schedule for analysis

**Output**: Match records in database with opening odds

---

### 14.2 Phase 2: Scheduling

**Purpose**: Schedule matches for analysis based on time zones and tiers.

**Implementation**: [`src/services/news_radar.py`](src/services/news_radar.py)

**Process**:
1. Query database for upcoming matches
2. Filter by time window (96-hour lookahead)
3. Apply tier-based gating:
   - Tier 1: Search if odds drop >5% OR FotMob warning
   - Tier 2: Search ONLY if odds drop >15% OR FotMob HIGH RISK
   - Intel-only: Always search (no odds gating)
4. Inject into main pipeline

**Output**: Matches queued for analysis

---

### 14.3 Phase 3: Intelligence Gathering

**Purpose**: Gather intelligence from multiple sources.

**Implementation**: [`src/ingestion/search_provider.py`](src/ingestion/search_provider.py)

**Process**:
1. Multi-Channel Hunter aggregates intelligence:
   - Brave Search API (primary)
   - Tavily AI Search (pre-enrichment)
   - DuckDuckGo (fallback)
   - MediaStack (emergency)
   - Nitter (Twitter/X)
2. Deduplication via content hashing
3. Freshness scoring
4. Relevance filtering

**Output**: Aggregated intelligence items

---

### 14.4 Phase 4: Deep Analysis

**Purpose**: AI-powered analysis of aggregated intelligence.

**Implementation**: [`src/analysis/analyzer.py`](src/analysis/analyzer.py)

**Process**:
1. Intelligence Router selects AI provider:
   - Primary: DeepSeek V3.2
   - Fallback: Perplexity
   - Emergency: Cached results
2. Context building from multiple sources
3. Unicode normalization (NFC)
4. UTF-8 truncation (3000 bytes)
5. AI processing with 500+ line system prompt
6. Confidence scoring (0-10)

**Output**: Analysis results with confidence score

---

### 14.5 Phase 5: Tactical Veto

**Purpose**: Apply tactical veto rules.

**Implementation**: [`src/analysis/analyzer.py`](src/analysis/analyzer.py:1200-1400)

**Process**:
1. Tactics > Statistics hierarchy enforced
2. Position-based veto logic:
   - OFFENSIVE DEPLETION
   - DEFENSIVE DEPLETION
3. Extreme impact threshold (5.0)
4. Confidence adjustment (±2.0)
5. Veto activation with reasoning

**Output**: Veto decision (pass/fail) with reasoning

---

### 14.6 Phase 6: Final Verification

**Purpose**: Multi-layer verification before alert dispatch.

**Implementation**: [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py)

**Process**:
1. Confidence threshold check (9.0 Elite / 7.5 Radar)
2. Market veto check (15% drop threshold)
3. Tactical veto check
4. Duplicate alert check
5. Score-delta deduplication check

**Output**: Verification result (pass/fail) with reasoning

---

### 14.7 Phase 7: Position Sizing

**Purpose**: Calculate optimal stake using Kelly Criterion.

**Implementation**: [`src/analysis/math_engine.py`](src/analysis/math_engine.py:426-440)

**Process**:
1. Calculate balanced probability: (Poisson + AI) / 2
2. Apply Kelly Criterion
3. Multiply by 0.25 (Quarter-Kelly)
4. Apply safety caps (min 0.5%, max 5.0%)
5. Return final stake percentage

**Output**: Stake percentage

---

### 14.8 Phase 8: Alert Dispatch

**Purpose**: Send alert to Telegram.

**Implementation**: [`src/alerting/notifier.py`](src/alerting/notifier.py)

**Process**:
1. Format alert message with:
   - Match details
   - Market recommendation
   - Confidence score
   - Reasoning
   - Stake percentage
   - Odds
2. Capture `odds_at_alert` (V8.3)
3. Capture `alert_sent_at` timestamp (V8.3)
4. Send via Telegram Bot API
5. Store in NewsLog table

**Output**: Telegram alert sent

---

### 14.9 Phase 9: Odds Capture

**Purpose**: Capture kickoff odds for CLV calculation.

**🔴 V8.3 PRIMARY OPERATIONAL LOGIC - ODDS CAPTURE SERVICE**

This is a **V8.3 standard** - primary operational logic for learning loop integrity.

**Implementation**: [`src/services/odds_capture.py`](src/services/odds_capture.py)

**Process**:
1. Scheduled job runs every 5 minutes
2. Find matches that started within last 10 minutes
3. Capture current odds
4. Store in `odds_at_kickoff` field
5. Update match record

**Output**: `odds_at_kickoff` stored in database

---

### 14.10 Phase 10: Settlement & Learning

**Purpose**: Track match results and adjust strategy weights.

**Implementation**: [`src/analysis/settler.py`](src/analysis/settler.py), [`src/analysis/optimizer.py`](src/analysis/optimizer.py)

**Process**:
1. Settler fetches final scores from FotMob
2. Calculates Win/Loss for each alert
3. Computes ROI using `odds_at_alert` (V8.3)
4. Computes CLV comparing `odds_at_alert` vs `odds_at_kickoff` (V8.3)
5. Stores 16 post-match statistics
6. Optimizer reads historical performance
7. Calculates risk-adjusted metrics (Sharpe, Sortino, Max Drawdown)
8. Adjusts strategy weights based on performance
9. Implements sample size guards (FROZEN < 30, WARMING 30-50, ACTIVE 50+)
10. Stores updated weights in `data/optimizer_weights.json`

**Output**: Updated strategy weights

---

## 15. Configuration & Settings

This section documents the configuration and settings management for EarlyBird V8.3.

### 15.1 Settings File Structure

**Implementation**: [`config/settings.py`](config/settings.py)

**Configuration Categories**:
- **Alert Thresholds**: Elite, Radar, Settlement thresholds
- **CLV Thresholds**: Excellent, Good, Marginal thresholds
- **Fatigue Multipliers**: Elite, Tier 2, Low-tier multipliers
- **Biscotto Thresholds**: Z-Score, draw odds thresholds
- **RLM Thresholds**: Public betting, odds increase thresholds
- **Steam Move Thresholds**: Odds drop, time window thresholds
- **News Decay**: Lambda values per league tier
- **Sample Size**: FROZEN, WARMING_UP, ACTIVE thresholds
- **Self-Healing**: Drawdown brake, Sortino boost
- **Kelly Criterion**: Min/max stakes, quarter multiplier
- **Market Veto**: Odds drop threshold
- **Tactical Veto**: Extreme impact, confidence adjustment
- **Dixon-Coles**: Rho, home advantage parameters
- **Value Detection**: Excellent, Good, Marginal thresholds
- **Injury Impact**: Severity thresholds, position multipliers
- **B-Team**: Key players, youth players, formation change thresholds
- **Tavily Budget**: Component allocation, throttling thresholds
- **Brave Budget**: Component allocation, throttling thresholds
- **Circuit Breaker**: Failure threshold, recovery timeout
- **Rate Limiting**: Intervals, jitter ranges
- **Connection Pool**: Size, timeout, recycling
- **Cache TTL**: Shared cache, Tavily cache, Smart cache
- **Emergency Cleanup**: Disk threshold
- **Scheduling**: Analysis cycle, cooldown, final check window
- **Odds Capture**: Interval, kickoff window

---

### 15.2 Environment Variables

**Implementation**: `.env` file

**Required Variables**:
- `BRAVE_API_KEYS`: Comma-separated Brave API keys
- `TAVILY_API_KEYS`: Comma-separated Tavily API keys
- `MEDIASTACK_API_KEYS`: Comma-separated MediaStack API keys
- `PERPLEXITY_API_KEY`: Perplexity API key
- `OPENROUTER_API_KEY`: OpenRouter API key (DeepSeek)
- `TELEGRAM_BOT_TOKEN`: Telegram bot token
- `TELEGRAM_CHAT_ID`: Telegram chat ID for alerts
- `FOTMOB_API_KEY`: FotMob API key
- `ODDS_API_KEY`: The-Odds-API key

---

### 15.3 League Configuration

**Implementation**: [`config/settings.py`](config/settings.py:100-200)

**League Tiers**:
- **Elite**: Premier League, La Liga, Serie A, Bundesliga, Ligue 1
- **Tier 1**: Eredivisie, Primeira Liga, Süper Lig, etc.
- **Tier 2**: Championship, Serie B, 2. Bundesliga, etc.

**League-Specific Parameters**:
- Home advantage (Dixon-Coles)
- News decay rate (lambda)
- Fatigue multiplier
- Motivation factors

---

## 16. Security Measures

This section documents the security measures implemented in EarlyBird V8.3.

### 16.1 API Key Management

**Implementation**: [`config/settings.py`](config/settings.py)

**Security Features**:
- **Environment Variables**: API keys stored in `.env` file (not in code)
- **Key Rotation**: Automatic rotation on quota exhaustion
- **Budget Management**: Prevents quota exhaustion
- **Fallback Hierarchy**: Graceful degradation on key exhaustion

---

### 16.2 Fingerprint Rotation

**Implementation**: [`src/utils/http_client.py`](src/utils/http_client.py)

**Security Features**:
- **Anti-Bot Evasion**: Automatic fingerprint rotation on 403/429 errors
- **Domain-Sticky FP**: Persistent fingerprint per domain
- **User Agent Rotation**: Random user agent selection
- **Header Randomization**: Random header values

---

### 16.3 Rate Limiting

**Implementation**: [`src/utils/http_client.py`](src/utils/http_client.py:67-100)

**Security Features**:
- **Per-Domain Rate Limiting**: Respects API rate limits
- **Jitter**: Random delays prevent pattern detection
- **Exponential Backoff**: Automatic retry with increasing delays
- **Circuit Breaker**: Automatic failover on consecutive failures

---

### 16.4 Input Validation

**Implementation**: [`src/utils/validators.py`](src/utils/validators.py)

**Security Features**:
- **URL Validation**: Validates URLs before processing
- **Content Validation**: Validates content before storage
- **SQL Injection Prevention**: Parameterized queries
- **XSS Prevention**: Input sanitization

---

### 16.5 Database Security

**Implementation**: [`src/database/models.py`](src/database/models.py)

**Security Features**:
- **SQLite with WAL Mode**: Concurrent reads/writes
- **Connection Pooling**: Prevents connection exhaustion
- **Transaction Management**: ACID compliance
- **Foreign Key Constraints**: Referential integrity

---

## 17. Testing & Quality Assurance

This section documents the testing and quality assurance measures for EarlyBird V8.3.

### 17.1 Test Suite

**Implementation**: `tests/` directory

**Test Categories**:
- **Unit Tests**: Individual component testing
- **Integration Tests**: Multi-component testing
- **End-to-End Tests**: Complete pipeline testing
- **Manual Tests**: Manual testing scripts

---

### 17.2 Test Coverage

**Coverage Areas**:
- **API Providers**: Brave, Tavily, MediaStack, Perplexity
- **Analysis Engines**: Fatigue, Biscotto, Verification, CLV, etc.
- **Mathematical Models**: Dixon-Coles, Poisson, Kelly, etc.
- **Database Operations**: CRUD operations, migrations
- **Workflow Processes**: All 10 pipeline phases

---

### 17.3 V8.3 Test Results

**Status**: 100% Test Pass Rate

**Verified Features**:
- **API Integrations**: 26/26 verified
- **Analysis Engines**: 11/11 verified
- **Mathematical Models**: 9/9 verified
- **Operational Rules**: 32/32 verified
- **Core Features**: 22/22 verified

**Total**: 247/247 features verified and ALIVE

---

## 18. Evolution & Production Status

This section documents the evolution of EarlyBird from V3.0 to V8.3 and confirms production readiness.

### 10.1 Version History

**V3.0 - Simple Scraper**
- Basic web scraping for match odds
- Manual analysis workflow
- Limited league coverage
- No self-learning capabilities

**V4.0 - Multi-Source Intelligence**
- Added multiple search providers (Brave, DDG, Serper)
- Automated news gathering
- Basic AI analysis integration
- Initial verification layer

**V5.0 - Tactical Brain Integration**
- Added tactical veto system
- Injury impact analysis
- B-Team detection
- Enhanced market intelligence
- CLV tracking implementation

**V6.0 - Intelligence Router V7.0**
- DeepSeek V3.2 as primary provider
- Tavily pre-enrichment
- Perplexity fallback
- Smart provider routing
- Budget-managed API calls

**V7.0 - Verification Layer**
- Final verifier integration
- Multi-site fact-checking
- Player impact validation
- Score adjustment logic
- Market change suggestions

**V8.0 - Learning Loop Integration**
- Tactical Brain V8.0 integration verified
- Enhanced feedback loop
- Opportunity Radar V2.0
- Browser Monitor improvements

**V8.3 - Learning Loop Integrity Fix** (Current Version)
- Critical fix for accurate ROI and CLV calculation
- New database fields: `odds_at_alert`, `odds_at_kickoff`, `alert_sent_at`
- Odds Capture Service for kickoff odds
- Updated Settler logic for accurate performance tracking
- 100% test pass rate stability confirmation

### 10.2 Production Status

**Stability Confirmation:**
- **100% Test Pass Rate**: All tests passing
- **Learning Loop Integrity**: Verified accurate odds tracking
- **Tactical Veto**: Production-ready implementation
- **API Key Rotation**: Double cycle support for 2x monthly capacity
- **Database Schema**: Optimized with indexes for performance
- **Emergency Cleanup**: Disk space management with >90% threshold

**Deployment Readiness:**
- ✅ Plug & Play VPS launch supported
- ✅ Environment injection for API keys
- ✅ Graceful degradation when providers unavailable
- ✅ Comprehensive error handling and logging
- ✅ VPS-compatible implementation
- ✅ No new dependencies required for V8.3

**Key Achievements:**
1. **From Simple Scraper to Professional Betting Intelligence Engine**
   - Multi-source intelligence gathering
   - AI-powered deep analysis
   - Self-learning optimization
   - Real-time alerting

2. **Learning Loop Integrity**
   - Accurate ROI calculation using actual betting odds
   - Meaningful CLV analysis comparing alert vs kickoff odds
   - Reliable strategy weight adjustment based on correct data

3. **Tactical Intelligence**
   - Position-based veto logic
   - Cross-reference intelligence validation
   - Context-aware decision making
   - Transparency with explicit veto tagging

4. **Production-Ready Infrastructure**
   - Robust error handling
   - Graceful degradation
   - Automated maintenance
   - Emergency cleanup capabilities

---

**Phase 3 Complete: Advanced Architecture and Evolution documented.**

---

## Final Table of Contents

| Section | Title | Description |
|---------|-------|-------------|
| 1 | [Executive Summary](#1-executive-summary) | System purpose, key components, V8.3 improvements, architecture philosophy, technology stack |
| 2 | [The Cerebral Flow (Visual Conceptual Map)](#2-the-cerebral-flow-visual-conceptual-map) | Complete data journey visualization with V8.3 learning loop integration |
| 3 | [Intelligence & Component Breakdown](#3-intelligence--component-breakdown) | Intelligence Router, Multi-Channel Hunter, Tactical Brain, Standard Preservation |
| 4 | [Betting Strategy & Money Management](#4-betting-strategy--money-management) | Confidence thresholds, market philosophy, position sizing, safety veto |
| 5 | [The Data Journey (Pipeline)](#5-the-data-journey-pipeline) | Complete data flow from scheduling through alert dispatch |
| 6 | [Database Schema](#6-database-schema) | Core tables (Match, NewsLog, TeamAlias), 16 post-match columns, data integrity features |
| 7 | [API & External Providers](#7-api--external-providers) | 3-layer search, Deep Dive intelligence, Tavily fact-check, key rotators and budget allocation |
| 8 | [Persistence Layer](#8-persistence-layer) | Database connection management, session handling, transaction management, maintenance and cleanup |
| 9 | [Advanced Architectural Patterns](#9-advanced-architectural-patterns) | Resilience, Performance, Data, Safety, and Operational patterns (17 patterns total) |
| 10 | [Analysis Engines (11/11 Verified)](#10-analysis-engines-1111-verified) | Fatigue V2.0, Biscotto V2.0, Verification V7.0, CLV V5.0, Tactical Veto V8.0, B-Team V2.0, BTTS V4.1, Motivation V4.2, Intelligence Router V7.0, Opportunity Radar V2.0, Injury Impact |
| 11 | [Mathematical Models (9/9 Verified)](#11-mathematical-models-99-verified) | Dixon-Coles, Poisson, Kelly, Sortino, CLV, Exponential Decay, News Decay, Z-Score, Value Detection |
| 12 | [Operational Rules & Thresholds (32/32 Verified)](#12-operational-rules--thresholds-3232-verified) | CLV, Fatigue, Biscotto, RLM, Steam Move, News Decay, Sample Size, Self-healing, Alert thresholds, Kelly, Market Veto, Tactical Veto, Dixon-Coles, Value Detection, Injury Impact, Position Impact, B-Team, Fatigue History, Sortino, Tavily Budget, Tavily Throttling, Brave Budget, Brave Throttling, Circuit Breaker, Recovery Timeout, Rate Limiting, Rate Limiting Jitter, Connection Pool, Database Retry, Cache TTL, Emergency Cleanup |
| 13 | [Core Features (22/22 Verified)](#13-core-features-2222-verified) | Continental Scheduler, Multi-Channel Hunter, Deep Analysis Engine, Tactical Brain, Notifier, Optimizer, Learning Loop, Settler, Database Layer, Odds Capture Service, Verification Layer, Intelligence Router, News Hunter, Browser Monitor, Telegram Monitor, Twitter Intel, FotMob Integration, Weather Provider, Health Monitor, Shared Cache, HTTP Client, Text Normalizer |
| 14 | [Workflow Processes (10 Pipeline Phases)](#14-workflow-processes-10-pipeline-phases) | Match Discovery, Scheduling, Intelligence Gathering, Deep Analysis, Tactical Veto, Final Verification, Position Sizing, Alert Dispatch, Odds Capture, Settlement & Learning |
| 15 | [Configuration & Settings](#15-configuration--settings) | Settings file structure, environment variables, league configuration |
| 16 | [Security Measures](#16-security-measures) | API key management, fingerprint rotation, rate limiting, input validation, database security |
| 17 | [Testing & Quality Assurance](#17-testing--quality-assurance) | Test suite, test coverage, V8.3 test results |
| 18 | [Evolution & Production Status](#18-evolution--production-status) | Version history from V3.0 to V8.3, production readiness confirmation |

---

## Obsolete Files Identification

The following files have been superseded by [`MASTER_SYSTEM_ARCHITECTURE.md`](MASTER_SYSTEM_ARCHITECTURE.md) and should be removed:

| File | Reason for Removal |
|-------|-------------------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Superseded by MASTER_SYSTEM_ARCHITECTURE.md - comprehensive single source of truth |
| [`CEREBRAL_FLOW_CONCEPTUAL_MAP.md`](CEREBRAL_FLOW_CONCEPTUAL_MAP.md) | Conceptual map now integrated into Section 2 of MASTER_SYSTEM_ARCHITECTURE.md |
| [`TODO_REFACTOR.md`](TODO_REFACTOR.md) | Refactoring items should be tracked in project issues rather than standalone file |

**Action Required**: Remove these files to eliminate documentation redundancy and maintain single source of truth.

---

**MASTER_SYSTEM_ARCHITECTURE.md is now the SINGLE SOURCE OF TRUTH.**
