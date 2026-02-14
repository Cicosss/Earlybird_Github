#!/usr/bin/env python3
"""
Quick script to check league_key to league_id mapping
"""
from src.database.supabase_provider import get_supabase

try:
    sb = get_supabase()
    if sb:
        # Fetch all active leagues
        leagues = sb.get_active_leagues()
        print(f'Total active leagues: {len(leagues)}')
        print('\nFirst 10 leagues:')
        for i, league in enumerate(leagues[:10], 1):
            print(f"{i}. API Key: {league.get('api_key')}, ID: {league.get('id')}, Name: {league.get('name')}")
    else:
        print('Supabase provider not available')
except Exception as e:
    print(f'Error: {e}')
