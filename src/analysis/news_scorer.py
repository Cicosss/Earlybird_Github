"""
News Importance Scorer - V8.1

Pre-processes news items to calculate importance score BEFORE sending to DeepSeek.
This provides transparency into how much weight the news carries in the final decision.

Scoring Factors:
1. SOURCE CREDIBILITY (0-3 points): Based on SOURCE_TIERS database
2. CONTENT KEYWORDS (0-4 points): Injury, lineup, transfer keywords
3. FRESHNESS (0-2 points): How recent is the news
4. SPECIFICITY (0-1 point): Does it mention specific player names

Total: 0-10 points

Usage:
    from src.analysis.news_scorer import score_news_item, score_news_batch
    
    result = score_news_item(news_item)
    # Returns: NewsScore with raw_score, tier, breakdown, and driver
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from src.processing.sources_config import get_trust_score, SourceTier, DEFAULT_SOURCE_TIER

logger = logging.getLogger(__name__)


# ============================================
# KEYWORD PATTERNS FOR CONTENT SCORING
# ============================================

# High-impact keywords (injury confirmed, ruled out)
HIGH_IMPACT_KEYWORDS = [
    # English
    r'\b(ruled out|confirmed out|will miss|sidelined|injured|unavailable)\b',
    r'\b(starting xi|starting lineup|confirmed lineup)\b',
    r'\b(out for|absent|suspended|banned)\b',
    # Italian
    r'\b(infortunato|salta|assente|out|escluso)\b',
    # Spanish
    r'\b(lesionado|baja confirmada|descartado|ausente)\b',
    # Turkish
    r'\b(sakatlık|kadro dışı|forma giyemeyecek)\b',
    # Greek
    r'\b(τραυματίας|απών|εκτός)\b',
]

# Medium-impact keywords (potential issues)
MEDIUM_IMPACT_KEYWORDS = [
    r'\b(doubt|doubtful|fitness test|race against time)\b',
    r'\b(knock|minor injury|precaution|rested)\b',
    r'\b(squad|team news|lineup|convocados)\b',
    # Transfer-related
    r'\b(transfer|signing|loan|deal)\b',
]

# Low-impact keywords (general news)
LOW_IMPACT_KEYWORDS = [
    r'\b(training|practice|press conference)\b',
    r'\b(interview|quotes|comments)\b',
]


@dataclass
class NewsScore:
    """Result of news importance scoring."""
    raw_score: float          # 0-10 total score
    tier: str                 # "HIGH", "MEDIUM", "LOW"
    source_tier: int          # 1, 2, or 3
    source_weight: float      # 0.0-1.0
    source_type: str          # "official", "newspaper", etc.
    
    # Score breakdown
    source_points: float      # 0-3 from source credibility
    content_points: float     # 0-4 from keyword analysis
    freshness_points: float   # 0-2 from recency
    specificity_points: float # 0-1 from player mentions
    
    # Analysis metadata
    primary_driver: str       # Main reason for high/low score
    detected_keywords: List[str] = field(default_factory=list)
    players_mentioned: List[str] = field(default_factory=list)
    news_age_hours: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "raw_score": round(self.raw_score, 2),
            "tier": self.tier,
            "source_tier": self.source_tier,
            "source_weight": self.source_weight,
            "source_type": self.source_type,
            "breakdown": {
                "source": round(self.source_points, 2),
                "content": round(self.content_points, 2),
                "freshness": round(self.freshness_points, 2),
                "specificity": round(self.specificity_points, 2),
            },
            "primary_driver": self.primary_driver,
            "detected_keywords": self.detected_keywords[:5],  # Limit to 5
            "players_mentioned": self.players_mentioned[:3],  # Limit to 3
        }


def _score_source(url: str) -> tuple[float, SourceTier]:
    """
    Score the news source credibility (0-3 points).
    
    TIER 1 sources (in Supabase white-list): 3 points
    TIER 3 sources (not in white-list): 1 point
    
    Note: TIER 2 has been eliminated - sources are either in white-list (Tier 1)
    or not (Tier 3). This is the "Zero-Maintenance Credibility Strategy".
    """
    tier_info = get_trust_score(url)
    
    if tier_info.tier == 1:
        return 3.0, tier_info
    else:
        return 1.0, tier_info


def _score_content(text: str) -> tuple[float, List[str]]:
    """
    Score the news content based on keyword analysis (0-4 points).
    
    High-impact keywords: +2 points each (max 4)
    Medium-impact keywords: +1 point each (max 2)
    """
    if not text:
        return 0.0, []
    
    text_lower = text.lower()
    detected = []
    score = 0.0
    
    # Check high-impact keywords
    for pattern in HIGH_IMPACT_KEYWORDS:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        if matches:
            detected.extend(matches)
            score += 2.0
            if score >= 4.0:
                break
    
    # If not maxed, check medium-impact keywords
    if score < 4.0:
        for pattern in MEDIUM_IMPACT_KEYWORDS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            if matches:
                detected.extend(matches)
                score += 1.0
                if score >= 4.0:
                    break
    
    return min(4.0, score), detected


def _score_freshness(date_str: str) -> tuple[float, Optional[float]]:
    """
    Score the news freshness (0-2 points).
    
    < 2 hours old: 2 points
    < 12 hours old: 1 point
    > 12 hours old: 0 points
    """
    if not date_str:
        return 0.5, None  # Unknown freshness, give benefit of doubt
    
    try:
        # Try to parse common date formats
        now = datetime.now(timezone.utc)
        
        # Handle relative dates like "2 hours ago"
        if 'hour' in date_str.lower():
            match = re.search(r'(\d+)\s*hour', date_str.lower())
            if match:
                hours = int(match.group(1))
                if hours < 2:
                    return 2.0, float(hours)
                elif hours < 12:
                    return 1.0, float(hours)
                else:
                    return 0.0, float(hours)
        
        if 'minute' in date_str.lower() or 'min' in date_str.lower():
            return 2.0, 0.5  # Very fresh
        
        if 'day' in date_str.lower():
            match = re.search(r'(\d+)\s*day', date_str.lower())
            if match:
                days = int(match.group(1))
                return 0.0, float(days * 24)
        
        # Try ISO format parsing
        for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
            try:
                news_date = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                hours_old = (now - news_date).total_seconds() / 3600
                
                if hours_old < 2:
                    return 2.0, hours_old
                elif hours_old < 12:
                    return 1.0, hours_old
                else:
                    return 0.0, hours_old
            except ValueError:
                continue
        
        return 0.5, None  # Unknown format
        
    except Exception:
        return 0.5, None


def _score_specificity(text: str) -> tuple[float, List[str]]:
    """
    Score specificity based on player name mentions (0-1 point).
    
    Specific player names increase relevance.
    """
    if not text:
        return 0.0, []
    
    # Simple heuristic: look for capitalized words that could be names
    # More sophisticated: use a player database
    
    # Pattern for potential player names (Capitalized words, 2-20 chars)
    name_pattern = r'\b([A-Z][a-z]{1,15}(?:\s+[A-Z][a-z]{1,15})?)\b'
    
    # Exclude common non-name words
    exclude_words = {
        'The', 'This', 'That', 'Monday', 'Tuesday', 'Wednesday', 'Thursday',
        'Friday', 'Saturday', 'Sunday', 'January', 'February', 'March', 'April',
        'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December',
        'Premier', 'League', 'Champions', 'Europa', 'Serie', 'Bundesliga', 'LaLiga',
        'Manchester', 'Liverpool', 'Arsenal', 'Chelsea', 'Barcelona', 'Madrid',
    }
    
    matches = re.findall(name_pattern, text)
    players = [m for m in matches if m not in exclude_words and len(m) > 3]
    
    # Deduplicate
    players = list(set(players))
    
    if players:
        return 1.0, players[:5]
    
    return 0.0, []


def _determine_tier(score: float) -> str:
    """Determine tier label from raw score."""
    if score >= 7.0:
        return "HIGH"
    elif score >= 4.0:
        return "MEDIUM"
    else:
        return "LOW"


def _determine_primary_driver(
    source_points: float,
    content_points: float,
    freshness_points: float,
    specificity_points: float,
    source_type: str
) -> str:
    """Determine the primary driver of the score."""
    drivers = [
        (source_points, f"Source credibility ({source_type})"),
        (content_points, "Content keywords"),
        (freshness_points, "News freshness"),
        (specificity_points, "Player specificity"),
    ]
    
    # Sort by points, highest first
    drivers.sort(key=lambda x: x[0], reverse=True)
    
    return drivers[0][1]


def score_news_item(news_item: Dict[str, Any]) -> NewsScore:
    """
    Calculate importance score for a single news item.
    
    Args:
        news_item: Dict with keys like 'link', 'snippet', 'title', 'date'
        
    Returns:
        NewsScore with full breakdown
    """
    url = news_item.get('link', '') or news_item.get('url', '')
    text = f"{news_item.get('title', '')} {news_item.get('snippet', '')}"
    date_str = news_item.get('date', '')
    
    # Score each factor
    source_points, source_info = _score_source(url)
    content_points, detected_keywords = _score_content(text)
    freshness_points, news_age_hours = _score_freshness(date_str)
    specificity_points, players = _score_specificity(text)
    
    # Calculate total
    raw_score = source_points + content_points + freshness_points + specificity_points
    
    # Determine tier and driver
    tier = _determine_tier(raw_score)
    primary_driver = _determine_primary_driver(
        source_points, content_points, freshness_points, 
        specificity_points, source_info.source_type
    )
    
    return NewsScore(
        raw_score=raw_score,
        tier=tier,
        source_tier=source_info.tier,
        source_weight=source_info.weight,
        source_type=source_info.source_type,
        source_points=source_points,
        content_points=content_points,
        freshness_points=freshness_points,
        specificity_points=specificity_points,
        primary_driver=primary_driver,
        detected_keywords=detected_keywords,
        players_mentioned=players,
        news_age_hours=news_age_hours,
    )


def score_news_batch(news_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Score a batch of news items and return aggregate statistics.
    
    Args:
        news_items: List of news item dicts
        
    Returns:
        Dict with:
        - items: List of scored items
        - aggregate: Aggregate stats (avg_score, max_score, best_source)
        - top_item: The highest-scoring news item
    """
    if not news_items:
        return {
            "items": [],
            "aggregate": {
                "avg_score": 0.0,
                "max_score": 0.0,
                "total_items": 0,
                "high_tier_count": 0,
            },
            "top_item": None,
        }
    
    scored_items = []
    for item in news_items:
        score = score_news_item(item)
        scored_items.append({
            "original": item,
            "score": score,
        })
    
    # Sort by score descending
    scored_items.sort(key=lambda x: x["score"].raw_score, reverse=True)
    
    # Calculate aggregates
    scores = [x["score"].raw_score for x in scored_items]
    high_tier = [x for x in scored_items if x["score"].tier == "HIGH"]
    
    top_item = scored_items[0] if scored_items else None
    
    return {
        "items": scored_items,
        "aggregate": {
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
            "total_items": len(scored_items),
            "high_tier_count": len(high_tier),
        },
        "top_item": top_item,
    }


