import os
import logging
import requests
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from io import BytesIO
from typing import Optional, Tuple

# ============================================
# OCR QUALITY FILTERS (V4.2 - SPY-FILTER)
# ============================================
MIN_TEXT_LENGTH = 50  # Minimum characters to be considered valid
MAX_NOISE_RATIO = 0.4  # Max ratio of non-alphanumeric chars

# Keywords that indicate a valid squad/lineup image (multi-language)
SQUAD_KEYWORDS = [
    # English
    'squad', 'lineup', 'team', 'starting', 'bench', 'absent', 'injured', 'suspended',
    'out', 'missing', 'available', 'list', 'xi', 'formation',
    # Italian
    'formazione', 'titolari', 'panchina', 'assenti', 'indisponibili', 'convocati',
    # Turkish
    'kadro', 'ilk', 'yedek', 'sakat', 'cezali', 'eksik',
    # Portuguese
    'escalacao', 'titulares', 'reservas', 'desfalques', 'relacionados',
    # Spanish
    'alineacion', 'titulares', 'suplentes', 'bajas', 'convocados',
    # Polish
    'sklad', 'podstawowy', 'rezerwowi', 'kontuzjowani',
    # Romanian
    'echipa', 'titulari', 'rezerve', 'absenti'
]


def _is_valid_ocr_text(text: str) -> Tuple[bool, str]:
    """
    Validate OCR output quality to filter out garbage/noise.
    
    Args:
        text: Raw OCR text (uppercase)
        
    Returns:
        Tuple of (is_valid, reason)
    """
    if not text:
        return False, "Empty text"
    
    # Check minimum length
    if len(text) < MIN_TEXT_LENGTH:
        return False, f"Too short ({len(text)} chars < {MIN_TEXT_LENGTH})"
    
    # Check noise ratio (too many special chars = garbage image)
    alphanumeric = sum(1 for c in text if c.isalnum() or c.isspace())
    noise_ratio = 1 - (alphanumeric / len(text)) if len(text) > 0 else 1
    if noise_ratio > MAX_NOISE_RATIO:
        return False, f"Too noisy ({noise_ratio:.1%} non-alphanumeric)"
    
    # Check for squad-related keywords
    text_lower = text.lower()
    has_keyword = any(keyword in text_lower for keyword in SQUAD_KEYWORDS)
    
    if not has_keyword:
        return False, "No squad keywords found"
    
    return True, "Valid squad content"


def process_squad_image(image_url: str) -> Optional[str]:
    """
    Download and extract text from squad list image using OCR.
    V4.2: Added quality filters to discard garbage/noise images.
    
    Args:
        image_url: URL of the squad list image (supports http://, https://, file://)
    
    Returns:
        Extracted text (uppercase) or None if failed/invalid
    """
    try:
        logging.info(f"📸 Processing squad image: {image_url}")
        
        # Handle local file paths (file:// protocol)
        if image_url.startswith('file://'):
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
        img = img.convert('L')
        
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
            lang='tur+ita+pol+eng',
            config='--psm 6'  # Assume uniform block of text
        )
        
        # Clean and normalize
        text = extracted_text.strip().upper()
        
        logging.info(f"📝 OCR Raw: {len(text)} characters")
        logging.debug(f"OCR Text Preview: {text[:200]}")
        
        # ============================================
        # V4.2: QUALITY FILTER - Discard garbage
        # ============================================
        is_valid, reason = _is_valid_ocr_text(text)
        
        if not is_valid:
            logging.warning(f"🗑️ OCR DISCARDED: {reason}")
            return None
        
        logging.info(f"✅ OCR VALID: {reason} ({len(text)} chars)")
        return text
        
    except Exception as e:
        logging.error(f"Error processing squad image: {e}")
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
    surnames = []
    for word in words:
        # Remove special characters
        clean_word = ''.join(c for c in word if c.isalnum())
        
        # Must be all caps, reasonable length
        if len(clean_word) >= 3 and len(clean_word) <= 15:
            if clean_word.isupper():
                surnames.append(clean_word)
    
    return list(set(surnames))  # Deduplicate
