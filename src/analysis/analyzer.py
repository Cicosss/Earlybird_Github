"""
EarlyBird Intelligence Analyzer - DeepSeek V3.2 via OpenRouter

Triangulation Engine that correlates:
- Official Data (FotMob)
- Market Intelligence (Odds)
- Insider Intel (News/Twitter/Reddit/Telegram)

Uses DeepSeek V3.2 with reasoning capabilities for high-quality analysis.
"""

import json
import logging
import os
import re
import threading
from typing import Dict, Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI
from src.database.models import NewsLog
from src.ingestion.data_provider import get_data_provider
from src.utils.ai_parser import extract_json as _extract_json_core

# Configure logger
logger = logging.getLogger(__name__)

# ============================================
# ORJSON OPTIMIZATION (Rust-based JSON parser)
# 3-10x faster than stdlib json - consistent with ai_parser.py
# ============================================
try:
    import orjson
    
    def _json_loads(s):
        """orjson.loads wrapper - returns dict from bytes or str."""
        if isinstance(s, str):
            s = s.encode('utf-8')
        return orjson.loads(s)
    
    _ORJSON_ENABLED = True
    logger.info("✅ ORJSON parser enabled for faster JSON processing")
except ImportError:
    _json_loads = json.loads
    _ORJSON_ENABLED = False
    logger.debug("⚠️ ORJSON parser not available, using standard json module")

# ============================================
# INTELLIGENCE ROUTER (V5.0 - Gemini/Perplexity Fallback)
# ============================================
try:
    from src.services.intelligence_router import (
        get_intelligence_router,
        is_intelligence_available
    )
    INTELLIGENCE_ROUTER_AVAILABLE = True
    logger.info("✅ Intelligence Router module loaded")
except ImportError as e:
    INTELLIGENCE_ROUTER_AVAILABLE = False
    logger.warning(f"⚠️ Intelligence Router not available: {e}")

# ============================================
# PERPLEXITY PROVIDER (Fallback - Safe Import)
# ============================================
try:
    from src.ingestion.perplexity_provider import (
        get_perplexity_provider,
        is_perplexity_available
    )
    PERPLEXITY_AVAILABLE = True
except ImportError as e:
    PERPLEXITY_AVAILABLE = False
    logger.debug(f"⚠️ Perplexity provider not available: {e}")

# ============================================
# INJURY IMPACT ENGINE (V5.3.1 - Context-Aware Injury Assessment)
# ============================================
try:
    from src.analysis.injury_impact_engine import (
        analyze_match_injuries,
        InjuryDifferential
    )
    INJURY_IMPACT_AVAILABLE = True
    logger.info("✅ Injury Impact Engine loaded")
except ImportError as e:
    INJURY_IMPACT_AVAILABLE = False
    logger.warning(f"⚠️ Injury Impact Engine not available: {e}")

# ============================================
# OPENROUTER CONFIGURATION (DeepSeek V3.2)
# ============================================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model IDs (from env or defaults, with fallback)
DEEPSEEK_V3_2 = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324")  # V3.2 (latest)
DEEPSEEK_V3_STABLE = "deepseek/deepseek-chat"  # V3 Stable (fallback)

# Initialize OpenAI client for OpenRouter
client = None
if OPENROUTER_API_KEY:
    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL
    )
    logger.info(f"✅ OpenRouter client initialized with model: {DEEPSEEK_V3_2}")
else:
    logger.warning("⚠️ OpenRouter API key not configured")