def format_news_score_for_prompt(news_score: NewsScore) -> str:
    """
    Format news score for inclusion in DeepSeek prompt.
    
    This gives DeepSeek explicit information about news credibility.
    """
    return (
        f"[NEWS CREDIBILITY: {news_score.tier}]\n"
        f"- Source: TIER {news_score.source_tier} ({news_score.source_type}) - weight {news_score.source_weight:.0%}\n"
        f"- Score: {news_score.raw_score:.1f}/10 ({news_score.primary_driver})\n"
        f"- Keywords detected: {', '.join(news_score.detected_keywords[:3]) if news_score.detected_keywords else 'None'}"
    )


def format_batch_score_for_prompt(batch_result: Dict[str, Any]) -> str:
    """
    Format batch news score for inclusion in DeepSeek prompt.
    """
    agg = batch_result["aggregate"]
    top = batch_result.get("top_item")
    
    lines = [
        f"[NEWS INTELLIGENCE SUMMARY]",
        f"- Total sources: {agg['total_items']}",
        f"- Average credibility: {agg['avg_score']:.1f}/10",
        f"- High-tier sources: {agg['high_tier_count']}",
    ]
    
    if top:
        score = top["score"]
        lines.append(f"- Best source: TIER {score.source_tier} ({score.source_type}) - {score.raw_score:.1f}/10")
        if score.detected_keywords:
            lines.append(f"- Key signals: {', '.join(score.detected_keywords[:3])}")
    
    return "\n".join(lines)


