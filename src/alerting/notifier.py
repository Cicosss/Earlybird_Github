"""
EarlyBird Notifier Module

Handles all Telegram alert notifications with:
- Retry logic via tenacity
- HTML formatting with fallback to plain text
- Odds movement analysis
- Multi-source intelligence display

V8.2: Production-ready with comprehensive error handling

Phase 1 Critical Fix: Added Unicode normalization and safe UTF-8 truncation
"""
 
import os
import re
import html
import time
import logging
import unicodedata
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path
 
import requests
import requests.exceptions
import pytz
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


def normalize_unicode(text: str) -> str:
    """
    Normalize Unicode to NFC form for consistent text handling.
    
    Phase 1 Critical Fix: Ensures special characters from Turkish, Polish,
    Greek, Arabic, Chinese, Japanese, Korean, and other languages
    are handled consistently across all components.
    
    Args:
        text: Input text to normalize
        
    Returns:
        Normalized text in NFC form
    """
    if not text:
        return ""
    return unicodedata.normalize('NFC', text)


def truncate_utf8(text: str, max_bytes: int) -> str:
    """
    Truncate text to fit within max_bytes UTF-8 encoded.
    
    Phase 1 Critical Fix: Safe truncation that preserves UTF-8 characters
    instead of cutting at arbitrary byte positions which can corrupt
    multi-byte characters.
    
    Args:
        text: Input text to truncate
        max_bytes: Maximum bytes in UTF-8 encoding
        
    Returns:
        Truncated text with valid UTF-8 characters
    """
    if not text:
        return ""
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text
    # Truncate and decode, removing incomplete characters
    truncated = encoded[:max_bytes].decode('utf-8', errors='ignore')
    return truncated

# Load environment variables
load_dotenv()

# ============================================
# CONFIGURATION
# ============================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Verify credentials are loaded securely
if TELEGRAM_TOKEN:
    logging.debug("Telegram token caricato da variabile ambiente")
if TELEGRAM_CHAT_ID:
    logging.debug("Telegram chat ID caricato da variabile ambiente")

# ============================================
# CONSTANTS
# ============================================
TELEGRAM_MESSAGE_LIMIT = 4000
TELEGRAM_TRUNCATED_LIMIT = 3900
TELEGRAM_TIMEOUT_SECONDS = 30
TELEGRAM_DOCUMENT_TIMEOUT = 60

# ============================================
# TEXT CLEANING HELPERS
# ============================================


def strip_html_links(text: str) -> str:
    """
    Remove HTML anchor tags from text, keeping only the link text.

    Args:
        text: Text potentially containing HTML links

    Returns:
        Text with <a href='...'>text</a> replaced by just 'text'
    """
    return re.sub(r"<a href='[^']*'>([^<]*)</a>", r'\1', text)


def _clean_ai_text(text: Optional[str]) -> str:
    """
    Clean AI-generated text to remove redundant link references.

    The AI sometimes includes "Leggi la fonte" or "Link:" in its output,
    which duplicates the actual clickable link we append separately.

    Args:
        text: Raw AI-generated text (reasoning, combo_reasoning, etc.)

    Returns:
        Cleaned text with HTML-escaped content and removed link references
    """
    if not text:
        return ""

    # HTML escape for security (prevent injection)
    cleaned = html.escape(text)

    # Remove common AI-generated link phrases (Italian + English)
    patterns_to_remove = [
        r'Leggi la fonte originale\.?',
        r'Leggi la fonte\.?',
        r'Leggi news\.?',
        r'Read more\.?',
        r'Read the source\.?',
        r'Source:.*?(?=\s|$)',
        r'Link:.*?(?=\s|$)',
        r'Fonte:.*?(?=\s|$)',
        r'📎\s*Leggi\s*News\.?',
        r'🔗\s*Leggi\s*(la\s*)?(fonte|news)\.?',
        r'https?://\S+',  # Remove any URLs
    ]

    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Strip trailing/leading whitespace and normalize multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned


# ============================================
# TELEGRAM API RETRY WRAPPER
# ============================================


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError))
)
def _send_telegram_request(url: str, payload: Dict[str, Any], timeout: int = TELEGRAM_TIMEOUT_SECONDS) -> requests.Response:
    """
    Internal function to send Telegram API request with tenacity retry.

    Retries on Timeout and ConnectionError only.
    Does NOT retry on 4xx client errors (except 429 rate limit handled separately).

    Args:
        url: Telegram API endpoint
        payload: Request payload
        timeout: Request timeout in seconds

    Returns:
        Response object

    Raises:
        requests.exceptions.Timeout: On timeout (will be retried by tenacity)
        requests.exceptions.ConnectionError: On connection error (will be retried by tenacity)
    """
    response = requests.post(url, data=payload, timeout=timeout)

    # Handle rate limiting with custom backoff
    if response.status_code == 429:
        retry_after = int(response.headers.get('Retry-After', 5))
        logging.warning(f"Telegram rate limit (429), attesa {retry_after}s...")
        time.sleep(retry_after)
        raise requests.exceptions.ConnectionError("Rate limited - triggering retry")

    # Handle server errors (5xx) - trigger retry
    if response.status_code >= 500:
        logging.warning(f"Telegram server error ({response.status_code}), triggering retry...")
        raise requests.exceptions.ConnectionError(f"Server error {response.status_code}")

    return response


# ============================================
# ODDS MOVEMENT CALCULATION
# ============================================


