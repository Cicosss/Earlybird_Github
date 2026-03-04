#!/usr/bin/env python3
"""
Script to create the missing mirror file data/supabase_mirror.json
This will enable the fallback mechanism for News Radar.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


def main():
    """Create the mirror file from Supabase."""
    print("=" * 60)
    print("CREATING MIRROR FILE FROM SUPABASE")
    print("=" * 60)

    try:
        from src.database.supabase_provider import SupabaseProvider

        print("\n🔄 Initializing SupabaseProvider...")
        provider = SupabaseProvider()

        if not provider.is_connected():
            print(f"\n❌ Supabase not connected: {provider.get_connection_error()}")
            print("ℹ️  Cannot create mirror without Supabase connection")
            return False

        print("\n✅ Supabase connected")
        print("\n🔄 Creating local mirror...")

        success = provider.create_local_mirror()

        if success:
            print("\n✅ Mirror file created successfully")
            print("📁 Location: data/supabase_mirror.json")

            # Verify file exists
            mirror_path = Path("data/supabase_mirror.json")
            if mirror_path.exists():
                file_size = mirror_path.stat().st_size
                print(f"📊 File size: {file_size} bytes")

                # Read and validate the mirror file
                import json

                with open(mirror_path, "r", encoding="utf-8") as f:
                    mirror_data = json.load(f)

                print("📊 Mirror contents:")
                for key, value in mirror_data.items():
                    if isinstance(value, list):
                        print(f"  - {key}: {len(value)} records")
                    elif isinstance(value, dict):
                        if "tweets" in value:
                            print(f"  - {key}: {len(value.get('tweets', []))} tweets")
                        else:
                            print(f"  - {key}: {len(value)} keys")
                    else:
                        print(f"  - {key}: {type(value).__name__}")

                return True
            else:
                print("\n❌ Mirror file was not created")
                return False
        else:
            print("\n❌ Failed to create mirror file")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