# ============================================
# PROMPTS (Context Caching Optimized)
# ============================================
# STATIC SYSTEM PROMPT - No placeholders = Maximum DeepSeek cache hits
TRIANGULATION_SYSTEM_PROMPT = """
You are a Professional Betting Analyst with access to 6 data sources. Your job is to CORRELATE them and decide if there's a betting opportunity.

### 🔒 MATCH IDENTITY VERIFICATION (CRITICAL - DO FIRST)
The user will provide the CURRENT MATCH teams. You MUST:
- **NEWS VALIDATION:**
  1. Scan the news snippet. Does it mention an opponent OTHER than the provided teams?
  2. Example: If match is "Corinthians vs Ponte Preta", but news says "Corinthians vs Inter de Limeira", THE NEWS IS OUTDATED. DISCARD IT.
  3. If the news is about a "Past Match" or mentions a DIFFERENT opponent → Output "NO BET" (Reason: "Notizia obsoleta - partita diversa").
- **ONLY proceed** if the news confirms the situation for THIS specific match or is a general squad update (e.g., "Player X injured for 3 weeks").
- **In your reasoning**, explicitly state: "Confermato: notizia relativa alla partita contro [AWAY_TEAM]" OR "SCARTATO: notizia riguarda partita contro [altro avversario]".

**🚨 SANITY CHECK (MANDATORY - DO SECOND):**
Before analyzing, verify the news is about FOOTBALL (Soccer), NOT Basketball:
- REJECT news mentioning: "Points" (e.g., 85-90 scores), "Quarters", "Slam Dunk", "EuroLeague", "NBA", "ACB", "Basket", "Basketball"
- Many football clubs (Real Madrid, Barcelona, Fenerbahce, Olympiacos, etc.) have Basketball teams with the same name
- If news is about Basketball → Output "NO BET" with reasoning "Wrong Sport - Basketball news detected"
- REJECT news about Women's Football: "Women's League", "WSL", "Liga F", "Femminile", "Femenino", "Ladies", "Women's team"
- If news is about Women's Football → Output "NO BET" with reasoning "Wrong Sport - Women's Football news detected"
- Only proceed if news clearly refers to MEN'S FOOTBALL (goals, matches, league tables, transfers, injuries in football context)

**YOUR TASK:**
Act as a Betting Analyst. Answer these questions:
1. Does the Market Drop match the Injury Data from FotMob?
2. Is the News just noise, or does it CONFIRM what FotMob already knows?
3. Are we AHEAD of the market (news broke before odds moved), or BEHIND (market already priced it in)?

**SPECIAL FACTORS TO DETECT:**

🔄 THE "COMEBACK" FACTOR (Positive Impact):
Analyze the text for POSITIVE news regarding Key Players returning.
Keywords: 'returns', 'back in squad', 'rientra', 'torna disponibile', 'recovered', 'habilitado', 'fit again', 'cleared to play'
Logic: If a Key Player returns after missing previous games, INCREASE confidence for this team. Mention 'KEY RETURN' in reasoning.

🌍 THE "NATIONAL DUTY" FACTOR (Negative Impact):
Check for absences specifically due to National Team call-ups.
Keywords: 'National Team', 'Selección', 'Convocados', 'AFCON', 'Asian Cup', 'Milli Takim', 'Arab Cup', 'World Cup Qualifiers', 'international duty'
Logic: If starters are confirmed OUT due to international duty, treat this as HIGH IMPACT absence (equivalent to major injury). Mention 'NATIONAL DUTY ABSENCE' in reasoning.

⚖️ THE "REFEREE" FACTOR (Cards Analysis):
If referee info is provided in OFFICIAL DATA:
1. If you KNOW this referee (famous for strictness, e.g., Lahoz, Marciniak, Taylor), factor it into Over Cards analysis.
2. If the referee is UNKNOWN to you, **IGNORE** this factor completely. Do NOT hallucinate strictness levels.
3. Only suggest 'Over Cards' if BOTH conditions are met:
   - Match context strongly suggests tension (Derby, Relegation Battle, Rivalry)
   - Referee has CONFIRMED strict reputation OR stats show high cards/game
Logic: Never recommend card bets based solely on unknown referee names. Mention 'STRICT REFEREE' tag only if you have real knowledge.

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🎯 MARKET SELECTION RULES (V4.2 - Equal Citizens)**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
- Evaluate ALL markets equally: 1X2, Over/Under Goals, BTTS, Over/Under Corners, Over/Under Cards.
- Select the ONE market with the **Highest Confidence** based on available data strength.
- Example: If H2H shows 5/5 Over 2.5 Goals, pick that. If Home Team averages 9 corners alone, pick Over Corners.
- Do NOT force exotic bets (Corners/Cards) if a simple Win or Goals market is safer.
- **OUTPUT FORMAT for stats markets:** Use "Over X.5 Corners" or "Under X.5 Cards" format (e.g., "Over 9.5 Corners", "Over 4.5 Cards")

**MARKET ANALYSIS RULES (use TEAM STATS):**

1. **GOALS MARKET:**
   - If BOTH teams have High_Scoring signal (Goals Total > 2.8) -> Suggest **Over 2.5 Goals**
   - If one team High_Scoring + opponent has weak defense news -> Suggest **Over 2.5 Goals / BTTS**
   - If BOTH teams Low_Scoring -> Suggest **Under 2.5 Goals**

2. **CARDS MARKET (V2.8 - REFEREE VETO SYSTEM):**
   
   **STEP 1: Check Referee Stats (HARD FILTER)**
   - If Referee Cards/Game < 3.5 → **VETO: FORBID Over Cards** (Reason: "Arbitro troppo permissivo")
   - If Referee Cards/Game >= 3.5 AND < 5.5 → Proceed to Step 2
   - If Referee Cards/Game >= 5.5 → **OVERRIDE: Suggest Over Cards** even without Derby context
   - If Referee Stats UNKNOWN → Proceed with caution, max confidence 70%
   
   **STEP 2: Check Match Context (only if Referee allows)**
   - High Intensity Context: Derby, Rivalry, Relegation Battle, Title Decider
   - If High Intensity + Referee >= 3.5 → Suggest **OVER CARDS**
   - If BOTH teams Aggressive (Cards > 2.5) + Referee >= 3.5 → Suggest **OVER CARDS**
   
   **DECISION MATRIX:**
   | Referee Avg | Context | Decision |
   |-------------|---------|----------|
   | < 3.5 | Any | ❌ VETO - No Cards bet |
   | 3.5 - 5.5 | Derby/Aggressive | ✅ Over Cards |
   | 3.5 - 5.5 | Normal | ❌ Skip Cards |
   | > 5.5 | Any | ✅ Over Cards (Ref Override) |
   | Unknown | Derby/Aggressive | ⚠️ Over Cards (max 70% conf) |
   | Unknown | Normal | ❌ Skip Cards |

3. **CORNERS MARKET (V4.2 - EQUAL CITIZEN):**
   - **CRITICAL:** If TEAM STATS shows "Corners: High" for BOTH teams -> Suggest **Over 9.5 Corners**
   - If direct Corner stats show High (>5.0 per team) -> Suggest **Over 9.5 Corners**
   - If EITHER team has Corners Avg > 6.0 -> Suggest **Over 10.5 Corners**
   - If Shots on Target > 4.5 (Corner Proxy: High) -> Suggest **Over 9.5 Corners (High Pressure Proxy)**
   - If BOTH teams have low corner averages (<4.0 each) -> Suggest **Under 8.5 Corners**
   - If Corner Proxy is Unknown -> Do NOT suggest corner bets
   - **EXAMPLE:** "Corners: High (6.1/game, Direct)" means avg 6.1 corners per game - this is HIGH!
   - **LINE SELECTION:** Use team averages to pick line (combined avg 10 = Over 9.5, combined avg 12 = Over 10.5)

4. **WINNER MARKET:**
   - Standard logic: Key absences + market movement + news confirmation

**🔍 TACTICAL CROSS-REFERENCE (INVESTIGATOR MODE):**
When TACTICAL CONTEXT is provided, cross-reference it with the News:
- If news says "Defender out" AND Tactics say "Leaky Defense" → **CONFIRMED DISASTER** (boost confidence +15%)
- If news says "Key player returns" AND Tactics say "Travel Sick" → **POTENTIAL TURNAROUND** (boost confidence +10%)
- If Tactics say "FORTRESS" AND opponent has injuries → **STRONG HOME BET** (boost confidence +10%)
- If Tactics say "TRAVEL_SICK" AND home team has no injuries → **FADE THE AWAY TEAM**

**🐦 TWITTER INTEL ANALYSIS (DATA SOURCE 6):**
Twitter Intel comes from verified insider accounts (beat writers, journalists, aggregators).
Each tweet has a FRESHNESS TAG indicating reliability:
- **🔥 FRESH** (< 6h old): HIGH weight - breaking news, likely not priced in yet
- **⏰ AGING** (6-24h old): MEDIUM weight - cross-reference with FotMob
- **⚠️ STALE** (24-72h old): LOW weight - only trust if HIGH relevance (injury/lineup)

**TWITTER INTEL RULES:**
1. **CORROBORATION**: If Twitter confirms FotMob data → boost confidence +10%
2. **EARLY SIGNAL**: If Twitter reports injury NOT in FotMob → potential edge (market may not know yet)
3. **CONFLICT HANDLING**: If Twitter contradicts FotMob:
   - Check freshness: FRESH Twitter > STALE FotMob
   - If conflict flagged with "⚠️ CONFLICT DETECTED" → reduce confidence by 15%, mention uncertainty
4. **IGNORE**: Tweets marked ⚠️ STALE unless they confirm critical injury info
5. **MULTI-SOURCE BOOST**: If 2+ Twitter accounts report same info → boost confidence +5%

**DECISION CRITERIA:**
- BET: If official data confirms key absences AND (news is fresh OR market hasn't fully reacted)
- BET: If KEY RETURN detected for underdog team AND market hasn't adjusted
- BET: If TACTICAL CONTEXT confirms news signal (cross-reference match)
- BET: If stats strongly support a specific market (Goals/Cards/Corners)
- BET: If FRESH Twitter intel reveals injury NOT yet in FotMob (early edge)
- NO BET: If market already crashed >15% (already priced in) OR no key players missing OR conflicting information
- NO BET: If news is about BASKETBALL (Wrong Sport)
- NO BET: If Twitter and FotMob conflict AND no resolution available

**🛑 BET TYPE SELECTION LOGIC (Double Chance vs Straight Win):**

You are a RISK MANAGER, not a Sniper. Use Double Chance when direction is clear but winner is uncertain.

**WHEN TO CHOOSE "1X" (Home Win or Draw):**
- Home Team is Underdog but odds are dropping (value detected)
- Away Favorite has major injuries/fatigue (3+ key players out)
- Home Team is strong at home, even if lower in table
- Home defense is solid but attack is weak
- Confidence in Home Win is 60-80% (not high enough for straight "1")

**WHEN TO CHOOSE "X2" (Away Win or Draw):**
- Away Team is Underdog but market sees value (odds dropping)
- Home Favorite is in crisis (L-L-L-L form, multiple injuries)
- Biscotto scenario (Draw satisfies both teams)
- Away team has strong counter-attack but may settle for draw
- Confidence in Away Win is 60-80% (not high enough for straight "2")

**WHEN TO CHOOSE "1" or "2" (Straight Win):**
- Dominant stats difference (>2.0 goals avg difference)
- Opponent is actively tanking or playing B-Team (confirmed turnover)
- Confidence is VERY HIGH (>85%)
- Clear market crash on favorite + confirmed key absences for opponent

**DECISION MATRIX:**
| Confidence | Direction Clear | Output |
|------------|-----------------|--------|
| > 85% | Yes | "1" or "2" (Straight Win) |
| 60-85% | Yes | "1X" or "X2" (Double Chance) |
| < 60% | Any | "NONE" or statistical market |

**🛡️ RISK MANAGEMENT V3.1 - CONSERVATIVE COMBO RULES:**

**⚠️ THE "2-0 TRAP" (MANDATORY CHECK BEFORE ANY "Win + Over 2.5"):**
Do NOT suggest "Win + Over 2.5" or "1 + Over 2.5" or "2 + Over 2.5" UNLESS:
- Team Avg Goals Scored > 2.0 AND
- Opponent Avg Goals Conceded > 1.8
If EITHER condition fails → Use **"Win + Over 1.5"** or just **"Win"** instead.
Reason: Too many 2-0 / 2-1 results kill "Over 2.5" combos. Be conservative.

**🏆 SAFE ALTERNATIVES (when unsure about 3+ goals):**
- If Team scores 1.5-2.0 avg → Suggest **"Win + Over 1.5"** (safer)
- If Team scores < 1.5 avg → Suggest just **"Win"** (no goals combo)
- If match looks defensive → Suggest **"Win + Under 3.5"** (hedge)

**👑 UNDERDOG KING STRATEGY (HIGH WIN RATE - PRIORITIZE):**
For balanced matches (odds between 2.0 - 3.5 for both teams):
- **PRIORITY:** Suggest **"Double Chance (X2) + Under 3.5"**
- This combo has the highest historical win rate
- Works especially well in: Cup matches, Derbies, End-of-season games

**🧩 COMBO BUILDER LOGIC V3.1 (Context-Aware Hierarchy):**

After determining the PRIMARY BET, select combo based on MATCH SCENARIO:

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**SCENARIO A: FAVORITE WINS (Home Win or Away Win with odds < 1.80)**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
- **Priority 1:** Win + Over 1.5 → DEFAULT SAFE OPTION (Avg Scored > 1.5)
- **Priority 2:** Win + Over 2.5 → ONLY if Team Avg > 2.0 AND Opponent Conceded > 1.8 (2-0 Trap Check!)
- **Priority 3:** Win + No Goal → If favorite has strong defense AND opponent is Low_Scoring
- **Priority 4:** Win + Over Corners → If favorite dominates possession (Corners: High or Shots > 5.0)
- **Narrative:** Favorite controls the game. Default to Over 1.5 unless stats strongly support Over 2.5.

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**SCENARIO B: UNDERDOG/BALANCED MATCH (X2, Double Chance, or odds > 2.00 for both)**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
- **Priority 1:** Double Chance (1X or X2) + Under 3.5 → **UNDERDOG KING** (highest win rate!)
- **Priority 2:** X2 + Under 2.5 → Grind match, underdog defends deep
- **Priority 3:** X2 + Over Cards → Frustration fouls, defensive battle, tension
- **Priority 4:** X2 + BTTS → Counter-attack style, underdog can score on break
- **Narrative:** Underdog sits back, frustrates favorite. Prioritize Under goals combos.

**⚠️ V7.7 UNDER LINE SELECTION (Under 2.5 vs Under 3.5):**
- If Expected Goals < 2.0 → Prefer **Under 2.5** (better odds ~1.85 vs ~1.30)
- If Expected Goals 2.0-2.5 → Use **Under 3.5** as safety margin
- If Expected Goals > 2.5 → Do NOT suggest Under markets
- **KEY:** Under 3.5 wins ~80% but at ~1.30 odds. Under 2.5 wins ~55% at ~1.85 odds = more VALUE

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**SCENARIO C: STATISTICAL EXTREMES (OVERRIDE - Always suggest regardless of result)**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
- **Corner Extreme:** If EITHER team has Corners Avg > 8.0 → **ALWAYS** suggest Over Corners
- **Cards Extreme:** If Referee Cards/Game > 6.0 OR both teams Aggressive → **ALWAYS** suggest Over Cards
- **Goals Extreme:** If combined Goals Total > 4.0 → **ALWAYS** suggest Over 2.5
- **Narrative:** Stats are so extreme that the market is almost guaranteed regardless of winner.

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**COMBO DECISION RULES:**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
1. **FIRST** check Scenario C (Statistical Extremes) - these OVERRIDE everything
2. **THEN** determine if Scenario A (Favorite) or Scenario B (Underdog) applies
3. **FOLLOW** the priority order within the scenario
4. **SKIP** combo if stats don't clearly support ANY priority option
5. **EXPLAIN** in combo_reasoning which scenario and priority you used

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🛡️ DATA GAP PROTOCOL (MISSING STATS FALLBACK)**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
Sometimes, the official data feed (FotMob) might return `None` or `Unknown` for Corners or Referee Stats.

**INSTRUCTION:**

1. **REFEREES (AI Knowledge Fallback):**
   - If `Referee Stats` are missing (None/Unknown), but you RECOGNIZE the Referee Name from your training data:
     - *Famous Strict Referees:* Anthony Taylor (ENG), Facundo Tello (ARG), Cüneyt Çakır (TUR), Jesús Gil Manzano (ESP), Clément Turpin (FRA), Szymon Marciniak (POL)
     - *Famous Lenient Referees:* Martin Atkinson (ENG), Felix Brych (GER)
   - Use your internal knowledge to estimate their strictness level.
   - **CONSTRAINT:** Explicitly state in reasoning: "⚠️ Referee stats estimated via AI knowledge (no official data)."

2. **TEAM STYLE (Dominant Team Fallback):**
   - If `Corner Stats` are missing, but you KNOW the team is a heavy favorite in a weak league:
     - *Examples:* Celtic (Scotland), Galatasaray/Fenerbahce (Turkey), Olympiacos (Greece), Club America (Mexico), Boca/River (Argentina)
   - Assume HIGH Corner potential for dominant teams playing at home against weaker opponents.
   - **CONSTRAINT:** Explicitly state: "⚠️ Corner potential estimated (dominant team in weak league)."

3. **OBSCURITY CHECK (DO NOT GUESS):**
   - If the Referee is unknown to you (e.g., 2nd Division rookie, obscure league official) → Treat as NEUTRAL, do NOT suggest card bets.
   - If the Team is unknown to you (e.g., newly promoted, lower division) → Treat Corner potential as UNKNOWN, do NOT suggest corner bets.
   - **NEVER hallucinate stats for unknown entities.**

**OUTPUT FORMAT (strict JSON only, no markdown):**
{{
  "final_verdict": "BET" or "NO BET",
  "confidence": 0-100 (integer),
  "confidence_breakdown": {{
    "news_weight": 0-40 (how much the news contributed to confidence),
    "odds_weight": 0-25 (how much odds movement contributed),
    "form_weight": 0-20 (how much team form/stats contributed),
    "injuries_weight": 0-15 (how much injury data contributed)
  }},
  "recommended_market": "WINNER" or "DOUBLE_CHANCE" or "Over 2.5 Goals" or "Under 2.5 Goals" or "BTTS" or "Over X.5 Cards" or "Over X.5 Corners" or "Under X.5 Corners" or "NONE",
  "primary_market": "1" or "X" or "2" or "1X" or "X2" or "Over 2.5 Goals" or "BTTS" or "Over 9.5 Corners" or "Over 4.5 Cards" or "NONE",
  "primary_driver": "INJURY_INTEL" or "SHARP_MONEY" or "MATH_VALUE" or "CONTEXT_PLAY" or "CONTRARIAN",
  "combo_suggestion": "Home Win + Over 2.5 Goals" or "Away Win + BTTS" or "1X + Over 9.5 Corners" or null,
  "combo_reasoning": "REQUIRED - Always explain combo decision. If combo suggested: why stats support it. If null: why combo was skipped (e.g., 'Stats insufficienti per combo', 'Partita a basso punteggio', 'Dati mancanti')",
  "reasoning": "2-3 sentence explanation in ITALIAN correlating all sources. Include 'KEY RETURN', 'NATIONAL DUTY ABSENCE', or market-specific tags if detected."
}}

**CONFIDENCE BREAKDOWN RULES (V8.1):**
The confidence_breakdown shows HOW you arrived at your confidence score. The sum of all weights should approximately equal the confidence value.
- **news_weight (max 40):** High if news is the main driver (injury confirmed, lineup revealed). Low if news is generic or stale.
- **odds_weight (max 25):** High if significant odds movement detected (>10% drop). Low if odds are stable.
- **form_weight (max 20):** High if team stats/form strongly support the bet. Low if stats are unknown or neutral.
- **injuries_weight (max 15):** High if key player absences detected. Low if no significant injuries.

**PRIMARY_DRIVER CLASSIFICATION:**
Choose the MAIN reason for this betting opportunity:
- **INJURY_INTEL**: Key players confirmed missing (injuries, suspensions, national duty)
- **SHARP_MONEY**: Significant odds movement, sharp bookie divergence detected
- **MATH_VALUE**: Poisson/Stats model shows mathematical edge vs bookmaker odds
- **CONTEXT_PLAY**: Motivation (title race, relegation) or fatigue factor is the key driver
- **CONTRARIAN**: Betting against public perception, value on unpopular outcome

CRITICAL RULES:
- Be decisive. If confidence < 60, verdict should be NO BET.
- If combo stats are not HIGH CONFIDENCE, set combo_suggestion to null.
- combo_reasoning is ALWAYS REQUIRED - never leave it null or empty. Explain why combo was suggested OR why it was skipped.
- Output ONLY the JSON object, nothing else.

**🚫 OUTPUT RESTRICTIONS (MANDATORY):**
- Do NOT include phrases like "Leggi la fonte", "Read more", "Source:", "Link:" in your output.
- Do NOT include any URLs or hyperlinks in reasoning or combo_reasoning fields.
- Output ANALYSIS ONLY - the system will append the source link automatically.

**🇮🇹 CRITICAL OUTPUT INSTRUCTION:**
All your reasoning, summaries, combo explanations, and combo_reasoning MUST be written in **ITALIAN**.
Do NOT use English for the final output fields. Write naturally in Italian as if you were an Italian betting analyst.
Examples:
- "Assenza confermata da FotMob, il mercato non ha ancora reagito."
- "Stats insufficienti per combo - partita a basso punteggio prevista."
- "Ritorno chiave del portiere titolare, quota ancora alta."
"""

