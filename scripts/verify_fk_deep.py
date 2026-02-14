#!/usr/bin/env python3
"""
Deep Foreign Key Verification Script (CoVe Mode Phase 3)

This script performs deep verification of foreign key relationships:
1. Checks for NULL values in FK columns
2. Verifies all FK references exist
3. Checks for orphaned records
4. Validates data integrity

Author: Database Architect (CoVe Mode)
Date: 2026-02-11
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple, Set
from datetime import datetime

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("ERROR: Supabase client not installed. Run: pip install supabase")
    sys.exit(1)


class DeepFKVerifier:
    """Performs deep verification of foreign key relationships."""
    
    def __init__(self):
        self.client = None
        self.issues = []
        self.warnings = []
        
    def connect(self) -> bool:
        """Connect to Supabase."""
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_KEY", "")
        
        if not supabase_url or not supabase_key:
            print("ERROR: SUPABASE_URL or SUPABASE_KEY not configured in .env")
            return False
        
        try:
            self.client = create_client(supabase_url, supabase_key)
            print(f"✅ Connected to Supabase")
            return True
        except Exception as e:
            print(f"ERROR: Failed to connect to Supabase: {e}")
            return False
    
    def get_all_records(self, table_name: str) -> List[Dict[str, Any]]:
        """Get all records from a table."""
        try:
            # Fetch in batches to handle large tables
            all_records = []
            batch_size = 100
            offset = 0
            
            while True:
                response = self.client.table(table_name).select("*").range(offset, offset + batch_size - 1).execute()
                batch = response.data
                
                if not batch:
                    break
                
                all_records.extend(batch)
                
                if len(batch) < batch_size:
                    break
                
                offset += batch_size
            
            return all_records
        except Exception as e:
            self.issues.append(f"Failed to fetch records from {table_name}: {e}")
            return []
    
    def check_null_values(self, table_name: str, fk_column: str) -> Tuple[int, List[str]]:
        """Check for NULL values in a FK column."""
        records = self.get_all_records(table_name)
        null_count = 0
        null_ids = []
        
        for record in records:
            if record.get(fk_column) is None or record.get(fk_column) == "":
                null_count += 1
                null_ids.append(record.get('id', 'unknown'))
        
        return null_count, null_ids
    
    def check_orphaned_records(self, 
                                child_table: str, 
                                parent_table: str, 
                                fk_column: str) -> Tuple[int, List[Dict[str, Any]]]:
        """Check for orphaned records (FK references that don't exist)."""
        child_records = self.get_all_records(child_table)
        parent_records = self.get_all_records(parent_table)
        
        parent_ids = {p['id'] for p in parent_records}
        
        orphaned = []
        for record in child_records:
            fk_value = record.get(fk_column)
            if fk_value not in parent_ids:
                orphaned.append({
                    'id': record.get('id'),
                    f'{fk_column}': fk_value
                })
        
        return len(orphaned), orphaned
    
    def verify_countries_to_continents(self) -> Dict[str, Any]:
        """Verify countries -> continents FK relationship."""
        print("\n" + "="*60)
        print("🔍 DEEP VERIFICATION: countries -> continents")
        print("="*60)
        
        # Check for NULL continent_id
        null_count, null_ids = self.check_null_values("countries", "continent_id")
        print(f"NULL continent_id values: {null_count}")
        if null_count > 0:
            self.issues.append(f"countries: {null_count} records have NULL continent_id")
            if null_ids:
                self.issues.append(f"  Affected IDs: {null_ids[:10]}")
        
        # Check for orphaned records
        orphaned_count, orphaned = self.check_orphaned_records(
            "countries", "continents", "continent_id"
        )
        print(f"Orphaned records: {orphaned_count}")
        if orphaned_count > 0:
            self.issues.append(f"countries: {orphaned_count} orphaned records (invalid continent_id)")
            if orphaned:
                self.issues.append(f"  Sample orphans: {orphaned[:5]}")
        
        # Get detailed statistics
        countries = self.get_all_records("countries")
        continents = self.get_all_records("continents")
        
        # Count countries per continent
        continent_counts = {}
        for country in countries:
            continent_id = country.get('continent_id')
            if continent_id:
                continent_counts[continent_id] = continent_counts.get(continent_id, 0) + 1
        
        print("\nCountries per continent:")
        for continent in continents:
            cid = continent['id']
            cname = continent['name']
            count = continent_counts.get(cid, 0)
            print(f"  {cname}: {count} countries")
        
        return {
            'null_count': null_count,
            'orphaned_count': orphaned_count,
            'valid': null_count == 0 and orphaned_count == 0
        }
    
    def verify_leagues_to_countries(self) -> Dict[str, Any]:
        """Verify leagues -> countries FK relationship."""
        print("\n" + "="*60)
        print("🔍 DEEP VERIFICATION: leagues -> countries")
        print("="*60)
        
        # Check for NULL country_id
        null_count, null_ids = self.check_null_values("leagues", "country_id")
        print(f"NULL country_id values: {null_count}")
        if null_count > 0:
            self.issues.append(f"leagues: {null_count} records have NULL country_id")
            if null_ids:
                self.issues.append(f"  Affected IDs: {null_ids[:10]}")
        
        # Check for orphaned records
        orphaned_count, orphaned = self.check_orphaned_records(
            "leagues", "countries", "country_id"
        )
        print(f"Orphaned records: {orphaned_count}")
        if orphaned_count > 0:
            self.issues.append(f"leagues: {orphaned_count} orphaned records (invalid country_id)")
            if orphaned:
                self.issues.append(f"  Sample orphans: {orphaned[:5]}")
        
        # Get detailed statistics
        leagues = self.get_all_records("leagues")
        countries = self.get_all_records("countries")
        
        # Count leagues per country
        country_counts = {}
        for league in leagues:
            country_id = league.get('country_id')
            if country_id:
                country_counts[country_id] = country_counts.get(country_id, 0) + 1
        
        print("\nLeagues per country (top 10):")
        sorted_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)
        for country_id, count in sorted_countries[:10]:
            country = next((c for c in countries if c['id'] == country_id), None)
            if country:
                print(f"  {country['name']}: {count} leagues")
        
        # Check for duplicate api_keys
        api_keys = [l['api_key'] for l in leagues]
        unique_keys = set(api_keys)
        if len(api_keys) != len(unique_keys):
            duplicates = [k for k in unique_keys if api_keys.count(k) > 1]
            self.issues.append(f"leagues: Duplicate api_keys found: {duplicates}")
        else:
            print(f"\n✅ All {len(api_keys)} api_keys are unique")
        
        return {
            'null_count': null_count,
            'orphaned_count': orphaned_count,
            'valid': null_count == 0 and orphaned_count == 0
        }
    
    def verify_news_sources_to_leagues(self) -> Dict[str, Any]:
        """Verify news_sources -> leagues FK relationship."""
        print("\n" + "="*60)
        print("🔍 DEEP VERIFICATION: news_sources -> leagues")
        print("="*60)
        
        # Check for NULL league_id
        null_count, null_ids = self.check_null_values("news_sources", "league_id")
        print(f"NULL league_id values: {null_count}")
        if null_count > 0:
            self.issues.append(f"news_sources: {null_count} records have NULL league_id")
            if null_ids:
                self.issues.append(f"  Affected IDs: {null_ids[:10]}")
        
        # Check for orphaned records
        orphaned_count, orphaned = self.check_orphaned_records(
            "news_sources", "leagues", "league_id"
        )
        print(f"Orphaned records: {orphaned_count}")
        if orphaned_count > 0:
            self.issues.append(f"news_sources: {orphaned_count} orphaned records (invalid league_id)")
            if orphaned:
                self.issues.append(f"  Sample orphans: {orphaned[:5]}")
        
        # Get detailed statistics
        news_sources = self.get_all_records("news_sources")
        leagues = self.get_all_records("leagues")
        
        # Count news_sources per league
        league_counts = {}
        for source in news_sources:
            league_id = source.get('league_id')
            if league_id:
                league_counts[league_id] = league_counts.get(league_id, 0) + 1
        
        print("\nNews sources per league (top 10):")
        sorted_leagues = sorted(league_counts.items(), key=lambda x: x[1], reverse=True)
        for league_id, count in sorted_leagues[:10]:
            league = next((l for l in leagues if l['id'] == league_id), None)
            if league:
                print(f"  {league['api_key']}: {count} sources")
        
        # Check for duplicate domains
        domains = [s.get('domain') for s in news_sources if s.get('domain')]
        unique_domains = set(domains)
        if len(domains) != len(unique_domains):
            duplicates = [d for d in unique_domains if domains.count(d) > 1]
            self.issues.append(f"news_sources: Duplicate domains found: {duplicates[:10]}")
        else:
            print(f"\n✅ All {len(domains)} domains are unique")
        
        # Check for empty domains
        empty_domains = [s['id'] for s in news_sources if not s.get('domain')]
        if empty_domains:
            self.issues.append(f"news_sources: {len(empty_domains)} records have empty domain")
            self.issues.append(f"  Affected IDs: {empty_domains[:10]}")
        
        return {
            'null_count': null_count,
            'orphaned_count': orphaned_count,
            'valid': null_count == 0 and orphaned_count == 0
        }
    
    def verify_sqlite_tables(self) -> Dict[str, Any]:
        """Verify SQLite local database tables in detail."""
        print("\n" + "="*60)
        print("🔍 DEEP VERIFICATION: SQLite Database")
        print("="*60)
        
        try:
            import sqlite3
            db_path = Path("data/earlybird.db")
            
            if not db_path.exists():
                self.issues.append(f"SQLite database not found at {db_path}")
                return {'valid': False}
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            results = {}
            
            # Verify each table
            tables_to_check = {
                'matches': 48,
                'team_aliases': 73,
                'odds_snapshots': 0,
                'news_logs': 1,
                'telegram_channels': 0,
                'telegram_message_logs': 0
            }
            
            for table_name, expected_count in tables_to_check.items():
                # Check if table exists
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                if not cursor.fetchone():
                    self.issues.append(f"SQLite.{table_name}: Table does not exist")
                    results[table_name] = {'valid': False}
                    continue
                
                # Get record count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                
                # Get schema
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [col[1] for col in cursor.fetchall()]
                
                print(f"\n{table_name}:")
                print(f"  Records: {count} (expected: {expected_count})")
                print(f"  Columns: {columns}")
                
                valid = count == expected_count
                
                if not valid:
                    self.issues.append(
                        f"SQLite.{table_name}: Expected {expected_count} records, found {count}"
                    )
                
                results[table_name] = {
                    'count': count,
                    'expected': expected_count,
                    'columns': columns,
                    'valid': valid
                }
            
            conn.close()
            
            return {
                'valid': all(r.get('valid', False) for r in results.values()),
                'tables': results
            }
            
        except Exception as e:
            self.issues.append(f"Failed to verify SQLite database: {e}")
            return {'valid': False}
    
    def run_verification(self) -> Dict[str, Any]:
        """Run complete deep verification."""
        print("\n" + "="*80)
        print("🔍 DEEP FOREIGN KEY VERIFICATION (CoVe Mode Phase 3)")
        print("="*80)
        print(f"Timestamp: {datetime.utcnow().isoformat()}")
        
        # Connect to Supabase
        if not self.connect():
            print("\n❌ FAILED: Could not connect to Supabase")
            return {'success': False, 'issues': self.issues}
        
        # Verify each FK relationship
        results = {
            'countries_to_continents': self.verify_countries_to_continents(),
            'leagues_to_countries': self.verify_leagues_to_countries(),
            'news_sources_to_leagues': self.verify_news_sources_to_leagues(),
            'sqlite': self.verify_sqlite_tables()
        }
        
        # Summary
        print("\n" + "="*80)
        print("📊 DEEP VERIFICATION SUMMARY")
        print("="*80)
        
        all_valid = all(
            r.get('valid', False) 
            for r in results.values()
        )
        
        if all_valid:
            print("✅ ALL DEEP VERIFICATIONS PASSED")
        else:
            print("❌ SOME DEEP VERIFICATIONS FAILED")
        
        print(f"\nIssues found: {len(self.issues)}")
        print(f"Warnings: {len(self.warnings)}")
        
        if self.issues:
            print("\n❌ ISSUES:")
            for issue in self.issues:
                print(f"  - {issue}")
        
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        return {
            'success': True,
            'all_valid': all_valid,
            'results': results,
            'issues': self.issues,
            'warnings': self.warnings,
            'timestamp': datetime.utcnow().isoformat()
        }


