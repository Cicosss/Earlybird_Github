"""
Nitter Instance Configuration
==============================
List of working public Nitter instances for the Instance Pool Manager.

These instances are used by the NitterPool to rotate through available
instances when fetching Twitter/X content, helping to avoid 403 errors
and rate limiting.
"""

# List of working public Nitter instances
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://xcancel.com",
    "https://nitter.privacyredirect.com",
    "https://lightbrd.com",
    "https://nitter.space",
    "https://nitter.tiekoetter.com",
    "https://nuku.trabun.org",
    "https://nitter.kuuro.net",
    "https://nitter.privacydev.net",
    "https://nitter.hostux.net",
    "https://nitter.at",
    "https://nt.ggtyler.dev",
    "https://nitter.private.coffee",
]

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