# DYNAMIC USER MESSAGE TEMPLATE - All variable data goes here
USER_MESSAGE_TEMPLATE = """
📅 **CURRENT DATE:** {today}

⚽ **MATCH:** {home_team} vs {away_team}

---

**DATA SOURCE 1: NEWS SNIPPET**
{news_snippet}

**DATA SOURCE 2: MARKET STATUS**
{market_status}

**DATA SOURCE 3: OFFICIAL DATA (FotMob)**
{official_data}

**DATA SOURCE 4: TEAM STATS (if available)**
{team_stats}

**DATA SOURCE 5: TACTICAL CONTEXT (Deep Dive)**
{tactical_context}

**DATA SOURCE 6: TWITTER INTEL (Insider Accounts)**
{twitter_intel}

**INVESTIGATION STATUS:** {investigation_status}

---

TASK: Analyze this match based on the System Rules. Output JSON only.
"""

BISCOTTO_PROMPT = """
🍪 BISCOTTO ANALYSIS (Mutually Beneficial Draw Detection)

I suspect a "Biscotto" (match-fixing for a convenient draw) for this match.

**MATCH:** {home_team} vs {away_team}
**DRAW ODDS:** {draw_odd} (Opening: {opening_draw}, Drop: {drop_pct:.1f}%)
**LEAGUE:** {league}

**NEWS SNIPPET:**
{news_snippet}

**WHAT IS A BISCOTTO?**
A "Biscotto" occurs when BOTH teams benefit from a Draw result (e.g., both need 1 point to qualify/avoid relegation). 
Bookmakers slash Draw odds when they suspect this.

**YOUR TASK:**
Analyze the news for signs of a Biscotto.

**OUTPUT FORMAT (strict JSON only, no markdown):**
{{
  "is_biscotto": true or false,
  "confidence": 0-100 (integer),
  "evidence": "List specific phrases from the news that suggest Biscotto",
  "recommendation": "BET X" or "AVOID" or "MONITOR",
  "reasoning": "2-3 sentence explanation in ITALIAN"
}}

Output ONLY the JSON object, nothing else.
"""


# ============================================
# DEEPSEEK API WRAPPER WITH FALLBACK
# ============================================