def calculate_odds_movement(opening_odd: Optional[float], current_odd: Optional[float]) -> Dict[str, Any]:
    """
    Calculate odds drop percentage and determine market reaction.

    Args:
        opening_odd: Opening odds value
        current_odd: Current odds value

    Returns:
        Dict with: drop_percent, emoji, message (in Italian)
    """
    if not opening_odd or not current_odd or opening_odd == 0:
        return {
            'drop_percent': 0,
            'emoji': '❓',
            'message': 'Quote non disponibili'
        }

    drop = ((opening_odd - current_odd) / opening_odd) * 100

    if drop > 15:
        return {
            'drop_percent': round(drop, 1),
            'emoji': '📉',
            'message': f'CROLLO QUOTE (-{round(drop, 1)}%) - Notizia probabilmente già prezzata. ⚠️ CAUTELA'
        }
    elif drop >= 5:
        return {
            'drop_percent': round(drop, 1),
            'emoji': '↘️',
            'message': f'IN CALO (-{round(drop, 1)}%) - Il mercato sta reagendo'
        }
    elif drop >= -5:  # Small change either direction
        return {
            'drop_percent': round(drop, 1),
            'emoji': '💎',
            'message': f'VALORE INTATTO ({round(drop, 1):+}%) - Il mercato non ha ancora reagito! 🎯'
        }
    else:  # Odds rising (negative drop)
        return {
            'drop_percent': round(drop, 1),
            'emoji': '📈',
            'message': f'QUOTE IN SALITA ({round(drop, 1):+}%) - Movimento contrario rilevato'
        }


# ============================================
# COMBO EXTRACTION
# ============================================


def extract_combo_from_summary(news_summary: Optional[str]) -> tuple:
    """
    Extract combo suggestion and reasoning from news summary.

    Args:
        news_summary: Raw news summary text

    Returns:
        Tuple of (primary_market, combo_suggestion, combo_reasoning)
    """
    primary_market = None
    combo_suggestion = None
    combo_reasoning = None

    if not news_summary:
        return primary_market, combo_suggestion, combo_reasoning

    # Extract primary market
    market_match = re.search(r'📊 MERCATO: ([^\n]+)', news_summary)
    if market_match:
        primary_market = market_match.group(1).strip()

    # Extract combo suggestion (if present)
    combo_match = re.search(r'🧩 SMART COMBO: ([^\n]+)', news_summary)
    if combo_match:
        combo_suggestion = combo_match.group(1).strip()

    # Extract combo reasoning (from └─ line or ℹ️ Combo: line)
    reasoning_match = re.search(r'└─ ([^\n]+)', news_summary)
    if reasoning_match:
        combo_reasoning = reasoning_match.group(1).strip()
    else:
        # Try the "Combo skipped" format
        skipped_match = re.search(r'ℹ️ Combo: ([^\n]+)', news_summary)
        if skipped_match:
            combo_reasoning = skipped_match.group(1).strip()

    return primary_market, combo_suggestion, combo_reasoning


# ============================================
# MESSAGE SECTION BUILDERS
# ============================================

def _build_bet_section(
    recommended_market: Optional[str],
    combo_suggestion: Optional[str],
    combo_reasoning_clean: Optional[str],
    math_edge: Optional[Dict[str, Any]],
    financial_risk: Optional[str]
) -> str:
    """Build the betting suggestion section of the message."""
    bet_section = ""

    # Primary market recommendation
    if recommended_market and recommended_market != 'NONE':
        bet_section = f"🎯 <b>Mercato Consigliato:</b> {html.escape(recommended_market)}\n"

    # Combo suggestion
    if combo_suggestion and combo_suggestion != 'None':
        bet_section += f"🧩 <b>COMBO SMART:</b> {html.escape(combo_suggestion)}\n"
        if combo_reasoning_clean and 'insufficien' not in combo_reasoning_clean.lower():
            bet_section += f"   <i>({combo_reasoning_clean})</i>\n"
    elif combo_reasoning_clean:
        # Discrete footer for negative result - show why combo was skipped
        bet_section += f"<i>ℹ️ Combo: {combo_reasoning_clean}</i>\n"

    # Math Edge section (Poisson model value detection)
    if math_edge and math_edge.get('edge', 0) > 5:
        edge_pct = math_edge.get('edge', 0)
        kelly = math_edge.get('kelly_stake', 0)
        market = math_edge.get('market', 'Unknown')

        # Edge label dinamica con spiegazione
        if edge_pct >= 10:
            edge_label = "🎯🎯 Valore eccezionale (bet molto forte)"
        elif edge_pct >= 7:
            edge_label = "🎯 Eccellente valore (bet forte)"
        else:  # 5 < edge < 7
            edge_label = "✅ Buon valore (bet consigliata)"

        # Kelly label dinamica con spiegazione
        if kelly <= 0:
            kelly_label = "⚪ SKIP (nessuna puntata)"
        elif kelly < 1:
            kelly_label = "🟡 BASSO (punta poco)"
        elif kelly < 3:
            kelly_label = "🟢 MEDIO (punta moderato)"
        elif kelly < 5:
            kelly_label = "🔵 ALTO (punta consistente)"
        else:
            kelly_label = "🟣 MOLTO ALTO (punta massimo)"

        bet_section += f"🧮 <b>VALORE MATEMATICO:</b>\n"
        bet_section += f"   📊 Edge: {edge_pct:+.1f}% su {html.escape(market)} - {edge_label}\n"
        bet_section += f"   💰 Kelly: {kelly:.2f}% del capitale - {kelly_label}\n"

    # Financial Risk section (B-Team Detection)
    if financial_risk and financial_risk.upper() in ['CRITICAL', 'WARNING']:
        risk_emoji = "🚨" if financial_risk.upper() == "CRITICAL" else "⚠️"
        risk_label = "B-TEAM CONFERMATO" if financial_risk.upper() == "CRITICAL" else "ROTAZIONE PROBABILE"
        bet_section += f"{risk_emoji} <b>ALLARME ROSA:</b> {risk_label}\n"

    return bet_section


