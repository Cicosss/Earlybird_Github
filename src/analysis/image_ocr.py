import logging
import os
import re
from difflib import SequenceMatcher
from io import BytesIO

import pytesseract
import requests
from PIL import Image, ImageEnhance, ImageFilter

# Import centralized keyword dictionaries for intent-based analysis
# These are class-level constants in RelevanceAnalyzer
from src.utils.content_analysis import RelevanceAnalyzer

# Extract keyword dictionaries from RelevanceAnalyzer class
INJURY_KEYWORDS = RelevanceAnalyzer.INJURY_KEYWORDS
SUSPENSION_KEYWORDS = RelevanceAnalyzer.SUSPENSION_KEYWORDS
YOUTH_CALLUP_KEYWORDS = RelevanceAnalyzer.YOUTH_CALLUP_KEYWORDS
CUP_ABSENCE_KEYWORDS = RelevanceAnalyzer.CUP_ABSENCE_KEYWORDS
SQUAD_KEYWORDS = RelevanceAnalyzer.SQUAD_KEYWORDS

# ============================================
# OCR QUALITY FILTERS (V5.1 - INTENT-DETECTOR + GOLDEN KEYWORD BYPASS)
# ============================================
MIN_TEXT_LENGTH = 20  # Reduced from 30 - more permissive for brief high-value alerts
MAX_NOISE_RATIO = 0.5  # Increased from 0.4 - allow more noise
FUZZY_MATCH_THRESHOLD = 60  # Threshold for fuzzy matching (0-100)


# ============================================
# TEXT NORMALIZATION
# ============================================
def normalize_ocr_text(text: str) -> str:
    """
    Normalize OCR text to handle common OCR errors.

    - Remove extra whitespace
    - Replace common OCR confusions (1->I, 0->O, etc.)
    - Normalize special characters

    Args:
        text: Raw OCR text

    Returns:
        Normalized text
    """
    if not text:
        return ""

    # Common OCR character confusions
    replacements = {
        "1": "I",  # 1 often misread as I
        "0": "O",  # 0 often misread as O
        "5": "S",  # 5 often misread as S
        "2": "Z",  # 2 sometimes misread as Z
    }

    normalized = text.upper()

    # Apply character replacements at word boundaries
    # Matches characters at:
    # - Start of string followed by letter
    # - After non-word char followed by letter
    # - After letter followed by non-word char
    # - After letter followed by end of string
    for old, new in replacements.items():
        normalized = re.sub(rf"(?:(?<=^)|(?<=\W)|(?<=[A-Z])){old}(?=[A-Z]|$|\W)", new, normalized)

    # Remove extra whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


# ============================================
# INTENT KEYWORDS (Multi-language)
# ============================================
# Combine all intent keywords from content_analysis.py
INTENT_KEYWORDS = {
    "injury": INJURY_KEYWORDS,
    "suspension": SUSPENSION_KEYWORDS,
    "youth_callup": YOUTH_CALLUP_KEYWORDS,
    "cup_absence": CUP_ABSENCE_KEYWORDS,
}

# Combine all keywords for comprehensive intent detection
ALL_INTENT_KEYWORDS: list[str] = []
for category_keywords in INTENT_KEYWORDS.values():
    ALL_INTENT_KEYWORDS.extend(category_keywords)
ALL_INTENT_KEYWORDS.extend(SQUAD_KEYWORDS)


def _has_intent_keywords(text: str) -> tuple[bool, str]:
    """
    Check if OCR text contains intent keywords (injury, suspension, youth callup, etc.).

    This is the NEW intent-based approach - we're looking for PURPOSE, not IDENTITY.

    Args:
        text: OCR text to analyze

    Returns:
        Tuple of (has_intent, matched_category)
    """
    if not text:
        return False, "No text"

    text_lower = text.lower()

    # Check each intent category
    for category, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return True, category

    # Check squad/lineup keywords
    for keyword in SQUAD_KEYWORDS:
        if keyword in text_lower:
            return True, "squad_list"

    return False, "No intent keywords"


