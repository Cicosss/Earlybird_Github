"""
EarlyBird Stats Dashboard Generator

Creates visual statistics dashboard for Telegram /stat command.
Uses matplotlib to generate a professional-looking stats image.
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Output path for generated images
STATS_IMAGE_PATH = "temp/stats_dashboard.png"
OPTIMIZER_WEIGHTS_FILE = "data/optimizer_weights.json"

# Color scheme (Dark theme)
COLORS = {
    'background': '#0f172a',      # Deep blue/black
    'card_bg': '#1e293b',         # Slate gray
    'text_primary': '#f8fafc',    # White
    'text_secondary': '#94a3b8',  # Gray
    'accent_green': '#22c55e',    # Green (profit)
    'accent_red': '#ef4444',      # Red (loss)
    'accent_blue': '#3b82f6',     # Blue (neutral)
    'accent_yellow': '#eab308',   # Yellow (warning)
    'border': '#334155',          # Border gray
}


def get_stats_data() -> Dict:
    """
    Extract performance statistics from optimizer data and database.
    
    Returns:
        Dict with all computed metrics
    """
    stats = {
        'total_bets': 0,
        'wins': 0,
        'losses': 0,
        'profit': 0.0,
        'roi': 0.0,
        'win_rate': 0.0,
        'capital': 1000.0,  # Base capital
        'max_drawdown': 0.0,
        'sharpe': 0.0,
        'best_league': 'N/A',
        'best_driver': 'N/A',
        'last_updated': 'Mai',
    }
    
    try:
        # Load optimizer data (primary source of truth for settled bets)
        if os.path.exists(OPTIMIZER_WEIGHTS_FILE):
            with open(OPTIMIZER_WEIGHTS_FILE, 'r') as f:
                optimizer_data = json.load(f)

            # Global stats
            global_stats = optimizer_data.get('global', {})
            stats['total_bets'] = global_stats.get('total_bets', 0)
            stats['profit'] = global_stats.get('total_profit', 0.0)
            stats['roi'] = global_stats.get('overall_roi', 0.0) * 100  # Convert to %
            stats['last_updated'] = optimizer_data.get('last_updated', 'Mai')
            
            # Calculate wins/losses from league stats
            total_wins = 0
            total_losses = 0
            best_roi = -999
            best_league_name = 'N/A'
            
            for league, markets in optimizer_data.get('stats', {}).items():
                for market_type, market_stats in markets.items():
                    total_wins += market_stats.get('wins', 0)
                    bets = market_stats.get('bets', 0)
                    total_losses += (bets - market_stats.get('wins', 0))
                    
                    # Track best performing league
                    if market_stats.get('bets', 0) >= 5:
                        league_roi = market_stats.get('roi', 0)
                        if league_roi > best_roi:
                            best_roi = league_roi
                            # Clean up league name for display
                            best_league_name = league.replace('soccer_', '').replace('_', ' ').title()[:20]
            
            stats['wins'] = total_wins
            stats['losses'] = total_losses
            stats['best_league'] = best_league_name
            
            # Calculate win rate
            if stats['total_bets'] > 0:
                stats['win_rate'] = (stats['wins'] / stats['total_bets']) * 100
            
            # Capital calculation (base 1000 + profit, assuming 10€ per bet)
            stats['capital'] = 1000 + (stats['profit'] * 10)
            
            # Get max drawdown from any strategy
            max_dd = 0
            for league, markets in optimizer_data.get('stats', {}).items():
                for market_type, market_stats in markets.items():
                    dd = abs(market_stats.get('max_drawdown', 0))
                    if dd > max_dd:
                        max_dd = dd
            stats['max_drawdown'] = max_dd * 100  # Convert to %
            
            # Best driver
            best_driver_roi = -999
            for driver, driver_stats in optimizer_data.get('drivers', {}).items():
                if driver_stats.get('bets', 0) >= 3:
                    if driver_stats.get('roi', 0) > best_driver_roi:
                        best_driver_roi = driver_stats.get('roi', 0)
                        stats['best_driver'] = driver.replace('_', ' ').title()[:15]
            
    except Exception as e:
        logger.error(f"Error loading stats data: {e}")
    
    # Also check database for additional context
    try:
        from src.database.models import NewsLog, Match, SessionLocal
        db = SessionLocal()
        
        # Count total alerts sent
        alerts_sent = db.query(NewsLog).filter(NewsLog.sent == True).count()
        if alerts_sent > stats['total_bets']:
            # Use DB count if optimizer hasn't tracked all yet
            pass  # Keep optimizer data as source of truth for settled bets
        
        db.close()
    except Exception as e:
        logger.warning(f"Could not query database: {e}")
    
    return stats


def draw_dashboard(stats: Dict = None) -> str:
    """
    Generate a visual dashboard image using matplotlib.
    
    Args:
        stats: Optional pre-computed stats dict. If None, will fetch.
        
    Returns:
        Path to generated image file
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        from matplotlib.patches import FancyBboxPatch
    except ImportError:
        logger.error("matplotlib not installed. Run: pip install matplotlib")
        raise ImportError("matplotlib required for stats dashboard")
    
    if stats is None:
        stats = get_stats_data()
    
    # Create figure with dark background
    fig, ax = plt.subplots(figsize=(10, 8), facecolor=COLORS['background'])
    ax.set_facecolor(COLORS['background'])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.axis('off')
    
    # Title (no emoji to avoid font warnings)
    ax.text(5, 7.5, 'EARLYBIRD STATS', fontsize=24, fontweight='bold',
            color=COLORS['text_primary'], ha='center', va='center',
            fontfamily='sans-serif')
    
    # Subtitle with date
    date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    ax.text(5, 7.0, f'Aggiornato: {date_str}', fontsize=10,
            color=COLORS['text_secondary'], ha='center', va='center')
    
    # Define card positions (2 columns, 4 rows)
    cards = [
        # Row 1
        {'x': 0.5, 'y': 5.5, 'label': 'SCOMMESSE', 'value': str(stats['total_bets']), 'color': COLORS['accent_blue']},
        {'x': 5.25, 'y': 5.5, 'label': 'PROFITTO', 'value': f"€{stats['profit']*10:.0f}", 
         'color': COLORS['accent_green'] if stats['profit'] >= 0 else COLORS['accent_red']},
        # Row 2
        {'x': 0.5, 'y': 4.0, 'label': 'ROI', 'value': f"{stats['roi']:.1f}%",
         'color': COLORS['accent_green'] if stats['roi'] >= 0 else COLORS['accent_red']},
        {'x': 5.25, 'y': 4.0, 'label': 'DRAWDOWN', 'value': f"-{stats['max_drawdown']:.1f}%",
         'color': COLORS['accent_yellow'] if stats['max_drawdown'] < 15 else COLORS['accent_red']},
        # Row 3
        {'x': 0.5, 'y': 2.5, 'label': 'WIN RATE', 'value': f"{stats['win_rate']:.1f}%",
         'color': COLORS['accent_green'] if stats['win_rate'] >= 50 else COLORS['accent_yellow']},
        {'x': 5.25, 'y': 2.5, 'label': 'CAPITALE', 'value': f"€{stats['capital']:.0f}",
         'color': COLORS['accent_blue']},
        # Row 4
        {'x': 0.5, 'y': 1.0, 'label': 'VINCENTI', 'value': str(stats['wins']), 'color': COLORS['accent_green']},
        {'x': 5.25, 'y': 1.0, 'label': 'PERDENTI', 'value': str(stats['losses']), 'color': COLORS['accent_red']},
    ]
    
    # Draw cards
    card_width = 4.25
    card_height = 1.2
    
    for card in cards:
        # Card background
        rect = FancyBboxPatch(
            (card['x'], card['y'] - card_height/2),
            card_width, card_height,
            boxstyle="round,pad=0.02,rounding_size=0.15",
            facecolor=COLORS['card_bg'],
            edgecolor=COLORS['border'],
            linewidth=1
        )
        ax.add_patch(rect)
        
        # Label (top of card)
        ax.text(card['x'] + card_width/2, card['y'] + 0.25, card['label'],
                fontsize=10, color=COLORS['text_secondary'],
                ha='center', va='center', fontweight='normal')
        
        # Value (center of card, large)
        ax.text(card['x'] + card_width/2, card['y'] - 0.2, card['value'],
                fontsize=22, color=card['color'],
                ha='center', va='center', fontweight='bold')
    
    # Footer with best performers (no emoji to avoid font warnings)
    footer_y = 0.2
    ax.text(2.5, footer_y, f"Best League: {stats['best_league']}", 
            fontsize=9, color=COLORS['text_secondary'], ha='center')
    ax.text(7.5, footer_y, f"Best Driver: {stats['best_driver']}", 
            fontsize=9, color=COLORS['text_secondary'], ha='center')
    
    # Ensure temp directory exists
    Path(STATS_IMAGE_PATH).parent.mkdir(parents=True, exist_ok=True)
    
    # Save figure
    plt.tight_layout()
    plt.savefig(STATS_IMAGE_PATH, dpi=150, facecolor=COLORS['background'],
                edgecolor='none', bbox_inches='tight', pad_inches=0.3)
    plt.close(fig)
    
    logger.info(f"📊 Stats dashboard saved to {STATS_IMAGE_PATH}")
    return STATS_IMAGE_PATH