def _build_referee_section(referee_intel: Optional[Dict[str, Any]], combo_suggestion: Optional[str], recommended_market: Optional[str]) -> str:
    """Build the referee intelligence section for cards market transparency."""
    referee_section = ""

    if not referee_intel or not isinstance(referee_intel, dict):
        return referee_section

    # Check if this is a cards-related suggestion
    combo_lower = (combo_suggestion or '').lower()
    market_lower = (recommended_market or '').lower()
    is_cards_bet = 'card' in combo_lower or 'card' in market_lower

    if not is_cards_bet:
        return referee_section

    ref_name = referee_intel.get('referee_name', 'Unknown')
    ref_cards_avg = referee_intel.get('referee_cards_avg')
    ref_strictness = referee_intel.get('referee_strictness', 'Unknown')
    home_cards = referee_intel.get('home_cards_avg')
    away_cards = referee_intel.get('away_cards_avg')
    cards_reasoning = referee_intel.get('cards_reasoning', '')

    # Build referee intel string
    if ref_name and ref_name != 'Unknown':
        referee_section = f"⚖️ <b>ARBITRO:</b> {html.escape(ref_name)}"
        if ref_cards_avg:
            referee_section += f" ({ref_cards_avg:.1f} cart/partita"
            if ref_strictness and ref_strictness != 'Unknown':
                referee_section += f", {ref_strictness}"
            referee_section += ")"
        referee_section += "\n"

        # Team cards stats
        if home_cards or away_cards:
            team_stats = []
            if home_cards:
                team_stats.append(f"Casa: {home_cards:.1f}")
            if away_cards:
                team_stats.append(f"Trasf: {away_cards:.1f}")
            if team_stats:
                referee_section += f"   🟨 Media squadre: {' | '.join(team_stats)} cart/partita\n"

        # Reasoning
        if cards_reasoning:
            referee_section += f"   <i>💡 {html.escape(cards_reasoning)}</i>\n"

    return referee_section


def _build_twitter_section(twitter_intel: Optional[Dict[str, Any]]) -> str:
    """Build the Twitter insider intel section."""
    twitter_section = ""

    if not twitter_intel or not isinstance(twitter_intel, dict):
        return twitter_section

    tweets = twitter_intel.get('tweets', [])
    if not tweets:
        return twitter_section

    twitter_section = "🐦 <b>INSIDER INTEL:</b>\n"
    for tweet in tweets[:2]:  # Max 2 tweets to keep message compact
        handle = tweet.get('handle', '')
        content = tweet.get('content', '')[:100]  # Truncate
        topics = tweet.get('topics', [])
        topic_str = f" [{', '.join(topics)}]" if topics else ""
        twitter_section += f"   • {html.escape(handle)}: <i>{html.escape(content)}...</i>{topic_str}\n"

    return twitter_section


def _build_injury_section(
    injury_intel: Optional[Dict[str, Any]],
    home_team: str,
    away_team: str
) -> str:
    """Build the injury impact section."""
    injury_section = ""

    if not injury_intel or not isinstance(injury_intel, dict):
        return injury_section

    home_severity = injury_intel.get('home_severity', 'LOW')
    away_severity = injury_intel.get('away_severity', 'LOW')
    home_starters = injury_intel.get('home_missing_starters', 0)
    away_starters = injury_intel.get('away_missing_starters', 0)
    home_key = injury_intel.get('home_key_players', [])
    away_key = injury_intel.get('away_key_players', [])
    favors = injury_intel.get('favors', 'neutral')

    # Only show if there's meaningful injury data
    has_significant_home = home_starters > 0 or home_key or home_severity in ('HIGH', 'CRITICAL')
    has_significant_away = away_starters > 0 or away_key or away_severity in ('HIGH', 'CRITICAL')

    if not has_significant_home and not has_significant_away:
        return injury_section

    injury_section = "🏥 <b>ASSENZE:</b>\n"
    severity_emoji_map = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}

    # Home team injuries
    if has_significant_home:
        severity_emoji = severity_emoji_map.get(home_severity, "⚪")
        injury_section += f"   🏠 {home_team}: {severity_emoji} {home_severity}"
        if home_starters > 0:
            injury_section += f" ({home_starters} titolari)"
        if home_key:
            key_names = ', '.join(home_key[:2])  # Max 2 names
            injury_section += f" - ⭐{html.escape(key_names)}"
        injury_section += "\n"

    # Away team injuries
    if has_significant_away:
        severity_emoji = severity_emoji_map.get(away_severity, "⚪")
        injury_section += f"   🚌 {away_team}: {severity_emoji} {away_severity}"
        if away_starters > 0:
            injury_section += f" ({away_starters} titolari)"
        if away_key:
            key_names = ', '.join(away_key[:2])
            injury_section += f" - ⭐{html.escape(key_names)}"
        injury_section += "\n"

    # Summary of who it favors
    if favors == 'home':
        injury_section += f"   📊 <i>Vantaggio {home_team}</i>\n"
    elif favors == 'away':
        injury_section += f"   📊 <i>Vantaggio {away_team}</i>\n"

    return injury_section


