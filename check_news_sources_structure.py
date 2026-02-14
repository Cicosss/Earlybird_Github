#!/usr/bin/env python3
"""
Quick script to check Supabase news_sources structure
"""
from src.database.supabase_provider import get_supabase

try:
    sb = get_supabase()
    if sb:
        # Fetch all news sources
        all_sources = sb.fetch_all_news_sources()
        print(f'Total news sources: {len(all_sources)}')
        print('\nFirst 5 news sources:')
        for i, source in enumerate(all_sources[:5], 1):
            print(f"{i}. {source}")
        
        # Check if there's a field for domain
        if all_sources:
            print('\nAvailable fields in news_sources:')
            print(list(all_sources[0].keys()))
    else:
        print('Supabase provider not available')
except Exception as e:
    print(f'Error: {e}')
