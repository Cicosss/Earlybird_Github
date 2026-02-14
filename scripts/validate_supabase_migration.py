#!/usr/bin/env python3
"""
Supabase Migration Plan Validation Script (CoVe Mode)

This script performs rigorous validation of the migration plan by:
1. Connecting to Supabase using available credentials
2. Verifying record counts in all tables
3. Validating foreign key relationships
4. Checking schema consistency
5. Comparing with the migration plan document

Author: Database Architect (CoVe Mode)
Date: 2026-02-11
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
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


class SupabaseValidator:
    """Validates Supabase database structure and data against migration plan."""
    
    def __init__(self):
        self.client = None
        self.errors = []
        self.warnings = []
        self.validation_results = {}
        
    def connect(self) -> bool:
        """Connect to Supabase using environment credentials."""
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_KEY", "")
        
        if not supabase_url or not supabase_key:
            self.errors.append("SUPABASE_URL or SUPABASE_KEY not configured in .env")
            return False
        
        try:
            self.client = create_client(supabase_url, supabase_key)
            print(f"✅ Connected to Supabase: {supabase_url[:30]}...")
            return True
        except Exception as e:
            self.errors.append(f"Failed to connect to Supabase: {e}")
            return False
    
    def count_records(self, table_name: str) -> Tuple[int, bool]:
        """Count records in a table."""
        try:
            response = self.client.table(table_name).select("*", count="exact").execute()
            count = response.count if hasattr(response, 'count') else len(response.data)
            return count, True
        except Exception as e:
            self.errors.append(f"Failed to count records in {table_name}: {e}")
            return 0, False
    
    def verify_foreign_key(self, 
                           child_table: str, 
                           parent_table: str, 
                           fk_column: str) -> Tuple[int, int, bool]:
        """
        Verify foreign key relationships.
        Returns: (valid_count, invalid_count, success)
        """
        try:
            # Get all records from child table
            child_response = self.client.table(child_table).select(f"id, {fk_column}").execute()
            child_records = child_response.data
            
            if not child_records:
                return 0, 0, True
            
            # Get all parent IDs
            parent_response = self.client.table(parent_table).select("id").execute()
            parent_ids = {p['id'] for p in parent_response.data}
            
            # Count valid and invalid references
            valid_count = 0
            invalid_count = 0
            invalid_records = []
            
            for record in child_records:
                fk_value = record.get(fk_column)
                if fk_value in parent_ids:
                    valid_count += 1
                else:
                    invalid_count += 1
                    invalid_records.append({
                        'id': record['id'],
                        f'{fk_column}': fk_value
                    })
            
            if invalid_count > 0:
                self.errors.append(
                    f"FK Violation: {child_table}.{fk_column} -> {parent_table}.id: "
                    f"{invalid_count}/{len(child_records)} invalid references"
                )
                if len(invalid_records) <= 10:
                    self.errors.append(f"  Invalid records: {invalid_records}")
            
            return valid_count, invalid_count, True
            
        except Exception as e:
            self.errors.append(f"Failed to verify FK {child_table}.{fk_column} -> {parent_table}: {e}")
            return 0, 0, False
    
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Get schema information for a table."""
        try:
            response = self.client.table(table_name).select("*").limit(1).execute()
            if response.data:
                return {
                    'columns': list(response.data[0].keys()),
                    'sample_record': response.data[0]
                }
            return {'columns': [], 'sample_record': None}
        except Exception as e:
            self.errors.append(f"Failed to get schema for {table_name}: {e}")
            return {'columns': [], 'sample_record': None}
    
    def validate_continents(self) -> Dict[str, Any]:
        """Validate continents table."""
        print("\n" + "="*60)
        print("🌍 VALIDATING: continents")
        print("="*60)
        
        count, success = self.count_records("continents")
        if not success:
            return {'valid': False}
        
        print(f"Record count: {count}")
        
        # Expected: 3 records
        expected_count = 3
        if count != expected_count:
            self.errors.append(
                f"continents: Expected {expected_count} records, found {count}"
            )
        
        # Get schema
        schema = self.get_table_schema("continents")
        print(f"Columns: {schema['columns']}")
        
        # Expected columns
        expected_columns = ['id', 'name', 'active_hours_utc', 'created_at', 'updated_at']
        missing_columns = set(expected_columns) - set(schema['columns'])
        extra_columns = set(schema['columns']) - set(expected_columns)
        
        if missing_columns:
            self.errors.append(f"continents: Missing columns: {missing_columns}")
        if extra_columns:
            self.warnings.append(f"continents: Extra columns: {extra_columns}")
        
        # Check active_hours_utc structure
        if schema['sample_record']:
            active_hours = schema['sample_record'].get('active_hours_utc', [])
            if not isinstance(active_hours, list):
                self.errors.append(
                    f"continents: active_hours_utc should be a list, got {type(active_hours)}"
                )
            else:
                print(f"Sample active_hours_utc: {active_hours}")
        
        return {
            'valid': count == expected_count and not missing_columns,
            'count': count,
            'expected_count': expected_count,
            'schema': schema
        }
    
    def validate_countries(self) -> Dict[str, Any]:
        """Validate countries table."""
        print("\n" + "="*60)
        print("🏳️ VALIDATING: countries")
        print("="*60)
        
        count, success = self.count_records("countries")
        if not success:
            return {'valid': False}
        
        print(f"Record count: {count}")
        
        # Expected: 28 records
        expected_count = 28
        if count != expected_count:
            self.errors.append(
                f"countries: Expected {expected_count} records, found {count}"
            )
        
        # Get schema
        schema = self.get_table_schema("countries")
        print(f"Columns: {schema['columns']}")
        
        # Expected columns
        expected_columns = ['id', 'continent_id', 'name', 'iso_code', 'created_at', 'updated_at']
        missing_columns = set(expected_columns) - set(schema['columns'])
        extra_columns = set(schema['columns']) - set(expected_columns)
        
        if missing_columns:
            self.errors.append(f"countries: Missing columns: {missing_columns}")
        if extra_columns:
            self.warnings.append(f"countries: Extra columns: {extra_columns}")
        
        # Verify FK to continents
        valid_count, invalid_count, fk_success = self.verify_foreign_key(
            "countries", "continents", "continent_id"
        )
        
        print(f"FK to continents: {valid_count}/{count} valid")
        if invalid_count > 0:
            print(f"  ⚠️  {invalid_count} invalid references")
        
        return {
            'valid': count == expected_count and not missing_columns and invalid_count == 0,
            'count': count,
            'expected_count': expected_count,
            'fk_valid': valid_count,
            'fk_invalid': invalid_count,
            'schema': schema
        }
    
    def validate_leagues(self) -> Dict[str, Any]:
        """Validate leagues table."""
        print("\n" + "="*60)
        print("⚽ VALIDATING: leagues")
        print("="*60)
        
        count, success = self.count_records("leagues")
        if not success:
            return {'valid': False}
        
        print(f"Record count: {count}")
        
        # Expected: 56 records
        expected_count = 56
        if count != expected_count:
            self.errors.append(
                f"leagues: Expected {expected_count} records, found {count}"
            )
        
        # Get schema
        schema = self.get_table_schema("leagues")
        print(f"Columns: {schema['columns']}")
        
        # Expected columns
        expected_columns = ['id', 'country_id', 'api_key', 'tier_name', 'priority', 'is_active', 'created_at', 'updated_at']
        missing_columns = set(expected_columns) - set(schema['columns'])
        extra_columns = set(schema['columns']) - set(expected_columns)
        
        if missing_columns:
            self.errors.append(f"leagues: Missing columns: {missing_columns}")
        if extra_columns:
            self.warnings.append(f"leagues: Extra columns: {extra_columns}")
        
        # Verify FK to countries
        valid_count, invalid_count, fk_success = self.verify_foreign_key(
            "leagues", "countries", "country_id"
        )
        
        print(f"FK to countries: {valid_count}/{count} valid")
        if invalid_count > 0:
            print(f"  ⚠️  {invalid_count} invalid references")
        
        # Check api_key uniqueness
        if schema['sample_record']:
            try:
                response = self.client.table("leagues").select("api_key").execute()
                api_keys = [r['api_key'] for r in response.data]
                unique_keys = set(api_keys)
                if len(api_keys) != len(unique_keys):
                    duplicates = [k for k in unique_keys if api_keys.count(k) > 1]
                    self.errors.append(f"leagues: Duplicate api_keys found: {duplicates}")
                else:
                    print(f"✅ All {count} api_keys are unique")
            except Exception as e:
                self.warnings.append(f"Could not check api_key uniqueness: {e}")
        
        return {
            'valid': count == expected_count and not missing_columns and invalid_count == 0,
            'count': count,
            'expected_count': expected_count,
            'fk_valid': valid_count,
            'fk_invalid': invalid_count,
            'schema': schema
        }
    
    def validate_news_sources(self) -> Dict[str, Any]:
        """Validate news_sources table."""
        print("\n" + "="*60)
        print("📰 VALIDATING: news_sources")
        print("="*60)
        
        count, success = self.count_records("news_sources")
        if not success:
            return {'valid': False}
        
        print(f"Record count: {count}")
        
        # Expected: 140 records
        expected_count = 140
        if count != expected_count:
            self.errors.append(
                f"news_sources: Expected {expected_count} records, found {count}"
            )
        
        # Get schema
        schema = self.get_table_schema("news_sources")
        print(f"Columns: {schema['columns']}")
        
        # Expected columns (based on migration plan)
        expected_columns = ['id', 'league_id', 'domain', 'language_iso', 'is_active', 'created_at', 'updated_at']
        missing_columns = set(expected_columns) - set(schema['columns'])
        extra_columns = set(schema['columns']) - set(expected_columns)
        
        if missing_columns:
            self.errors.append(f"news_sources: Missing columns: {missing_columns}")
        if extra_columns:
            self.warnings.append(f"news_sources: Extra columns: {extra_columns}")
        
        # Verify FK to leagues
        valid_count, invalid_count, fk_success = self.verify_foreign_key(
            "news_sources", "leagues", "league_id"
        )
        
        print(f"FK to leagues: {valid_count}/{count} valid")
        if invalid_count > 0:
            print(f"  ⚠️  {invalid_count} invalid references")
        
        return {
            'valid': count == expected_count and not missing_columns and invalid_count == 0,
            'count': count,
            'expected_count': expected_count,
            'fk_valid': valid_count,
            'fk_invalid': invalid_count,
            'schema': schema
        }
    
    def validate_sqlite_tables(self) -> Dict[str, Any]:
        """Validate SQLite local database tables."""
        print("\n" + "="*60)
        print("💾 VALIDATING: SQLite Local Database")
        print("="*60)
        
        try:
            import sqlite3
            db_path = Path("data/earlybird.db")
            
            if not db_path.exists():
                self.errors.append(f"SQLite database not found at {db_path}")
                return {'valid': False}
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"Tables found: {tables}")
            
            results = {}
            
            # Expected tables and their record counts
            expected_tables = {
                'matches': 48,
                'team_aliases': 73,
                'odds_snapshots': 0,
                'news_logs': 1,
                'telegram_channels': 0,
                'telegram_message_logs': 0
            }
            
            for table_name, expected_count in expected_tables.items():
                if table_name in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    print(f"{table_name}: {count} records (expected: {expected_count})")
                    
                    if count != expected_count:
                        self.errors.append(
                            f"SQLite.{table_name}: Expected {expected_count} records, found {count}"
                        )
                    
                    results[table_name] = {
                        'count': count,
                        'expected': expected_count,
                        'valid': count == expected_count
                    }
                else:
                    self.errors.append(f"SQLite.{table_name}: Table not found")
                    results[table_name] = {'valid': False}
            
            conn.close()
            
            return {
                'valid': all(r.get('valid', False) for r in results.values()),
                'tables': results
            }
            
        except Exception as e:
            self.errors.append(f"Failed to validate SQLite database: {e}")
            return {'valid': False}
    
    def compare_with_mirror(self) -> Dict[str, Any]:
        """Compare Supabase data with local mirror."""
        print("\n" + "="*60)
        print("🪞 COMPARING: Supabase vs Mirror")
        print("="*60)
        
        mirror_path = Path("data/supabase_mirror.json")
        
        if not mirror_path.exists():
            self.warnings.append("Mirror file not found at data/supabase_mirror.json")
            return {'valid': False, 'mirror_exists': False}
        
        try:
            with open(mirror_path, 'r') as f:
                mirror_data = json.load(f)
            
            mirror_timestamp = mirror_data.get('timestamp', 'Unknown')
            mirror_version = mirror_data.get('version', 'Unknown')
            mirror_data_content = mirror_data.get('data', {})
            
            print(f"Mirror timestamp: {mirror_timestamp}")
            print(f"Mirror version: {mirror_version}")
            
            results = {}
            
            # Compare each table
            for table_name in ['continents', 'countries', 'leagues', 'news_sources']:
                mirror_count = len(mirror_data_content.get(table_name, []))
                
                # Get Supabase count
                supabase_count, success = self.count_records(table_name)
                
                if success:
                    match = mirror_count == supabase_count
                    status = "✅" if match else "⚠️"
                    print(f"{status} {table_name}: Mirror={mirror_count}, Supabase={supabase_count}")
                    
                    results[table_name] = {
                        'mirror_count': mirror_count,
                        'supabase_count': supabase_count,
                        'match': match
                    }
                else:
                    results[table_name] = {'match': False}
            
            return {
                'valid': all(r.get('match', False) for r in results.values()),
                'mirror_exists': True,
                'tables': results
            }
            
        except Exception as e:
            self.errors.append(f"Failed to compare with mirror: {e}")
            return {'valid': False, 'mirror_exists': False}
    
    def run_validation(self) -> Dict[str, Any]:
        """Run complete validation suite."""
        print("\n" + "="*80)
        print("🔍 SUPABASE MIGRATION PLAN VALIDATION (CoVe Mode)")
        print("="*80)
        print(f"Timestamp: {datetime.utcnow().isoformat()}")
        
        # Connect to Supabase
        if not self.connect():
            print("\n❌ FAILED: Could not connect to Supabase")
            return {'success': False, 'errors': self.errors}
        
        # Validate each table
        results = {
            'continents': self.validate_continents(),
            'countries': self.validate_countries(),
            'leagues': self.validate_leagues(),
            'news_sources': self.validate_news_sources(),
            'sqlite': self.validate_sqlite_tables(),
            'mirror': self.compare_with_mirror()
        }
        
        # Summary
        print("\n" + "="*80)
        print("📊 VALIDATION SUMMARY")
        print("="*80)
        
        all_valid = all(
            r.get('valid', False) 
            for r in results.values() 
            if r not in ['mirror']  # mirror comparison is informational
        )
        
        if all_valid:
            print("✅ ALL VALIDATIONS PASSED")
        else:
            print("❌ SOME VALIDATIONS FAILED")
        
        print(f"\nErrors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")
        
        if self.errors:
            print("\n❌ ERRORS:")
            for error in self.errors:
                print(f"  - {error}")
        
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        return {
            'success': True,
            'all_valid': all_valid,
            'results': results,
            'errors': self.errors,
            'warnings': self.warnings,
            'timestamp': datetime.utcnow().isoformat()
        }