def _build_verification_section(verification_info: Optional[Dict[str, Any]]) -> str:
    """Build the verification layer section."""
    verification_section = ""

    if not verification_info or not isinstance(verification_info, dict):
        return verification_section

    status = verification_info.get('status', '')
    confidence = verification_info.get('confidence', '')
    reasoning = verification_info.get('reasoning', '')
    inconsistencies = verification_info.get('inconsistencies_count', 0)

    # Status emoji and label
    if status == 'confirm':
        status_emoji = "✅"
        status_label = "VERIFICATO"
    elif status == 'change_market':
        status_emoji = "🔄"
        status_label = "MERCATO MODIFICATO"
    else:
        status_emoji = "⚠️"
        status_label = status.upper() if status else "UNKNOWN"

    # Confidence emoji
    conf_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(confidence, "⚪")

    verification_section = f"🔍 <b>VERIFICA:</b> {status_emoji} {status_label} {conf_emoji} ({confidence})\n"

    # Show inconsistencies count if any
    if inconsistencies > 0:
        verification_section += f"   ⚠️ {inconsistencies} incongruenze rilevate\n"

    # Show reasoning (truncated)
    if reasoning:
        reasoning_clean = html.escape(reasoning[:150])
        verification_section += f"   <i>{reasoning_clean}...</i>\n"

    return verification_section


def _build_convergence_section(is_convergent: bool, convergence_sources: Optional[Dict[str, Any]]) -> str:
    """
    V9.5: Build the cross-source convergence section.
    
    Displays high-priority tag when signal is confirmed by both Web (Brave) and Social (Nitter) sources.
    
    Args:
        is_convergent: True if convergence detected
        convergence_sources: Dict with web and social signal details
        
    Returns:
        Formatted convergence section string
    """
    convergence_section = ""
    
    if not is_convergent:
        return convergence_section
    
    # High-priority convergence tag
    convergence_section = "🔴 <b>CONFERMA MULTIPLA: WEB + SOCIAL</b>\n"
    
    # Add source details if available
    if convergence_sources and isinstance(convergence_sources, dict):
        web_info = convergence_sources.get('web', {})
        social_info = convergence_sources.get('social', {})
        
        web_conf = web_info.get('confidence', 0)
        social_conf = social_info.get('confidence', 0)
        web_source = web_info.get('source', 'Brave')
        social_handle = social_info.get('handle', 'Nitter')
        signal_type = web_info.get('type', 'Unknown')
        
        # Signal type
        convergence_section += f"📊 <b>Segnale:</b> {html.escape(signal_type)}\n"
        
        # Web source details
        convergence_section += f"🌐 <b>Web Source:</b> {html.escape(web_source)} (Confidence: {web_conf*100:.0f}%)\n"
        
        # Social source details
        if social_handle:
            convergence_section += f"🐦 <b>Social Source:</b> @{html.escape(social_handle)} (Confidence: {social_conf*100:.0f}%)\n"
        else:
            convergence_section += f"🐦 <b>Social Source:</b> Nitter (Confidence: {social_conf*100:.0f}%)\n"
        
        # Time difference if available
        time_diff = convergence_sources.get('time_diff_hours')
        if time_diff is not None:
            convergence_section += f"⏱️ <b>Time Diff:</b> {time_diff:.1f}h\n"
    
    return convergence_section


def _build_confidence_breakdown_section(confidence_breakdown: Optional[Dict[str, Any]]) -> str:
    """Build the confidence breakdown section for transparency."""
    breakdown_section = ""

    if not confidence_breakdown or not isinstance(confidence_breakdown, dict):
        return breakdown_section

    news_w = confidence_breakdown.get('news_weight', 0)
    odds_w = confidence_breakdown.get('odds_weight', 0)
    form_w = confidence_breakdown.get('form_weight', 0)
    injuries_w = confidence_breakdown.get('injuries_weight', 0)

    # Only show if we have meaningful breakdown
    if not any([news_w, odds_w, form_w, injuries_w]):
        return breakdown_section

    # Create user-friendly explanation
    drivers = []
    if news_w >= 10:
        drivers.append(f"📰 Notizia ({news_w}%)")
    if odds_w >= 10:
        drivers.append(f"📈 Quota ({odds_w}%)")
    if form_w >= 10:
        drivers.append(f"📊 Stats ({form_w}%)")
    if injuries_w >= 10:
        drivers.append(f"🏥 Infortuni ({injuries_w}%)")

    if drivers:
        # Find the main driver (highest percentage)
        main_driver = max([
            (news_w, "📰 Notizia"),
            (odds_w, "📈 Quota"),
            (form_w, "📊 Stats"),
            (injuries_w, "🏥 Infortuni")
        ], key=lambda x: x[0])

        main_name, main_pct = main_driver[1], main_driver[0]
        other_drivers = [d for d in drivers if not d.startswith(main_name.split()[0])]

        if other_drivers:
            breakdown_section = f"🎯 <b>Segnale Principale:</b> {main_name} ({main_pct}%)\n"
            breakdown_section += f"   📋 Altri fattori: {', '.join(other_drivers)}\n"
        else:
            breakdown_section = f"🎯 <b>Segnale Principale:</b> {main_name} ({main_pct}%)\n"

    return breakdown_section


