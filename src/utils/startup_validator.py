#!/usr/bin/env python3
"""
EarlyBird Startup Validator - Pre-Flight Guard

Validates all environment variables before system startup.
Provides clear, actionable error messages and graceful degradation.

Based on COVE_STARTUP_VALIDATION_ANALYSIS.md Phase 1 & Phase 3 Implementation
"""

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Set

import requests
from dotenv import load_dotenv

# Load .env file from project root
env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)


class ValidationStatus(Enum):
    """Validation result status."""

    READY = "✅ READY"
    FAIL = "❌ FAIL"
    WARN = "⚠️ WARN"


@dataclass
class ValidationResult:
    """Result of validating a single configuration item."""

    key: str
    status: ValidationStatus
    message: str
    is_critical: bool
    is_empty: bool  # Distinguish missing vs empty


@dataclass
class APIConnectivityResult:
    """Result of API connectivity test."""

    api_name: str
    status: ValidationStatus
    response_time_ms: Optional[float]
    quota_info: Optional[str]
    error_message: Optional[str]


@dataclass
class ConfigFileValidationResult:
    """Result of configuration file validation."""

    file_path: str
    status: ValidationStatus
    file_size_bytes: int
    last_modified: Optional[str]
    error_message: Optional[str]


@dataclass
class StartupValidationReport:
    """Complete startup validation report."""

    critical_results: List[ValidationResult]
    optional_results: List[ValidationResult]
    overall_status: ValidationStatus
    summary: str
    api_connectivity_results: List[APIConnectivityResult]
    config_file_results: List[ConfigFileValidationResult]
    disabled_features: Set[str]
    timestamp: str


# Global storage for the most recent validation report
# This allows bot components to access validation results for intelligent decision-making
_global_validation_report: Optional[StartupValidationReport] = None


def get_validation_report() -> Optional[StartupValidationReport]:
    """
    Get the most recent startup validation report.

    Returns:
        StartupValidationReport if validation has been run, None otherwise
    """
    return _global_validation_report


def is_feature_disabled(feature: str) -> bool:
    """
    Check if a feature is disabled based on validation results.

    Args:
        feature: Feature name to check (e.g., 'telegram_monitor', 'perplexity_fallback')

    Returns:
        True if feature is disabled, False otherwise
    """
    report = get_validation_report()
    if report is None:
        return False
    return feature in report.disabled_features


