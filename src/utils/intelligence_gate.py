"""
Multi-Level Intelligence Gate - V9.5

A 3-level Gating System for NitterMonitor and NewsHunter to handle global intelligence
at 5% of current cost while filtering non-English/Italian content efficiently.

GATE LEVELS:
- Level 1: Zero-Cost Keyword Check (local, no API calls)
- Level 2: Economic AI Translation (DeepSeek V3 via OpenRouter) - for translation/classification
- Level 3: Deep R1 Reasoning (DeepSeek R1 via OpenRouter) - for Triangulation/Verification/Verdict

MODEL HIERARCHY:
- Model A (Standard): deepseek/deepseek-chat - Translation, metadata extraction, low-priority tasks
- Model B (Reasoner): deepseek/deepseek-r1-0528:free - Triangulation, Verification, BET/NO BET verdict

EXPECTED COST SAVINGS: 95% reduction in token costs by filtering at local level.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION - V9.5 MODEL HIERARCHY
# ============================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Model A (Standard): For translation, metadata extraction, low-priority tasks
DEEPSEEK_V3_MODEL = "deepseek/deepseek-chat"  # DeepSeek V3 Stable via OpenRouter
MODEL_A_STANDARD = DEEPSEEK_V3_MODEL

# Model B (Reasoner): For Triangulation, VerificationLayer, final BET/NO BET verdict
MODEL_B_REASONER = "deepseek/deepseek-r1-0528:free"  # DeepSeek R1 Deep Reasoner via OpenRouter

# ============================================
# KEYWORD DICTIONARIES (Level 1 - Zero Cost)
# ============================================

# Keywords for injury-related content in various languages
INJURY_KEYWORDS = {
    "english": [
        "injury", "injured", "hamstring", "muscle", "knock", "blow",
        "ruled out", "sidelined", "absent", "unavailable", "doubt",
        "fitness", "medical", "scan", "test", "assessment", "problem",
        "issue", "concern", "setback", "strain", "tear", "groin",
    ],
    "spanish": [
        "lesión",        # injury
        "huelga",        # strike
        "lesionado",     # injured
        "dolor",         # pain
        "problema físico",  # physical problem
        "baja",          # absence/miss
        "reserva",       # reserve/bench
        "descartado",    # ruled out
        "duda",          # doubtful
        "convocatoria",  # call-up/squad announcement
    ],
    "arabic": [
        "إصابة",         # injury
        "أزمة",          # crisis
        "إصابة طبية",    # medical injury
        "مشكلة صحية",    # health problem
        "غياب",          # absence
        "مصاب",          # injured
        "الاحتياط",      # reserve/bench
        "تشكيلة",        # lineup/formation
    ],
    "french": [
        "blessure",      # injury
        "grève",         # strike
        "douleur",       # pain
        "problème physique",  # physical problem
        "absence",       # absence
        "blessé",        # injured
        "forfait",       # ruled out
        "réserve",       # reserve/bench
        "composition",   # lineup/formation
    ],
    "german": [
        "verletzung",    # injury
        "streik",        # strike
        "schmerz",       # pain
        "körperliches problem",  # physical problem
        "abwesenheit",   # absence
        "verletzt",      # injured
        "reservist",     # reserve/bench
        "aufstellung",   # lineup/formation
    ],
    "portuguese": [
        "lesão",         # injury
        "greve",         # strike
        "dor",           # pain
        "problema físico",  # physical problem
        "ausência",      # absence
        "lesionado",     # injured
        "reserva",       # reserve/bench
        "escalação",     # lineup/formation
    ],
    "polish": [
        "kontuzja",      # injury
        "strajk",        # strike
        "ból",           # pain
        "problem fizyczny",  # physical problem
        "nieobecność",   # absence
        "kontuzjowany",  # injured
        "rezerwowy",     # reserve/bench
        "skład",         # lineup/formation
    ],
    "turkish": [
        "sakatlık",      # injury
        "grev",          # strike
        "ağrı",          # pain
        "fiziksel sorun",  # physical problem
        "yokluk",        # absence
        "sakat",         # injured
        "yedek",         # reserve/bench
        "kadro",         # lineup/formation
    ],
    "russian": [
        "травма",        # injury
        "забастовка",    # strike
        "боль",          # pain
        "физическая проблема",  # physical problem
        "отсутствие",    # absence
        "травмирован",   # injured
        "запасной",      # reserve/bench
        "состав",        # lineup/formation
    ],
    "dutch": [
        "blessure",      # injury
        "staking",       # strike
        "pijn",          # pain
        "fysiek probleem",  # physical problem
        "afwezigheid",   # absence
        "geblesseerd",   # injured
        "reservespeler", # reserve/bench
        "opstelling",    # lineup/formation
    ],
}

# Keywords for team-related content
TEAM_KEYWORDS = {
    "spanish": [
        "equipo",        # team
        "jugador",       # player
        "entrenador",    # coach
        "club",          # club
        "alineación",    # lineup
        "once titular",  # starting eleven
        "banquillo",     # bench
        "convocatoria",  # call-up/squad
    ],
    "arabic": [
        "فريق",          # team
        "لاعب",          # player
        "مدرب",          # coach
        "نادي",          # club
        "تشكيلة",        # lineup
        "الفريق الأساسي", # starting team
        "الاحتياط",      # reserve/bench
        "القائمة",       # squad list
    ],
    "french": [
        "équipe",        # team
        "joueur",        # player
        "entraîneur",    # coach
        "club",          # club
        "composition",   # lineup
        "titulaire",     # starter
        "remplaçant",    # substitute
        "effectif",      # squad
    ],
    "german": [
        "mannschaft",    # team
        "spieler",       # player
        "trainer",       # coach
        "verein",        # club
        "aufstellung",   # lineup
        "stammspieler",  # starter
        "ersatzspieler", # substitute
        "kader",         # squad
    ],
    "portuguese": [
        "equipe",        # team
        "jogador",       # player
        "treinador",     # coach
        "clube",         # club
        "escalação",     # lineup
        "titular",       # starter
        "reserva",       # substitute
        "elenco",        # squad
    ],
    "polish": [
        "drużyna",       # team
        "zawodnik",      # player
        "trener",        # coach
        "klub",          # club
        "skład",         # lineup
        "wyjściowy",     # starter
        "rezerwowy",     # substitute
        "kadr",          # squad
    ],
    "turkish": [
        "takım",         # team
        "oyuncu",        # player
        "antrenör",      # coach
        "kulüp",         # club
        "kadro",         # lineup
        "ilk on bir",    # starting eleven
        "yedek",         # substitute
        "squad",         # squad
    ],
    "russian": [
        "команда",       # team
        "игрок",         # player
        "тренер",        # coach
        "клуб",          # club
        "состав",        # lineup
        "основной",      # starter
        "запасной",      # substitute
        "состав",        # squad
    ],
    "dutch": [
        "team",          # team
        "speler",        # player
        "trainer",       # coach
        "club",          # club
        "opstelling",    # lineup
        "basis",         # starter
        "wisselspeler",  # substitute
        "selectie",      # squad
    ],
}

# Flatten all keywords for efficient matching
ALL_INJURY_KEYWORDS = []
for lang, keywords in INJURY_KEYWORDS.items():
    ALL_INJURY_KEYWORDS.extend(keywords)

ALL_TEAM_KEYWORDS = []
for lang, keywords in TEAM_KEYWORDS.items():
    ALL_TEAM_KEYWORDS.extend(keywords)

ALL_KEYWORDS = ALL_INJURY_KEYWORDS + ALL_TEAM_KEYWORDS

# ============================================
# LEVEL 1: ZERO-COST KEYWORD CHECK
# ============================================

def level_1_keyword_check(text: str) -> Tuple[bool, Optional[str]]:
    """
    Level 1: Zero-cost local keyword check.
    Returns True if text contains relevant keywords in non-English/Italian languages.
    Returns False to discard immediately if no keywords match.

    This is a zero-cost pre-AI filter that checks content against native
    language keywords BEFORE any API calls. Only content that passes this gate
    proceeds to Level 2 (DeepSeek analysis).

    Args:
        text: Raw tweet/article text

    Returns:
        Tuple of (passes_gate: bool, triggered_keyword: Optional[str])
        - passes_gate: True if at least one keyword found, False otherwise
        - triggered_keyword: The first keyword that triggered the gate, or None

    Note:
        - Handles UTF-8 encoding properly for Arabic, Spanish, and French characters
        - Case-insensitive matching
        - Fast string matching only (no API calls)
        - Expected to filter ~95% of content at zero cost
    """
    if not text:
        logger.debug("🚪 [INTEL-GATE-L1] DISCARDED - Empty text")
        return False, None

    # Normalize text for matching (lowercase)
    text_lower = text.lower()

    # Check all language dictionaries
    for keyword in ALL_KEYWORDS:
        if keyword in text_lower:
            logger.info(f"🚪 [INTEL-GATE-L1] PASSED - Keyword found: '{keyword}'")
            return True, keyword

    logger.debug(f"🚪 [INTEL-GATE-L1] DISCARDED - No native keywords found")
    return False, None


def level_1_keyword_check_with_details(text: str) -> Dict[str, Any]:
    """
    Level 1: Zero-cost local keyword check with detailed results.

    Extended version of level_1_keyword_check that returns additional details
    about which language and keyword type triggered the gate.

    Args:
        text: Raw tweet/article text

    Returns:
        Dict with keys:
            - passes_gate: bool - Whether the gate was passed
            - triggered_keyword: Optional[str] - The keyword that triggered the gate
            - keyword_type: Optional[str] - 'injury' or 'team'
            - language: Optional[str] - Language code (e.g., 'spanish', 'arabic')
    """
    if not text:
        logger.debug("🚪 [INTEL-GATE-L1] DISCARDED - Empty text")
        return {
            "passes_gate": False,
            "triggered_keyword": None,
            "keyword_type": None,
            "language": None
        }

    # Normalize text for matching (lowercase)
    text_lower = text.lower()

    # Check injury keywords first
    for lang, keywords in INJURY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                logger.info(f"🚪 [INTEL-GATE-L1] PASSED - Injury keyword found: '{keyword}' ({lang})")
                return {
                    "passes_gate": True,
                    "triggered_keyword": keyword,
                    "keyword_type": "injury",
                    "language": lang
                }

    # Check team keywords
    for lang, keywords in TEAM_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                logger.info(f"🚪 [INTEL-GATE-L1] PASSED - Team keyword found: '{keyword}' ({lang})")
                return {
                    "passes_gate": True,
                    "triggered_keyword": keyword,
                    "keyword_type": "team",
                    "language": lang
                }

    logger.debug(f"🚪 [INTEL-GATE-L1] DISCARDED - No native keywords found")
    return {
        "passes_gate": False,
        "triggered_keyword": None,
        "keyword_type": None,
        "language": None
    }


# ============================================
# LEVEL 2: ECONOMIC AI TRANSLATION
# ============================================

def build_level_2_prompt(text: str) -> str:
    """
    Build prompt for Level 2 DeepSeek-V3 analysis.

    This prompt asks for:
    - One-sentence translation to Italian
    - Boolean classification: is_relevant
    - Specific instruction: "Rilevante solo se parla di infortuni o cambi formazione"

    Args:
        text: The text to analyze

    Returns:
        Formatted prompt for DeepSeek-V3
    """
    prompt = f"""Translate the following text to Italian and determine if it contains relevant injury or team information.