def main():
    """Main entry point."""
    verifier = DeepFKVerifier()
    results = verifier.run_verification()
    
    # Save results to file
    output_path = Path("docs/SUPABASE_DEEP_FK_VERIFICATION_REPORT.md")
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, 'w') as f:
        f.write("# Deep Foreign Key Verification Report\n\n")
        f.write(f"**Generated**: {results['timestamp']}\n")
        f.write(f"**Status**: {'✅ PASSED' if results['all_valid'] else '❌ FAILED'}\n\n")
        
        f.write("## Verification Results\n\n")
        
        for relation_name, relation_result in results['results'].items():
            status = "✅" if relation_result.get('valid', False) else "❌"
            f.write(f"### {status} {relation_name}\n\n")
            
            if 'null_count' in relation_result:
                f.write(f"- NULL FK values: {relation_result['null_count']}\n")
            if 'orphaned_count' in relation_result:
                f.write(f"- Orphaned records: {relation_result['orphaned_count']}\n")
            if 'tables' in relation_result:
                for tname, tresult in relation_result['tables'].items():
                    tstatus = "✅" if tresult.get('valid', False) else "❌"
                    f.write(f"- {tstatus} {tname}: {tresult.get('count', 'N/A')} records\n")
            
            f.write("\n")
        
        if results['issues']:
            f.write("## Issues\n\n")
            for issue in results['issues']:
                f.write(f"- {issue}\n")
            f.write("\n")
        
        if results['warnings']:
            f.write("## Warnings\n\n")
            for warning in results['warnings']:
                f.write(f"- {warning}\n")
            f.write("\n")
    
    print(f"\n📄 Report saved to: {output_path}")
    
    return 0 if results['all_valid'] else 1


if __name__ == "__main__":
    sys.exit(main())
