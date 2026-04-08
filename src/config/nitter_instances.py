"""
Nitter Instance Configuration
==============================
List of working public Nitter instances for the Instance Pool Manager.

These instances are used by the NitterPool to rotate through available
instances when fetching Twitter/X content, helping to avoid 403 errors
and rate limiting.
"""

# List of working public Nitter instances (V14.0 COVE FIX: Removed 6 dead instances)
# Verified alive per status.d420.de monitoring (2026-04-06):
# - nitter.net (NL, latest 2026.03.31), nitter.space (US, outdated),
# - nitter.tiekoetter.com (DE), nuku.trabun.org (CL), nitter.catsarch.com (US/DE)
# - nitter.privacyredirect.com (FI, Anubis-protected), lightbrd.com (TR, NSFW)
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://xcancel.com",
    "https://nitter.privacyredirect.com",
    "https://lightbrd.com",
    "https://nitter.space",
    "https://nitter.tiekoetter.com",
    "https://nuku.trabun.org",
    "https://nitter.catsarch.com",
]

# REMOVED dead instances (2026-04-07 COVE FIX):
# - nitter.kuuro.net: 403 Forbidden
# - nitter.privacydev.net: Connection refused
# - nitter.hostux.net: Connection refused
# - nitter.at: Connection refused
# - nt.ggtyler.dev: Connection refused
# - nitter.private.coffee: Connection refused

# Circuit breaker configuration
CIRCUIT_BREAKER_CONFIG = {
    "failure_threshold": 3,  # Number of consecutive failures before opening circuit
    "recovery_timeout": 600,  # Seconds to wait before attempting recovery (10 minutes)
    "half_open_max_calls": 1,  # Number of calls allowed in HALF_OPEN state
}

# FIX #2: VPS Timeout Handling - Distinguish between transient and permanent failures
# Transient errors (network issues, temporary timeouts) should have higher threshold
# Permanent errors (403, 429, blocked) should use standard threshold
TRANSIENT_ERROR_CONFIG = {
    "failure_threshold": 5,  # Higher threshold for transient errors (VPS network instability)
    "recovery_timeout": 300,  # Shorter recovery timeout for transient errors (5 minutes)
    "error_types": [
        "TimeoutError",
        "asyncio.TimeoutError",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "ConnectionAbortedError",
    ],
}

# Round-robin configuration
ROUND_ROBIN_CONFIG = {
    "initial_index": 0,  # Starting index for round-robin rotation
}