def _fuzzy_match_keywords(
    text: str, keywords: list[str], threshold: int = FUZZY_MATCH_THRESHOLD
) -> tuple[bool, str]:
    """
    Perform fuzzy matching on OCR text against keywords.

    This handles OCR errors where text is slightly garbled but still recognizable.

    Args:
        text: OCR text to match
        keywords: List of keywords to match against
        threshold: Minimum fuzzy ratio (0-100)

    Returns:
        Tuple of (matched, matched_keyword)
    """
    text_normalized = normalize_ocr_text(text)
    text_lower = text_normalized.lower()

    for keyword in keywords:
        keyword_lower = keyword.lower()

        # Try exact match first (fastest)
        if keyword_lower in text_lower:
            return True, keyword

        # Try fuzzy matching for partial matches
        # Check if keyword appears as a substring with fuzzy tolerance
        for word in text_lower.split():
            # Use SequenceMatcher for similarity calculation (built-in, no external deps)
            # Convert threshold from 0-100 to 0.0-1.0
            similarity = SequenceMatcher(None, keyword_lower, word).ratio()
            similarity_percent = similarity * 100

            if similarity_percent >= threshold:
                logging.debug(
                    f"Fuzzy match: '{keyword}' ~ '{word}' (similarity: {similarity_percent:.1f}%)"
                )
                return True, keyword

    return False, None


def _is_valid_ocr_text(text: str, channel_info: dict | None = None) -> tuple[bool, str]:
    """
    Validate OCR output quality using INTENT-BASED analysis.

    V5.1 Changes (OCR Length Filter Hotfix):
    - Golden Keyword Bypass: Check for high-value keywords BEFORE length filter
    - Reduced MIN_TEXT_LENGTH from 30 to 20 characters
    - Use len(text.strip()) to ensure we don't count empty spaces
    - This prevents false negatives for brief but critical alerts like "ICARDI OUT"

    V5.0 Changes:
    - Removed strict team name requirement
    - Added intent-based keyword detection
    - Added fuzzy matching for OCR errors
    - Added contextual channel trust bypass
    - More permissive thresholds

    Args:
        text: Raw OCR text (uppercase)
        channel_info: Optional dict with channel metadata for context trust

    Returns:
        Tuple of (is_valid, reason)
    """
    if not text:
        return False, "Empty text"

    # ============================================
    # CONTEXTUAL CHANNEL TRUST BYPASS
    # ============================================
    # If image is from a dedicated team/league channel, trust the context
    if channel_info:
        channel_type = channel_info.get("type")
        team_name = channel_info.get("team")

        # Team-specific channels: assume images belong to that team
        if channel_type == "team" and team_name:
            logging.info(f"🔓 CHANNEL TRUST BYPASS: Image from {team_name} channel - auto-approved")
            return True, f"Channel trust bypass (team: {team_name})"

    # ============================================
    # GOLDEN KEYWORD BYPASS (V5.1 - BEFORE LENGTH CHECK!)
    # ============================================
    # Check for high-value keywords BEFORE applying length filter
    # This prevents false negatives for brief but critical alerts like "ICARDI OUT"
    has_intent, category = _has_intent_keywords(text)
    if has_intent:
        logging.info(f"🔑 GOLDEN KEYWORD BYPASS: {category} detected - bypassing length filter")
        return True, f"Golden keyword bypass: {category}"

    # Try fuzzy matching for OCR errors
    all_keywords = ALL_INTENT_KEYWORDS
    matched, matched_keyword = _fuzzy_match_keywords(text, all_keywords)
    if matched:
        logging.info(
            f"🔑 FUZZY KEYWORD BYPASS: {matched_keyword} detected - bypassing length filter"
        )
        return True, f"Fuzzy keyword bypass: {matched_keyword}"

    # ============================================
    # BASIC QUALITY CHECKS
    # ============================================
    # Check minimum length using strip() to ensure we don't count empty spaces
    text_stripped = text.strip()
    if len(text_stripped) < MIN_TEXT_LENGTH:
        return False, f"Too short ({len(text_stripped)} chars < {MIN_TEXT_LENGTH})"

    # Check noise ratio (increased threshold for permissiveness)
    alphanumeric = sum(1 for c in text if c.isalnum() or c.isspace())
    noise_ratio = 1 - (alphanumeric / len(text)) if len(text) > 0 else 1
    if noise_ratio > MAX_NOISE_RATIO:
        return False, f"Too noisy ({noise_ratio:.1%} non-alphanumeric)"

    # ============================================
    # FALLBACK: PERMISSIVE MODE
    # ============================================
    # If we have reasonable text length and low noise, pass it forward
    # Let the LLM decide if it's noise - we can't afford false negatives
    if len(text) >= 50 and noise_ratio < 0.3:
        logging.info("⚠️ PERMISSIVE PASS: No keywords but good quality - forwarding to LLM")
        return True, "Permissive pass (good quality, no keywords)"

    return False, "No intent keywords detected and quality insufficient for permissive pass"