Reply ONLY with JSON in this exact format: {{"translation": "str", "is_relevant": bool}}

Text: {text}

IMPORTANT:
- Translate to Italian in one sentence
- Set is_relevant to true ONLY if the text discusses injuries (infortuni) or lineup changes (cambi formazione)
- If the text is about salaries, transfers, or other non-betting topics, set is_relevant to false
- Return ONLY valid JSON, no other text

Respond with JSON only."""
    return prompt


def parse_level_2_response(response: str) -> Optional[Dict]:
    """
    Parse Level 2 DeepSeek-V3 response.

    Args:
        response: Raw response text from DeepSeek

    Returns:
        Dict with 'translation' and 'is_relevant' keys, or None on failure
    """
    if not response:
        return None

    try:
        # Try to parse as JSON
        data = json.loads(response)

        # Extract required fields
        translation = data.get("translation", "")
        is_relevant = data.get("is_relevant", False)

        # Validate types
        if not isinstance(translation, str):
            logger.warning(f"⚠️ [INTEL-GATE-L2] Invalid translation type: {type(translation)}")
            translation = ""

        # Handle boolean conversion (may come as string)
        if isinstance(is_relevant, str):
            is_relevant = is_relevant.lower() in ('true', 'yes', 'si', '1')
        elif not isinstance(is_relevant, bool):
            is_relevant = bool(is_relevant)

        return {
            "translation": translation,
            "is_relevant": is_relevant
        }

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ [INTEL-GATE-L2] Failed to parse JSON: {e}")
        # Try to extract JSON from response
        try:
            import re
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                return parse_level_2_response(json_match.group())
        except Exception:
            pass
        return None
    except Exception as e:
        logger.error(f"❌ [INTEL-GATE-L2] Error parsing response: {e}")
        return None


async def level_2_translate_and_classify(text: str, ai_provider=None) -> Dict[str, Any]:
    """
    Level 2: Use DeepSeek V3 via OpenRouter to translate and classify.

    This method uses DeepSeek-V3 (NOT R1) for translation and classification
    of content that passed the Level 1 keyword gate.

    Args:
        text: Text that passed Level 1
        ai_provider: Optional AI provider instance with OpenRouter access.
                    If None, will use direct HTTP client.

    Returns:
        Dict with keys:
            - translation: str - Italian translation
            - is_relevant: bool - Whether content is betting-relevant
            - success: bool - Whether the API call succeeded
            - error: Optional[str] - Error message if failed
    """
    if not OPENROUTER_API_KEY:
        logger.warning("⚠️ [INTEL-GATE-L2] OPENROUTER_API_KEY not set, skipping analysis")
        return {
            "translation": "",
            "is_relevant": False,
            "success": False,
            "error": "OPENROUTER_API_KEY not set"
        }

    try:
        # Build prompt
        prompt = build_level_2_prompt(text)

        # Prepare request
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://earlybird.betting",
            "X-Title": "EarlyBird Betting Intelligence"
        }

        payload = {
            "model": DEEPSEEK_V3_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 500
        }

        # Import http_client for the request
        from src.utils.http_client import get_http_client
        http_client = get_http_client()

        if not http_client:
            logger.error("❌ [INTEL-GATE-L2] HTTP client not available")
            return {
                "translation": "",
                "is_relevant": False,
                "success": False,
                "error": "HTTP client not available"
            }

        # Make request
        logger.info(f"🤖 [INTEL-GATE-L2] Analyzing with DeepSeek-V3...")
        response = http_client.post_sync(
            OPENROUTER_API_URL,
            rate_limit_key="openrouter",
            headers=headers,
            json=payload,
            timeout=30,
            max_retries=1
        )

        # Handle response
        if response.status_code == 429:
            logger.warning(f"⚠️ [INTEL-GATE-L2] Rate limit hit (429)")
            return {
                "translation": "",
                "is_relevant": False,
                "success": False,
                "error": "Rate limit hit"
            }

        if response.status_code != 200:
            logger.error(f"❌ [INTEL-GATE-L2] API error: HTTP {response.status_code}")
            return {
                "translation": "",
                "is_relevant": False,
                "success": False,
                "error": f"HTTP {response.status_code}"
            }

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            logger.warning(f"⚠️ [INTEL-GATE-L2] Empty response")
            return {
                "translation": "",
                "is_relevant": False,
                "success": False,
                "error": "Empty response"
            }

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            logger.warning(f"⚠️ [INTEL-GATE-L2] No content in response")
            return {
                "translation": "",
                "is_relevant": False,
                "success": False,
                "error": "No content in response"
            }

        # Parse response
        result = parse_level_2_response(content)
        if result:
            logger.info(
                f"✅ [INTEL-GATE-L2] Complete - Translation: '{result['translation'][:50]}...', "
                f"Relevant: {result['is_relevant']}"
            )
            return {
                "translation": result["translation"],
                "is_relevant": result["is_relevant"],
                "success": True,
                "error": None
            }
        else:
            logger.warning(f"⚠️ [INTEL-GATE-L2] Failed to parse response")
            return {
                "translation": "",
                "is_relevant": False,
                "success": False,
                "error": "Failed to parse response"
            }

    except Exception as e:
        logger.error(f"❌ [INTEL-GATE-L2] Error: {e}")
        return {
            "translation": "",
            "is_relevant": False,
            "success": False,
            "error": str(e)
        }


# ============================================
# COMBINED GATE FUNCTION
# ============================================

async def apply_intelligence_gate(text: str, ai_provider=None) -> Dict[str, Any]:
    """
    Apply the 3-level intelligence gate to content.

    This function applies Levels 1 and 2 of the gate sequentially:
    1. Level 1: Zero-cost keyword check (local)
    2. Level 2: AI translation and classification (if Level 1 passes)

    Level 3 (R1 reasoning) is handled separately in Task 2.

    Args:
        text: Raw content to analyze
        ai_provider: Optional AI provider instance

    Returns:
        Dict with comprehensive gate results:
            - level_1_passed: bool - Whether Level 1 gate was passed
            - level_1_keyword: Optional[str] - Keyword that triggered Level 1
            - level_1_details: Dict - Detailed Level 1 results
            - level_2_passed: bool - Whether Level 2 gate was passed
            - level_2_translation: Optional[str] - Italian translation
            - level_2_relevant: bool - Whether content is betting-relevant
            - level_2_success: bool - Whether Level 2 API call succeeded
            - final_decision: str - 'proceed' or 'discard'
            - discard_reason: Optional[str] - Reason for discarding
    """
    result = {
        "level_1_passed": False,
        "level_1_keyword": None,
        "level_1_details": None,
        "level_2_passed": False,
        "level_2_translation": None,
        "level_2_relevant": False,
        "level_2_success": False,
        "final_decision": "discard",
        "discard_reason": None
    }

    # Level 1: Zero-cost keyword check
    level_1_result = level_1_keyword_check_with_details(text)
    result["level_1_details"] = level_1_result
    result["level_1_passed"] = level_1_result["passes_gate"]
    result["level_1_keyword"] = level_1_result.get("triggered_keyword")

    if not level_1_result["passes_gate"]:
        result["discard_reason"] = "Level 1: No native keywords found"
        logger.info(f"🚪 [INTEL-GATE] DISCARDED - Level 1: No native keywords found")
        return result

    # Level 2: AI translation and classification
    level_2_result = await level_2_translate_and_classify(text, ai_provider)
    result["level_2_translation"] = level_2_result.get("translation", "")
    result["level_2_relevant"] = level_2_result.get("is_relevant", False)
    result["level_2_success"] = level_2_result.get("success", False)

    if not level_2_result.get("success"):
        # Level 2 failed - proceed anyway (better to have false positives than miss intel)
        result["final_decision"] = "proceed"
        result["discard_reason"] = None
        logger.warning(f"⚠️ [INTEL-GATE] PROCEED - Level 2 failed, allowing through")
        return result

    result["level_2_passed"] = level_2_result["is_relevant"]

    if not level_2_result["is_relevant"]:
        result["final_decision"] = "discard"
        result["discard_reason"] = "Level 2: Not betting-relevant"
        logger.info(f"🚪 [INTEL-GATE] DISCARDED - Level 2: Not betting-relevant")
        return result

    # Both levels passed
    result["final_decision"] = "proceed"
    result["discard_reason"] = None
    logger.info(f"✅ [INTEL-GATE] PASSED - Proceeding to processing")
    return result


# ============================================
# LEVEL 3: R1 DEEP REASONING (Triangulation/Verification)
# ============================================

LEVEL_3_REASONING_PROMPT = """You are an Elite Sports Betting Analyst with access to triangulated intelligence.