def generate_dashboard() -> str:
    """
    Main entry point for dashboard generation.
    Fetches stats and generates the image.
    
    Returns:
        Path to generated image file
    """
    logger.info("🎨 Generating stats dashboard...")
    stats = get_stats_data()
    return draw_dashboard(stats)


def get_text_summary() -> str:
    """
    Generate a text-only summary (fallback if matplotlib fails).
    
    Returns:
        Formatted text summary
    """
    stats = get_stats_data()
    
    profit_emoji = "📈" if stats['profit'] >= 0 else "📉"
    win_emoji = "🟢" if stats['win_rate'] >= 50 else "🟡"
    
    summary = f"""
📊 <b>EARLYBIRD STATS</b>
━━━━━━━━━━━━━━━━━━━━

🎰 Scommesse: <b>{stats['total_bets']}</b>
{profit_emoji} Profitto: <b>€{stats['profit']*10:.0f}</b>
📊 ROI: <b>{stats['roi']:.1f}%</b>
⚠️ Drawdown: <b>-{stats['max_drawdown']:.1f}%</b>

{win_emoji} Win Rate: <b>{stats['win_rate']:.1f}%</b>
💰 Capitale: <b>€{stats['capital']:.0f}</b>

✅ Vincenti: <b>{stats['wins']}</b>
❌ Perdenti: <b>{stats['losses']}</b>

━━━━━━━━━━━━━━━━━━━━
🏆 Best League: {stats['best_league']}
🎯 Best Driver: {stats['best_driver']}
"""
    return summary.strip()


# CLI test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing stats dashboard generation...")
    
    # Test data extraction
    stats = get_stats_data()
    print(f"\nStats data: {json.dumps(stats, indent=2)}")
    
    # Test text summary
    print("\nText summary:")
    print(get_text_summary())
    
    # Test image generation
    try:
        img_path = generate_dashboard()
        print(f"\n✅ Dashboard saved to: {img_path}")
    except ImportError as e:
        print(f"\n⚠️ Could not generate image: {e}")
        print("Text fallback available via get_text_summary()")