def main():
    """Main entry point."""
    validator = SupabaseValidator()
    results = validator.run_validation()
    
    # Save results to file
    output_path = Path("docs/SUPABASE_MIGRATION_VALIDATION_REPORT.md")
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, 'w') as f:
        f.write("# Supabase Migration Plan Validation Report\n\n")
        f.write(f"**Generated**: {results['timestamp']}\n")
        f.write(f"**Status**: {'✅ PASSED' if results['all_valid'] else '❌ FAILED'}\n\n")
        
        f.write("## Validation Results\n\n")
        
        for table_name, table_result in results['results'].items():
            if table_name == 'mirror':
                continue
            
            status = "✅" if table_result.get('valid', False) else "❌"
            f.write(f"### {status} {table_name}\n\n")
            
            if 'count' in table_result:
                f.write(f"- Records: {table_result['count']} (expected: {table_result.get('expected_count', 'N/A')})\n")
            if 'fk_valid' in table_result:
                f.write(f"- FK Valid: {table_result['fk_valid']}/{table_result['count']}\n")
            if 'fk_invalid' in table_result and table_result['fk_invalid'] > 0:
                f.write(f"- FK Invalid: {table_result['fk_invalid']}\n")
            if 'tables' in table_result:
                for tname, tresult in table_result['tables'].items():
                    tstatus = "✅" if tresult.get('valid', False) else "❌"
                    f.write(f"- {tstatus} {tname}: {tresult.get('count', 'N/A')} records\n")
            
            f.write("\n")
        
        if results['errors']:
            f.write("## Errors\n\n")
            for error in results['errors']:
                f.write(f"- {error}\n")
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