def _build_date_line(match_obj: Any) -> str:
    """Build the date/time line for the match."""
    date_line = ""

    if not hasattr(match_obj, 'start_time') or not match_obj.start_time:
        return date_line

    try:
        # Ensure UTC first (handle naive datetime from DB)
        if match_obj.start_time.tzinfo is None:
            utc_time = match_obj.start_time.replace(tzinfo=timezone.utc)
        else:
            utc_time = match_obj.start_time

        # Convert to Rome timezone
        rome_tz = pytz.timezone('Europe/Rome')
        local_time = utc_time.astimezone(rome_tz)
        date_str = local_time.strftime('%d/%m %H:%M')
        date_line = f"📅 {date_str}\n"
    except Exception as e:
        logging.debug(f"Formattazione data fallita: {e}")

    return date_line


def _truncate_message_if_needed(
    message: str,
    header: str,
    date_line: str,
    match_str: str,
    score: int,
    odds_line: str,
    movement: Dict[str, Any],
    source_indicator: str,
    bet_section: str,
    breakdown_section: str,
    injury_section: str,
    referee_section: str,
    twitter_section: str,
    verification_section: str,
    news_summary_clean: str,
    news_link: str,
    convergence_section: str = ""
) -> str:
    """Truncate message if it exceeds Telegram limits."""
    if len(message) <= TELEGRAM_MESSAGE_LIMIT:
        return message

    # Truncate news_summary to fit, keeping structure intact
    overflow = len(message) - TELEGRAM_TRUNCATED_LIMIT  # Leave margin for truncation notice
    if len(news_summary_clean) > overflow + 100:
        news_summary_truncated = news_summary_clean[:-(overflow + 50)] + "... [TRONCATO]"
        message = (
            f"{header}\n"
            f"{date_line}"
            f"⚽ <b>{match_str}</b>\n"
            f"📊 <b>Punteggio: {score}/10</b>\n"
            f"{odds_line}"
            f"{movement['emoji']} <b>{movement['message']}</b>\n"
            f"{convergence_section}"
            f"{source_indicator}"
            f"{bet_section}"
            f"{breakdown_section}"
            f"{injury_section}"
            f"{referee_section}"
            f"{twitter_section}"
            f"{verification_section}\n"
            f"📝 <i>{news_summary_truncated}</i>"
            f"{news_link}"
        )
        logging.debug(f"Message truncated from {len(message) + overflow} to {len(message)} chars")

    return message


# ============================================
# WRAPPER FUNCTION FOR MAIN.PY COMPATIBILITY
# ============================================


def send_alert_wrapper(**kwargs) -> None:
    """
    V9.5: Wrapper function to convert main.py keyword arguments to notifier.send_alert positional arguments.
    
    Main.py calls send_alert with keyword arguments that don't match the function signature.
    This wrapper handles the conversion.
    
    Args:
        **kwargs: Keyword arguments from main.py
        
    Keyword argument mapping:
        - match -> match_obj
        - score -> score
        - market -> recommended_market
        - home_context, away_context -> (not used directly, but kept for compatibility)
        - home_stats, away_stats -> (not used directly)
        - news_articles -> news_summary (first article)
        - twitter_intel -> twitter_intel
        - fatigue_differential -> (not used directly)
        - injury_impact_home, injury_impact_away -> injury_intel
        - biscotto_result -> (not used directly)
        - market_intel -> (not used directly)
        - verification_result -> verification_info
        - is_convergent -> is_convergent (V9.5)
        - convergence_sources -> convergence_sources (V9.5)
    """
    # Extract and convert keyword arguments
    match_obj = kwargs.get('match')
    score = kwargs.get('score')
    league = kwargs.get('league', '') or getattr(match_obj, 'league', '')
    
    # Build news_summary from news_articles
    news_articles = kwargs.get('news_articles', [])
    news_summary = news_articles[0].get('snippet', '') if news_articles else ''
    news_url = news_articles[0].get('link', '') if news_articles else ''
    
    # Extract optional parameters with defaults
    combo_suggestion = kwargs.get('combo_suggestion')
    combo_reasoning = kwargs.get('combo_reasoning')
    recommended_market = kwargs.get('market') or kwargs.get('recommended_market')
    math_edge = kwargs.get('math_edge')
    is_update = kwargs.get('is_update', False)
    financial_risk = kwargs.get('financial_risk')
    intel_source = kwargs.get('intel_source', 'web')
    referee_intel = kwargs.get('referee_intel')
    twitter_intel = kwargs.get('twitter_intel')
    validated_home_team = kwargs.get('validated_home_team')
    validated_away_team = kwargs.get('validated_away_team')
    verification_info = kwargs.get('verification_result')
    injury_intel = kwargs.get('injury_impact_home') or kwargs.get('injury_impact_away')
    confidence_breakdown = kwargs.get('confidence_breakdown')
    
    # V9.5: Extract convergence parameters
    is_convergent = kwargs.get('is_convergent', False)
    convergence_sources = kwargs.get('convergence_sources')
    
    # Call the actual send_alert function with positional arguments
    send_alert(
        match_obj=match_obj,
        news_summary=news_summary,
        news_url=news_url,
        score=score,
        league=league,
        combo_suggestion=combo_suggestion,
        combo_reasoning=combo_reasoning,
        recommended_market=recommended_market,
        math_edge=math_edge,
        is_update=is_update,
        financial_risk=financial_risk,
        intel_source=intel_source,
        referee_intel=referee_intel,
        twitter_intel=twitter_intel,
        validated_home_team=validated_home_team,
        validated_away_team=validated_away_team,
        verification_info=verification_info,
        injury_intel=injury_intel,
        confidence_breakdown=confidence_breakdown,
        is_convergent=is_convergent,
        convergence_sources=convergence_sources
    )


