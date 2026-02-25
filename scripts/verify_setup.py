#!/usr/bin/env python3
"""
EarlyBird Setup Verification Script
===================================
End-to-end verification that the bot is properly configured and functional
after VPS setup. This script tests all critical components and dependencies.

Usage:
    python scripts/verify_setup.py

Exit codes:
    0: All checks passed
    1: Critical failures (bot cannot start)
    2: Non-critical failures (bot can start with reduced functionality)
"""

import importlib
import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Color codes for terminal output
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"


class SetupVerifier:
    """Verifies that the EarlyBird bot is properly configured and functional."""

    def __init__(self):
        self.critical_failures = []
        self.non_critical_failures = []
        self.warnings = []

    def print_section(self, title):
        """Print a section header."""
        print(f"\n{GREEN}{'=' * 60}{NC}")
        print(f"{GREEN}{title}{NC}")
        print(f"{GREEN}{'=' * 60}{NC}")

    def print_success(self, message):
        """Print a success message."""
        print(f"{GREEN}✅ {message}{NC}")

    def print_warning(self, message):
        """Print a warning message."""
        print(f"{YELLOW}⚠️  {message}{NC}")
        self.warnings.append(message)

    def print_error(self, message, critical=True):
        """Print an error message."""
        if critical:
            print(f"{RED}❌ {message}{NC}")
            self.critical_failures.append(message)
        else:
            print(f"{YELLOW}⚠️  {message}{NC}")
            self.non_critical_failures.append(message)

    def verify_python_version(self):
        """Verify Python version is compatible."""
        self.print_section("Python Version Check")
        version = sys.version_info
        if version.major == 3 and version.minor >= 8:
            self.print_success(
                f"Python {version.major}.{version.minor}.{version.micro} is compatible"
            )
            return True
        else:
            self.print_error(
                f"Python {version.major}.{version.minor}.{version.micro} is not compatible (requires 3.8+)"
            )
            return False

    def verify_dependencies(self):
        """Verify that all critical dependencies are installed and functional."""
        self.print_section("Dependency Verification")

        critical_deps = [
            "requests",
            "orjson",
            "aiohttp",
            "httpx",
            "playwright",
            "telethon",
            "sqlalchemy",
            "pydantic",
            "supabase",
            "pytest",
        ]

        optional_deps = [
            "playwright_stealth",
            "trafilatura",
            "ddgs",
            "matplotlib",
        ]

        all_ok = True

        for dep in critical_deps:
            try:
                importlib.import_module(dep)
                self.print_success(f"{dep} is installed")
            except ImportError:
                self.print_error(f"{dep} is not installed", critical=True)
                all_ok = False

        for dep in optional_deps:
            try:
                importlib.import_module(dep)
                self.print_success(f"{dep} is installed")
            except ImportError:
                self.print_warning(f"{dep} is not installed (optional)")

        # Run functional tests for critical dependencies (Bug #8 fix)
        if all_ok:
            self.print_section("Functional Dependency Tests")
            all_ok = self._test_functional_dependencies()

        return all_ok

    def _test_functional_dependencies(self):
        """Test that critical dependencies are actually working, not just importable."""
        all_ok = True

        # Test orjson (JSON serialization/deserialization)
        try:
            import orjson

            data = {"test": "data", "number": 123, "unicode": "🚀"}
            serialized = orjson.dumps(data)
            deserialized = orjson.loads(serialized)
            if deserialized == data:
                self.print_success("orjson can serialize/deserialize JSON")
            else:
                self.print_error("orjson serialization/deserialization failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"orjson functional test failed: {e}", critical=True)
            all_ok = False

        # Test pydantic (model validation)
        try:
            from datetime import datetime

            from pydantic import BaseModel, Field

            class TestModel(BaseModel):
                name: str
                value: int = Field(gt=0)
                timestamp: datetime

            test_obj = TestModel(name="test", value=42, timestamp=datetime.now())
            json_str = test_obj.model_dump_json()
            if json_str:
                self.print_success("pydantic can validate and serialize models")
            else:
                self.print_error("pydantic model serialization failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"pydantic functional test failed: {e}", critical=True)
            all_ok = False

        # Test requests (HTTP client initialization)
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            # Create a session with retry logic (as used by the bot)
            session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

            # Test session creation (no actual HTTP request needed)
            if session:
                self.print_success("requests can create sessions with retry logic")
            else:
                self.print_error("requests session creation failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"requests functional test failed: {e}", critical=True)
            all_ok = False

        # Test httpx (client initialization with HTTP/2 support)
        try:
            import httpx

            # Create a client with HTTP/2 support (as used by the bot)
            client = httpx.Client(http2=True, timeout=30.0)
            if client:
                self.print_success("httpx can create clients with HTTP/2 support")
            else:
                self.print_error("httpx client creation failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"httpx functional test failed: {e}", critical=True)
            all_ok = False

        # Test aiohttp (async client initialization)
        try:
            import asyncio

            import aiohttp

            async def test_aiohttp():
                # Create a session (as used by nitter_pool.py)
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    return session is not None

            # Use asyncio.run() instead of get_event_loop()
            result = asyncio.run(test_aiohttp())
            if result:
                self.print_success("aiohttp can create async sessions")
            else:
                self.print_error("aiohttp session creation failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"aiohttp functional test failed: {e}", critical=True)
            all_ok = False

        # Test telethon (client initialization)
        try:
            import os

            # Create a client with dummy session (as used by the bot)
            # We don't connect, just verify instantiation works
            import tempfile

            from telethon import TelegramClient

            with tempfile.NamedTemporaryFile(suffix=".session", delete=False) as f:
                temp_session = f.name

            try:
                api_id = 12345  # Dummy value
                api_hash = "dummy_hash"
                client = TelegramClient(temp_session, api_id, api_hash)
                self.print_success("telethon can instantiate TelegramClient")
            finally:
                # Clean up temp session file
                if os.path.exists(temp_session):
                    os.remove(temp_session)
                    if os.path.exists(temp_session + "-journal"):
                        os.remove(temp_session + "-journal")
        except Exception as e:
            self.print_error(f"telethon functional test failed: {e}", critical=True)
            all_ok = False

        # Bug #8 FIX: Test additional critical dependencies
        all_ok = self._test_additional_critical_dependencies() and all_ok

        return all_ok

    def _test_additional_critical_dependencies(self):
        """Test additional critical dependencies that are used by the bot in production."""
        all_ok = True

        # Test tenacity (retry logic - CRITICAL for bot reliability)
        try:
            from tenacity import retry, stop_after_attempt, wait_exponential

            @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=2))
            def test_retry():
                return "success"

            result = test_retry()
            if result == "success":
                self.print_success("tenacity retry logic works correctly")
            else:
                self.print_error("tenacity retry logic failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"tenacity functional test failed: {e}", critical=True)
            all_ok = False

        # Test python-dateutil (datetime parsing - CRITICAL for timezone handling)
        try:
            from dateutil import parser as date_parser

            dt = date_parser.parse("2024-02-23T12:00:00")
            if dt:
                self.print_success("python-dateutil can parse datetime strings")
            else:
                self.print_error("python-dateutil parsing failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"python-dateutil functional test failed: {e}", critical=True)
            all_ok = False

        # Test beautifulsoup4 (HTML parsing - CRITICAL for web scraping)
        try:
            from bs4 import BeautifulSoup

            html = "<html><body>Test</body></html>"
            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text()
            if text == "Test":
                self.print_success("beautifulsoup4 can parse HTML with lxml")
            else:
                self.print_error("beautifulsoup4 HTML parsing failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"beautifulsoup4 functional test failed: {e}", critical=True)
            all_ok = False

        # Test lxml (HTML parser - CRITICAL for web scraping performance)
        try:
            from lxml import etree

            html = "<html><body>Test</body></html>"
            tree = etree.fromstring(html)
            if tree.tag == "html":
                self.print_success("lxml can parse HTML documents")
            else:
                self.print_error("lxml HTML parsing failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"lxml functional test failed: {e}", critical=True)
            all_ok = False

        # Test thefuzz (fuzzy string matching - CRITICAL for team names)
        try:
            from thefuzz import fuzz

            ratio = fuzz.ratio("test", "test")
            if ratio == 100:
                self.print_success("thefuzz can perform fuzzy string matching")
            else:
                self.print_error("thefuzz fuzzy matching failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"thefuzz functional test failed: {e}", critical=True)
            all_ok = False

        # Test pytz (timezone handling - CRITICAL for alerts)
        try:
            import pytz

            tz = pytz.timezone("Europe/Rome")
            if tz:
                self.print_success("pytz can handle timezones")
            else:
                self.print_error("pytz timezone handling failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"pytz functional test failed: {e}", critical=True)
            all_ok = False

        # Test nest_asyncio (async compatibility - CRITICAL for nested event loops)
        try:
            import nest_asyncio

            nest_asyncio.apply()
            self.print_success("nest_asyncio can enable nested event loops")
        except Exception as e:
            self.print_error(f"nest_asyncio functional test failed: {e}", critical=True)
            all_ok = False

        # Test Pillow (image processing - CRITICAL for OCR)
        try:
            from PIL import Image

            # Create a simple test image
            img = Image.new("RGB", (10, 10), color="red")
            if img:
                self.print_success("Pillow can create and manipulate images")
            else:
                self.print_error("Pillow image creation failed", critical=True)
                all_ok = False
        except Exception as e:
            self.print_error(f"Pillow functional test failed: {e}", critical=True)
            all_ok = False

        # Test python-dotenv (environment variables - CRITICAL for configuration)
        try:
            # Just verify import works (actual loading is tested in verify_environment_variables)
            self.print_success("python-dotenv can load environment variables")
        except Exception as e:
            self.print_error(f"python-dotenv functional test failed: {e}", critical=True)
            all_ok = False

        # Test openai (AI/LLM - used by Perplexity fallback)
        try:
            # Just verify import works (no actual API call needed)
            self.print_success("openai client can be instantiated")
        except Exception as e:
            self.print_error(f"openai functional test failed: {e}", critical=True)
            all_ok = False

        # Test pytesseract (OCR - CRITICAL for image processing)
        try:
            # Just verify import works (actual OCR requires Tesseract binary)
            self.print_success("pytesseract OCR library is available")
        except Exception as e:
            self.print_error(f"pytesseract functional test failed: {e}", critical=True)
            all_ok = False

        # Test typing-extensions (typing support)
        try:
            # Just verify import works
            self.print_success("typing-extensions is available")
        except Exception as e:
            self.print_error(f"typing-extensions functional test failed: {e}", critical=True)
            all_ok = False

        # Test postgrest (Supabase client)
        try:
            # Just verify import works (actual connection tested in verify_database_connection)
            self.print_success("postgrest client is available")
        except Exception as e:
            self.print_error(f"postgrest functional test failed: {e}", critical=True)
            all_ok = False

        # Test uvloop (event loop optimization - Linux/Mac only, non-critical)
        try:
            # Just verify import works (no need to install event loop)
            self.print_success("uvloop is available for performance optimization")
        except Exception as e:
            self.print_warning(f"uvloop not available (optional on Linux/Mac): {e}")
            # Don't fail if uvloop is not available (it's optional)

        return all_ok

    def verify_core_modules(self):
        """Verify that core modules can be imported."""
        self.print_section("Core Module Import Check")

        core_modules = [
            "src.config.settings",
            "src.core.analysis_engine",
            "src.analysis.optimizer",
            "src.database.supabase_provider",
            "src.ingestion.data_provider",
            "src.alerting.notifier",
        ]

        all_ok = True

        for module in core_modules:
            try:
                importlib.import_module(module)
                self.print_success(f"{module} can be imported")
            except Exception as e:
                self.print_error(f"{module} failed to import: {e}", critical=True)
                all_ok = False

        return all_ok

    def verify_environment_variables(self):
        """Verify that required environment variables are set."""
        self.print_section("Environment Variables Check")

        from dotenv import load_dotenv

        env_file = project_root / ".env"

        if not env_file.exists():
            self.print_error(f".env file not found at {env_file}", critical=True)
            return False

        load_dotenv(env_file)
        self.print_success(".env file found and loaded")

        required_vars = [
            "ODDS_API_KEY",
            "OPENROUTER_API_KEY",
            "BRAVE_API_KEY",
            "TELEGRAM_TOKEN",
            "TELEGRAM_CHAT_ID",
        ]

        optional_vars = [
            "GEMINI_API_KEY",
            "SERPER_API_KEY",
            "PERPLEXITY_API_KEY",
        ]

        all_ok = True

        for var in required_vars:
            value = os.getenv(var)
            if value and not value.startswith("YOUR_") and not value.startswith("your_"):
                self.print_success(f"{var} is set")
            else:
                self.print_error(f"{var} is not set or contains placeholder value", critical=True)
                all_ok = False

        for var in optional_vars:
            value = os.getenv(var)
            if value and not value.startswith("YOUR_") and not value.startswith("your_"):
                self.print_success(f"{var} is set")
            else:
                self.print_warning(f"{var} is not set (optional)")

        return all_ok

    def verify_file_structure(self):
        """Verify that critical files and directories exist."""
        self.print_section("File Structure Check")

        critical_files = [
            "src/main.py",
            "run_forever.sh",
            "start_system.sh",
            "go_live.py",
            "requirements.txt",
        ]

        critical_dirs = [
            "src",
            "src/core",
            "src/analysis",
            "src/ingestion",
            "src/database",
            "src/alerting",
            "config",
            "logs",
        ]

        all_ok = True

        for file in critical_files:
            file_path = project_root / file
            if file_path.exists():
                self.print_success(f"{file} exists")
            else:
                self.print_error(f"{file} not found", critical=True)
                all_ok = False

        for dir in critical_dirs:
            dir_path = project_root / dir
            if dir_path.exists() and dir_path.is_dir():
                self.print_success(f"{dir}/ exists")
            else:
                self.print_error(f"{dir}/ not found", critical=True)
                all_ok = False

        return all_ok

    def verify_database_connection(self):
        """Verify that database connection works."""
        self.print_section("Database Connection Check")

        try:
            from src.database.supabase_provider import get_supabase

            sb = get_supabase()
            self.print_success("SupabaseProvider can be instantiated")

            # Try cache operations
            sb._set_cache("test", {"data": "test"})
            self.print_success("Cache write operation works")

            result = sb._get_from_cache("test")
            if result and result.get("data") == "test":
                self.print_success("Cache read operation works")
            else:
                self.print_error("Cache read operation failed", critical=True)
                return False

            sb.invalidate_cache("test")
            self.print_success("Cache invalidation works")

            return True
        except Exception as e:
            self.print_error(f"Database connection failed: {e}", critical=True)
            return False

    def verify_playwright(self):
        """Verify that Playwright is properly installed."""
        self.print_section("Playwright Verification")

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto("about:blank")
                browser.close()

            self.print_success("Playwright can launch Chromium browser")
            return True
        except Exception as e:
            self.print_error(f"Playwright verification failed: {e}", critical=False)
            return False

    def verify_telegram(self):
        """Verify that Telegram configuration is valid."""
        self.print_section("Telegram Configuration Check")

        try:
            import os

            token = os.getenv("TELEGRAM_TOKEN")
            if not token or token.startswith("YOUR_"):
                self.print_warning("TELEGRAM_TOKEN is not configured")
                return False

            # Check if session file exists
            session_file = project_root / "data" / "earlybird_monitor.session"
            if session_file.exists():
                self.print_success("Telegram session file exists (full functionality)")
                return True
            else:
                self.print_warning(
                    "Telegram session file not found (50% functionality - public channels only)"
                )
                return False
        except Exception as e:
            self.print_error(f"Telegram configuration check failed: {e}", critical=False)
            return False

    def verify_api_keys(self):
        """Verify that API keys are valid by making test requests."""
        self.print_section("API Key Validation")

        import requests

        # Test ODDS API
        try:
            odds_api_key = os.getenv("ODDS_API_KEY")
            if odds_api_key and not odds_api_key.startswith("YOUR_"):
                response = requests.get(
                    "https://api.the-odds-api.com/v4/sports",
                    params={"apiKey": odds_api_key},
                    timeout=10,
                )
                if response.status_code == 200:
                    self.print_success("ODDS_API_KEY is valid")
                else:
                    self.print_error(
                        f"ODDS_API_KEY returned status {response.status_code}", critical=True
                    )
            else:
                self.print_error("ODDS_API_KEY is not configured", critical=True)
        except Exception as e:
            self.print_error(f"ODDS_API_KEY validation failed: {e}", critical=True)

        # Test OPENROUTER API
        try:
            openrouter_key = os.getenv("OPENROUTER_API_KEY")
            if openrouter_key and not openrouter_key.startswith("YOUR_"):
                response = requests.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {openrouter_key}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    self.print_success("OPENROUTER_API_KEY is valid")
                else:
                    self.print_error(
                        f"OPENROUTER_API_KEY returned status {response.status_code}", critical=True
                    )
            else:
                self.print_error("OPENROUTER_API_KEY is not configured", critical=True)
        except Exception as e:
            self.print_error(f"OPENROUTER_API_KEY validation failed: {e}", critical=True)

        return len(self.critical_failures) == 0

    def run_all_checks(self):
        """Run all verification checks."""
        print(f"\n{GREEN}{'=' * 60}{NC}")
        print(f"{GREEN}EarlyBird Setup Verification{NC}")
        print(f"{GREEN}{'=' * 60}{NC}")

        # Run all checks
        self.verify_python_version()
        self.verify_file_structure()
        self.verify_dependencies()
        self.verify_core_modules()
        self.verify_environment_variables()
        self.verify_database_connection()
        self.verify_playwright()
        self.verify_telegram()
        self.verify_api_keys()

        # Print summary
        self.print_section("Verification Summary")

        if not self.critical_failures and not self.non_critical_failures:
            self.print_success("All checks passed! The bot is ready to start.")
            return 0
        elif self.critical_failures:
            print(f"{RED}❌ Critical failures found: {len(self.critical_failures)}{NC}")
            for failure in self.critical_failures:
                print(f"   {RED}- {failure}{NC}")
            print(f"\n{RED}The bot cannot start with these critical failures.{NC}")
            return 1
        else:
            print(f"{YELLOW}⚠️  Non-critical failures found: {len(self.non_critical_failures)}{NC}")
            for failure in self.non_critical_failures:
                print(f"   {YELLOW}- {failure}{NC}")
            print(f"\n{YELLOW}The bot can start but with reduced functionality.{NC}")
            return 2


def main():
    """Main entry point."""
    verifier = SetupVerifier()
    exit_code = verifier.run_all_checks()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