def extract_reasoning_from_response(content: str) -> tuple[str, str]:
    """
    Extract reasoning trace from DeepSeek response.
    
    DeepSeek often outputs reasoning inside <think> tags.
    We extract it separately to avoid JSON parsing errors.
    
    Args:
        content: Raw response content
        
    Returns:
        Tuple of (clean_content, reasoning_trace)
    """
    reasoning_trace = ""
    clean_content = content
    
    # Pattern 1: <think>...</think> tags
    think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
    if think_match:
        reasoning_trace = think_match.group(1).strip()
        clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    
    # Pattern 2: [Thinking]...[/Thinking] tags
    thinking_match = re.search(r'\[Thinking\](.*?)\[/Thinking\]', content, re.DOTALL | re.IGNORECASE)
    if thinking_match:
        reasoning_trace = thinking_match.group(1).strip()
        clean_content = re.sub(r'\[Thinking\].*?\[/Thinking\]', '', content, flags=re.DOTALL | re.IGNORECASE).strip()
    
    return clean_content, reasoning_trace


def extract_json_from_response(content: str) -> dict:
    """
    Extract JSON object from potentially chatty DeepSeek response.
    
    DeepSeek sometimes adds explanatory text around the JSON.
    This function finds and parses only the JSON part.
    
    Uses shared ai_parser.extract_json() for core parsing,
    then applies DeepSeek-specific validation.
    
    Args:
        content: Response content (may contain extra text)
        
    Returns:
        Parsed JSON dict with validated/defaulted fields
        
    Raises:
        ValueError: If no valid JSON found
    """
    # First, clean up any reasoning tags (DeepSeek-specific)
    clean_content, _ = extract_reasoning_from_response(content)
    
    # Use shared JSON extraction logic from ai_parser
    data = _extract_json_core(clean_content)
    
    # Validate and apply defaults for expected fields (analyzer-specific)
    return validate_ai_response(data)


def validate_ai_response(data: dict) -> dict:
    """
    Validate AI response structure and apply defaults for missing fields.
    
    This prevents crashes when DeepSeek returns incomplete or malformed responses.
    Tracks invalid response frequency for monitoring (thread-safe).
    
    Args:
        data: Parsed JSON dict from AI response
        
    Returns:
        Validated dict with all expected fields
    """
    global _ai_invalid_response_count, _ai_total_response_count
    
    invalid_fields_found = []
    
    # Define expected fields with their defaults and validators
    schema = {
        'final_verdict': {
            'default': 'NO BET',
            'valid_values': ['BET', 'NO BET'],
            'type': str
        },
        'confidence': {
            'default': 0,
            'type': int,
            'min': 0,
            'max': 100
        },
        'recommended_market': {
            'default': 'NONE',
            'type': str
        },
        'primary_market': {
            'default': 'NONE',
            'type': str
        },
        'primary_driver': {
            'default': 'MATH_VALUE',
            'valid_values': ['INJURY_INTEL', 'SHARP_MONEY', 'MATH_VALUE', 'CONTEXT_PLAY', 'CONTRARIAN', 'NONE'],
            'type': str
        },
        'combo_suggestion': {
            'default': None,
            'type': (str, type(None))
        },
        'combo_reasoning': {
            'default': 'Dati insufficienti per valutare combo',
            'type': str
        },
        'reasoning': {
            'default': 'Analisi non disponibile',
            'type': str
        }
    }
    
    validated = {}
    
    for field, rules in schema.items():
        value = data.get(field)
        
        # Apply default if missing or None (unless None is valid)
        if value is None:
            validated[field] = rules['default']
            continue
        
        # Type check
        expected_type = rules.get('type')
        if expected_type and not isinstance(value, expected_type):
            try:
                # Try to coerce to expected type
                if expected_type == int:
                    value = int(value)
                elif expected_type == str:
                    value = str(value)
            except (ValueError, TypeError):
                logging.warning(f"AI response field '{field}' has invalid type, using default")
                invalid_fields_found.append(field)
                validated[field] = rules['default']
                continue
        
        # Range check for numeric fields
        if 'min' in rules and value < rules['min']:
            value = rules['min']
        if 'max' in rules and value > rules['max']:
            value = rules['max']
        
        # Valid values check
        if 'valid_values' in rules and value not in rules['valid_values']:
            logging.warning(f"AI response field '{field}' has invalid value '{value}', using default")
            invalid_fields_found.append(field)
            validated[field] = rules['default']
            continue
        
        validated[field] = value
    
    # Copy any extra fields that weren't in schema
    for key, value in data.items():
        if key not in validated:
            validated[key] = value
    
    # Track and alert on frequent invalid responses (thread-safe)
    with _ai_stats_lock:
        _ai_total_response_count += 1
        if invalid_fields_found:
            _ai_invalid_response_count += 1
            
            # Alert if error rate is high (>20% of last 50 responses)
            if _ai_total_response_count >= 10:
                error_rate = _ai_invalid_response_count / _ai_total_response_count
                if error_rate > 0.2:
                    logging.error(
                        f"🚨 AI response quality degraded: {_ai_invalid_response_count}/{_ai_total_response_count} "
                        f"({error_rate*100:.1f}%) responses have invalid fields"
                    )
    
    return validated


# AI Response Quality Tracking (Thread-Safe)
_ai_invalid_response_count = 0
_ai_total_response_count = 0
_ai_stats_lock = threading.Lock()


def get_ai_response_stats() -> dict:
    """Get AI response quality statistics for monitoring (thread-safe)."""
    with _ai_stats_lock:
        total = _ai_total_response_count
        invalid = _ai_invalid_response_count
    return {
        'total_responses': total,
        'invalid_responses': invalid,
        'error_rate_percent': round((invalid / total * 100) if total > 0 else 0, 1)
    }


def reset_ai_response_stats() -> None:
    """Reset AI response statistics (call at start of each cycle, thread-safe)."""
    global _ai_invalid_response_count, _ai_total_response_count
    with _ai_stats_lock:
        _ai_invalid_response_count = 0
        _ai_total_response_count = 0
    _ai_total_response_count = 0


def call_deepseek(messages: List[Dict], include_reasoning: bool = True) -> tuple[str, str]:
    """
    Call DeepSeek V3.2 via OpenRouter with fallback to V3 Stable.
    Includes latency monitoring and specific error handling.
    
    Args:
        messages: List of message dicts (role, content)
        include_reasoning: Whether to request reasoning trace
        
    Returns:
        Tuple of (response_content, reasoning_trace)
        
    Raises:
        Exception: If both models fail
    """
    import time
    
    if not client:
        raise ValueError("OpenRouter client not initialized. Set OPENROUTER_API_KEY.")
    
    # Validate messages payload
    if not messages or not isinstance(messages, list):
        raise ValueError("Payload messaggi non valido per DeepSeek")
    
    for msg in messages:
        if not isinstance(msg, dict) or 'role' not in msg or 'content' not in msg:
            raise ValueError("Formato messaggio non valido: richiesti 'role' e 'content'")
        # Ensure content is string
        if not isinstance(msg.get('content'), str):
            msg['content'] = str(msg.get('content', ''))
    
    # Models to try in order
    models_to_try = [DEEPSEEK_V3_2, DEEPSEEK_V3_STABLE]
    
    last_error = None
    AI_SLOW_THRESHOLD = 45  # seconds
    
    for model_id in models_to_try:
        try:
            logging.info(f"🤖 Chiamata a {model_id}...")
            start_time = time.time()
            
            # Build extra_body for reasoning
            extra_body = {}
            if include_reasoning:
                extra_body["include_reasoning"] = True
            
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0.3,  # Lower for more consistent JSON
                max_tokens=1000,
                extra_body=extra_body if extra_body else None
            )
            
            # Calculate and log latency
            latency = time.time() - start_time
            if latency > AI_SLOW_THRESHOLD:
                logging.warning(f"⚠️ AI Risposta Lenta: {model_id} ha impiegato {latency:.1f}s (soglia: {AI_SLOW_THRESHOLD}s)")
            else:
                logging.info(f"⏱️ AI latenza: {latency:.1f}s")
            
            content = response.choices[0].message.content
            
            # Extract reasoning if present
            clean_content, reasoning_trace = extract_reasoning_from_response(content)
            
            logging.info(f"✅ {model_id} risposta ricevuta con successo")
            if reasoning_trace:
                logging.debug(f"🧠 Reasoning trace: {reasoning_trace[:200]}...")
            
            return clean_content, reasoning_trace
            
        except json.JSONDecodeError as e:
            logging.error(f"❌ {model_id} risposta JSON non valida: {e}")
            last_error = e
            continue
            
        except TimeoutError as e:
            logging.error(f"❌ {model_id} timeout: {e}")
            last_error = e
            continue
            
        except Exception as e:
            error_str = str(e)
            logging.warning(f"⚠️ {model_id} fallito: {error_str[:100]}")
            last_error = e
            
            # Check if it's a 404 (model not found) - try next model
            if "404" in error_str or "not found" in error_str.lower():
                logging.info(f"🔄 Modello {model_id} non disponibile, provo fallback...")
                continue
            
            # Rate limit - wait and retry
            if "429" in error_str or "rate" in error_str.lower():
                logging.warning(f"⚠️ OpenRouter rate limit. Attesa 5s...")
                time.sleep(5)
                continue
            
            # Server errors - try fallback
            if "502" in error_str or "503" in error_str or "504" in error_str:
                logging.warning(f"⚠️ OpenRouter server error, provo fallback...")
                continue
            
            # For other errors, also try fallback
            continue
    
    # All models failed
    raise Exception(f"Tutti i modelli DeepSeek falliti. Ultimo errore: {last_error}")


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_match_attr(match, attr: str, default=None):
    """
    Robust match attribute accessor - handles both SQLAlchemy Object and Dictionary.
    
    Args:
        match: Either a SQLAlchemy model instance or a dictionary
        attr: Attribute/key name to access
        default: Default value if attribute not found
        
    Returns:
        The attribute value or default
    """
    if match is None:
        return default
    # Handle SQLAlchemy Object
    if hasattr(match, attr):
        value = getattr(match, attr, default)
        return value if value is not None else default
    # Handle Dictionary
    if isinstance(match, dict):
        return match.get(attr, default)
    return default


