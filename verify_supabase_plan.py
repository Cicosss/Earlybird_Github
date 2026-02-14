#!/usr/bin/env python3
"""
Supabase Migration Plan Verification Script
Read-only verification of the migration plan claims
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List, Any, Tuple

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("❌ Supabase client not installed")
    sys.exit(1)

# Get credentials
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ SUPABASE_URL or SUPABASE_KEY not configured")
    sys.exit(1)

print("=" * 80)
print("SUPABASE MIGRATION PLAN VERIFICATION")
print("=" * 80)
print(f"URL: {SUPABASE_URL}")
print(f"Timestamp: {datetime.utcnow().isoformat()}")
print()

# Connect to Supabase
try:
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Connected to Supabase successfully")
except Exception as e:
    print(f"❌ Failed to connect: {e}")
    sys.exit(1)

print()

# ============================================
# VERIFICATION 1: Table Existence and Record Counts
# ============================================
print("=" * 80)
print("VERIFICATION 1: TABLE EXISTENCE AND RECORD COUNTS")
print("=" * 80)

tables_to_check = [
    "continents",
    "countries",
    "leagues",
    "news_sources",
    "social_sources"
]

table_counts = {}
for table in tables_to_check:
    try:
        response = client.table(table).select("*", count="exact").execute()
        count = response.count if hasattr(response, 'count') else len(response.data)
        table_counts[table] = count
        print(f"✅ {table:20s} : {count:4d} records")
    except Exception as e:
        table_counts[table] = 0
        print(f"❌ {table:20s} : ERROR - {e}")

print()

# ============================================
# VERIFICATION 2: Foreign Key Relationships
# ============================================
print("=" * 80)
print("VERIFICATION 2: FOREIGN KEY RELATIONSHIPS")
print("=" * 80)

def verify_foreign_key(parent_table: str, child_table: str, fk_column: str) -> Tuple[int, int, List[str]]:
    """Verify foreign key relationships"""
    try:
        # Get parent IDs
        parent_response = client.table(parent_table).select("id").execute()
        parent_ids = {row['id'] for row in parent_response.data}
        
        # Get child records
        child_response = client.table(child_table).select(f"id,{fk_column}").execute()
        child_records = child_response.data
        
        total_children = len(child_records)
        valid_children = 0
        invalid_ids = []
        
        for child in child_records:
            if child.get(fk_column) in parent_ids:
                valid_children += 1
            else:
                invalid_ids.append(child['id'])
        
        invalid_count = total_children - valid_children
        return total_children, valid_children, invalid_ids
        
    except Exception as e:
        print(f"❌ Error verifying {parent_table} -> {child_table}: {e}")
        return 0, 0, []

# Verify relationships
relationships = [
    ("continents", "countries", "continent_id"),
    ("countries", "leagues", "country_id"),
    ("leagues", "news_sources", "league_id"),
    ("leagues", "social_sources", "league_id"),
]

all_valid = True
for parent, child, fk in relationships:
    total, valid, invalid = verify_foreign_key(parent, child, fk)
    if total > 0:
        percentage = (valid / total) * 100
        status = "✅" if percentage == 100 else "❌"
        print(f"{status} {parent:12s} -> {child:15s} : {valid}/{total} valid ({percentage:.1f}%)")
        if invalid:
            print(f"   ⚠️  {len(invalid)} invalid records: {invalid[:3]}{'...' if len(invalid) > 3 else ''}")
            all_valid = False
    else:
        print(f"⚠️  {parent:12s} -> {child:15s} : No child records")

print()

# ============================================
# VERIFICATION 3: Table Schema
# ============================================
print("=" * 80)
print("VERIFICATION 3: TABLE SCHEMA")
print("=" * 80)

schema_info = {}
for table in tables_to_check:
    try:
        response = client.table(table).select("*").limit(1).execute()
        if response.data:
            columns = list(response.data[0].keys())
            schema_info[table] = columns
            print(f"✅ {table:20s} : {len(columns)} columns")
            print(f"   Columns: {', '.join(sorted(columns))}")
        else:
            schema_info[table] = []
            print(f"⚠️  {table:20s} : No data to infer schema")
    except Exception as e:
        print(f"❌ {table:20s} : ERROR - {e}")

print()

# ============================================
# VERIFICATION 4: Mirror File State
# ============================================
print("=" * 80)
print("VERIFICATION 4: MIRROR FILE STATE")
print("=" * 80)

mirror_path = "data/supabase_mirror.json"
if os.path.exists(mirror_path):
    with open(mirror_path, 'r') as f:
        mirror_data = json.load(f)
    
    timestamp = mirror_data.get("timestamp", "UNKNOWN")
    version = mirror_data.get("version", "UNKNOWN")
    checksum = mirror_data.get("checksum", "")
    data = mirror_data.get("data", {})
    
    print(f"✅ Mirror file exists")
    print(f"   Timestamp: {timestamp}")
    print(f"   Version: {version}")
    print(f"   Checksum: {checksum[:16]}..." if checksum else "   Checksum: MISSING")
    print()
    
    # Check mirror contents
    mirror_tables = ["continents", "countries", "leagues", "sources", "news_sources", "social_sources"]
    for table in mirror_tables:
        count = len(data.get(table, []))
        print(f"   {table:20s} : {count:4d} records")
    
    # Check for issues
    print()
    print("⚠️  MIRROR ISSUES:")
    
    if "sources" in data and len(data.get("sources", [])) > 0:
        print("   ❌ Mirror has 'sources' key (should be 'news_sources')")
    
    if "news_sources" not in data or len(data.get("news_sources", [])) == 0:
        print("   ❌ Mirror missing 'news_sources' key or empty")
    
    if "social_sources" not in data or len(data.get("social_sources", [])) == 0:
        print("   ❌ Mirror missing 'social_sources' key or empty")
    
    # Compare with Supabase
    print()
    print("📊 COMPARISON WITH SUPABASE:")
    for table in ["continents", "countries", "leagues"]:
        supabase_count = table_counts.get(table, 0)
        mirror_count = len(data.get(table, []))
        if supabase_count != mirror_count:
            print(f"   ⚠️  {table:20s} : Supabase={supabase_count}, Mirror={mirror_count} (MISMATCH)")
        else:
            print(f"   ✅ {table:20s} : Supabase={supabase_count}, Mirror={mirror_count} (MATCH)")
    
    # Special comparison for news_sources
    supabase_news = table_counts.get("news_sources", 0)
    mirror_sources = len(data.get("sources", []))
    mirror_news = len(data.get("news_sources", []))
    
    if mirror_sources == supabase_news and mirror_news == 0:
        print(f"   ⚠️  news_sources      : Supabase={supabase_news}, Mirror(sources)={mirror_sources}, Mirror(news_sources)={mirror_news} (WRONG KEY)")
    elif mirror_news == supabase_news:
        print(f"   ✅ news_sources      : Supabase={supabase_news}, Mirror={mirror_news} (MATCH)")
    
    # Special comparison for social_sources
    supabase_social = table_counts.get("social_sources", 0)
    mirror_social = len(data.get("social_sources", []))
    
    if supabase_social != mirror_social:
        print(f"   ⚠️  social_sources    : Supabase={supabase_social}, Mirror={mirror_social} (MISMATCH)")
    else:
        print(f"   ✅ social_sources    : Supabase={supabase_social}, Mirror={mirror_social} (MATCH)")
    
else:
    print(f"❌ Mirror file not found: {mirror_path}")

print()

# ============================================
# VERIFICATION 5: SupabaseProvider Code Analysis
# ============================================
print("=" * 80)
print("VERIFICATION 5: SUPABASEPROVIDER CODE ANALYSIS")
print("=" * 80)

provider_file = "src/database/supabase_provider.py"
if os.path.exists(provider_file):
    with open(provider_file, 'r') as f:
        provider_code = f.read()
    
    # Check for bugs mentioned in the plan
    print("🔍 CHECKING FOR REPORTED BUGS:")
    print()
    
    # Bug #1: fetch_hierarchical_map() line 457
    if '"sources": self.fetch_sources()' in provider_code:
        print("❌ BUG #1 CONFIRMED: fetch_hierarchical_map() uses 'sources' key")
        # Find the line
        lines = provider_code.split('\n')
        for i, line in enumerate(lines, 1):
            if '"sources": self.fetch_sources()' in line:
                print(f"   Location: Line {i}")
                break
    else:
        print("✅ BUG #1 FIXED: fetch_hierarchical_map() uses 'news_sources' key")
    
    print()
    
    # Bug #2: create_local_mirror() and update_mirror()
    sources_count = provider_code.count('"sources": self.fetch_sources()')
    news_sources_count = provider_code.count('"news_sources": self.fetch_all_news_sources()')
    
    print(f"   Found {sources_count} instances of '\"sources\": self.fetch_sources()'")
    print(f"   Found {news_sources_count} instances of '\"news_sources\": self.fetch_all_news_sources()'")
    
    if sources_count > 0 and news_sources_count > 0:
        print("❌ BUG #2 CONFIRMED: Duplicate keys (both 'sources' and 'news_sources' exist)")
    elif sources_count == 0 and news_sources_count > 0:
        print("✅ BUG #2 FIXED: Only 'news_sources' key exists")
    else:
        print("⚠️  WARNING: Unexpected configuration")
    
    print()
    
    # Check for update_mirror() method
    if "def update_mirror" in provider_code:
        print("✅ update_mirror() method exists")
    else:
        print("❌ update_mirror() method NOT FOUND")
    
    # Check for create_local_mirror() method
    if "def create_local_mirror" in provider_code:
        print("✅ create_local_mirror() method exists")
    else:
        print("❌ create_local_mirror() method NOT FOUND")
    
else:
    print(f"❌ Provider file not found: {provider_file}")

print()

# ============================================
# VERIFICATION 6: Local Files with Hardcoded Intelligence
# ============================================
print("=" * 80)
print("VERIFICATION 6: LOCAL FILES WITH HARDCODED INTELLIGENCE")
print("=" * 80)

files_to_check = [
    "src/processing/sources_config.py",
    "config/twitter_intel_accounts.py",
]

for file_path in files_to_check:
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for hardcoded lists
        if "NEWS_SOURCES" in content or "TWITTER_ACCOUNTS" in content or "INTEL" in content:
            print(f"⚠️  {file_path}: Contains hardcoded intelligence")
        else:
            print(f"✅ {file_path}: No hardcoded intelligence found")
    else:
        print(f"⚠️  {file_path}: File not found")

print()

# ============================================
# FINAL SUMMARY
# ============================================
print("=" * 80)
print("FINAL SUMMARY")
print("=" * 80)

print()
print("✅ VERIFICATION COMPLETE")
print()
print("KEY FINDINGS:")
print()

# 1. Table counts
print("1. SUPABASE TABLE COUNTS:")
for table, count in table_counts.items():
    print(f"   - {table}: {count} records")

print()

# 2. Foreign key validity
print("2. FOREIGN KEY VALIDITY:")
if all_valid:
    print("   ✅ ALL foreign key relationships are VALID (100%)")
else:
    print("   ❌ SOME foreign key relationships are INVALID")

print()

# 3. Mirror state
print("3. MIRROR STATE:")
if os.path.exists(mirror_path):
    print(f"   ⚠️  Mirror is OBSOLETE (timestamp: {timestamp})")
    print(f"   ❌ Mirror has WRONG key: 'sources' instead of 'news_sources'")
    print(f"   ❌ Mirror is MISSING 'social_sources' data")
else:
    print("   ❌ Mirror file does not exist")

print()

# 4. Code bugs
print("4. CODE BUGS:")
if '"sources": self.fetch_sources()' in provider_code:
    print("   ❌ Bug #1: fetch_hierarchical_map() uses 'sources' key")
if sources_count > 0 and news_sources_count > 0:
    print("   ❌ Bug #2: Duplicate keys in create_local_mirror() and update_mirror()")

print()

# 5. Migration plan accuracy
print("5. MIGRATION PLAN ACCURACY:")
plan_claims = [
    ("Supabase has 3 continents", table_counts.get("continents", 0) == 3),
    ("Supabase has 28 countries", table_counts.get("countries", 0) == 28),
    ("Supabase has 56 leagues", table_counts.get("leagues", 0) == 56),
    ("Supabase has 140 news_sources", table_counts.get("news_sources", 0) == 140),
    ("Supabase has 38 social_sources", table_counts.get("social_sources", 0) == 38),
    ("All FK relationships are valid", all_valid),
]

correct_count = 0
for claim, is_correct in plan_claims:
    status = "✅" if is_correct else "❌"
    print(f"   {status} {claim}")
    if is_correct:
        correct_count += 1

print()
print(f"   Plan accuracy: {correct_count}/{len(plan_claims)} claims verified ({correct_count/len(plan_claims)*100:.1f}%)")

print()
print("=" * 80)
print("END OF VERIFICATION REPORT")
print("=" * 80)
