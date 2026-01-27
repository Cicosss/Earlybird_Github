"""
EarlyBird Browser Fingerprint Manager

Sophisticated browser fingerprinting for anti-detection.
Rotates User-Agent and correlated headers to avoid rate limiting.

Features:
- 5+ distinct browser profiles (Chrome, Firefox, Safari, Edge)
- Correlated headers (UA + Sec-Fetch-* + Accept-Language)
- Auto-rotation every 8-25 requests (randomized threshold)
- Immediate rotation on 403/429 errors
- Thread-safe for concurrent use

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""
import logging
import random
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BrowserProfile:
    """
    Complete browser fingerprint profile.
    
    All headers are correlated to appear as a real browser.
    Chrome/Edge profiles include Sec-Ch-Ua headers.
    Firefox/Safari profiles omit Chrome-specific headers.
    """
    name: str
    user_agent: str
    accept_language: str
    accept_encoding: str
    sec_fetch_dest: str
    sec_fetch_mode: str
    sec_fetch_site: str
    sec_ch_ua: Optional[str] = None  # Chrome/Edge only
    sec_ch_ua_mobile: Optional[str] = None
    sec_ch_ua_platform: Optional[str] = None
    dnt: str = "1"  # Do Not Track


# ============================================
# BROWSER PROFILES (5+ distinct profiles)
# Updated Dec 2024 - Modern browser versions
# ============================================
BROWSER_PROFILES: List[BrowserProfile] = [
    # Chrome 131 - Windows (most common)
    BrowserProfile(
        name="chrome_win_131",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Windows"',
    ),
    # Firefox 133 - Windows
    BrowserProfile(
        name="firefox_win_133",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
        accept_language="en-US,en;q=0.5",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
        # Firefox does NOT send Sec-Ch-Ua headers
    ),
    # Safari 17.2 - macOS
    BrowserProfile(
        name="safari_mac_17",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
        # Safari does NOT send Sec-Ch-Ua headers
    ),
    # Edge 131 - Windows
    BrowserProfile(
        name="edge_win_131",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
        sec_ch_ua='"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Windows"',
    ),
    # Chrome 131 - Linux
    BrowserProfile(
        name="chrome_linux_131",
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Linux"',
    ),
    # Chrome 131 - macOS (additional profile for diversity)
    BrowserProfile(
        name="chrome_mac_131",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"macOS"',
    ),
]


class BrowserFingerprint:
    """
    Manages browser fingerprint rotation for anti-detection.
    
    Features:
    - 5+ distinct browser profiles with correlated headers
    - Auto-rotation every 8-25 requests (randomized)
    - Immediate rotation on 403/429 errors
    - Thread-safe for concurrent use
    
    Usage:
        fingerprint = BrowserFingerprint()
        headers = fingerprint.get_headers()  # Returns complete header dict
        fingerprint.force_rotate()  # Call on 403/429 errors
    """
    
    # Minimum rotation threshold
    MIN_ROTATION_THRESHOLD = 8
    MAX_ROTATION_THRESHOLD = 25
    
    def __init__(self):
        self._current_profile: Optional[BrowserProfile] = None
        self._request_count: int = 0
        self._rotation_threshold: int = self._new_threshold()
        self._lock: threading.Lock = threading.Lock()
        self._rotation_count: int = 0
        
        # V7.2: Domain-sticky profiles for session consistency
        # Maps domain -> BrowserProfile (persistent per domain)
        self._domain_profiles: Dict[str, BrowserProfile] = {}
        self._domain_request_counts: Dict[str, int] = {}
        
        # Select initial profile
        self._current_profile = random.choice(BROWSER_PROFILES)
        logger.debug(f"🎭 Fingerprint initialized with profile: {self._current_profile.name}")
    
    def _new_threshold(self) -> int:
        """Generate new random rotation threshold."""
        return random.randint(self.MIN_ROTATION_THRESHOLD, self.MAX_ROTATION_THRESHOLD)
    
    def _should_rotate(self) -> bool:
        """Check if rotation threshold reached."""
        return self._request_count >= self._rotation_threshold
    
    def _select_new_profile(self) -> BrowserProfile:
        """Select a different profile than current."""
        available = [p for p in BROWSER_PROFILES if p.name != self._current_profile.name]
        if not available:
            # Fallback if only one profile (shouldn't happen)
            return random.choice(BROWSER_PROFILES)
        return random.choice(available)
    
    def _rotate(self, reason: str = "threshold"):
        """
        Rotate to a new browser profile.
        
        Args:
            reason: Why rotation occurred (for logging)
        """
        old_profile = self._current_profile.name if self._current_profile else "none"
        self._current_profile = self._select_new_profile()
        self._request_count = 0
        self._rotation_threshold = self._new_threshold()
        self._rotation_count += 1
        
        logger.info(
            f"🔄 Fingerprint rotated ({reason}): {old_profile} → {self._current_profile.name} "
            f"(next rotation in ~{self._rotation_threshold} requests)"
        )
    
    def _build_headers_from_profile(self, profile: BrowserProfile) -> Dict[str, str]:
        """
        Build headers dict from a BrowserProfile.
        
        Args:
            profile: BrowserProfile to build headers from
            
        Returns:
            Dict with all browser headers
        """
        headers = {
            "User-Agent": profile.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": profile.accept_language,
            "Accept-Encoding": profile.accept_encoding,
            "Sec-Fetch-Dest": profile.sec_fetch_dest,
            "Sec-Fetch-Mode": profile.sec_fetch_mode,
            "Sec-Fetch-Site": profile.sec_fetch_site,
            "DNT": profile.dnt,
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        # Add Chrome/Edge specific headers if present
        if profile.sec_ch_ua:
            headers["Sec-Ch-Ua"] = profile.sec_ch_ua
        if profile.sec_ch_ua_mobile:
            headers["Sec-Ch-Ua-Mobile"] = profile.sec_ch_ua_mobile
        if profile.sec_ch_ua_platform:
            headers["Sec-Ch-Ua-Platform"] = profile.sec_ch_ua_platform
        
        return headers

    def get_headers(self) -> Dict[str, str]:
        """
        Get complete headers for current profile, rotating if needed.
        
        Thread-safe. Automatically rotates when threshold reached.
        
        Returns:
            Dict with all browser headers (User-Agent, Accept-*, Sec-Fetch-*, etc.)
        """
        with self._lock:
            # Check if rotation needed
            if self._should_rotate():
                self._rotate(reason="threshold")
            
            # Increment request count
            self._request_count += 1
            
            profile = self._current_profile
        
        return self._build_headers_from_profile(profile)
    
    def get_headers_for_domain(self, domain: str) -> Dict[str, str]:
        """
        V7.2: Get headers with domain-sticky fingerprint.
        
        Maintains consistent fingerprint per domain to avoid detection by sites
        that track session consistency. The same domain always gets the same
        browser profile, making the client appear as a consistent user.
        
        Thread-safe. Does NOT auto-rotate - profile is sticky per domain.
        
        Args:
            domain: Domain name (e.g., "example.com", "news.site.org")
            
        Returns:
            Dict with all browser headers, consistent for this domain
        """
        if not domain:
            # Fallback to regular rotation if no domain provided
            return self.get_headers()
        
        # Normalize domain (lowercase, strip whitespace)
        domain = domain.lower().strip()
        
        with self._lock:
            # Assign a profile to this domain if not already assigned
            if domain not in self._domain_profiles:
                # Select a profile different from recently used ones if possible
                used_profiles = set(p.name for p in self._domain_profiles.values())
                available = [p for p in BROWSER_PROFILES if p.name not in used_profiles]
                
                if not available:
                    # All profiles in use, just pick randomly
                    available = BROWSER_PROFILES
                
                self._domain_profiles[domain] = random.choice(available)
                self._domain_request_counts[domain] = 0
                logger.debug(f"🎭 Domain {domain} assigned profile: {self._domain_profiles[domain].name}")
            
            # Increment domain request count (for stats)
            self._domain_request_counts[domain] = self._domain_request_counts.get(domain, 0) + 1
            
            profile = self._domain_profiles[domain]
        
        return self._build_headers_from_profile(profile)
    
    def force_rotate_domain(self, domain: str) -> None:
        """
        V7.2: Force rotation for a specific domain (on 403/429 errors).
        
        Thread-safe. Assigns a new profile to the domain.
        
        Args:
            domain: Domain to rotate profile for
        """
        if not domain:
            return
        
        domain = domain.lower().strip()
        
        with self._lock:
            old_profile = self._domain_profiles.get(domain)
            old_name = old_profile.name if old_profile else "none"
            
            # Select a different profile
            available = [p for p in BROWSER_PROFILES if not old_profile or p.name != old_profile.name]
            if not available:
                available = BROWSER_PROFILES
            
            self._domain_profiles[domain] = random.choice(available)
            self._domain_request_counts[domain] = 0
            
            logger.info(f"🔄 Domain {domain} fingerprint rotated: {old_name} → {self._domain_profiles[domain].name}")
    
    def force_rotate(self):
        """
        Force immediate rotation (called on 403/429 errors).
        
        Thread-safe. Resets request count and generates new threshold.
        """
        with self._lock:
            self._rotate(reason="error_triggered")
    
    def get_current_profile_name(self) -> str:
        """Get name of current profile (for logging)."""
        with self._lock:
            return self._current_profile.name if self._current_profile else "unknown"
    
    def get_stats(self) -> Dict:
        """Get fingerprint statistics for monitoring."""
        with self._lock:
            return {
                "current_profile": self._current_profile.name if self._current_profile else None,
                "request_count": self._request_count,
                "rotation_threshold": self._rotation_threshold,
                "total_rotations": self._rotation_count,
                "available_profiles": len(BROWSER_PROFILES),
                # V7.2: Domain-sticky stats
                "domains_tracked": len(self._domain_profiles),
                "domain_profiles": {
                    domain: profile.name 
                    for domain, profile in self._domain_profiles.items()
                },
            }


# ============================================
# SINGLETON INSTANCE
# ============================================
_fingerprint_instance: Optional[BrowserFingerprint] = None
_fingerprint_lock = threading.Lock()


def get_fingerprint() -> BrowserFingerprint:
    """Get or create singleton BrowserFingerprint instance."""
    global _fingerprint_instance
    with _fingerprint_lock:
        if _fingerprint_instance is None:
            _fingerprint_instance = BrowserFingerprint()
            logger.info(f"🎭 BrowserFingerprint singleton created ({len(BROWSER_PROFILES)} profiles)")
        return _fingerprint_instance


def reset_fingerprint():
    """Reset singleton instance (for testing)."""
    global _fingerprint_instance
    with _fingerprint_lock:
        _fingerprint_instance = None


# ============================================
# VALIDATION HELPERS (for testing)
# ============================================
def validate_header_consistency(headers: Dict[str, str]) -> bool:
    """
    Validate that headers are internally consistent.
    
    Rules:
    - If User-Agent contains "Chrome", Sec-Ch-Ua should contain "Chrome"
    - If User-Agent contains "Firefox", Sec-Ch-Ua should be absent
    - If User-Agent contains "Safari" (not Chrome), Sec-Ch-Ua should be absent
    
    Returns:
        True if headers are consistent, False otherwise
    """
    ua = headers.get("User-Agent", "").lower()
    sec_ch_ua = headers.get("Sec-Ch-Ua", "")
    
    # Chrome check
    if "chrome" in ua and "edg" not in ua:
        # Chrome UA should have Chrome in Sec-Ch-Ua
        if sec_ch_ua and "chrome" not in sec_ch_ua.lower():
            return False
    
    # Edge check
    if "edg" in ua:
        # Edge UA should have Edge in Sec-Ch-Ua
        if sec_ch_ua and "edge" not in sec_ch_ua.lower():
            return False
    
    # Firefox check
    if "firefox" in ua:
        # Firefox should NOT have Sec-Ch-Ua
        if sec_ch_ua:
            return False
    
    # Safari check (Safari without Chrome)
    if "safari" in ua and "chrome" not in ua:
        # Safari should NOT have Sec-Ch-Ua
        if sec_ch_ua:
            return False
    
    return True


# ============================================
# CLI TEST
# ============================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("🎭 BROWSER FINGERPRINT TEST")
    print("=" * 60)
    
    fp = get_fingerprint()
    
    print(f"\n📊 Available profiles: {len(BROWSER_PROFILES)}")
    for p in BROWSER_PROFILES:
        print(f"   • {p.name}")
    
    print(f"\n🔍 Initial profile: {fp.get_current_profile_name()}")
    
    # Test header generation
    headers = fp.get_headers()
    print(f"\n📋 Generated headers:")
    for k, v in headers.items():
        print(f"   {k}: {v[:60]}..." if len(v) > 60 else f"   {k}: {v}")
    
    # Validate consistency
    is_consistent = validate_header_consistency(headers)
    print(f"\n✅ Headers consistent: {is_consistent}")
    
    # Test rotation
    print(f"\n🔄 Testing rotation (30 requests)...")
    for i in range(30):
        headers = fp.get_headers()
    
    stats = fp.get_stats()
    print(f"   Rotations occurred: {stats['total_rotations']}")
    print(f"   Current profile: {stats['current_profile']}")
    
    # Test force rotation
    print(f"\n⚡ Testing force_rotate()...")
    old_profile = fp.get_current_profile_name()
    fp.force_rotate()
    new_profile = fp.get_current_profile_name()
    print(f"   {old_profile} → {new_profile}")
    
    print("\n✅ Browser Fingerprint test complete")