YOUR TASK: Analyze the following intelligence and make a final BET/NO BET decision.

INTELLIGENCE PACKAGE:
{intel_package}

RULES:
1. Cross-reference all data sources (News, Market, FotMob, Twitter)
2. Apply Tactical Veto Rules when injury/absence data contradicts statistical signals
3. The 15% Market Veto: If odds already dropped >15%, value is gone - NO BET
4. Use ITALIAN for all reasoning

OUTPUT FORMAT (JSON only):
{{
  "final_verdict": "BET" or "NO BET",
  "confidence": 0-100,
  "reasoning": "Italian explanation correlating all sources",
  "recommended_market": "WINNER" or "GOALS" or "CARDS" or "CORNERS" or "BTTS" or "NONE",
  "primary_driver": "INJURY_INTEL" or "SHARP_MONEY" or "MATH_VALUE" or "CONTEXT_PLAY" or "CONTRARIAN",
  "risk_assessment": "LOW" or "MEDIUM" or "HIGH"
}}

Think carefully. Output JSON only."""


async def level_3_deep_reasoning(
    intel_package: Dict[str, Any],
    ai_provider=None
) -> Dict[str, Any]:
    """
    Level 3: Use DeepSeek R1 (Model B - Reasoner) for deep triangulation analysis.
    
    This is the heavy thinking layer that applies:
    - Cross-source correlation
    - Tactical Veto Rules
    - 15% Market Veto
    - Final BET/NO BET verdict
    
    Args:
        intel_package: Dict containing all intelligence:
            - news_snippet: str - The news text
            - market_status: str - Odds movement info
            - official_data: str - FotMob data
            - twitter_intel: str - Social intelligence
            - team_stats: str - Statistical context
            - is_convergent: bool - Cross-source convergence
        ai_provider: Optional AI provider instance with OpenRouter access
        
    Returns:
        Dict with keys:
            - final_verdict: str - 'BET' or 'NO BET'
            - confidence: int - 0-100
            - reasoning: str - Italian explanation
            - recommended_market: str - Market recommendation
            - primary_driver: str - Main reason for bet
            - risk_assessment: str - Risk level
            - success: bool - Whether the API call succeeded
            - error: Optional[str] - Error message if failed
            - reasoning_trace: Optional[str] - R1 thinking trace
    """
    if not OPENROUTER_API_KEY:
        logger.warning("⚠️ [INTEL-GATE-L3] OPENROUTER_API_KEY not set, skipping R1 reasoning")
        return {
            "final_verdict": "NO BET",
            "confidence": 0,
            "reasoning": "API non configurata",
            "recommended_market": "NONE",
            "primary_driver": "NONE",
            "risk_assessment": "HIGH",
            "success": False,
            "error": "OPENROUTER_API_KEY not set",
            "reasoning_trace": None
        }
    
    try:
        # Format intel package into prompt
        intel_text = json.dumps(intel_package, ensure_ascii=False, indent=2)
        prompt = LEVEL_3_REASONING_PROMPT.format(intel_package=intel_text)
        
        # Prepare request
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://earlybird.betting",
            "X-Title": "EarlyBird Betting Intelligence"
        }
        
        payload = {
            "model": MODEL_B_REASONER,  # Use R1 Reasoner for deep thinking
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,  # Lower for more consistent reasoning
            "max_tokens": 2000  # Allow longer reasoning
        }
        
        # Import http_client for the request
        from src.utils.http_client import get_http_client
        http_client = get_http_client()
        
        if not http_client:
            logger.error("❌ [INTEL-GATE-L3] HTTP client not available")
            return {
                "final_verdict": "NO BET",
                "confidence": 0,
                "reasoning": "Client HTTP non disponibile",
                "recommended_market": "NONE",
                "primary_driver": "NONE",
                "risk_assessment": "HIGH",
                "success": False,
                "error": "HTTP client not available",
                "reasoning_trace": None
            }
        
        # Make request
        logger.info(f"🧠 [INTEL-GATE-L3] Analyzing with DeepSeek R1 (Model B - Reasoner)...")
        response = http_client.post_sync(
            OPENROUTER_API_URL,
            rate_limit_key="openrouter",
            headers=headers,
            json=payload,
            timeout=60,  # Longer timeout for deep reasoning
            max_retries=2
        )
        
        # Handle response
        if response.status_code == 429:
            logger.warning(f"⚠️ [INTEL-GATE-L3] Rate limit hit (429)")
            return {
                "final_verdict": "NO BET",
                "confidence": 0,
                "reasoning": "Limite rate API raggiunto",
                "recommended_market": "NONE",
                "primary_driver": "NONE",
                "risk_assessment": "HIGH",
                "success": False,
                "error": "Rate limit hit",
                "reasoning_trace": None
            }
        
        if response.status_code != 200:
            logger.error(f"❌ [INTEL-GATE-L3] API error: HTTP {response.status_code}")
            return {
                "final_verdict": "NO BET",
                "confidence": 0,
                "reasoning": f"Errore API: HTTP {response.status_code}",
                "recommended_market": "NONE",
                "primary_driver": "NONE",
                "risk_assessment": "HIGH",
                "success": False,
                "error": f"HTTP {response.status_code}",
                "reasoning_trace": None
            }
        
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            logger.warning(f"⚠️ [INTEL-GATE-L3] Empty response")
            return {
                "final_verdict": "NO BET",
                "confidence": 0,
                "reasoning": "Risposta vuota da API",
                "recommended_market": "NONE",
                "primary_driver": "NONE",
                "risk_assessment": "HIGH",
                "success": False,
                "error": "Empty response",
                "reasoning_trace": None
            }
        
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            logger.warning(f"⚠️ [INTEL-GATE-L3] No content in response")
            return {
                "final_verdict": "NO BET",
                "confidence": 0,
                "reasoning": "Nessun contenuto nella risposta",
                "recommended_market": "NONE",
                "primary_driver": "NONE",
                "risk_assessment": "HIGH",
                "success": False,
                "error": "No content in response",
                "reasoning_trace": None
            }
        
        # Extract reasoning trace if present (R1 models use <think> tags)
        reasoning_trace = None
        clean_content = content
        import re
        think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
        if think_match:
            reasoning_trace = think_match.group(1).strip()
            clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            logger.info(f"🧠 [INTEL-GATE-L3] Reasoning trace captured ({len(reasoning_trace)} chars)")
        
        # Parse JSON response
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[^{}]*\}', clean_content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(clean_content)
            
            # Validate required fields with defaults
            final_verdict = result.get("final_verdict", "NO BET")
            if final_verdict not in ["BET", "NO BET"]:
                final_verdict = "NO BET"
            
            confidence = int(result.get("confidence", 0))
            confidence = max(0, min(100, confidence))
            
            logger.info(
                f"✅ [INTEL-GATE-L3] Complete - Verdict: {final_verdict}, "
                f"Confidence: {confidence}%, Market: {result.get('recommended_market', 'NONE')}"
            )
            
            return {
                "final_verdict": final_verdict,
                "confidence": confidence,
                "reasoning": result.get("reasoning", "Analisi non disponibile"),
                "recommended_market": result.get("recommended_market", "NONE"),
                "primary_driver": result.get("primary_driver", "NONE"),
                "risk_assessment": result.get("risk_assessment", "HIGH"),
                "success": True,
                "error": None,
                "reasoning_trace": reasoning_trace
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ [INTEL-GATE-L3] Failed to parse JSON: {e}")
            return {
                "final_verdict": "NO BET",
                "confidence": 0,
                "reasoning": "Errore parsing risposta JSON",
                "recommended_market": "NONE",
                "primary_driver": "NONE",
                "risk_assessment": "HIGH",
                "success": False,
                "error": f"JSON parse error: {e}",
                "reasoning_trace": reasoning_trace
            }
    
    except Exception as e:
        logger.error(f"❌ [INTEL-GATE-L3] Error: {e}")
        return {
            "final_verdict": "NO BET",
            "confidence": 0,
            "reasoning": f"Errore: {str(e)}",
            "recommended_market": "NONE",
            "primary_driver": "NONE",
            "risk_assessment": "HIGH",
            "success": False,
            "error": str(e),
            "reasoning_trace": None
        }


def should_use_level_3(
    level_2_result: Dict[str, Any],
    is_convergent: bool = False,
    confidence_threshold: float = 0.7
) -> bool:
    """
    Determine if Level 3 R1 reasoning should be used.
    
    We only invoke the expensive R1 reasoning when:
    1. Level 2 classified as relevant
    2. Signal is convergent (confirmed by both Web and Social)
    3. Confidence from previous processing is above threshold
    
    Args:
        level_2_result: Results from Level 2 processing
        is_convergent: Whether signal appears in both Web and Social
        confidence_threshold: Minimum confidence to trigger L3
        
    Returns:
        bool - Whether to invoke Level 3 reasoning
    """
    # Always use L3 for convergent signals (highest priority)
    if is_convergent:
        logger.info("🧠 [INTEL-GATE] Triggering Level 3 - Convergent signal detected")
        return True
    
    # Check Level 2 relevance
    if not level_2_result.get("is_relevant", False):
        return False
    
    # Check if Level 2 succeeded
    if not level_2_result.get("success", False):
        return False
    
    # For non-convergent signals, we still use L3 if relevant
    # (but this could be made stricter in future to save costs)
    logger.info("🧠 [INTEL-GATE] Triggering Level 3 - Relevant signal detected")
    return True


# ============================================
# UTILITY FUNCTIONS
# ============================================

def get_supported_languages() -> List[str]:
    """
    Get list of supported languages for keyword matching.

    Returns:
        List of language codes (e.g., ['spanish', 'arabic', 'french', ...])
    """
    return list(INJURY_KEYWORDS.keys())


def get_keyword_count() -> Dict[str, int]:
    """
    Get count of keywords per category.

    Returns:
        Dict with 'injury' and 'team' keyword counts
    """
    injury_count = sum(len(kws) for kws in INJURY_KEYWORDS.values())
    team_count = sum(len(kws) for kws in TEAM_KEYWORDS.values())
    return {
        "injury": injury_count,
        "team": team_count,
        "total": injury_count + team_count
    }


def print_gate_stats() -> None:
    """Print statistics about the intelligence gate."""
    stats = get_keyword_count()
    languages = get_supported_languages()

    logger.info("=" * 60)
    logger.info("🚪 INTELLIGENCE GATE STATISTICS")
    logger.info("=" * 60)
    logger.info(f"Supported Languages: {len(languages)}")
    logger.info(f"Languages: {', '.join(languages)}")
    logger.info(f"Injury Keywords: {stats['injury']}")
    logger.info(f"Team Keywords: {stats['team']}")
    logger.info(f"Total Keywords: {stats['total']}")
    logger.info(f"Expected Cost Savings: ~95% reduction in token costs")
    logger.info("=" * 60)


if __name__ == "__main__":
    # Test the gate
    print_gate_stats()

    # Test Level 1
    test_texts = [
        "El jugador tiene una lesión en la pierna",  # Spanish - injury
        "لاعب مصاب في الفريق",  # Arabic - injury
        "Le joueur est blessé",  # French - injury
        "The player scored a goal",  # English - should fail
        "Il giocatore è infortunato",  # Italian - should fail (we filter non-English/Italian)
    ]

    for text in test_texts:
        result = level_1_keyword_check(text)
        print(f"Text: {text[:50]}... -> Level 1: {result}")