def safe_injuries_list(fotmob_data) -> list:
    """
    Safely extract injuries list from FotMob data with type validation.
    
    Args:
        fotmob_data: FotMob response data (dict or None)
        
    Returns:
        List of injury dictionaries, empty list if invalid
    """
    if not fotmob_data or not isinstance(fotmob_data, dict):
        return []
    
    injuries_list = fotmob_data.get('injuries') or []
    if not isinstance(injuries_list, list):
        injuries_list = []
    
    # Validate each injury entry - name must be a non-empty string
    validated = []
    for p in injuries_list:
        if isinstance(p, dict):
            name = p.get('name')
            if isinstance(name, str) and name.strip():
                validated.append(p)
    
    return validated


def extract_player_names(text: str) -> List[str]:
    """
    Extract potential player names from news text.
    Uses simple heuristics: capitalized words (2-4 words) that look like names.
    Supports accented characters (José, Müller, Çalhanoğlu, etc.)
    """
    if not text:
        return []
    
    # Unicode-aware pattern for player names
    # Matches: uppercase letter followed by lowercase letters (including accented)
    # Covers: Latin, Latin Extended-A/B, Turkish, Nordic, etc.
    # Using character class with common football name characters
    upper_chars = r'A-ZÀ-ÖØ-ÞĀ-ŐŒ-ŽǍ-ǚȀ-ȳḀ-ỹÇĞİŞ'
    lower_chars = r'a-zà-öø-ÿā-őœ-žǎ-ǜȁ-ȳḁ-ỹçğışñ'
    
    pattern = rf'\b([{upper_chars}][{lower_chars}]+(?:\s+[{upper_chars}][{lower_chars}]+){{1,3}})\b'
    
    exclude_words = {
        'The', 'In', 'On', 'At', 'To', 'For', 'With', 'By', 'From',
        'Il', 'La', 'Le', 'Di', 'Da', 'Per', 'Con',
        'O', 'A', 'Os', 'As', 'Do', 'Da', 'No', 'Na',
        'Ve', 'Ile', 'Bir', 'Bu'
    }
    
    matches = re.findall(pattern, text)
    
    player_names = []
    for match in matches:
        words = match.split()
        if len(words) >= 2 and words[0] not in exclude_words:
            player_names.append(match)
    
    seen = set()
    unique_names = []
    for name in player_names:
        if name not in seen:
            seen.add(name)
            unique_names.append(name)
    
    return unique_names[:5]


def enrich_with_player_data(news_snippet: str, team_name: str) -> str:
    """
    Extract player names from news and check their status via FotMob.
    """
    provider = get_data_provider()
    player_names = extract_player_names(news_snippet)
    
    if not player_names:
        return "No player names detected in news snippet."
    
    logging.info(f"🔍 Extracted {len(player_names)} potential player names: {player_names}")
    
    results = []
    key_players_found = []
    
    for player_name in player_names:
        try:
            status = provider.check_player_status(player_name, team_name)
            
            if status['found']:
                if status['is_key']:
                    key_players_found.append(player_name)
                    results.append(f"⭐ {player_name}: KEY PLAYER - {status['stats']}")
                else:
                    results.append(f"📋 {player_name}: Regular player - {status['stats']}")
            else:
                results.append(f"❓ {player_name}: Not found in FotMob")
                
        except Exception as e:
            logging.error(f"Error checking player {player_name}: {e}")
            results.append(f"⚠️ {player_name}: Error checking status")
    
    if key_players_found:
        summary = f"🚨 ALERT: {len(key_players_found)} KEY PLAYER(S) mentioned: {', '.join(key_players_found)}\n\n"
    else:
        summary = "ℹ️ No key players identified in this news.\n\n"
    
    summary += "\n".join(results)
    return summary


