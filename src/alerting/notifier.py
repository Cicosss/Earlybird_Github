import os
import time
import html
import requests
import requests.exceptions
import logging
import pytz
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Verify credentials are loaded securely
if TELEGRAM_TOKEN:
    logging.debug("✅ Telegram token caricato da variabile ambiente")
if TELEGRAM_CHAT_ID:
    logging.debug("✅ Telegram chat ID caricato da variabile ambiente")


# ============================================
# TEXT CLEANING HELPER
# ============================================
def strip_html_links(text: str) -> str:
    """
    Remove HTML anchor tags from text, keeping only the link text.
    
    Args:
        text: Text potentially containing HTML links
        
    Returns:
        Text with <a href='...'>text</a> replaced by just 'text'
    """
    import re
    return re.sub(r"<a href='[^']*'>([^<]*)</a>", r'\1', text)


def _clean_ai_text(text: str) -> str:
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
    
    # 1. HTML escape for security (prevent injection)
    cleaned = html.escape(text)
    
    # 2. Remove common AI-generated link phrases (Italian + English)
    import re
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
    
    # 3. Strip trailing/leading whitespace and normalize multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


# ============================================
# TENACITY RETRY WRAPPER FOR TELEGRAM API
# ============================================
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError))
)
def _send_telegram_request(url: str, payload: dict, timeout: int = 30) -> requests.Response:
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
        logging.warning(f"⚠️ Telegram rate limit (429), attesa {retry_after}s...")
        time.sleep(retry_after)
        raise requests.exceptions.ConnectionError("Rate limited - triggering retry")
    
    # Handle server errors (5xx) - trigger retry
    if response.status_code >= 500:
        logging.warning(f"⚠️ Telegram server error ({response.status_code}), triggering retry...")
        raise requests.exceptions.ConnectionError(f"Server error {response.status_code}")
    
    return response