# ============================================
# CLI for testing
# ============================================
if __name__ == "__main__":
    # Test with sample news items
    test_items = [
        {
            "title": "Messi ruled out of El Clasico due to injury",
            "snippet": "Lionel Messi will miss Saturday's clash after sustaining a hamstring injury in training",
            "link": "https://www.bbc.com/sport/football/12345",
            "date": "2 hours ago",
        },
        {
            "title": "Transfer news roundup",
            "snippet": "Latest transfer rumors from around Europe",
            "link": "https://www.calciomercato.com/news/123",
            "date": "1 day ago",
        },
        {
            "title": "Coach confirms starting lineup",
            "snippet": "Manager reveals who will start in tomorrow's match",
            "link": "https://www.gazzetta.it/calcio/123",
            "date": "30 minutes ago",
        },
    ]
    
    print("=" * 60)
    print("📰 NEWS SCORER TEST")
    print("=" * 60)
    
    for item in test_items:
        score = score_news_item(item)
        print(f"\n📰 {item['title'][:50]}...")
        print(f"   Source: {item['link']}")
        print(f"   Score: {score.raw_score:.1f}/10 ({score.tier})")
        print(f"   Breakdown: source={score.source_points}, content={score.content_points}, "
              f"fresh={score.freshness_points}, specificity={score.specificity_points}")
        print(f"   Driver: {score.primary_driver}")
        print(f"   Keywords: {score.detected_keywords}")
    
    print("\n" + "=" * 60)
    print("📊 BATCH ANALYSIS")
    print("=" * 60)
    
    batch = score_news_batch(test_items)
    print(format_batch_score_for_prompt(batch))