# ============================================
# MAIN ALERT FUNCTION
# ============================================


def send_alert(
    match_obj: Any,
    news_summary: str,
    news_url: str,
    score: int,
    league: str,
    combo_suggestion: Optional[str] = None,
    combo_reasoning: Optional[str] = None,
    recommended_market: Optional[str] = None,
    math_edge: Optional[Dict[str, Any]] = None,
    is_update: bool = False,
    financial_risk: Optional[str] = None,
    intel_source: str = "web",
    referee_intel: Optional[Dict[str, Any]] = None,
    twitter_intel: Optional[Dict[str, Any]] = None,
    validated_home_team: Optional[str] = None,
    validated_away_team: Optional[str] = None,
    verification_info: Optional[Dict[str, Any]] = None,
    injury_intel: Optional[Dict[str, Any]] = None,
    confidence_breakdown: Optional[Dict[str, Any]] = None,
    is_convergent: bool = False,
    convergence_sources: Optional[Dict[str, Any]] = None
) -> None:
    """
    Sends a formatted alert to Telegram with odds movement analysis.

    Args:
        match_obj: Match database object with opening/current odds
        news_summary: News summary text
        news_url: Source URL
        score: Relevance score (0-10)
        league: League name
        combo_suggestion: Direct combo suggestion from NewsLog (optional)
        combo_reasoning: Why this combo was suggested (optional)
        recommended_market: Primary market recommendation (optional)
        math_edge: Dict with 'market', 'edge', 'kelly_stake' from Poisson model (optional)
        is_update: If True, this is an update to a previous alert (score increased)
        financial_risk: B-Team risk level from Financial Intelligence (optional)
        intel_source: Source of intelligence - "web", "telegram", "ocr" (optional)
        referee_intel: Dict with referee stats for cards market (optional)
        twitter_intel: Dict with Twitter insider intel (optional)
        validated_home_team: Corrected home team name if FotMob detected inversion (optional)
        validated_away_team: Corrected away team name if FotMob detected inversion (optional)
        verification_info: Verification Layer result (optional)
        injury_intel: Injury impact analysis (optional)
        confidence_breakdown: Confidence score breakdown (optional)
        is_convergent: V9.5 - True if signal confirmed by both Web and Social sources (optional)
        convergence_sources: V9.5 - Dict with web and social signal details (optional)
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram configuration missing. Skipping alert.")
        return

    # Use validated team names if provided, otherwise fall back to match_obj
    home_team = validated_home_team if validated_home_team else getattr(match_obj, 'home_team', 'Unknown')
    away_team = validated_away_team if validated_away_team else getattr(match_obj, 'away_team', 'Unknown')

    match_str = f"{home_team} vs {away_team}"

    # Calculate odds movement for home team (affected side)
    movement = calculate_odds_movement(
        getattr(match_obj, 'opening_home_odd', None),
        getattr(match_obj, 'current_home_odd', None)
    )

    # Build odds display (ITALIAN)
    odds_line = ""
    current_home_odd = getattr(match_obj, 'current_home_odd', None)
    opening_home_odd = getattr(match_obj, 'opening_home_odd', None)
    if opening_home_odd and current_home_odd:
        odds_line = f"📈 Quote: {opening_home_odd:.2f} → {current_home_odd:.2f}\n"

    # Use direct combo fields if provided, otherwise extract from summary
    if not combo_suggestion or not recommended_market:
        extracted_market, extracted_combo, extracted_reasoning = extract_combo_from_summary(news_summary)
        if not combo_suggestion:
            combo_suggestion = extracted_combo
        if not combo_reasoning:
            combo_reasoning = extracted_reasoning
        if not recommended_market:
            recommended_market = extracted_market

    # Clean AI-generated text to remove redundant link references
    combo_reasoning_clean = _clean_ai_text(combo_reasoning) if combo_reasoning else None
    news_summary_clean = _clean_ai_text(news_summary)

    # Build message sections
    bet_section = _build_bet_section(recommended_market, combo_suggestion, combo_reasoning_clean, math_edge, financial_risk)
    referee_section = _build_referee_section(referee_intel, combo_suggestion, recommended_market)
    twitter_section = _build_twitter_section(twitter_intel)
    injury_section = _build_injury_section(injury_intel, home_team, away_team)
    verification_section = _build_verification_section(verification_info)
    breakdown_section = _build_confidence_breakdown_section(confidence_breakdown)
    date_line = _build_date_line(match_obj)
    convergence_section = _build_convergence_section(is_convergent, convergence_sources)

    # Intel source indicator with enhanced attribution
    source_indicator = ""
    if intel_source and intel_source != "web":
        source_emoji = {"telegram": "💬", "ocr": "🔍"}.get(intel_source, "📰")
        source_indicator = f"{source_emoji} <b>Source:</b> {intel_source.upper()}\n"
    
    # V9.0: Enhanced source attribution with specific details
    # Check for additional source details in twitter_intel or other sources
    enhanced_source_section = ""
    
    if twitter_intel and isinstance(twitter_intel, dict):
        tweets = twitter_intel.get('tweets', [])
        if tweets and len(tweets) > 0:
            # Extract handle from first tweet for attribution
            first_tweet = tweets[0]
            handle = first_tweet.get('handle', '')
            if handle:
                enhanced_source_section = f"🐦 <b>Insider:</b> {html.escape(handle)}\n"
    
    # If no enhanced source info, use the basic source_indicator
    if not enhanced_source_section and source_indicator:
        enhanced_source_section = source_indicator
    elif not enhanced_source_section:
        # Default to web source if no specific source provided
        enhanced_source_section = "📡 <b>Source:</b> Web\n"

    # Header changes based on whether this is an update
    if is_update:
        header = f"🔄 <b>AGGIORNAMENTO</b> (Score Increased) | {league}"
    else:
        header = f"🚨 <b>EARLYBIRD ALERT</b> | {league}"

    # Build news link safely - only if URL is valid, with HTML escape
    news_link = ""
    if news_url and isinstance(news_url, str) and news_url.startswith('http'):
        safe_url = html.escape(news_url)
        news_link = f"\n\n🔗 <a href='{safe_url}'>Leggi la fonte originale</a>"

    # Build the message
    message = (
        f"{header}\n"
        f"{date_line}"
        f"⚽ <b>{match_str}</b>\n"
        f"📊 <b>Punteggio: {score}/10</b>\n"
        f"{odds_line}"
        f"{movement['emoji']} <b>{movement['message']}</b>\n"
        f"{convergence_section}"  # V9.5: Cross-Source Convergence (prominent position)
        f"{enhanced_source_section}"
        f"{bet_section}"
        f"{breakdown_section}"
        f"{injury_section}"
        f"{referee_section}"
        f"{twitter_section}"
        f"{verification_section}\n"
        f"📝 <i>{news_summary_clean}</i>"
        f"{news_link}"
    )

    # Truncate if needed
    message = _truncate_message_if_needed(
        message, header, date_line, match_str, score, odds_line, movement,
        enhanced_source_section, bet_section, breakdown_section, injury_section,
        referee_section, twitter_section, verification_section, news_summary_clean, news_link,
        convergence_section  # V9.5: Include convergence section in truncation
    )

    # Send to Telegram
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = _send_telegram_request(url, payload, timeout=TELEGRAM_TIMEOUT_SECONDS)
        if response.status_code == 200:
            link_status = "con link" if news_link else "senza link"
            logging.info(f"Telegram Alert sent for {match_str} | Movement: {movement['message']} | {link_status}")
        else:
            # HTML parsing failed - fallback to plain text
            _send_plain_text_fallback(url, message, news_url, match_str)
    except requests.exceptions.Timeout:
        logging.error(f"Telegram timeout dopo 3 tentativi")
    except requests.exceptions.ConnectionError as e:
        logging.error(f"Telegram errore connessione: {e}")
    except Exception as e:
        # Fallback to plain text on any exception
        _send_plain_text_fallback(url, message, news_url, match_str, exception=e)


def _send_plain_text_fallback(url: str, message: str, news_url: str, match_str: str, exception: Optional[Exception] = None) -> None:
    """Send a plain text fallback message when HTML fails."""
    if exception:
        logging.warning(f"HTML send exception ({exception}), falling back to plain text")
    else:
        logging.warning(f"HTML send failed, falling back to plain text")

    try:
        plain_msg = message.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
        plain_msg = strip_html_links(plain_msg)
        # Append raw URL so it's clickable in plain text
        if news_url and news_url.startswith('http'):
            plain_msg += f"\n\nLink: {news_url}"
        payload_plain = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": plain_msg,
            "disable_web_page_preview": True
        }
        response_plain = _send_telegram_request(url, payload_plain, timeout=TELEGRAM_TIMEOUT_SECONDS)
        if response_plain.status_code == 200:
            logging.info(f"Telegram Alert sent (plain text fallback) for {match_str}")
        else:
            logging.error(f"Invio alert fallito: {response_plain.text}")
    except Exception as e2:
        logging.error(f"Errore imprevisto invio alert Telegram: {e2}")


# ============================================
# STATUS MESSAGE FUNCTION
# ============================================


def send_status_message(text: str) -> bool:
    """
    Send a status/health message to Telegram (heartbeat, errors, etc.)
    Uses tenacity for intelligent retry on transient errors.

    Args:
        text: HTML-formatted message text

    Returns:
        True if sent successfully, False otherwise
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram configuration missing. Skipping status message.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = _send_telegram_request(url, payload, timeout=TELEGRAM_TIMEOUT_SECONDS)
        if response.status_code == 200:
            logging.info("Status message sent to Telegram")
            return True
        else:
            logging.error(f"Invio messaggio status fallito: {response.text}")
            return False
    except requests.exceptions.Timeout:
        logging.error("Telegram timeout dopo 3 tentativi")
        return False
    except requests.exceptions.ConnectionError as e:
        logging.error(f"Telegram errore connessione: {e}")
        return False
    except Exception as e:
        logging.error(f"Errore imprevisto invio status: {e}")
        return False


