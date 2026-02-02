#!/usr/bin/env python3
"""
FotMob Stats Inspector - V3.7 Diagnostic Tool

Inspects the FotMob API response structure to discover available stats.
Use this to find exact JSON keys for: Big Chances, Shots on Target, Fouls, etc.

Usage:
    python src/utils/inspect_fotmob.py
    python src/utils/inspect_fotmob.py --team "Real Madrid"
    python src/utils/inspect_fotmob.py --match-id 4255474
"""
import requests
import json
import argparse
import sys
from src.utils.validators import safe_get

# Browser headers to avoid 403
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.fotmob.com/',
    'Origin': 'https://www.fotmob.com'
}

BASE_URL = "https://www.fotmob.com/api"


def search_team(team_name: str) -> dict:
    """Search for a team and return first result."""
    url = f"{BASE_URL}/search/suggest?term={requests.utils.quote(team_name)}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    
    data = resp.json()
    for group in data:
        for suggestion in group.get('suggestions', []):
            if suggestion.get('type') == 'team':
                return {'id': suggestion['id'], 'name': suggestion['name']}
    return None


def get_team_last_match(team_id: int) -> int:
    """Get the last finished match ID for a team."""
    url = f"{BASE_URL}/teams?id={team_id}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    
    data = resp.json()
    fixtures = safe_get(data, 'fixtures', 'allFixtures', default={})
    previous = fixtures.get('previousMatches', [])
    
    if previous:
        return previous[0].get('id')
    return None


def get_match_details(match_id: int) -> dict:
    """Fetch full match details."""
    url = f"{BASE_URL}/matchDetails?matchId={match_id}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def inspect_stats(match_data: dict):
    """Parse and display all available stats from match data."""
    content = match_data.get('content', {})
    stats_data = content.get('stats', {})
    
    print("\n" + "=" * 60)
    print("📊 FOTMOB STATS STRUCTURE INSPECTION")
    print("=" * 60)
    
    # Show top-level keys in stats
    print(f"\n🔑 Top-level keys in 'content.stats': {list(stats_data.keys())}")
    
    # Try different known paths
    paths_to_try = [
        ('Periods.All.stats', lambda d: safe_get(d, 'Periods', 'All', 'stats', default=[])),
        ('Ede', lambda d: d.get('Ede', [])),
        ('stats', lambda d: d.get('stats', [])),
    ]
    
    stats_list = None
    used_path = None
    
    for path_name, extractor in paths_to_try:
        result = extractor(stats_data)
        if result:
            stats_list = result
            used_path = path_name
            break
    
    # Fallback: try first non-empty value
    if not stats_list and stats_data:
        for key, value in stats_data.items():
            if isinstance(value, list) and value:
                stats_list = value
                used_path = key
                break
    
    if not stats_list:
        print("\n❌ No stats found in expected paths!")
        print("\n📄 Raw stats_data structure:")
        print(json.dumps(stats_data, indent=2)[:2000])
        return
    
    print(f"\n✅ Found stats at path: content.stats.{used_path}")
    print(f"   Categories found: {len(stats_list)}")
    
    # Iterate through categories
    print("\n" + "-" * 60)
    print("📋 AVAILABLE STATS BY CATEGORY")
    print("-" * 60)
    
    all_stats = []
    
    for category in stats_list:
        if not isinstance(category, dict):
            continue
        
        cat_name = category.get('title', category.get('name', 'Unknown'))
        items = category.get('items', category.get('stats', []))
        
        print(f"\n📁 Category: {cat_name}")
        
        for item in items:
            if not isinstance(item, dict):
                continue
            
            title = item.get('title', item.get('name', 'Unknown'))
            stats = item.get('stats', [])
            
            home_val = away_val = "N/A"
            if len(stats) >= 2:
                home_stat = stats[0]
                away_stat = stats[1]
                home_val = home_stat.get('value', home_stat) if isinstance(home_stat, dict) else home_stat
                away_val = away_stat.get('value', away_stat) if isinstance(away_stat, dict) else away_stat
            
            print(f"   • {title:30} | Home: {str(home_val):8} | Away: {str(away_val):8}")
            all_stats.append(title)
    
    # Summary of key stats for V3.7+
    print("\n" + "=" * 60)
    print("🎯 KEY STATS FOR WAREHOUSING (V3.7+)")
    print("=" * 60)
    
    key_stats = ['Corners', 'Yellow cards', 'Red cards', 'Expected goals', 'xG', 
                 'Ball possession', 'Possession', 'Big chances', 'Shots on target',
                 'Fouls', 'Total shots', 'Shots off target']
    
    for key in key_stats:
        found = any(key.lower() in s.lower() for s in all_stats)
        status = "✅ Found" if found else "❌ Not found"
        print(f"   {key:25} {status}")


def main():
    parser = argparse.ArgumentParser(description='Inspect FotMob API stats structure')
    parser.add_argument('--team', type=str, default='Galatasaray', help='Team name to search')
    parser.add_argument('--match-id', type=int, help='Direct match ID (skip team search)')
    args = parser.parse_args()
    
    try:
        if args.match_id:
            match_id = args.match_id
            print(f"🔍 Using provided match ID: {match_id}")
        else:
            print(f"🔍 Searching for team: {args.team}")
            team = search_team(args.team)
            
            if not team:
                print(f"❌ Team '{args.team}' not found")
                sys.exit(1)
            
            print(f"✅ Found: {team['name']} (ID: {team['id']})")
            
            match_id = get_team_last_match(team['id'])
            if not match_id:
                print("❌ No recent matches found")
                sys.exit(1)
            
            print(f"📅 Last match ID: {match_id}")
        
        print(f"\n⏳ Fetching match details...")
        match_data = get_match_details(match_id)
        
        # Show match info
        general = match_data.get('general', {})
        home = safe_get(general, 'homeTeam', 'name', default='Home')
        away = safe_get(general, 'awayTeam', 'name', default='Away')
        print(f"⚽ Match: {home} vs {away}")
        
        # Inspect stats
        inspect_stats(match_data)
        
    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