class StartupValidator:
    """
    Centralized startup validator for EarlyBird system.

    Performs pre-flight checks on all environment variables
    and provides clear, actionable error messages.
    """

    # Critical keys - system cannot function without these
    CRITICAL_KEYS = {
        "ODDS_API_KEY": {
            "description": "Odds API (The-Odds-API.com)",
            "validation": lambda v: v and v != "YOUR_ODDS_API_KEY",
            "error_msg": "Odds API key is missing or invalid",
        },
        "OPENROUTER_API_KEY": {
            "description": "OpenRouter API (DeepSeek AI)",
            "validation": lambda v: v and v != "YOUR_OPENROUTER_API_KEY",
            "error_msg": "OpenRouter API key is missing or invalid",
        },
        "BRAVE_API_KEY": {
            "description": "Brave Search API",
            "validation": lambda v: v and v != "YOUR_BRAVE_API_KEY",
            "error_msg": "Brave API key is missing or invalid",
        },
        # SERPER_API_KEY removed - migrating to Brave
        # "SERPER_API_KEY": {
        #     "description": "Serper Search API",
        #     "validation": lambda v: v and v != "YOUR_SERPER_API_KEY",
        #     "error_msg": "Serper API key is missing or invalid",
        # },
        "TELEGRAM_BOT_TOKEN": {
            "description": "Telegram Bot Token",
            "validation": lambda v: v and v != "YOUR_TELEGRAM_BOT_TOKEN",
            "error_msg": "Telegram Bot Token is missing or invalid",
        },
        "TELEGRAM_CHAT_ID": {
            "description": "Telegram Chat ID (Admin)",
            "validation": lambda v: v and v.isdigit(),
            "error_msg": "Telegram Chat ID is missing or invalid",
        },
        "SUPABASE_URL": {
            "description": "Supabase Database URL",
            "validation": lambda v: v and v.startswith("https://"),
            "error_msg": "Supabase URL is missing or invalid",
        },
        "SUPABASE_KEY": {
            "description": "Supabase Database Key",
            "validation": lambda v: v and len(v) > 20,
            "error_msg": "Supabase key is missing or invalid",
        },
    }

    # Optional keys - system can degrade gracefully
    OPTIONAL_KEYS = {
        "TELEGRAM_API_ID": {
            "description": "Telegram API ID (Channel Monitoring)",
            "validation": lambda v: v and v.isdigit(),
            "error_msg": "Telegram API ID is missing - channel monitoring disabled",
            "disable_feature": "telegram_monitor",
        },
        "TELEGRAM_API_HASH": {
            "description": "Telegram API Hash (Channel Monitoring)",
            "validation": lambda v: v and len(v) > 10,
            "error_msg": "Telegram API Hash is missing - channel monitoring disabled",
            "disable_feature": "telegram_monitor",
        },
        "PERPLEXITY_API_KEY": {
            "description": "Perplexity API (Fallback AI Search)",
            "validation": lambda v: v and v != "YOUR_PERPLEXITY_API_KEY",
            "error_msg": "Perplexity API key is missing - using DeepSeek only",
            "disable_feature": "perplexity_fallback",
        },
        "API_FOOTBALL_KEY": {
            "description": "API-Football (Player Intelligence)",
            "validation": lambda v: v and v != "YOUR_API_FOOTBALL_KEY",
            "error_msg": "API-Football key is missing - player stats disabled",
            "disable_feature": "player_intelligence",
        },
        "TAVILY_API_KEY": {
            "description": "Tavily API (Match Enrichment)",
            "validation": lambda v: v and v != "YOUR_TAVILY_API_KEY",
            "error_msg": "Tavily API key is missing - using Brave only",
            "disable_feature": "tavily_enrichment",
        },
    }

    # Configuration files to validate
    CONFIG_FILES = [
        {
            "path": ".env",
            "description": "Environment variables",
            "min_size": 100,  # bytes
            "critical": True,
        },
        {
            "path": "config/settings.py",
            "description": "System settings",
            "min_size": 1000,
            "critical": True,
        },
        {
            "path": "config/news_radar_sources.json",
            "description": "News radar sources",
            "min_size": 100,
            "critical": False,
        },
        {
            "path": "config/browser_sources.json",
            "description": "Browser sources",
            "min_size": 100,
            "critical": False,
        },
    ]

    def __init__(self):
        """Initialize validator."""
        self.disabled_features: Set[str] = set()
        self.api_connectivity_results: List[APIConnectivityResult] = []
        self.config_file_results: List[ConfigFileValidationResult] = []

    def validate_key(self, key: str, config: dict, is_critical: bool) -> ValidationResult:
        """
        Validate a single environment variable.

        Args:
            key: Environment variable name
            config: Configuration dict with validation rules
            is_critical: Whether this is a critical key

        Returns:
            ValidationResult with status and message
        """
        value = os.getenv(key, "")

        # Check if missing (None) vs empty ("")
        is_empty = value == ""
        is_missing = value is None or value == ""

        # Distinguish between missing and empty
        if is_missing:
            status = ValidationStatus.FAIL if is_critical else ValidationStatus.WARN
            message = f"{key}: MISSING from .env"
            is_empty = True  # Treat missing as empty for reporting
        elif is_empty:
            status = ValidationStatus.FAIL if is_critical else ValidationStatus.WARN
            message = f"{key}: PRESENT BUT EMPTY in .env"
        else:
            # Run custom validation
            validation_func = config["validation"]
            if validation_func(value):
                status = ValidationStatus.READY
                message = f"{key}: OK ({config['description']})"
                is_empty = False
            else:
                status = ValidationStatus.FAIL if is_critical else ValidationStatus.WARN
                message = f"{key}: {config['error_msg']}"
                is_empty = True

        # Track disabled features
        if status in (ValidationStatus.WARN, ValidationStatus.FAIL) and not is_critical:
            feature = config.get("disable_feature")
            if feature:
                self.disabled_features.add(feature)

        return ValidationResult(
            key=key,
            status=status,
            message=message,
            is_critical=is_critical,
            is_empty=is_empty,
        )

    def _validate_python_version(self) -> ValidationResult:
        """
        Validate Python version meets minimum requirements.

        EarlyBird requires Python 3.10+ for:
        - str | None type hints (PEP 604)
        - ZoneInfo (Python 3.9+, but 3.10+ required for type hints)

        Returns:
            ValidationResult with status and message
        """
        required_version = (3, 10)
        current_version = sys.version_info[:2]

        if current_version >= required_version:
            return ValidationResult(
                key="PYTHON_VERSION",
                status=ValidationStatus.READY,
                message=f"Python {sys.version.split()[0]}: OK (requires 3.10+)",
                is_critical=True,
                is_empty=False,
            )
        else:
            return ValidationResult(
                key="PYTHON_VERSION",
                status=ValidationStatus.FAIL,
                message=f"Python {sys.version.split()[0]}: FAIL (requires 3.10+ for str | None type hints and ZoneInfo)",
                is_critical=True,
                is_empty=True,
            )

    def test_odds_api_connectivity(self) -> APIConnectivityResult:
        """Test Odds API connectivity and quota."""
        api_key = os.getenv("ODDS_API_KEY", "")

        if not api_key or api_key == "YOUR_ODDS_API_KEY":
            return APIConnectivityResult(
                api_name="Odds API",
                status=ValidationStatus.FAIL,
                response_time_ms=None,
                quota_info=None,
                error_message="API key not configured",
            )

        try:
            start_time = datetime.now()
            url = "https://api.the-odds-api.com/v4/sports"
            params = {"apiKey": api_key}

            response = requests.get(url, params=params, timeout=15)
            response_time = (datetime.now() - start_time).total_seconds() * 1000

            if response.status_code == 401:
                return APIConnectivityResult(
                    api_name="Odds API",
                    status=ValidationStatus.FAIL,
                    response_time_ms=response_time,
                    quota_info=None,
                    error_message="Invalid API key (401 Unauthorized)",
                )

            if response.status_code != 200:
                return APIConnectivityResult(
                    api_name="Odds API",
                    status=ValidationStatus.FAIL,
                    response_time_ms=response_time,
                    quota_info=None,
                    error_message=f"HTTP {response.status_code}",
                )

            # Extract quota info
            used = response.headers.get("x-requests-used", "?")
            remaining = response.headers.get("x-requests-remaining", "?")
            quota_info = f"{used} used, {remaining} remaining"

            return APIConnectivityResult(
                api_name="Odds API",
                status=ValidationStatus.READY,
                response_time_ms=response_time,
                quota_info=quota_info,
                error_message=None,
            )

        except requests.exceptions.Timeout:
            return APIConnectivityResult(
                api_name="Odds API",
                status=ValidationStatus.WARN,
                response_time_ms=None,
                quota_info=None,
                error_message="Connection timeout",
            )
        except Exception as e:
            return APIConnectivityResult(
                api_name="Odds API",
                status=ValidationStatus.FAIL,
                response_time_ms=None,
                quota_info=None,
                error_message=str(e),
            )

    def test_openrouter_api_connectivity(self) -> APIConnectivityResult:
        """Test OpenRouter API connectivity."""
        api_key = os.getenv("OPENROUTER_API_KEY", "")

        if not api_key or "YOUR_" in api_key:
            return APIConnectivityResult(
                api_name="OpenRouter API",
                status=ValidationStatus.FAIL,
                response_time_ms=None,
                quota_info=None,
                error_message="API key not configured",
            )

        try:
            start_time = datetime.now()
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            # Read model from environment variable to avoid hardcoding deprecated models
            model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324")
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "Say OK"}],
                "max_tokens": 10,
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response_time = (datetime.now() - start_time).total_seconds() * 1000

            if response.status_code == 401:
                return APIConnectivityResult(
                    api_name="OpenRouter API",
                    status=ValidationStatus.FAIL,
                    response_time_ms=response_time,
                    quota_info=None,
                    error_message="Invalid API key (401 Unauthorized)",
                )

            if response.status_code != 200:
                return APIConnectivityResult(
                    api_name="OpenRouter API",
                    status=ValidationStatus.FAIL,
                    response_time_ms=response_time,
                    quota_info=None,
                    error_message=f"HTTP {response.status_code}",
                )

            # Extract quota info from headers if available
            quota_info = None
            if "x-ratelimit-remaining" in response.headers:
                remaining = response.headers["x-ratelimit-remaining"]
                quota_info = f"{remaining} requests remaining"

            return APIConnectivityResult(
                api_name="OpenRouter API",
                status=ValidationStatus.READY,
                response_time_ms=response_time,
                quota_info=quota_info,
                error_message=None,
            )

        except requests.exceptions.Timeout:
            return APIConnectivityResult(
                api_name="OpenRouter API",
                status=ValidationStatus.WARN,
                response_time_ms=None,
                quota_info=None,
                error_message="Connection timeout (normal for LLM)",
            )
        except Exception as e:
            return APIConnectivityResult(
                api_name="OpenRouter API",
                status=ValidationStatus.FAIL,
                response_time_ms=None,
                quota_info=None,
                error_message=str(e),
            )

    def test_brave_api_connectivity(self) -> APIConnectivityResult:
        """Test Brave Search API connectivity (supports multiple keys)."""
        # Test all 3 keys
        keys = [
            os.getenv("BRAVE_API_KEY_1", ""),
            os.getenv("BRAVE_API_KEY_2", ""),
            os.getenv("BRAVE_API_KEY_3", ""),
        ]

        working_keys = 0
        total_response_time = 0
        last_error = None

        for i, api_key in enumerate(keys, 1):
            if not api_key or "YOUR_" in api_key or api_key == "":
                continue

            try:
                start_time = datetime.now()
                url = "https://api.search.brave.com/res/v1/web/search"
                headers = {
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                }
                params = {"q": "test", "count": 1}

                response = requests.get(url, headers=headers, params=params, timeout=15)
                response_time = (datetime.now() - start_time).total_seconds() * 1000

                if response.status_code == 200:
                    working_keys += 1
                    total_response_time += response_time
                elif response.status_code == 401:
                    last_error = f"Key {i}: Invalid (401)"
                elif response.status_code == 429:
                    working_keys += 1  # Key exists but rate limited
                    last_error = f"Key {i}: Rate limited (429)"

            except Exception as e:
                last_error = str(e)

        if working_keys == 0:
            return APIConnectivityResult(
                api_name="Brave API",
                status=ValidationStatus.FAIL,
                response_time_ms=None,
                quota_info=None,
                error_message=last_error or "No working keys found",
            )

        avg_response_time = total_response_time / working_keys
        quota_info = f"{working_keys}/3 keys working"

        return APIConnectivityResult(
            api_name="Brave API",
            status=ValidationStatus.READY,
            response_time_ms=avg_response_time,
            quota_info=quota_info,
            error_message=None,
        )

    def test_supabase_connectivity(self) -> APIConnectivityResult:
        """Test Supabase database connectivity."""
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_KEY", "")

        if not supabase_url or not supabase_key:
            return APIConnectivityResult(
                api_name="Supabase",
                status=ValidationStatus.WARN,
                response_time_ms=None,
                quota_info=None,
                error_message="Credentials not configured (optional)",
            )

        try:
            start_time = datetime.now()

            # Simple connection test
            response = requests.get(
                f"{supabase_url}/rest/v1/", headers={"apikey": supabase_key}, timeout=10
            )

            response_time = (datetime.now() - start_time).total_seconds() * 1000

            if response.status_code in [
                200,
                404,
            ]:  # 404 is OK (endpoint doesn't exist but auth works)
                return APIConnectivityResult(
                    api_name="Supabase",
                    status=ValidationStatus.READY,
                    response_time_ms=response_time,
                    quota_info=None,
                    error_message=None,
                )

            return APIConnectivityResult(
                api_name="Supabase",
                status=ValidationStatus.FAIL,
                response_time_ms=response_time,
                quota_info=None,
                error_message=f"HTTP {response.status_code}",
            )

        except Exception as e:
            return APIConnectivityResult(
                api_name="Supabase",
                status=ValidationStatus.FAIL,
                response_time_ms=None,
                quota_info=None,
                error_message=str(e),
            )

    def validate_config_file(self, config: dict) -> ConfigFileValidationResult:
        """
        Validate a configuration file.

        Args:
            config: Configuration dict with file info

        Returns:
            ConfigFileValidationResult with validation status
        """
        file_path = Path(config["path"])

        if not file_path.exists():
            return ConfigFileValidationResult(
                file_path=config["path"],
                status=ValidationStatus.FAIL if config["critical"] else ValidationStatus.WARN,
                file_size_bytes=0,
                last_modified=None,
                error_message=f"File not found: {config['path']}",
            )

        try:
            file_size = file_path.stat().st_size
            last_modified = datetime.fromtimestamp(file_path.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            if file_size < config["min_size"]:
                return ConfigFileValidationResult(
                    file_path=config["path"],
                    status=ValidationStatus.WARN,
                    file_size_bytes=file_size,
                    last_modified=last_modified,
                    error_message=f"File too small ({file_size} < {config['min_size']} bytes)",
                )

            # If it's a JSON file, validate syntax
            if file_path.suffix == ".json":
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        json.load(f)
                except json.JSONDecodeError as e:
                    return ConfigFileValidationResult(
                        file_path=config["path"],
                        status=ValidationStatus.FAIL,
                        file_size_bytes=file_size,
                        last_modified=last_modified,
                        error_message=f"Invalid JSON: {e}",
                    )

            return ConfigFileValidationResult(
                file_path=config["path"],
                status=ValidationStatus.READY,
                file_size_bytes=file_size,
                last_modified=last_modified,
                error_message=None,
            )

        except Exception as e:
            return ConfigFileValidationResult(
                file_path=config["path"],
                status=ValidationStatus.FAIL,
                file_size_bytes=0,
                last_modified=None,
                error_message=str(e),
            )

    def run_api_connectivity_tests(self) -> None:
        """Run all API connectivity tests."""
        print("\n" + "=" * 70)
        print("🌐 API CONNECTIVITY TESTS")
        print("=" * 70)

        # Test APIs in order of importance
        api_tests = [
            self.test_odds_api_connectivity,
            self.test_openrouter_api_connectivity,
            self.test_brave_api_connectivity,
            self.test_supabase_connectivity,
        ]

        for test_func in api_tests:
            result = test_func()
            self.api_connectivity_results.append(result)

            icon = result.status.value[:2]
            time_str = f"{result.response_time_ms:.0f}ms" if result.response_time_ms else "N/A"
            quota_str = f" | {result.quota_info}" if result.quota_info else ""

            print(f"{icon} {result.api_name}: {time_str}{quota_str}")
            if result.error_message:
                print(f"   └─ {result.error_message}")

    def validate_config_files(self) -> None:
        """Validate all configuration files."""
        print("\n" + "=" * 70)
        print("📁 CONFIGURATION FILES")
        print("=" * 70)

        for config in self.CONFIG_FILES:
            result = self.validate_config_file(config)
            self.config_file_results.append(result)

            icon = result.status.value[:2]
            size_str = f"{result.file_size_bytes} bytes" if result.file_size_bytes > 0 else "N/A"
            mod_str = f" | Modified: {result.last_modified}" if result.last_modified else ""

            print(f"{icon} {result.file_path}: {size_str}{mod_str}")
            if result.error_message:
                print(f"   └─ {result.error_message}")

    def validate_all(
        self, include_connectivity: bool = True, include_config_files: bool = True
    ) -> StartupValidationReport:
        """
        Validate all environment variables and optionally run enhanced diagnostics.

        Args:
            include_connectivity: Whether to run API connectivity tests
            include_config_files: Whether to validate configuration files

        Returns:
            StartupValidationReport with complete results
        """
        critical_results: list[str] = []
        optional_results: list[str] = []

        # Validate Python version FIRST (critical for type hints and ZoneInfo)
        python_version_result = self._validate_python_version()
        critical_results.append(python_version_result)

        # Validate critical keys
        for key, config in self.CRITICAL_KEYS.items():
            result = self.validate_key(key, config, is_critical=True)
            critical_results.append(result)

        # Validate optional keys
        for key, config in self.OPTIONAL_KEYS.items():
            result = self.validate_key(key, config, is_critical=False)
            optional_results.append(result)

        # Run enhanced diagnostics if requested
        if include_connectivity:
            self.run_api_connectivity_tests()

        if include_config_files:
            self.validate_config_files()

        # Determine overall status
        critical_failures = [r for r in critical_results if r.status == ValidationStatus.FAIL]
        if critical_failures:
            overall_status = ValidationStatus.FAIL
            summary = (
                f"❌ CRITICAL FAILURES: {len(critical_failures)} critical keys missing/invalid"
            )
        else:
            overall_status = ValidationStatus.READY
            warnings = [r for r in optional_results if r.status == ValidationStatus.WARN]
            if warnings:
                summary = f"⚠️ READY WITH WARNINGS: {len(warnings)} optional features disabled"
            else:
                summary = "✅ READY: All critical keys configured"

        return StartupValidationReport(
            critical_results=critical_results,
            optional_results=optional_results,
            overall_status=overall_status,
            summary=summary,
            api_connectivity_results=self.api_connectivity_results,
            config_file_results=self.config_file_results,
            disabled_features=self.disabled_features,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    def print_handshake_report(self, report: StartupValidationReport) -> None:
        """
        Print human-readable "Handshake Report" to terminal.

        Args:
            report: StartupValidationReport to display
        """
        print("\n" + "=" * 70)
        print("🦅 EARLYBIRD STARTUP VALIDATION - PRE-FLIGHT HANDSHAKE")
        print("=" * 70)
        print(f"📅 Timestamp: {report.timestamp}")

        # Print summary
        print(f"\n{report.summary}\n")

        # Print critical keys
        print("🔴 CRITICAL KEYS (Required for Operation):")
        print("-" * 70)
        for result in report.critical_results:
            icon = result.status.value[:2]  # ✅ or ❌
            print(f"{icon} {result.message}")

        # Print optional keys
        print("\n🟡 OPTIONAL KEYS (Graceful Degradation):")
        print("-" * 70)
        for result in report.optional_results:
            icon = result.status.value[:2]  # ✅ or ⚠️
            print(f"{icon} {result.message}")

        # Print disabled features
        if report.disabled_features:
            print(f"\n⚙️  DISABLED FEATURES: {', '.join(sorted(report.disabled_features))}")

        # Print API connectivity summary
        if report.api_connectivity_results:
            print("\n📊 API CONNECTIVITY SUMMARY:")
            print("-" * 70)
            for result in report.api_connectivity_results:
                icon = result.status.value[:2]
                time_str = f"{result.response_time_ms:.0f}ms" if result.response_time_ms else "N/A"
                quota_str = f" | {result.quota_info}" if result.quota_info else ""
                print(f"{icon} {result.api_name}: {time_str}{quota_str}")
                if result.error_message:
                    print(f"   └─ {result.error_message}")

        # Print config file summary
        if report.config_file_results:
            print("\n📁 CONFIGURATION FILES SUMMARY:")
            print("-" * 70)
            for result in report.config_file_results:
                icon = result.status.value[:2]
                size_str = (
                    f"{result.file_size_bytes} bytes" if result.file_size_bytes > 0 else "N/A"
                )
                mod_str = f" | {result.last_modified}" if result.last_modified else ""
                print(f"{icon} {result.file_path}: {size_str}{mod_str}")
                if result.error_message:
                    print(f"   └─ {result.error_message}")

        print("\n" + "=" * 70)

    def print_detailed_diagnostic_report(self, report: StartupValidationReport) -> None:
        """
        Print detailed diagnostic report with all information.

        Args:
            report: StartupValidationReport to display
        """
        print("\n" + "=" * 70)
        print("🦅 EARLYBIRD DETAILED DIAGNOSTIC REPORT")
        print("=" * 70)
        print(f"📅 Generated: {report.timestamp}")
        print(f"📊 Overall Status: {report.overall_status.value}")

        # Section 1: Environment Variables
        print("\n" + "=" * 70)
        print("🔧 ENVIRONMENT VARIABLES")
        print("=" * 70)

        print("\n🔴 CRITICAL KEYS:")
        print("-" * 70)
        for result in report.critical_results:
            status_color = "✅" if result.status == ValidationStatus.READY else "❌"
            print(f"{status_color} {result.key}")
            print(f"   Status: {result.status.value}")
            print(f"   Message: {result.message}")
            print(f"   Critical: {result.is_critical}")
            print(f"   Empty: {result.is_empty}")
            print()

        print("🟡 OPTIONAL KEYS:")
        print("-" * 70)
        for result in report.optional_results:
            status_color = "✅" if result.status == ValidationStatus.READY else "⚠️"
            print(f"{status_color} {result.key}")
            print(f"   Status: {result.status.value}")
            print(f"   Message: {result.message}")
            print(f"   Critical: {result.is_critical}")
            print(f"   Empty: {result.is_empty}")
            print()

        # Section 2: API Connectivity
        if report.api_connectivity_results:
            print("=" * 70)
            print("🌐 API CONNECTIVITY TESTS")
            print("=" * 70)

            for result in report.api_connectivity_results:
                status_color = (
                    "✅"
                    if result.status == ValidationStatus.READY
                    else ("⚠️" if result.status == ValidationStatus.WARN else "❌")
                )
                print(f"{status_color} {result.api_name}")
                print(f"   Status: {result.status.value}")
                print(
                    f"   Response Time: {result.response_time_ms:.2f}ms"
                    if result.response_time_ms
                    else "   Response Time: N/A"
                )
                if result.quota_info:
                    print(f"   Quota Info: {result.quota_info}")
                if result.error_message:
                    print(f"   Error: {result.error_message}")
                print()

        # Section 3: Configuration Files
        if report.config_file_results:
            print("=" * 70)
            print("📁 CONFIGURATION FILES")
            print("=" * 70)

            for result in report.config_file_results:
                status_color = (
                    "✅"
                    if result.status == ValidationStatus.READY
                    else ("⚠️" if result.status == ValidationStatus.WARN else "❌")
                )
                print(f"{status_color} {result.file_path}")
                print(f"   Status: {result.status.value}")
                print(f"   Size: {result.file_size_bytes} bytes")
                if result.last_modified:
                    print(f"   Last Modified: {result.last_modified}")
                if result.error_message:
                    print(f"   Error: {result.error_message}")
                print()

        # Section 4: Disabled Features
        if report.disabled_features:
            print("=" * 70)
            print("⚙️  DISABLED FEATURES")
            print("=" * 70)
            for feature in sorted(report.disabled_features):
                print(f"   • {feature}")
            print()

        # Section 5: Recommendations
        print("=" * 70)
        print("💡 RECOMMENDATIONS")
        print("=" * 70)

        critical_failures = [
            r for r in report.critical_results if r.status == ValidationStatus.FAIL
        ]
        if critical_failures:
            print("\n🔴 CRITICAL ISSUES (Must Fix):")
            for result in critical_failures:
                print(f"   • {result.message}")

        optional_warnings = [
            r for r in report.optional_results if r.status == ValidationStatus.WARN
        ]
        if optional_warnings:
            print("\n🟡 OPTIONAL WARNINGS (Can Ignore):")
            for result in optional_warnings:
                print(f"   • {result.message}")

        api_failures = [
            r for r in report.api_connectivity_results if r.status == ValidationStatus.FAIL
        ]
        if api_failures:
            print("\n🌐 API CONNECTIVITY ISSUES:")
            for result in api_failures:
                print(f"   • {result.api_name}: {result.error_message}")

        config_failures = [
            r for r in report.config_file_results if r.status == ValidationStatus.FAIL
        ]
        if config_failures:
            print("\n📁 CONFIGURATION FILE ISSUES:")
            for result in config_failures:
                print(f"   • {result.file_path}: {result.error_message}")

        if not critical_failures and not api_failures and not config_failures:
            print("\n✅ No critical issues detected. System is ready to launch.")

        print("\n" + "=" * 70)

    def should_exit(self, report: StartupValidationReport) -> bool:
        """
        Determine if system should exit based on validation results.

        Args:
            report: StartupValidationReport to evaluate

        Returns:
            True if system should exit, False otherwise
        """
        return report.overall_status == ValidationStatus.FAIL


def validate_startup(
    include_connectivity: bool = True, include_config_files: bool = True
) -> StartupValidationReport:
    """
    Convenience function to validate startup configuration.

    Args:
        include_connectivity: Whether to run API connectivity tests
        include_config_files: Whether to validate configuration files

    Returns:
        StartupValidationReport with validation results
    """
    validator = StartupValidator()
    report = validator.validate_all(
        include_connectivity=include_connectivity, include_config_files=include_config_files
    )
    validator.print_handshake_report(report)
    return report


def validate_startup_or_exit(
    include_connectivity: bool = True, include_config_files: bool = True
) -> StartupValidationReport:
    """
    Validate startup configuration and exit if critical failures found.

    This is the main entry point for startup validation.
    Call this at the beginning of main() or launcher.py:main()

    Args:
        include_connectivity: Whether to run API connectivity tests
        include_config_files: Whether to validate configuration files

    Returns:
        StartupValidationReport with validation results (for intelligent decision-making)
    """
    validator = StartupValidator()
    report = validator.validate_all(
        include_connectivity=include_connectivity, include_config_files=include_config_files
    )
    validator.print_handshake_report(report)

    # Store report globally for intelligent decision-making
    global _global_validation_report
    _global_validation_report = report

    if validator.should_exit(report):
        print("\n❌ STARTUP ABORTED: Fix critical configuration errors before retrying")
        print("💡 Run 'make check-apis' for detailed API diagnostics")
        print(
            "💡 Run 'python -m src.utils.startup_validator --detailed' for full diagnostic report"
        )
        sys.exit(1)

    print("\n✅ STARTUP VALIDATION PASSED: System ready to launch")
    return report


def validate_startup_detailed() -> None:
    """
    Validate startup configuration and print detailed diagnostic report.

    Use this for comprehensive system diagnostics.
    """
    validator = StartupValidator()
    report = validator.validate_all(include_connectivity=True, include_config_files=True)
    validator.print_detailed_diagnostic_report(report)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="EarlyBird Startup Validator")
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Print detailed diagnostic report instead of handshake report",
    )
    parser.add_argument(
        "--no-connectivity",
        action="store_true",
        help="Skip API connectivity tests",
    )
    parser.add_argument(
        "--no-config-files",
        action="store_true",
        help="Skip configuration file validation",
    )

    args = parser.parse_args()

    if args.detailed:
        validate_startup_detailed()
    else:
        validate_startup_or_exit(
            include_connectivity=not args.no_connectivity,
            include_config_files=not args.no_config_files,
        )
