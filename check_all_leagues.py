#!/usr/bin/env python3
"""
Quick script to check all Supabase leagues
"""
from src.database.supabase_provider import get_supabase

try:
    sb = get_supabase()
    if sb:
        leagues = sb.get_active_leagues()
        print(f'Total active leagues: {len(leagues)}')
        print('\nAll active leagues:')
        for i, league in enumerate(leagues, 1):
            print(f"{i}. {league.get('api_key')}: {league.get('name')} (priority: {league.get('priority')})")
    else:
        print('Supabase provider not available')
except Exception as e:
    print(f'Error: {e}')
