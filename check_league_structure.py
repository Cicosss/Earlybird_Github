#!/usr/bin/env python3
"""
Quick script to check Supabase league structure
"""
from src.database.supabase_provider import get_supabase

try:
    sb = get_supabase()
    if sb:
        leagues = sb.get_active_leagues()
        print(f'Total active leagues: {len(leagues)}')
        print('\nFirst 10 leagues:')
        for league in leagues[:10]:
            print(f"  - {league.get('api_key')}: {league.get('name')} (priority: {league.get('priority')}, is_active: {league.get('is_active')})")
    else:
        print('Supabase provider not available')
except Exception as e:
    print(f'Error: {e}')