def calculate_odds_movement(opening_odd: Optional[float], current_odd: Optional[float]) -> dict:
    """
    Calculate odds drop percentage and determine market reaction.
    Returns dict with: drop_percent, emoji, message (in Italian)
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

def extract_combo_from_summary(news_summary: str) -> tuple:
    """
    Extract combo suggestion and reasoning from news summary.
    
    Returns:
        Tuple of (primary_market, combo_suggestion, combo_reasoning)
    """
    import re
    
    primary_market = None
    combo_suggestion = None
    combo_reasoning = None
    
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


def send_alert(
    match_obj, 
    news_summary: str, 
    news_url: str, 
    score: int, 
    league: str,
    combo_suggestion: str = None,
    combo_reasoning: str = None,
    recommended_market: str = None,
    math_edge: dict = None,
    is_update: bool = False,
    financial_risk: str = None,
    intel_source: str = "web",
    referee_intel: dict = None,
    twitter_intel: dict = None,
    validated_home_team: str = None,
    validated_away_team: str = None,
    verification_info: dict = None,
    injury_intel: dict = None,
    confidence_breakdown: dict = None
):
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
            - referee_name: Name of the referee
            - referee_cards_avg: Average cards per game
            - referee_strictness: Strict/Medium/Lenient
            - home_cards_avg: Home team avg cards
            - away_cards_avg: Away team avg cards
            - cards_reasoning: Why cards bet was suggested
        twitter_intel: Dict with Twitter insider intel (optional)
            - tweets: List of relevant tweets with handle, content, topics
            - cache_age_minutes: Age of the cache in minutes
        validated_home_team: V5.1 - Corrected home team name if FotMob detected inversion (optional)
        validated_away_team: V5.1 - Corrected away team name if FotMob detected inversion (optional)
        verification_info: V7.0 - Verification Layer result (optional)
            - status: confirm/reject/change_market
            - confidence: HIGH/MEDIUM/LOW
            - reasoning: Italian explanation of verification result
            - inconsistencies_count: Number of detected inconsistencies
        injury_intel: V7.7 - Injury impact analysis (optional)
            - home_severity: LOW/MEDIUM/HIGH/CRITICAL
            - away_severity: LOW/MEDIUM/HIGH/CRITICAL
            - home_missing_starters: Number of starters missing
            - away_missing_starters: Number of starters missing
            - home_key_players: List of key players out
            - away_key_players: List of key players out
            - differential: Score adjustment value
            - favors: 'home' or 'away' or 'neutral'
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram configuration missing. Skipping alert.")
        return

    # V5.1: Use validated team names if provided, otherwise fall back to match_obj
    home_team = validated_home_team if validated_home_team else match_obj.home_team
    away_team = validated_away_team if validated_away_team else match_obj.away_team

    match_str = f"{home_team} vs {away_team}"
    
    # Calculate odds movement for home team (affected side)
    movement = calculate_odds_movement(
        match_obj.opening_home_odd, 
        match_obj.current_home_odd
    )
    
    # Build odds display (ITALIAN)
    odds_line = ""
    if match_obj.opening_home_odd and match_obj.current_home_odd:
        odds_line = f"📈 Quote: {match_obj.opening_home_odd:.2f} → {match_obj.current_home_odd:.2f}\n"
    
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
    
    # Build bet suggestion section (ITALIAN)
    bet_section = ""
    if recommended_market and recommended_market != 'NONE':
        bet_section = f"🎯 <b>Mercato Consigliato:</b> {html.escape(recommended_market)}\n"
    
    # Always show combo status for visibility
    if combo_suggestion and combo_suggestion != 'None':
        bet_section += f"🧩 <b>COMBO SMART:</b> {html.escape(combo_suggestion)}\n"
        if combo_reasoning_clean and 'insufficien' not in combo_reasoning_clean.lower():
            bet_section += f"   <i>({combo_reasoning_clean})</i>\n"
    elif combo_reasoning_clean:
        # Discrete footer for negative result - show why combo was skipped
        bet_section += f"<i>ℹ️ Combo: {combo_reasoning_clean}</i>\n"
    
    # Math Edge section (Poisson model value detection) - ITALIAN
    # V7.6: Enhanced with dynamic labels explaining Edge and Kelly values
    if math_edge and math_edge.get('edge', 0) > 5:
        edge_pct = math_edge.get('edge', 0)
        kelly = math_edge.get('kelly_stake', 0)
        market = math_edge.get('market', 'Unknown')
        
        # Edge label dinamica con spiegazione
        # NOTA: Threshold è > 5%, quindi logica semplificata per coerenza
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
    
    # Financial Risk section (B-Team Detection) - ITALIAN
    if financial_risk and financial_risk.upper() in ['CRITICAL', 'WARNING']:
        risk_emoji = "🚨" if financial_risk.upper() == "CRITICAL" else "⚠️"
        risk_label = "B-TEAM CONFERMATO" if financial_risk.upper() == "CRITICAL" else "ROTAZIONE PROBABILE"
        bet_section += f"{risk_emoji} <b>ALLARME ROSA:</b> {risk_label}\n"
    
    # V4.4.1: Referee Intelligence section (for cards market transparency)
    # Shows referee stats when a cards bet is suggested
    referee_section = ""
    if referee_intel and isinstance(referee_intel, dict):
        # Check if this is a cards-related suggestion
        combo_lower = (combo_suggestion or '').lower()
        market_lower = (recommended_market or '').lower()
        is_cards_bet = 'card' in combo_lower or 'card' in market_lower
        
        if is_cards_bet:
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

    # V4.5: Twitter Intel section (insider tweets)
    twitter_section = ""
    if twitter_intel and isinstance(twitter_intel, dict):
        tweets = twitter_intel.get('tweets', [])
        if tweets:
            twitter_section = "🐦 <b>INSIDER INTEL:</b>\n"
            for tweet in tweets[:2]:  # Max 2 tweets to keep message compact
                handle = tweet.get('handle', '')
                content = tweet.get('content', '')[:100]  # Truncate
                topics = tweet.get('topics', [])
                topic_str = f" [{', '.join(topics)}]" if topics else ""
                twitter_section += f"   • {html.escape(handle)}: <i>{html.escape(content)}...</i>{topic_str}\n"

    # V7.7: Injury Intel section (quality of missing players)
    injury_section = ""
    if injury_intel and isinstance(injury_intel, dict):
        home_severity = injury_intel.get('home_severity', 'LOW')
        away_severity = injury_intel.get('away_severity', 'LOW')
        home_starters = injury_intel.get('home_missing_starters', 0)
        away_starters = injury_intel.get('away_missing_starters', 0)
        home_key = injury_intel.get('home_key_players', [])
        away_key = injury_intel.get('away_key_players', [])
        favors = injury_intel.get('favors', 'neutral')
        
        # Only show if there's meaningful injury data
        # V7.7: Also show when severity is HIGH or CRITICAL even without starter counts
        has_significant_home = home_starters > 0 or home_key or home_severity in ('HIGH', 'CRITICAL')
        has_significant_away = away_starters > 0 or away_key or away_severity in ('HIGH', 'CRITICAL')
        
        if has_significant_home or has_significant_away:
            injury_section = "🏥 <b>ASSENZE:</b>\n"
            
            # Home team injuries
            if has_significant_home:
                severity_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(home_severity, "⚪")
                injury_section += f"   🏠 {home_team}: {severity_emoji} {home_severity}"
                if home_starters > 0:
                    injury_section += f" ({home_starters} titolari)"
                if home_key:
                    key_names = ', '.join(home_key[:2])  # Max 2 names
                    injury_section += f" - ⭐{html.escape(key_names)}"
                injury_section += "\n"
            
            # Away team injuries
            if has_significant_away:
                severity_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(away_severity, "⚪")
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

    # V7.0: Verification Layer section
    verification_section = ""
    if verification_info and isinstance(verification_info, dict):
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

    # V8.1: Confidence breakdown section (transparency)
    breakdown_section = ""
    if confidence_breakdown and isinstance(confidence_breakdown, dict):
        news_w = confidence_breakdown.get('news_weight', 0)
        odds_w = confidence_breakdown.get('odds_weight', 0)
        form_w = confidence_breakdown.get('form_weight', 0)
        injuries_w = confidence_breakdown.get('injuries_weight', 0)
        
        # Only show if we have meaningful breakdown
        if news_w or odds_w or form_w or injuries_w:
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

    # Intel source indicator
    source_indicator = ""
    if intel_source and intel_source != "web":
        source_emoji = {"telegram": "📡", "ocr": "🔍"}.get(intel_source, "📰")
        source_indicator = f"{source_emoji} Fonte: {intel_source.upper()}\n"

    # Header changes based on whether this is an update
    if is_update:
        header = f"🔄 <b>AGGIORNAMENTO</b> (Score Increased) | {league}"
    else:
        header = f"🚨 <b>EARLYBIRD ALERT</b> | {league}"
    
    # Clean news_summary using the robust helper function
    news_summary_clean = _clean_ai_text(news_summary)
    
    # Build news link safely - only if URL is valid, with HTML escape
    news_link = ""
    if news_url and isinstance(news_url, str) and news_url.startswith('http'):
        safe_url = html.escape(news_url)
        news_link = f"\n\n🔗 <a href='{safe_url}'>Leggi la fonte originale</a>"
    
    # Build date/time line if available (converted to Europe/Rome)
    date_line = ""
    if hasattr(match_obj, 'start_time') and match_obj.start_time:
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
    
    message = (
        f"{header}\n"
        f"{date_line}"
        f"⚽ <b>{match_str}</b>\n"
        f"📊 <b>Punteggio: {score}/10</b>\n"
        f"{odds_line}"
        f"{movement['emoji']} <b>{movement['message']}</b>\n"
        f"{source_indicator}"
        f"{bet_section}"
        f"{breakdown_section}"
        f"{injury_section}"
        f"{referee_section}"
        f"{twitter_section}"
        f"{verification_section}\n"
        f"📝 <i>{news_summary_clean}</i>"
        f"{news_link}"
    )

    # Telegram message limit is 4096 chars - truncate if needed
    if len(message) > 4000:
        # Truncate news_summary to fit, keeping structure intact
        overflow = len(message) - 3900  # Leave margin for truncation notice
        if len(news_summary_clean) > overflow + 100:
            news_summary_truncated = news_summary_clean[:-(overflow + 50)] + "... [TRONCATO]"
            message = (
                f"{header}\n"
                f"{date_line}"
                f"⚽ <b>{match_str}</b>\n"
                f"📊 <b>Punteggio: {score}/10</b>\n"
                f"{odds_line}"
                f"{movement['emoji']} <b>{movement['message']}</b>\n"
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

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = _send_telegram_request(url, payload, timeout=30)
        if response.status_code == 200:
            link_status = "con link" if news_link else "senza link"
            logging.info(f"Telegram Alert sent for {match_str} | Movement: {movement['message']} | {link_status}")
        else:
            # HTML parsing failed - fallback to plain text
            logging.warning(f"⚠️ HTML send failed ({response.status_code}), falling back to plain text")
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
            response_plain = _send_telegram_request(url, payload_plain, timeout=30)
            if response_plain.status_code == 200:
                logging.info(f"Telegram Alert sent (plain text) for {match_str}")
            else:
                logging.error(f"❌ Invio alert Telegram fallito anche in plain text: {response_plain.text}")
    except requests.exceptions.Timeout:
        logging.error(f"⚠️ Telegram timeout dopo 3 tentativi")
    except requests.exceptions.ConnectionError as e:
        logging.error(f"❌ Telegram errore connessione: {e}")
    except Exception as e:
        # Fallback to plain text on any exception
        logging.warning(f"⚠️ HTML send exception ({e}), falling back to plain text")
        try:
            plain_msg = message.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
            plain_msg = strip_html_links(plain_msg)
            if news_url and news_url.startswith('http'):
                plain_msg += f"\n\nLink: {news_url}"
            payload_plain = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": plain_msg,
                "disable_web_page_preview": True
            }
            response_plain = _send_telegram_request(url, payload_plain, timeout=30)
            if response_plain.status_code == 200:
                logging.info(f"Telegram Alert sent (plain text fallback) for {match_str}")
            else:
                logging.error(f"❌ Invio alert fallito: {response_plain.text}")
        except Exception as e2:
            logging.error(f"❌ Errore imprevisto invio alert Telegram: {e2}")


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
        response = _send_telegram_request(url, payload, timeout=30)
        if response.status_code == 200:
            logging.info("📤 Status message sent to Telegram")
            return True
        else:
            logging.error(f"❌ Invio messaggio status fallito: {response.text}")
            return False
    except requests.exceptions.Timeout:
        logging.error("⚠️ Telegram timeout dopo 3 tentativi")
        return False
    except requests.exceptions.ConnectionError as e:
        logging.error(f"❌ Telegram errore connessione: {e}")
        return False
    except Exception as e:
        logging.error(f"❌ Errore imprevisto invio status: {e}")
        return False


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
    
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    
    try:
        with open(file_path, 'rb') as doc:
            files = {'document': doc}
            data = {
                'chat_id': TELEGRAM_CHAT_ID,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, files=files, data=data, timeout=60)
            
            if response.status_code == 200:
                logging.info(f"📄 Document sent: {os.path.basename(file_path)}")
                return True
            else:
                logging.error(f"Failed to send document: {response.text}")
                return False
                
    except Exception as e:
        logging.error(f"Error sending document: {e}")
        return False


def send_biscotto_alert(
    match_obj,
    draw_odd: float,
    drop_pct: float,
    severity: str,
    reasoning: str,
    ai_analysis: dict = None
):
    """
    🍪 BISCOTTO ALERT: Special alert for suspicious Draw odds.
    
    Args:
        match_obj: Match database object
        draw_odd: Current draw odds
        drop_pct: Percentage drop from opening
        severity: EXTREME, HIGH, or MEDIUM
        reasoning: Explanation of why it's suspicious
        ai_analysis: Optional Gemini analysis results
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram configuration missing. Skipping biscotto alert.")
        return

    match_str = f"{match_obj.home_team} vs {match_obj.away_team}"
    
    # Severity emoji
    severity_emoji = {
        'EXTREME': '🔴',
        'HIGH': '🟠',
        'MEDIUM': '🟡'
    }.get(severity, '⚪')
    
    # Build opening odds display
    opening_draw = match_obj.opening_draw_odd
    odds_change = ""
    if opening_draw:
        odds_change = f" (era {opening_draw:.2f})"
    
    # AI analysis section
    ai_section = ""
    if ai_analysis:
        if ai_analysis.get('is_biscotto'):
            ai_section = (
                f"\n\n🤖 <b>AI CONFERMA:</b>\n"
                f"📊 Fiducia: {ai_analysis.get('confidence', 0)}%\n"
                f"📝 {ai_analysis.get('reasoning', 'N/A')}"
            )
        else:
            ai_section = f"\n\n🤖 AI: Non confermato (fiducia: {ai_analysis.get('confidence', 0)}%)"
    
    message = (
        f"🍪 <b>BISCOTTO RILEVATO</b> {severity_emoji}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚽ <b>{match_str}</b>\n"
        f"🏆 {match_obj.league}\n\n"
        f"📉 <b>Quota X:</b> {draw_odd:.2f}{odds_change}\n"
        f"📊 <b>Drop:</b> {drop_pct:.1f}%\n"
        f"⚠️ <b>Gravità:</b> {severity}\n\n"
        f"📝 <i>{reasoning}</i>"
        f"{ai_section}\n\n"
        f"💡 <b>Suggerimento:</b> Valuta scommessa su X (Pareggio)"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = _send_telegram_request(url, payload, timeout=30)
        if response.status_code == 200:
            logging.info(f"🍪 Biscotto Alert sent for {match_str} | Draw: {draw_odd} | Severity: {severity}")
        else:
            logging.error(f"❌ Invio alert Biscotto fallito: {response.text}")
    except requests.exceptions.Timeout:
        logging.error("⚠️ Telegram timeout dopo 3 tentativi")
    except requests.exceptions.ConnectionError as e:
        logging.error(f"❌ Telegram errore connessione: {e}")
    except Exception as e:
        logging.error(f"❌ Errore imprevisto invio alert Biscotto: {e}")