# ============================================
# BISCOTTO ALERT FUNCTION
# ============================================


def send_biscotto_alert(
    match_obj: Any,
    draw_odd: Optional[float] = None,
    drop_pct: Optional[float] = None,
    severity: Optional[str] = None,
    reasoning: Optional[str] = None,
    news_url: Optional[str] = None,
    league: Optional[str] = None,
    financial_risk: Optional[str] = None
) -> None:
    """
    Send a specialized alert for Biscotto (mutual draw benefit) detection.

    Args:
        match_obj: Match database object with team info and odds
        draw_odd: Draw odd value (from is_biscotto_suspect)
        drop_pct: Drop percentage (from is_biscotto_suspect)
        severity: Severity level: 'LOW', 'MEDIUM', 'HIGH', 'EXTREME' (from is_biscotto_suspect)
        reasoning: Reason for biscotto suspicion (from is_biscotto_suspect)
        news_url: Source URL for the news (optional)
        league: League name (optional)
        financial_risk: B-Team risk level from Financial Intelligence (optional)
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram configuration missing. Skipping biscotto alert.")
        return

    home_team = getattr(match_obj, 'home_team', 'Unknown')
    away_team = getattr(match_obj, 'away_team', 'Unknown')
    match_str = f"{home_team} vs {away_team}"

    # Use league from match_obj if not provided
    if not league:
        league = getattr(match_obj, 'league', 'Unknown')

    # Normalize severity (handle EXTREME from is_biscotto_suspect)
    severity_normalized = (severity or 'LOW').upper()
    if severity_normalized == 'EXTREME':
        severity_normalized = 'CRITICAL'

    # Build severity section with reasoning
    severity_emoji = {
        'LOW': '🟢',
        'MEDIUM': '🟡',
        'HIGH': '🟠',
        'CRITICAL': '🔴'
    }.get(severity_normalized, '⚪')

    # Build odds section
    odds_section = ""
    if draw_odd:
        odds_section = f"   📊 <b>Draw Odds:</b> {draw_odd:.2f}\n"
    if drop_pct is not None:
        odds_section += f"   📉 <b>Drop:</b> {drop_pct:.1f}%\n"

    # Build reasoning section
    reasoning_section = ""
    if reasoning:
        reasoning_section = f"   💡 <b>Motivo:</b> {html.escape(reasoning)}\n"

    # Build financial risk section (B-Team Detection)
    risk_section = ""
    if financial_risk and financial_risk.upper() in ['CRITICAL', 'WARNING']:
        risk_emoji = "🚨" if financial_risk.upper() == "CRITICAL" else "⚠️"
        risk_label = "B-TEAM CONFERMATO" if financial_risk.upper() == "CRITICAL" else "ROTAZIONE PROBABILE"
        risk_section = f"{risk_emoji} <b>ALLARME ROSA:</b> {risk_label}\n"

    # Build date/time line
    date_line = _build_date_line(match_obj)

    # Build news link safely - only if URL is valid, with HTML escape
    news_link = ""
    if news_url and isinstance(news_url, str) and news_url.startswith('http'):
        safe_url = html.escape(news_url)
        news_link = f"\n\n🔗 <a href='{safe_url}'>Leggi la fonte originale</a>"

    # Build the message
    message = (
        f"🍪 <b>BISCOTTO ALERT</b> | {league}\n"
        f"{date_line}"
        f"⚽ <b>{match_str}</b>\n"
        f"{severity_emoji} <b>Severità:</b> {severity_normalized}\n"
        f"\n"
        f"{odds_section}"
        f"{reasoning_section}"
        f"{risk_section}"
        f"{news_link}"
    )

    # Send to Telegram
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = _send_telegram_request(url, payload, timeout=TELEGRAM_TIMEOUT_SECONDS)
        if response.status_code == 200:
            link_status = "con link" if news_link else "senza link"
            logging.info(f"Biscotto Alert sent for {match_str} | Severity: {severity} | {link_status}")
        else:
            # HTML parsing failed - fallback to plain text
            _send_plain_text_fallback(url, message, news_url, match_str)
    except requests.exceptions.Timeout:
        logging.error(f"Telegram timeout per biscotto alert dopo 3 tentativi")
    except requests.exceptions.ConnectionError as e:
        logging.error(f"Telegram errore connessione (biscotto): {e}")
    except Exception as e:
        # Fallback to plain text on any exception
        _send_plain_text_fallback(url, message, news_url, match_str, exception=e)


# ============================================
# DOCUMENT SEND FUNCTION
# ============================================


def send_document(file_path: str, caption: str = "") -> bool:
    """
    Send a document (file) to Telegram.

    Args:
        file_path: Path to the file to send
        caption: Optional caption for the document (HTML supported)

    Returns:
        True if sent successfully, False otherwise
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram configuration missing. Skipping document send.")
        return False

    path = Path(file_path)
    if not path.exists():
        logging.error(f"File not found: {file_path}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"

    try:
        with open(path, 'rb') as doc:
            files = {'document': doc}
            data = {
                'chat_id': TELEGRAM_CHAT_ID,
                'caption': caption,
                'parse_mode': 'HTML'
            }

            response = requests.post(url, files=files, data=data, timeout=TELEGRAM_DOCUMENT_TIMEOUT)

            if response.status_code == 200:
                logging.info(f"Document sent: {path.name}")
                return True
            else:
                logging.error(f"Failed to send document: {response.text}")
                return False

    except Exception as e:
        logging.error(f"Error sending document: {e}")
        return False
