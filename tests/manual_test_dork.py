"""
Test: Insider Domain Dorking Query Builder

Verifies that search queries are correctly formatted for Brave/Google:
- site: operator syntax
- OR uppercase with spaces
- Parentheses grouping
- No protocol prefixes in domains
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ingestion.search_provider import SearchProvider, LEAGUE_DOMAINS


def test_query_format():
    """Test that query is correctly formatted."""
    p = SearchProvider()
    
    # Test Turkey
    q = p._build_insider_query("Galatasaray", "injury", "soccer_turkey_super_league")
    print(f"\n🇹🇷 Turkey Query:")
    print(f"   {q}")
    
    # Verify format
    assert '"Galatasaray"' in q, "Team should be quoted"
    assert "injury" in q, "Keywords should be present"
    assert "(site:" in q, "Site group should have opening parenthesis"
    assert " OR site:" in q, "OR should be uppercase with spaces"
    assert "ajansspor.com" in q, "Domain should be present"
    assert "-basket" in q, "Sport exclusions should be present"
    print("   ✅ Format OK")
    
    # Test Argentina
    q = p._build_insider_query("Boca Juniors", "lineup OR squad", "soccer_argentina_primera_division")
    print(f"\n🇦🇷 Argentina Query:")
    print(f"   {q}")
    assert "dobleamarilla.com.ar" in q
    print("   ✅ Format OK")
    
    # Test Scotland
    q = p._build_insider_query("Celtic", "injury", "soccer_spl")
    print(f"\n🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland Query:")
    print(f"   {q}")
    assert "dailyrecord.co.uk" in q
    print("   ✅ Format OK")
    
    # Test unknown league (no dorking)
    q = p._build_insider_query("Manchester United", "injury", "soccer_epl")
    print(f"\n🏴󠁧󠁢󠁥󠁮󠁧󠁿 Unknown League Query (no dorking):")
    print(f"   {q}")
    assert "site:" not in q, "Unknown league should not have site dorking"
    print("   ✅ No dorking for unknown league")


def test_domain_format():
    """Verify domains don't have protocols or paths."""
    print("\n🔍 Domain Format Check:")
    
    for league, domains in LEAGUE_DOMAINS.items():
        for domain in domains:
            assert not domain.startswith("http"), f"Domain {domain} has protocol prefix!"
            assert "/" not in domain, f"Domain {domain} has path!"
        print(f"   ✅ {league}: {len(domains)} domains OK")


def test_edge_cases():
    """Test edge cases."""
    p = SearchProvider()
    
    print("\n⚠️ Edge Cases:")
    
    # Empty team
    q = p._build_insider_query("", "injury", "soccer_turkey_super_league")
    print(f"   Empty team: {q[:50]}...")
    assert '""' in q, "Empty team should still be quoted"
    print("   ✅ Empty team handled")
    
    # None league_key
    q = p._build_insider_query("Test", "injury", None)
    print(f"   None league: {q[:50]}...")
    assert "site:" not in q, "None league should not have dorking"
    print("   ✅ None league handled")


if __name__ == "__main__":
    print("=" * 60)
    print("🔍 INSIDER DORKING QUERY TEST")
    print("=" * 60)
    
    test_domain_format()
    test_query_format()
    test_edge_cases()
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
