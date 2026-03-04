#!/bin/bash
# ============================================
# VPS Cache Recommendations Deployment Script
# ============================================
# 
# This script applies the VPS cache recommendations:
# 1. Set SUPABASE_CACHE_TTL_SECONDS=300 in .env
# 2. Verify cache metrics monitoring
# 3. Provide instructions for bypass_cache usage
# 4. Provide instructions for cache invalidation
#
# Author: Chain of Verification Mode
# Date: 2026-03-03
# ============================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 VPS CACHE RECOMMENDATIONS DEPLOYMENT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"
echo "📅 $(date)"
echo ""

# ============================================
# STEP 1: Verify .env file exists
# ============================================
echo -e "${YELLOW}[1/5] Verifying .env file...${NC}"

if [ ! -f .env ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo -e "${YELLOW}   Creating .env from template...${NC}"
    cp .env.template .env
    echo -e "${GREEN}   ✅ .env created from template${NC}"
else
    echo -e "${GREEN}   ✅ .env file found${NC}"
fi
echo ""

# ============================================
# STEP 2: Set SUPABASE_CACHE_TTL_SECONDS=300
# ============================================
echo -e "${YELLOW}[2/5] Setting SUPABASE_CACHE_TTL_SECONDS=300...${NC}"

# Check if SUPABASE_CACHE_TTL_SECONDS already exists
if grep -q "^SUPABASE_CACHE_TTL_SECONDS=" .env; then
    echo -e "${YELLOW}   ⚠️ SUPABASE_CACHE_TTL_SECONDS already exists in .env${NC}"
    # Update existing value
    sed -i 's/^SUPABASE_CACHE_TTL_SECONDS=.*/SUPABASE_CACHE_TTL_SECONDS=300/' .env
    echo -e "${GREEN}   ✅ SUPABASE_CACHE_TTL_SECONDS updated to 300${NC}"
else
    # Add new entry after SUPABASE_KEY
    sed -i '/^SUPABASE_KEY=/a SUPABASE_CACHE_TTL_SECONDS=300' .env
    echo -e "${GREEN}   ✅ SUPABASE_CACHE_TTL_SECONDS=300 added to .env${NC}"
fi
echo ""

# ============================================
# STEP 3: Verify cache metrics monitoring
# ============================================
echo -e "${YELLOW}[3/5] Verifying cache metrics monitoring...${NC}"

# Run test script to verify cache metrics
if [ -f test_cache_vps_recommendations.py ]; then
    echo -e "${CYAN}   Running cache metrics test...${NC}"
    python3 test_cache_vps_recommendations.py > /tmp/cache_test_output.txt 2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}   ✅ Cache metrics monitoring verified${NC}"
    else
        echo -e "${YELLOW}   ⚠️ Cache metrics test failed (check /tmp/cache_test_output.txt)${NC}"
    fi
else
    echo -e "${YELLOW}   ⚠️ test_cache_vps_recommendations.py not found${NC}"
fi
echo ""

# ============================================
# STEP 4: Create cache monitoring script
# ============================================
echo -e "${YELLOW}[4/5] Creating cache monitoring script...${NC}"

cat > monitor_cache_metrics.sh << 'EOF'
#!/bin/bash
# Cache Metrics Monitoring Script
# Run this script to monitor Supabase cache metrics

python3 << 'PYTHON'
import os
import sys
import json
from datetime import datetime

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.database.supabase_provider import SupabaseProvider

load_dotenv()

# Get SupabaseProvider instance
provider = SupabaseProvider()

# Get cache metrics
metrics = provider.get_cache_metrics()

# Print metrics in a nice format
print("=" * 60)
print("SUPABASE CACHE METRICS")
print("=" * 60)
print(f"📊 Total Requests: {metrics['total_requests']}")
print(f"✅ Cache Hits: {metrics['hit_count']}")
print(f"❌ Cache Misses: {metrics['miss_count']}")
print(f"🔄 Cache Bypass: {metrics['bypass_count']}")
print(f"📈 Hit Ratio: {metrics['hit_ratio_percent']:.1f}%")
print(f"⏱️ Cache TTL: {metrics['cache_ttl_seconds']}s")
print(f"🔑 Cached Keys: {metrics['cached_keys_count']}")
print("=" * 60)