def process_squad_image(image_url: str, channel_info: dict | None = None) -> str | None:
    """
    Download and extract text from squad list image using OCR.
    V5.1: OCR LENGTH FILTER HOTFIX - Golden Keyword Bypass
    V5.0: INTENT-BASED VALIDATION - Shift from "Identity" to "Intent".

    V5.1 Changes (Hotfix):
    - Golden Keyword Bypass: Check for high-value keywords BEFORE length filter
    - Reduced MIN_TEXT_LENGTH from 30 to 20 characters
    - Use len(text.strip()) to ensure we don't count empty spaces
    - Prevents false negatives for brief but critical alerts like "ICARDI OUT"

    V5.0 Changes:
    - Removed strict team name requirement
    - Added intent-based keyword detection (injury, suspension, youth callup)
    - Added fuzzy matching for OCR errors
    - Added contextual channel trust bypass
    - More permissive thresholds to reduce false negatives

    Args:
        image_url: URL of the squad list image (supports http://, https://, file://)
        channel_info: Optional dict with channel metadata for context trust bypass
                     Expected keys: 'type' (e.g., 'team'), 'team' (team name)

    Returns:
        Extracted text (uppercase) or None if failed/invalid
    """
    try:
        logging.info(f"📸 Processing squad image: {image_url}")

        # Handle local file paths (file:// protocol)
        if image_url.startswith("file://"):
            local_path = image_url[7:]  # Remove 'file://' prefix
            if not os.path.exists(local_path):
                logging.error(f"Local file not found: {local_path}")
                return None
            img = Image.open(local_path)
        else:
            # Download image from URL
            response = requests.get(image_url, timeout=10)
            if response.status_code != 200:
                logging.error(f"Failed to download image: {response.status_code}")
                return None
            img = Image.open(BytesIO(response.content))

        # Pre-process image for better OCR accuracy
        # 1. Convert to grayscale
        img = img.convert("L")

        # 2. Increase contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        # 3. Sharpen
        img = img.filter(ImageFilter.SHARPEN)

        # 4. Resize if too small (OCR works better on larger text)
        width, height = img.size
        if width < 1000:
            scale = 1000 / width
            img = img.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)

        # Run OCR with multiple languages
        # Turkish, Italian, Polish, English
        extracted_text = pytesseract.image_to_string(
            img,
            lang="tur+ita+pol+eng",
            config="--psm 6",  # Assume uniform block of text
        )

        # Clean and normalize
        text = extracted_text.strip().upper()

        logging.info(f"📝 OCR Raw: {len(text)} characters")
        logging.debug(f"OCR Text Preview: {text[:200]}")

        # ============================================
        # V5.0: INTENT-BASED VALIDATION - Smartly Permissive
        # ============================================
        is_valid, reason = _is_valid_ocr_text(text, channel_info)

        if not is_valid:
            logging.warning(f"🗑️ OCR DISCARDED: {reason}")
            return None

        logging.info(f"✅ OCR VALID: {reason} ({len(text)} chars)")
        return text

    except (FileNotFoundError, IsADirectoryError) as path_err:
        logging.warning(f"Invalid file path: {path_err}")
        return None

    except Image.UnidentifiedImageError as img_err:
        logging.warning(f"Invalid image format: {img_err}")
        return None

    except requests.Timeout as timeout_err:
        logging.warning(f"Network timeout downloading image: {timeout_err}")
        return None

    except requests.ConnectionError as conn_err:
        logging.warning(f"Network error downloading image: {conn_err}")
        return None

    except pytesseract.TesseractError as tess_err:
        logging.error(f"Tesseract OCR error (check language packs): {tess_err}")
        logging.error(
            "Install missing language packs: sudo apt-get install "
            "tesseract-ocr-tur tesseract-ocr-ita tesseract-ocr-pol"
        )
        return None

    except Exception as e:
        logging.error(f"Unexpected error processing squad image: {e}")
        import traceback

        logging.error(f"Traceback: {traceback.format_exc()}")
        return None


def extract_player_names(ocr_text: str) -> list:
    """
    Extract likely player names from OCR text.
    Looks for capitalized words (surnames) following patterns.

    Args:
        ocr_text: Raw OCR output

    Returns:
        List of detected player surnames
    """
    # Split by lines and words
    words = ocr_text.split()

    # Filter for capitalized words (2-15 chars) likely to be surnames
    surnames: list[str] = []
    for word in words:
        # Remove special characters
        clean_word = "".join(c for c in word if c.isalnum())

        # Must be all caps, reasonable length
        if len(clean_word) >= 3 and len(clean_word) <= 15:
            if clean_word.isupper():
                surnames.append(clean_word)

    return list(set(surnames))  # Deduplicate
