#!/usr/bin/env python3
"""
EarlyBird Version Module - Centralized Version Tracking (V11.1)

This module provides centralized version tracking for entire EarlyBird system.
All modules should import version information from this module to ensure consistency.

Version History:
- V11.1: Centralized version tracking implementation (2026-02-23)
- V11.0: Global Parallel Architecture (2026-02-19)
- V10.5: Previous version with various module-specific versions

Usage:
    from src.version import get_version, get_version_with_module

    # Get global version
    version = get_version()  # Returns "V11.1"

    # Get version with module name
    version_with_module = get_version_with_module("Global Orchestrator")  # Returns "Global Orchestrator V11.1"

Author: Lead Architect
Date: 2026-02-23
"""

from typing import Final

# ============================================
# CENTRALIZED VERSION INFORMATION
# ============================================
VERSION: Final[str] = "V11.1"
VERSION_MAJOR: Final[int] = 11
VERSION_MINOR: Final[int] = 1
VERSION_PATCH: Final[int] = 0  # Reserved for future use

# Version metadata
VERSION_DATE: Final[str] = "2026-02-23"
VERSION_NAME: Final[str] = "Centralized Version Tracking"
VERSION_DESCRIPTION: Final[str] = (
    "Centralized version tracking implementation with unified version number "
    "across all modules for better version management and tracking."
)


def get_version() -> str:
    """
    Get current version string.

    Returns:
        Version string in format "VX.Y" (e.g., "V11.1")
    """
    return VERSION


def get_version_tuple() -> tuple[int, int, int]:
    """
    Get version as a tuple (major, minor, patch).

    Returns:
        Version tuple (e.g., (11, 1, 0))
    """
    return (VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH)


def get_version_dict() -> dict[str, str | int]:
    """
    Get version information as a dictionary.

    Returns:
        Dictionary with version information:
        {
            "version": "V11.1",
            "major": 11,
            "minor": 1,
            "patch": 0,
            "date": "2026-02-23",
            "name": "Centralized Version Tracking",
            "description": "..."
        }
    """
    return {
        "version": VERSION,
        "major": VERSION_MAJOR,
        "minor": VERSION_MINOR,
        "patch": VERSION_PATCH,
        "date": VERSION_DATE,
        "name": VERSION_NAME,
        "description": VERSION_DESCRIPTION,
    }


def get_version_with_module(module_name: str) -> str:
    """
    Get version string with module name prefix.

    This is useful for logging and debugging to identify which module
    is reporting version.

    Args:
        module_name: Name of module (e.g., "Global Orchestrator", "Analysis Engine")

    Returns:
        Version string with module name (e.g., "Global Orchestrator V11.1")
    """
    return f"{module_name} {VERSION}"


def get_version_info() -> str:
    """
    Get a human-readable version information string.

    Returns:
        Multi-line string with version information
    """
    lines = [
        f"EarlyBird Version: {VERSION}",
        f"Release Date: {VERSION_DATE}",
        f"Release Name: {VERSION_NAME}",
        "",
        f"Description: {VERSION_DESCRIPTION}",
    ]
    return "\n".join(lines)


# ============================================
# HISTORICAL MODULE VERSIONS (For Reference)
# ============================================
# These are module-specific versions before centralization.
# They are kept here for historical reference and debugging.
HISTORICAL_MODULE_VERSIONS: Final[dict[str, str]] = {
    "Global Orchestrator": "V11.0",
    "Launcher": "V3.7",
    "Health Monitor": "V3.7",
    "Settlement Service": "V1.0",
    "Betting Quant": "V1.0",
    "Analysis Engine": "V1.0",
    "Notifier": "V8.2",
    "Reporter": "V2.0",
    "Fatigue Engine": "V2.0",
    "Injury Impact Engine": "V1.0",
    "Image OCR": "V4.2",
    "Analyzer": "V3.2",
    "Verification Layer": "V1.0",
    "Optimizer": "V3.0",
    "Alert Feedback Loop": "V1.0",
    "News Scorer": "V8.1",
    "Telegram Trust Score": "V1.0",
    "CLV Tracker": "V5.0",
    "Player Intel": "V2.0",
    "Final Alert Verifier": "V1.0",
    "Pydantic Schemas": "V4.1",
    "Perplexity Schemas": "V1.0",
    "Sources Config": "V4.4",
    "Telegram Listener": "V4.3",
}


def get_historical_version(module_name: str) -> str | None:
    """
    Get historical version of a module before centralization.

    Args:
        module_name: Name of module

    Returns:
        Historical version string (e.g., "V11.0") or None if not found
    """
    return HISTORICAL_MODULE_VERSIONS.get(module_name)


# ============================================
# VERSION COMPARISON UTILITIES
# ============================================
def version_matches(version_string: str) -> bool:
    """
    Check if a version string matches current version.

    Args:
        version_string: Version string to check (e.g., "V11.1", "11.1", "11.1.0")

    Returns:
        True if version matches, False otherwise
    """
    # Normalize version string
    normalized = version_string.replace("V", "").replace("v", "")
    parts = normalized.split(".")

    # Compare with current version
    if len(parts) >= 2:
        try:
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            return (major, minor, patch) == get_version_tuple()
        except (ValueError, IndexError):
            return False
    return False


def is_at_least(major: int, minor: int = 0, patch: int = 0) -> bool:
    """
    Check if current version is at least specified version.

    Args:
        major: Major version to check
        minor: Minor version to check (default: 0)
        patch: Patch version to check (default: 0)

    Returns:
        True if current version >= specified version, False otherwise
    """
    current = get_version_tuple()
    return current >= (major, minor, patch)


# ============================================
# EXPORTS
# ============================================
__all__ = [
    "VERSION",
    "VERSION_MAJOR",
    "VERSION_MINOR",
    "VERSION_PATCH",
    "VERSION_DATE",
    "VERSION_NAME",
    "VERSION_DESCRIPTION",
    "get_version",
    "get_version_tuple",
    "get_version_dict",
    "get_version_with_module",
    "get_version_info",
    "HISTORICAL_MODULE_VERSIONS",
    "get_historical_version",
    "version_matches",
    "is_at_least",
]