# Get lock stats
lock_stats = provider.get_cache_lock_stats()
print("CACHE LOCK STATS")
print("=" * 60)
print(f"⏳ Wait Count: {lock_stats['wait_count']}")
print(f"⏱️ Wait Time Total: {lock_stats['wait_time_total']}s")
print(f"⏱️ Wait Time Avg: {lock_stats['wait_time_avg']}s")
print(f"⚠️ Timeout Count: {lock_stats['timeout_count']}")
print("=" * 60)

# Export to JSON for external monitoring
timestamp = datetime.now().isoformat()
export_data = {
    "timestamp": timestamp,
    "cache_metrics": metrics,
    "lock_stats": lock_stats
}

# Save to metrics file
metrics_dir = "data/metrics"
os.makedirs(metrics_dir, exist_ok=True)
metrics_file = f"{metrics_dir}/supabase_cache_metrics.json"
with open(metrics_file, "w") as f:
    json.dump(export_data, f, indent=2)

print(f"💾 Metrics saved to: {metrics_file}")
PYTHON
EOF

chmod +x monitor_cache_metrics.sh
echo -e "${GREEN}   ✅ monitor_cache_metrics.sh created${NC}"
echo ""

# ============================================
# STEP 5: Create cache invalidation script
# ============================================
echo -e "${YELLOW}[5/5] Creating cache invalidation script...${NC}"

cat > invalidate_cache.sh << 'EOF'
#!/bin/bash
# Cache Invalidation Script
# Run this script to invalidate Supabase cache

python3 << 'PYTHON'
import os
import sys

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.database.supabase_provider import SupabaseProvider

load_dotenv()

# Get SupabaseProvider instance
provider = SupabaseProvider()

print("=" * 60)
print("CACHE INVALIDATION")
print("=" * 60)
print("Choose an option:")
print("1. Invalidate all cache")
print("2. Invalidate leagues cache only")
print("3. Cancel")
print("=" * 60)

choice = input("Enter your choice (1-3): ")

if choice == "1":
    provider.invalidate_cache()
    print("✅ All cache invalidated")
elif choice == "2":
    provider.invalidate_leagues_cache()
    print("✅ Leagues cache invalidated")
else:
    print("❌ Operation cancelled")
PYTHON
EOF

chmod +x invalidate_cache.sh
echo -e "${GREEN}   ✅ invalidate_cache.sh created${NC}"
echo ""

# ============================================
# SUMMARY
# ============================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ DEPLOYMENT COMPLETE!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}📖 NEXT STEPS:${NC}"
echo ""
echo -e "${CYAN}1. Monitor Cache Metrics:${NC}"
echo "   Run: ./monitor_cache_metrics.sh"
echo ""
echo -e "${CYAN}2. Use Bypass Cache for Critical Operations:${NC}"
echo "   Example: provider.get_active_leagues(bypass_cache=True)"
echo ""
echo -e "${CYAN}3. Invalidate Cache When Leagues are Modified:${NC}"
echo "   Run: ./invalidate_cache.sh"
echo ""
echo -e "${CYAN}4. Verify Configuration:${NC}"
echo "   Check .env file for SUPABASE_CACHE_TTL_SECONDS=300"
echo ""
echo -e "${CYAN}5. Restart System (if needed):${NC}"
echo "   Run: ./start_system.sh"
echo ""
echo -e "${YELLOW}📚 DOCUMENTATION:${NC}"
echo "   - Cache metrics are included in heartbeat messages"
echo "   - Cache TTL is now 300 seconds (5 minutes)"
echo "   - Cache invalidation is manual via invalidate_cache.sh"
echo ""