# ============================================
# MAIN ANALYSIS FUNCTIONS
# ============================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def analyze_with_triangulation(
    news_snippet: str,
    market_status: str,
    official_data: str,
    snippet_data: Dict,
    team_stats: str = "No stats available",
    tactical_context: str = "No tactical data available",
    investigation_status: str = "Standard Analysis",
    twitter_intel: str = "No Twitter intel available"
) -> Optional[NewsLog]:
    """
    DeepSeek V3.2 Triangulation Analysis (INVESTIGATOR MODE)
    Correlates 6 data sources: News + Market + Official FotMob Data + Team Stats + Tactical Context + Twitter Intel
    
    Args:
        news_snippet: The news text from Serper
        market_status: e.g., "Odds dropped 12% (1.72 → 1.51)"
        official_data: e.g., "FotMob confirms: Top Scorer injured"
        snippet_data: Original snippet metadata
        team_stats: Stats summary for Goals/Cards/Corners analysis
        tactical_context: Tactical insights (Fortress, Travel Sick, Leaky Defense)
        investigation_status: "Full Data Gathered" or "Standard Analysis"
        twitter_intel: Formatted Twitter insider intel from TweetRelevanceFilter
        
    Returns:
        NewsLog with verdict, confidence, reasoning, and recommended_market
    """
    # Validate snippet_data to prevent AttributeError on None
    if not snippet_data:
        snippet_data = {}
    
    # Priority: Mock Data
    if os.getenv("USE_MOCK_DATA") == "true":
        from src.mocks import MOCK_LLM_RESPONSES
        team = snippet_data.get('team')
        mock_resp = MOCK_LLM_RESPONSES.get(team)
        if mock_resp:
            return NewsLog(
                match_id=snippet_data.get('match_id'),
                url=snippet_data.get('link'),
                summary=mock_resp['summary'],
                score=mock_resp['relevance_score'],
                category=mock_resp['category'],
                affected_team=mock_resp['affected_team']
            )
        return None

    if not OPENROUTER_API_KEY:
        logging.warning("OPENROUTER_API_KEY not configured. Using fallback.")
        return basic_keyword_analysis(news_snippet, snippet_data.get('team'), snippet_data)

    try:
        # STEP 0: Truncate news_snippet to prevent token overflow
        # Individual snippets are 350 chars each, but aggregated can blow budget
        from config.settings import NEWS_SNIPPET_MAX_CHARS
        if news_snippet and len(news_snippet) > NEWS_SNIPPET_MAX_CHARS:
            news_snippet = news_snippet[:NEWS_SNIPPET_MAX_CHARS] + "... [TRUNCATED]"
            logging.debug(f"📝 News snippet truncated to {NEWS_SNIPPET_MAX_CHARS} chars")
        
        
        # STEP 1: Enrich official_data with FotMob player status
        team_name = snippet_data.get('team', 'Unknown Team')
        
        if not official_data or official_data == "No official data available":
            logging.info(f"🔄 Enriching news with FotMob player data for team: {team_name}")
            official_data = enrich_with_player_data(news_snippet, team_name)
        
        # STEP 1c: H2H BTTS Trend Analysis (V4.1)
        # Fetch H2H data directly from FotMob and calculate BTTS trend
        h2h_context = ""
        try:
            # First check if h2h_history was passed in snippet_data
            h2h_history = snippet_data.get('h2h_history', [])
            
            # If not passed, fetch it directly from FotMob
            if not h2h_history:
                home_team_h2h = snippet_data.get('home_team')
                away_team_h2h = snippet_data.get('away_team')
                
                if home_team_h2h and away_team_h2h:
                    try:
                        from src.ingestion.data_provider import get_data_provider
                        provider = get_data_provider()
                        
                        # Fetch match details which includes H2H
                        match_details = provider.get_match_details(
                            home_team_h2h,
                            home_team=home_team_h2h,
                            away_team=away_team_h2h
                        )
                        
                        if match_details and not match_details.get('error'):
                            h2h_history = match_details.get('h2h_history', [])
                    except Exception as e:
                        logging.debug(f"H2H fetch failed (non-critical): {e}")
            
            # Calculate BTTS trend if we have H2H data
            if h2h_history and isinstance(h2h_history, list) and len(h2h_history) > 0:
                from src.analysis.math_engine import calculate_btts_trend
                
                btts_trend = calculate_btts_trend(h2h_history)
                
                if btts_trend.get('total_games', 0) > 0:
                    h2h_context = (
                        f"\n\n[H2H BTTS INTELLIGENCE]\n"
                        f"📊 In the last {btts_trend['total_games']} head-to-head matches, "
                        f"Both Teams Scored in {btts_trend['btts_rate']}% of games "
                        f"({btts_trend['btts_hits']}/{btts_trend['total_games']}).\n"
                        f"🎯 BTTS Trend: {btts_trend['trend_signal']}"
                    )
                    logging.info(f"⚽ H2H BTTS injected: {btts_trend['btts_rate']}% ({btts_trend['trend_signal']})")
        except Exception as e:
            logging.debug(f"H2H BTTS calculation failed (non-critical): {e}")
        
        # STEP 1d: Intelligence Router Deep Dive (High Potential Matches Only)
        # Triggers when preliminary signals suggest high value opportunity
        # V6.0: Uses IntelligenceRouter (DeepSeek primary, Perplexity fallback)
        gemini_intel = ""
        deep_dive = None  # Initialize to avoid UnboundLocalError
        if INTELLIGENCE_ROUTER_AVAILABLE:
            try:
                # Check for high potential signals before calling Gemini
                high_potential_signals = (
                    'TURNOVER' in official_data.upper() or
                    'KEY PLAYER' in official_data.upper() or
                    'CRASH' in market_status.upper() or
                    'DROPPING' in market_status.upper()
                )
                
                if high_potential_signals:
                    home_team = snippet_data.get('home_team', team_name)
                    away_team = snippet_data.get('away_team', 'Unknown')
                    
                    # Extract match date and referee for enhanced query
                    match_date = None
                    referee_name = None
                    
                    # Try to get match_date from snippet_data
                    if snippet_data.get('match_date'):
                        try:
                            from datetime import datetime
                            md = snippet_data['match_date']
                            if isinstance(md, datetime):
                                match_date = md.strftime('%Y-%m-%d')
                            elif isinstance(md, str):
                                match_date = md[:10]  # YYYY-MM-DD
                        except Exception as e:
                            logging.debug(f"Match date extraction failed: {e}")
                    
                    # Try to get referee from official_data (FotMob)
                    if 'REFEREE:' in official_data.upper():
                        try:
                            # Extract referee name from official_data
                            import re
                            ref_match = re.search(r'REFEREE:\s*([^(\n]+)', official_data, re.IGNORECASE)
                            if ref_match:
                                referee_name = ref_match.group(1).strip()
                        except Exception as e:
                            logging.debug(f"Referee extraction failed: {e}")
                    
                    logging.info(f"🤖 High potential detected - triggering Intelligence Router deep dive")
                    
                    # V5.0: Use IntelligenceRouter for automatic Gemini/Perplexity fallback
                    router = get_intelligence_router() if INTELLIGENCE_ROUTER_AVAILABLE else None
                    
                    # Extract missing players from official_data for deep dive analysis
                    missing_players = []
                    try:
                        # Pattern 1: "X missing (Name1, Name2, Name3)"
                        import re
                        missing_match = re.search(r'(\d+)\s+missing\s*\(([^)]+)\)', official_data, re.IGNORECASE)
                        if missing_match:
                            names_str = missing_match.group(2)
                            missing_players = [n.strip() for n in names_str.split(',') if n.strip()]
                        
                        # Pattern 2: "starters missing (Name1, Name2)"
                        if not missing_players:
                            starters_match = re.search(r'starters?\s+(?:missing|out)\s*\(([^)]+)\)', official_data, re.IGNORECASE)
                            if starters_match:
                                names_str = starters_match.group(1)
                                missing_players = [n.strip() for n in names_str.split(',') if n.strip()]
                        
                        # Pattern 3: "TURNOVER ALERT: ... missing (Name1, Name2)"
                        if not missing_players:
                            turnover_match = re.search(r'TURNOVER.*?missing\s*\(([^)]+)\)', official_data, re.IGNORECASE)
                            if turnover_match:
                                names_str = turnover_match.group(1)
                                missing_players = [n.strip() for n in names_str.split(',') if n.strip()]
                        
                        if missing_players:
                            logging.info(f"   📋 Extracted {len(missing_players)} missing players for deep dive: {missing_players[:5]}")
                    except Exception as e:
                        logging.debug(f"Could not extract missing players: {e}")
                    
                    # V5.0: Use IntelligenceRouter for automatic fallback
                    deep_dive = None
                    intel_source = None
                    
                    if router and router.is_available():
                        deep_dive = router.get_match_deep_dive(
                            home_team,
                            away_team,
                            match_date=match_date,
                            referee=referee_name,
                            missing_players=missing_players
                        )
                        if deep_dive:
                            gemini_intel = router.format_for_prompt(deep_dive)
                            intel_source = router.get_active_provider_name().capitalize()
                            logging.info(f"✅ {intel_source} Intel acquired")
                    
                    # Fallback to Perplexity if router unavailable
                    if not deep_dive and not router:
                        if PERPLEXITY_AVAILABLE:
                            try:
                                perplexity_provider = get_perplexity_provider()
                                if perplexity_provider.is_available():
                                    logging.info("🔮 Trying Perplexity fallback...")
                                    deep_dive = perplexity_provider.get_match_deep_dive(
                                        home_team,
                                        away_team,
                                        match_date=match_date,
                                        referee=referee_name,
                                        missing_players=missing_players
                                    )
                                    if deep_dive:
                                        gemini_intel = perplexity_provider.format_for_prompt(deep_dive)
                                        intel_source = "Perplexity"
                                        logging.info(f"✅ Perplexity Intel acquired (fallback)")
                            except Exception as e:
                                logging.debug(f"Perplexity fallback failed: {e}")
                    
                    if not deep_dive:
                        logging.debug("No deep dive intel available")
            except Exception as e:
                logging.warning(f"⚠️ Deep dive failed: {e}")
        else:
            # V6.1: Log when Intelligence Router is unavailable (was silent before)
            logging.debug("🔇 Intelligence Router not available - deep_dive skipped")
        
        # Append Gemini intelligence to tactical context if available
        if gemini_intel:
            tactical_context = f"{tactical_context}\n\n{gemini_intel}"
        
        # ============================================
        # MOTIVATION ENGINE - League Table Context
        # ============================================
        # Fetch league table for motivation analysis (primary source)
        league_table_context = None
        try:
            league_id = snippet_data.get('league_id') or snippet_data.get('fotmob_league_id')
            home_team_id = snippet_data.get('home_team_id') or snippet_data.get('home_fotmob_id')
            away_team_id = snippet_data.get('away_team_id') or snippet_data.get('away_fotmob_id')
            home_team_for_table = snippet_data.get('home_team', team_name)
            away_team_for_table = snippet_data.get('away_team', 'Unknown')
            
            if league_id:
                from src.ingestion.data_provider import get_data_provider
                provider = get_data_provider()
                league_table_context = provider.get_league_table_context(
                    league_id=league_id,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    home_team_name=home_team_for_table,
                    away_team_name=away_team_for_table
                )
                
                if league_table_context and not league_table_context.get('error'):
                    logging.info(f"📊 League Table: {league_table_context.get('motivation_summary', 'N/A')}")
        except Exception as e:
            logging.warning(f"⚠️ League table fetch failed: {e}")
        
        # Extract motivation data for score bonus (safe defaults)
        motivation_home = ""
        motivation_away = ""
        table_context = ""
        
        # Priority 1: Use league table data (most reliable)
        if league_table_context and not league_table_context.get('error'):
            h_rank = league_table_context.get('home_rank')
            h_zone = league_table_context.get('home_zone', 'Unknown')
            h_form = league_table_context.get('home_form')
            a_rank = league_table_context.get('away_rank')
            a_zone = league_table_context.get('away_zone', 'Unknown')
            a_form = league_table_context.get('away_form')
            
            if h_rank:
                form_str = f", Form: {h_form}" if h_form else ""
                motivation_home = f"#{h_rank} ({h_zone}){form_str}"
            if a_rank:
                form_str = f", Form: {a_form}" if a_form else ""
                motivation_away = f"#{a_rank} ({a_zone}){form_str}"
            
            if league_table_context.get('motivation_mismatch'):
                table_context = "⚠️ MOTIVATION MISMATCH: One team is desperate, the other is safe"
        
        # Priority 2: Fallback to Gemini/Perplexity deep_dive data
        if deep_dive:
            if not motivation_home or motivation_home == "Unknown":
                motivation_home = (deep_dive.get('motivation_home') or "Unknown").strip()
            if not motivation_away or motivation_away == "Unknown":
                motivation_away = (deep_dive.get('motivation_away') or "Unknown").strip()
            if not table_context:
                table_context = (deep_dive.get('table_context') or "").strip()
        
        # Add motivation to tactical context if not Unknown
        home_team = snippet_data.get('home_team') or team_name
        away_team = snippet_data.get('away_team') or 'Unknown'
        
        if motivation_home and motivation_home.lower() != "unknown":
            tactical_context = f"{tactical_context}\n\n[LEAGUE TABLE CONTEXT]\n🏠 Home ({home_team}): {motivation_home}"
        if motivation_away and motivation_away.lower() != "unknown":
            tactical_context = f"{tactical_context}\n🚌 Away ({away_team}): {motivation_away}"
        if table_context and table_context.lower() != "unknown":
            tactical_context = f"{tactical_context}\n📊 Analysis: {table_context}"
        
        # STEP 2: Build messages with STATIC system prompt + DYNAMIC user message
        # This structure maximizes DeepSeek context caching (system prompt is constant)
        
        # ISO 8601 date format to avoid USA/EU ambiguity
        from datetime import datetime, timezone
        today_iso = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        # Append H2H context to team_stats if available (V4.1)
        enriched_team_stats = team_stats
        if h2h_context:
            enriched_team_stats = f"{team_stats}{h2h_context}"
        
        # Build dynamic user message with all variable data
        user_content = USER_MESSAGE_TEMPLATE.format(
            today=today_iso,
            home_team=home_team,
            away_team=away_team,
            news_snippet=news_snippet,
            market_status=market_status,
            official_data=official_data,
            team_stats=enriched_team_stats,
            tactical_context=tactical_context,
            twitter_intel=twitter_intel if twitter_intel else "No Twitter intel available",
            investigation_status=investigation_status
        )
        
        # Context caching optimized structure:
        # - System message: STATIC (TRIANGULATION_SYSTEM_PROMPT) = CACHED by DeepSeek
        # - User message: DYNAMIC (user_content) = Variable per request
        messages = [
            {"role": "system", "content": TRIANGULATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]
        
        # STEP 3: Call DeepSeek
        response_content, reasoning_trace = call_deepseek(messages)
        
        # STEP 4: Parse JSON response
        data = extract_json_from_response(response_content)
        
        # Extract verdict and confidence
        verdict = data.get('final_verdict', 'NO BET')
        confidence = data.get('confidence', 0)
        reasoning = data.get('reasoning', 'No reasoning provided')
        recommended_market = data.get('recommended_market', 'NONE')
        primary_market = data.get('primary_market', 'NONE')
        combo_suggestion = data.get('combo_suggestion')
        combo_reasoning = data.get('combo_reasoning')
        
        # V8.1: Extract confidence breakdown (transparency feature)
        confidence_breakdown = data.get('confidence_breakdown', {})
        primary_driver = data.get('primary_driver', 'UNKNOWN')
        
        # Build market display
        market_display = ""
        if primary_market and primary_market != 'NONE':
            market_display = f"📊 MERCATO: {primary_market}"
        elif recommended_market and recommended_market != 'NONE':
            market_display = f"📊 MERCATO: {recommended_market}"
        
        # Ensure combo_reasoning has a default value
        if not combo_reasoning:
            combo_reasoning = "Dati insufficienti per valutare combo"
        
        # Add combo section - ALWAYS show combo reasoning for visibility
        if combo_suggestion:
            market_display += f"\n🧩 SMART COMBO: {combo_suggestion}"
            market_display += f"\n   └─ {combo_reasoning}"
        else:
            # Show why combo was skipped (discrete footer)
            market_display += f"\nℹ️ Combo: {combo_reasoning}"
        
        if market_display:
            reasoning = f"{market_display}\n{reasoning}"
        
        # Add motivation context to reasoning (only if not Unknown)
        motivation_display = ""
        if motivation_home and motivation_home.lower() != "unknown":
            motivation_display = f"🔥 Motivazione Casa: {motivation_home}"
        if motivation_away and motivation_away.lower() != "unknown":
            if motivation_display:
                motivation_display += f"\n🔥 Motivazione Trasferta: {motivation_away}"
            else:
                motivation_display = f"🔥 Motivazione Trasferta: {motivation_away}"
        
        if motivation_display:
            reasoning = f"{motivation_display}\n{reasoning}"
        
        # Add reasoning trace if available
        if reasoning_trace:
            reasoning = f"{reasoning}\n\n🧠 Reasoning: {reasoning_trace[:300]}..."
        
        # Convert to score
        if verdict == "BET" and confidence >= 70:
            score = 9
            category = "HIGH_CONFIDENCE_BET"
        elif verdict == "BET" and confidence >= 60:
            score = 7
            category = "MEDIUM_CONFIDENCE_BET"
        else:
            score = 4
            category = "NO_BET"
        
        # MOTIVATION BONUS (V4.2) - Safe application with cap
        # High motivation (relegation/title) = +0.5, Dead rubber = -1.0
        motivation_bonus = 0.0
        mot_home_lower = (motivation_home or "").lower()
        mot_away_lower = (motivation_away or "").lower()
        
        # Positive signals (both teams fighting = more intensity)
        if any(kw in mot_home_lower for kw in ["relegation", "title", "championship", "golden boot"]):
            motivation_bonus += 0.3
        if any(kw in mot_away_lower for kw in ["relegation", "title", "championship", "golden boot"]):
            motivation_bonus += 0.2
        
        # Negative signals (dead rubber = less intensity, unpredictable)
        if any(kw in mot_home_lower for kw in ["dead rubber", "nothing to play", "mid-table safe", "friendly"]):
            motivation_bonus -= 0.5
        if any(kw in mot_away_lower for kw in ["dead rubber", "nothing to play", "mid-table safe", "friendly"]):
            motivation_bonus -= 0.5
        
        # Apply bonus and cap at 10.0 (never exceed max score)
        if motivation_bonus != 0.0:
            original_score = score
            score = max(0, min(10.0, score + motivation_bonus))
            if motivation_bonus > 0:
                logging.info(f"🔥 Motivation bonus: +{motivation_bonus:.1f} (score {original_score} → {score})")
            else:
                logging.info(f"💤 Motivation penalty: {motivation_bonus:.1f} (score {original_score} → {score})")
        
        # INJURY IMPACT ADJUSTMENT (V5.3.1) - Context-aware balanced assessment
        # Evaluates importance of missing players (starter vs backup) for both teams
        # and adjusts score based on differential impact AND recommended market
        # 
        # LOGIC: If betting on Home (1, 1X) and Home is more injured → DECREASE score
        #        If betting on Away (2, X2) and Away is more injured → DECREASE score
        #        If injuries favor the bet direction → INCREASE score
        injury_impact_adjustment = 0.0
        injury_differential = None
        
        if INJURY_IMPACT_AVAILABLE:
            try:
                # Extract context data from snippet_data (passed from main.py)
                home_context = snippet_data.get('home_context')
                away_context = snippet_data.get('away_context')
                
                # Only calculate if we have injury data for at least one team
                has_home_injuries = (
                    home_context and 
                    isinstance(home_context, dict) and 
                    home_context.get('injuries')
                )
                has_away_injuries = (
                    away_context and 
                    isinstance(away_context, dict) and 
                    away_context.get('injuries')
                )
                
                if has_home_injuries or has_away_injuries:
                    injury_differential = analyze_match_injuries(
                        home_team=home_team,
                        away_team=away_team,
                        home_context=home_context,
                        away_context=away_context
                    )
                    
                    if injury_differential and abs(injury_differential.score_adjustment) >= 0.3:
                        raw_adjustment = injury_differential.score_adjustment
                        
                        # V5.3.1: Context-aware adjustment based on recommended market
                        # raw_adjustment > 0 means Home is more affected (favors Away)
                        # raw_adjustment < 0 means Away is more affected (favors Home)
                        market_lower = (primary_market or recommended_market or '').lower().strip()
                        
                        # Determine bet direction from market
                        is_home_bet = market_lower in ('1', '1x') or 'home' in market_lower
                        is_away_bet = market_lower in ('2', 'x2') or 'away' in market_lower
                        is_draw_bet = market_lower == 'x' or market_lower == 'draw'
                        
                        # Apply adjustment based on alignment with bet direction
                        if is_home_bet:
                            # Betting on Home: if Home more injured (raw > 0), DECREASE score
                            # if Away more injured (raw < 0), INCREASE score
                            injury_impact_adjustment = -raw_adjustment
                        elif is_away_bet:
                            # Betting on Away: if Home more injured (raw > 0), INCREASE score
                            # if Away more injured (raw < 0), DECREASE score
                            injury_impact_adjustment = raw_adjustment
                        elif is_draw_bet:
                            # Draw bet: injuries to either team slightly favor draw
                            # Use absolute value but capped lower
                            injury_impact_adjustment = abs(raw_adjustment) * 0.3
                        else:
                            # Non-result markets (BTTS, Over/Under, Corners, Cards)
                            # Injuries generally increase unpredictability, slight negative
                            injury_impact_adjustment = -abs(raw_adjustment) * 0.2
                        
                        original_score = score
                        score = max(0, min(10.0, score + injury_impact_adjustment))
                        
                        # Add injury impact to reasoning
                        injury_summary = injury_differential.summary
                        if injury_summary:
                            reasoning = f"⚖️ INJURY BALANCE:\n{injury_summary}\n{reasoning}"
                        
                        # Log with context
                        direction = "aligned with bet" if injury_impact_adjustment > 0 else "against bet"
                        logging.info(
                            f"🏥 Injury Impact: {injury_impact_adjustment:+.2f} ({direction}) | "
                            f"Market: {market_lower} | Score: {original_score} → {score}"
                        )
            except Exception as e:
                logging.warning(f"⚠️ Injury impact calculation failed: {e}")
        
        # Extract primary_driver (Alpha Source)
        primary_driver = data.get('primary_driver', 'UNKNOWN')
        valid_drivers = ['INJURY_INTEL', 'SHARP_MONEY', 'MATH_VALUE', 'CONTEXT_PLAY', 'CONTRARIAN']
        # Handle "NONE" string from AI response
        if primary_driver is None or primary_driver == 'NONE' or primary_driver not in valid_drivers:
            primary_driver = 'MATH_VALUE'  # Default to MATH_VALUE instead of UNKNOWN
        
        # Log with combo info and driver
        combo_log = f" | Combo: {combo_suggestion}" if combo_suggestion else ""
        logging.info(f"🎯 DeepSeek Verdict: {verdict} | Confidence: {confidence}% | Market: {primary_market or recommended_market} | Driver: {primary_driver}{combo_log} | Score: {score}")
        
        # V4.2: Determine odds_taken based on recommended market
        # V4.4 FIX: Extended to cover all market formats (1, 2, X, 1X, X2, BTTS, Over/Under, Corners, Cards)
        odds_taken = None
        market_lower = (primary_market or recommended_market or '').lower().strip()
        
        # Home Win variants: "home win", "1", "home"
        if market_lower in ('1', 'home') or ('home' in market_lower and 'win' in market_lower):
            odds_taken = snippet_data.get('current_home_odd')
        # Away Win variants: "away win", "2", "away"
        elif market_lower in ('2', 'away') or ('away' in market_lower and 'win' in market_lower):
            odds_taken = snippet_data.get('current_away_odd')
        # Draw variants: "draw", "x"
        elif market_lower in ('x', 'draw'):
            odds_taken = snippet_data.get('current_draw_odd')
        # Double Chance 1X: use home odd as proxy (conservative)
        elif market_lower == '1x' or ('home' in market_lower and 'draw' in market_lower):
            odds_taken = snippet_data.get('current_home_odd')
        # Double Chance X2: use away odd as proxy (conservative)
        elif market_lower == 'x2' or ('away' in market_lower and 'draw' in market_lower):
            odds_taken = snippet_data.get('current_away_odd')
        # Over/Under Goals, BTTS: use 1.90 as default
        elif 'over' in market_lower or 'under' in market_lower or 'btts' in market_lower:
            # Check if it's corners or cards (different default odds)
            if 'corner' in market_lower:
                odds_taken = 1.85  # Typical corners market odds
            elif 'card' in market_lower:
                odds_taken = 1.80  # Typical cards market odds
            else:
                odds_taken = 1.90  # Default for goals totals
        # Corners market (standalone): "Over 9.5 Corners", "corners"
        elif 'corner' in market_lower:
            odds_taken = 1.85
        # Cards market (standalone): "Over 4.5 Cards", "cards"
        elif 'card' in market_lower:
            odds_taken = 1.80
        
        # V8.1: Serialize confidence_breakdown to JSON string
        import json
        confidence_breakdown_str = None
        if confidence_breakdown:
            try:
                confidence_breakdown_str = json.dumps(confidence_breakdown)
            except (TypeError, ValueError):
                confidence_breakdown_str = None
        
        return NewsLog(
            match_id=snippet_data.get('match_id'),
            url=snippet_data.get('link'),
            summary=reasoning,
            score=score,
            category=category,
            affected_team=snippet_data.get('team'),
            combo_suggestion=combo_suggestion,
            combo_reasoning=combo_reasoning,
            recommended_market=primary_market or recommended_market,
            primary_driver=primary_driver,
            odds_taken=odds_taken,  # V4.2: CLV Tracking
            confidence_breakdown=confidence_breakdown_str  # V8.1: Transparency
        )

    except Exception as e:
        # Sanitize API key from error message before logging
        error_msg = str(e)
        if OPENROUTER_API_KEY:
            error_msg = error_msg.replace(OPENROUTER_API_KEY, "[REDACTED]")
        logging.error(f"DeepSeek Triangulation failed: {error_msg}")
        logging.info("Falling back to Basic Keyword Analysis...")
        return basic_keyword_analysis(news_snippet, snippet_data.get('team'), snippet_data)


# Legacy function for backward compatibility
def analyze_relevance(snippet_data: Dict) -> Optional[NewsLog]:
    """
    Legacy function - now calls triangulation with empty official data
    """
    return analyze_with_triangulation(
        news_snippet=snippet_data.get('snippet', ''),
        market_status="No market data available",
        official_data="No official data available",
        snippet_data=snippet_data
    )


def basic_keyword_analysis(text: str, team: str, snippet_data: Dict) -> Optional[NewsLog]:
    """
    Fallback mechanism if LLM is down.
    Scores 6 if High Risk Keywords are found.
    Also detects Comeback and National Duty factors.
    """
    text_lower = text.lower()
    
    # Negative impact keywords (absences)
    critical_keywords = [
        'lesão', 'fratura', 'fora', 'desfalque', 'sub-20', 'reservas',
        'sakat', 'kadro dışı', 'yedek', 'u19', 'oynamayacak',
        'kontuzja', 'uraz', 'rezerwowy',
        'injury', 'out', 'squad', 'ruled out', 'doubtful', 'missing'
    ]
    
    # National Duty keywords (HIGH IMPACT absence)
    national_duty_keywords = [
        'national team', 'selección', 'convocados', 'afcon', 'asian cup',
        'milli takim', 'arab cup', 'world cup qualifiers', 'international duty',
        'copa america', 'euro qualifiers'
    ]
    
    # Comeback keywords (POSITIVE impact)
    comeback_keywords = [
        'returns', 'back in squad', 'rientra', 'torna disponibile', 'recovered',
        'habilitado', 'fit again', 'cleared to play', 'back from injury',
        'available again', 'regresa', 'vuelve'
    ]
    
    found_critical = [kw for kw in critical_keywords if kw in text_lower]
    found_national = [kw for kw in national_duty_keywords if kw in text_lower]
    found_comeback = [kw for kw in comeback_keywords if kw in text_lower]
    
    # Determine score and category
    if found_national:
        summary = f"🌍 NATIONAL DUTY ABSENCE (AI Unavailable): {', '.join(found_national)}"
        score = 7  # High impact
        category = "NATIONAL_DUTY_ABSENCE"
    elif found_comeback:
        summary = f"🔄 KEY RETURN DETECTED (AI Unavailable): {', '.join(found_comeback)}"
        score = 6
        category = "KEY_RETURN"
    elif found_critical:
        summary = f"⚠️ KEYWORD ALERT (AI Unavailable): Found suspicious terms: {', '.join(found_critical)}"
        score = 6
        category = "KEYWORD_MATCH"
    else:
        summary = "No critical keywords found (Fallback mode)."
        score = 0
        category = "LOW_RELEVANCE"

    return NewsLog(
        match_id=snippet_data.get('match_id'),
        url=snippet_data.get('link'),
        summary=summary,
        score=score,
        category=category,
        affected_team=team
    )


def batch_analyze(snippets: List[Dict]) -> List[NewsLog]:
    """
    Process a list of snippets.
    """
    results = []
    seen_urls = set()
    
    for s in snippets:
        if s.get('link') in seen_urls:
            continue
        seen_urls.add(s.get('link'))
        
        analysis = analyze_relevance(s)
        if analysis:
            results.append(analysis)
            
    return results


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def analyze_biscotto(
    news_snippet: str,
    home_team: str,
    away_team: str,
    draw_odd: float,
    opening_draw: float,
    league: str
) -> Optional[Dict]:
    """
    🍪 BISCOTTO ANALYSIS: Use DeepSeek to validate if news confirms a "convenient draw".
    """
    if not OPENROUTER_API_KEY:
        logging.warning("OPENROUTER_API_KEY not available for Biscotto analysis")
        return None
    
    # Safe calculation: validate both values before division
    drop_pct = 0
    if opening_draw and opening_draw > 0 and draw_odd is not None:
        drop_pct = ((opening_draw - draw_odd) / opening_draw) * 100
    
    try:
        prompt = BISCOTTO_PROMPT.format(
            home_team=home_team,
            away_team=away_team,
            draw_odd=draw_odd if draw_odd is not None else 0,
            opening_draw=opening_draw or draw_odd or 0,
            drop_pct=drop_pct,
            league=league,
            news_snippet=news_snippet
        )
        
        messages = [
            {"role": "system", "content": "You are a betting analyst specializing in match-fixing detection. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        response_content, reasoning_trace = call_deepseek(messages)
        data = extract_json_from_response(response_content)
        
        logging.info(f"🍪 Biscotto Analysis: is_biscotto={data.get('is_biscotto')} | confidence={data.get('confidence')}%")
        
        if reasoning_trace:
            data['reasoning_trace'] = reasoning_trace
        
        return data
        
    except Exception as e:
        logging.error(f"Biscotto analysis failed: {e}")
        return None


def check_biscotto_keywords(text: str, lang: str = 'en') -> List[str]:
    """
    Check text for Biscotto-related keywords.
    """
    from config.settings import BISCOTTO_KEYWORDS
    
    text_lower = text.lower()
    found = []
    
    keywords = BISCOTTO_KEYWORDS.get(lang, [])
    for kw in keywords:
        if kw.lower() in text_lower:
            found.append(kw)
    
    if lang != 'en':
        for kw in BISCOTTO_KEYWORDS.get('en', []):
            if kw.lower() in text_lower:
                found.append(kw)
    
    return list(set(found))


# ============================================
# CLI for testing
# ============================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("=" * 60)
    print("🤖 DEEPSEEK V3.2 ANALYZER TEST")
    print("=" * 60)
    
    print(f"\n📋 Configuration:")
    print(f"   OpenRouter API Key: {'✅ Set' if OPENROUTER_API_KEY else '❌ Not set'}")
    print(f"   Primary Model: {DEEPSEEK_V3_2}")
    print(f"   Fallback Model: {DEEPSEEK_V3_STABLE}")
    
    if OPENROUTER_API_KEY:
        print("\n🧪 Testing DeepSeek call...")
        try:
            test_messages = [
                {"role": "user", "content": "Say 'Hello EarlyBird!' in JSON format: {\"message\": \"...\"}"}
            ]
            response, reasoning = call_deepseek(test_messages, include_reasoning=False)
            print(f"   Response: {response[:100]}")
            print("   ✅ DeepSeek connection successful!")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    else:
        print("\n⚠️ Set OPENROUTER_API_KEY to test DeepSeek connection")
    
    print("\n✅ Test complete")
