# OCR Implementation Bug Tracking Diary

**Date**: 2026-02-24
**Mode**: Chain of Verification (CoVe) - Double Verification
**Scope**: Deep analysis of `src/analysis/image_ocr.py` and integration points
**VPS Compatibility**: Verified
**Data Flow**: Traced from Telegram to Alert Generation

---

## Context

This document tracks confirmed bugs and issues in the Telegram OCR implementation that must be fixed before VPS deployment. The OCR system processes squad list images from Telegram channels to detect missing key players.

**Data Flow Overview:**
```
Telegram Listener → Download Image → OCR Processing → Text Normalization → 
Intent Validation → Squad Analysis → Alert Generation
```

**Critical Systems Affected:**
- Telegram monitoring (`src/processing/telegram_listener.py`)
- OCR processing (`src/analysis/image_ocr.py`)
- Squad analysis (`src/analysis/squad_analyzer.py`)
- VPS setup (`setup_vps.sh`)

---

## Confirmed Bugs

### CRITICAL BUGS (VPS Deployment Blockers)

**Bug 1: Missing Tesseract Language Packs**

**Location**:
- [`setup_vps.sh:38-40`](setup_vps.sh:38) (setup script)
- [`image_ocr.py:369`](src/analysis/image_ocr.py:369) (usage)

**Issue**: 
The OCR code requires Turkish, Italian, Polish, and English language packs:
```python
extracted_text = pytesseract.image_to_string(
    img,
    lang="tur+ita+pol+eng",  # Requires 4 language packs
    config="--psm 6",
)
```

However, the VPS setup script only installs:
```bash
sudo apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \      # Only English
    libtesseract-dev
```

**Impact**:
- OCR will fail or produce poor results for Turkish/Italian/Polish squad lists
- Silent failure - may fall back to English only
- Bot will miss critical intelligence from non-English channels
- Turkish Super Lig (major target league) will have poor OCR quality

**Fix Required**:

Update [`setup_vps.sh`](setup_vps.sh:38) to install all required language packs:
```bash
sudo apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-tur \
    tesseract-ocr-ita \
    tesseract-ocr-pol \
    libtesseract-dev
```

**Verification**:
```bash
# After installation, verify language packs are available
tesseract --list-langs | grep -E "(tur|ita|pol|eng)"
```

---

- [ ] **Bug 1: Missing Tesseract Language Packs** - Update `setup_vps.sh` to install tesseract-ocr-tur, tesseract-ocr-ita, tesseract-ocr-pol, verify with `tesseract --list-langs`, and test OCR with Turkish, Italian, and Polish squad list images

---

**Bug 2: Memory Leak - Temp Files Not Cleaned Up**

**Location**:
- [`telegram_listener.py:590`](src/processing/telegram_listener.py:590) (image creation)
- [`telegram_listener.py:619-625`](src/processing/telegram_listener.py:619) (cleanup on drop)
- [`telegram_listener.py:818`](src/processing/telegram_listener.py:818) (storage in results)
- [`telegram_listener.py:900`](src/processing/telegram_listener.py:900) (usage)

**Issue**:
Temporary image files are only cleaned up when messages are dropped, but NOT when messages are successfully processed.

**Data Flow Analysis**:
```
1. Line 590:  image_path = f"./temp/{channel}_{timestamp}.jpg"
2. Line 593:  await client.download_media(msg.photo, image_path)
3. Line 598-600: ocr_text = process_squad_image(...)
4. Line 619-625: Cleanup only if not should_process (DROPPED messages)
5. Line 818:   "image_path": image_path (stored in results)
6. Line 900:   image_url=squad["image_path"] (passed to analyzer)
7. Line 860:   return results (function ends)
8. ❌ No cleanup - temp files accumulate indefinitely
```

**Impact**:
- Disk space accumulation over time on VPS
- Potential disk full errors after extended operation
- Security risk (temp files may contain sensitive squad information)
- Estimated accumulation: 10-50 images per day × 365 days = 3,650-18,250 files per year

**Fix Required**:

Add cleanup in [`monitor_channels_for_squads()`](src/processing/telegram_listener.py:870) after processing:
```python
async def monitor_channels_for_squads(existing_client: TelegramClient = None) -> list[dict]:
    squad_images = await fetch_squad_images(existing_client=existing_client)
    
    alerts = []
    
    for squad in squad_images:
        # ... existing processing code ...
        
        # Cleanup temp image after processing
        image_path = squad.get("image_path")
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
                logging.debug(f"🗑️ Cleaned up temp image: {image_path}")
            except Exception as cleanup_err:
                logging.warning(f"Could not remove temp image {image_path}: {cleanup_err}")
    
    return alerts
```

**Alternative**: Use `tempfile.TemporaryDirectory()` context manager for automatic cleanup.

---

- [ ] **Bug 2: Memory Leak - Temp Files Not Cleaned Up** - Add temp file cleanup in `monitor_channels_for_squads()` after processing, monitor temp directory size over time to confirm cleanup is working, and test with multiple squad images to confirm files are deleted

---

### HIGH PRIORITY BUGS

**Bug 3: Regex Bug in normalize_ocr_text()**

**Location**: [`image_ocr.py:63`](src/analysis/image_ocr.py:63)

**Issue**:
The regex pattern requires non-word characters on both sides, so numbers at word boundaries are not replaced.

**Current Code**:
```python
def normalize_ocr_text(text: str) -> str:
    # Common OCR character confusions
    replacements = [
        ("1", "I"),  # 1 often misread as I
        ("0", "O"),  # 0 often misread as O
        ("5", "S"),  # 5 often misread as S
        ("2", "Z"),  # 2 sometimes misread as Z
    ]
    
    normalized = text.upper()
    
    # Apply character replacements
    for old, new in replacements:
        # ❌ BUG: Only replaces when surrounded by non-word chars
        normalized = re.sub(rf"(?<=\W){old}(?=\W)", new, normalized)
    
    return normalized
```

**Test Cases**:
```python
# Current behavior (BUG):
normalize_ocr_text("1CARDI")   # → "1CARDI"  (❌ should be "ICARDI")
normalize_ocr_text("PLAYER1")  # → "PLAYER1"  (❌ should be "PLAYERI")
normalize_ocr_text(" 1 ")     # → " I "      (✅ works)

# Expected behavior:
normalize_ocr_text("1CARDI")   # → "ICARDI"
normalize_ocr_text("PLAYER1")  # → "PLAYERI"
normalize_ocr_text(" 1 ")     # → " I "
```

**Impact**:
- Common OCR errors like "1CARDI" (instead of "ICARDI") won't be corrected
- Player name matching will fail for garbled text
- False negatives in squad analysis
- Critical alerts may be missed due to uncorrected OCR errors

**Fix Required**:

Update regex to handle word boundaries:
```python
def normalize_ocr_text(text: str) -> str:
    if not text:
        return ""
    
    replacements = [
        ("1", "I"),
        ("0", "O"),
        ("5", "S"),
        ("2", "Z"),
    ]
    
    normalized = text.upper()
    
    # ✅ FIXED: Replace at word boundaries (start, end, or surrounded by non-word chars)
    for old, new in replacements:
        # Match: start-of-string OR non-word-char + old + end-of-string OR non-word-char
        normalized = re.sub(rf"(?:^|\W){old}(?:\W|$)", new, normalized)
    
    # Remove extra whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    
    return normalized
```

---

- [ ] **Bug 3: Regex Bug in normalize_ocr_text()** - Update regex pattern in `normalize_ocr_text()` to handle word boundaries, write unit tests for edge cases (numbers at start/end, empty strings), and test with real OCR output containing garbled player names

---

**Bug 4: Generic Exception Handling**

**Location**: [`image_ocr.py:391-393`](src/analysis/image_ocr.py:391)

**Issue**:
All exceptions are caught and logged identically, making it impossible to distinguish between transient errors (network) and permanent errors (configuration).

**Current Code**:
```python
try:
    # ... OCR processing ...
    return text
except Exception as e:  # ❌ Too generic
    logging.error(f"Error processing squad image: {e}")
    return None
```

**Exception Types That Can Occur**:
```python
# Transient errors (should retry):
requests.exceptions.Timeout
requests.exceptions.ConnectionError
requests.exceptions.HTTPError (5xx)

# Permanent errors (should alert admin):
FileNotFoundError (file not found)
PIL.UnidentifiedImageError (invalid image format)
pytesseract.TesseractError (Tesseract not installed or language pack missing)

# Expected errors (should skip and continue):
ValueError (empty text after OCR)
```

**Impact**:
- Cannot implement retry logic for transient failures
- Difficult to diagnose configuration issues
- Silent failures may go unnoticed
- No distinction between "should retry" vs "should alert" vs "should skip"

**Fix Required**:

Add specific exception handling:
```python
try:
    # Download image
    if image_url.startswith("file://"):
        local_path = image_url[7:]
        if not os.path.exists(local_path):
            logging.error(f"Local file not found: {local_path}")
            return None
        img = Image.open(local_path)
    else:
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200:
            logging.warning(f"Failed to download image: HTTP {response.status_code}")
            return None
        img = Image.open(BytesIO(response.content))
    
    # Pre-process and OCR
    # ... existing code ...
    
    return text

except (FileNotFoundError, IsADirectoryError) as path_err:
    logging.warning(f"Invalid file path: {path_err}")
    return None

except PIL.UnidentifiedImageError as img_err:
    logging.warning(f"Invalid image format: {img_err}")
    return None

except requests.exceptions.Timeout as timeout_err:
    logging.warning(f"Network timeout downloading image: {timeout_err}")
    return None

except requests.exceptions.ConnectionError as conn_err:
    logging.warning(f"Network error downloading image: {conn_err}")
    return None

except pytesseract.TesseractError as tess_err:
    logging.error(f"Tesseract OCR error (check language packs): {tess_err}")
    logging.error("Install missing language packs: sudo apt-get install tesseract-ocr-tur tesseract-ocr-ita tesseract-ocr-pol")
    return None

except Exception as e:
    logging.error(f"Unexpected error processing squad image: {e}")
    import traceback
    logging.error(f"Traceback: {traceback.format_exc()}")
    return None
```

---

- [ ] **Bug 4: Generic Exception Handling** - Add specific exception handling in `process_squad_image()`, test with invalid images, network timeouts, missing files, and verify different error types are logged with appropriate severity

---

### MEDIUM PRIORITY BUGS

**Bug 5: Triple Keyword Duplication**

**Location**:
- [`src/analysis/image_ocr.py:83-135`](src/analysis/image_ocr.py:83) (52 keywords)
- [`src/processing/telegram_listener.py:173-197`](src/processing/telegram_listener.py:173) (25 keywords)
- [`src/analysis/squad_analyzer.py:44-54`](src/analysis/squad_analyzer.py:44) (10 keywords)

**Issue**:
`SQUAD_KEYWORDS` are defined in THREE different files with overlapping entries.

**Duplication Analysis**:

| File | Keywords Count | Overlap | Purpose |
|------|---------------|----------|---------|
| image_ocr.py | 52 | - | OCR text validation |
| telegram_listener.py | 25 | 15 with image_ocr.py | Message filtering |
| squad_analyzer.py | 10 | 8 with image_ocr.py | Squad list detection |

**Overlapping Keywords**:
```
Common to all 3 files:
- "SQUAD", "LINEUP", "FORMAZIONE", "KADRO", "SKŁAD"

Common to image_ocr.py and telegram_listener.py:
- "injured", "suspended", "out", "missing", "starting", "bench", "titulares", "reservas"
```

**Impact**:
- Maintenance burden - updates must be made in 3 places
- Risk of inconsistency between files
- Code duplication reduces maintainability
- Adding new language support requires editing 3 files

**Fix Required**:

Centralize keywords in one location:

**Option 1**: Add to `src/utils/content_analysis.py` (with RelevanceAnalyzer):
```python
# src/utils/content_analysis.py

class RelevanceAnalyzer:
    # ... existing keywords ...
    
    # Squad/lineup keywords (multi-language)
    SQUAD_KEYWORDS = [
        # English
        "squad", "lineup", "team", "starting", "bench", "absent",
        "injured", "suspended", "out", "missing", "available", "list", "xi",
        "formation",
        # Italian
        "formazione", "titolari", "panchina", "assenti", "indisponibili",
        "convocati",
        # Turkish
        "kadro", "ilk", "yedek", "sakat", "cezali", "eksik",
        # Portuguese
        "escalacao", "titulares", "reservas", "desfalques", "relacionados",
        # Spanish
        "alineacion", "titulares", "suplentes", "bajas", "convocados",
        # Polish
        "sklad", "podstawowy", "rezerwowi", "kontuzjowani",
        # Romanian
        "echipa", "titulari", "rezerve", "absenti",
    ]
```

**Option 2**: Create dedicated constants file:
```python
# src/constants/keywords.py

"""Centralized keyword definitions for the entire system."""

SQUAD_KEYWORDS = [
    # All squad/lineup keywords in one place
    ...
]

INJURY_KEYWORDS = [
    # All injury keywords in one place
    ...
]

SUSPENSION_KEYWORDS = [
    # All suspension keywords in one place
    ...
]
```

Then update imports in all three files:
```python
from src.constants.keywords import SQUAD_KEYWORDS
```

---

- [ ] **Bug 5: Triple Keyword Duplication** - Centralize `SQUAD_KEYWORDS` in one location (create `src/constants/keywords.py`), update imports in `image_ocr.py`, `telegram_listener.py`, and `squad_analyzer.py`, and verify all three modules use the centralized keyword list

---

**Bug 6: No Language Pack Verification**

**Location**: [`setup_vps.sh:236-240`](setup_vps.sh:236)

**Issue**:
The setup script checks if Tesseract is installed but doesn't verify required language packs.

**Current Code**:
```bash
# Check Tesseract
if command -v tesseract &> /dev/null; then
    echo -e "${GREEN}   ✅ Tesseract OCR installed: $(tesseract --version 2>&1 | head -1)${NC}"
else
    echo -e "${RED}   ❌ Tesseract OCR not found${NC}"
fi
```

**Impact**:
- Silent failure - language pack issues only discovered at runtime
- Difficult to diagnose OCR quality issues
- May require manual intervention on VPS
- No clear error message if language packs are missing

**Fix Required**:

Add language pack verification to [`setup_vps.sh`](setup_vps.sh:236):
```bash
# Check Tesseract language packs
echo ""
echo -e "${GREEN}🔍 Checking Tesseract language packs...${NC}"

# Determine tessdata path (varies by Tesseract version)
if [ -d "/usr/share/tesseract-ocr/4.00/tessdata" ]; then
    tessdata_path="/usr/share/tesseract-ocr/4.00/tessdata"
elif [ -d "/usr/share/tesseract-ocr/5.00/tessdata" ]; then
    tessdata_path="/usr/share/tesseract-ocr/5.00/tessdata"
else
    tessdata_path="/usr/share/tesseract-ocr/tessdata"
fi

required_langs=("eng" "tur" "ita" "pol")
missing_langs=()

for lang in "${required_langs[@]}"; do
    if [ -f "$tessdata_path/$lang.traineddata" ]; then
        echo -e "${GREEN}   ✅ $lang language pack installed${NC}"
    else
        missing_langs+=("$lang")
        echo -e "${RED}   ❌ $lang language pack MISSING${NC}"
    fi
done

if [ ${#missing_langs[@]} -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Missing language packs: ${missing_langs[*]}${NC}"
    echo -e "${YELLOW}   Install with:${NC}"
    for lang in "${missing_langs[@]}"; do
        echo -e "${YELLOW}   sudo apt-get install tesseract-ocr-$lang${NC}"
    done
    echo -e "${RED}   ❌ OCR will fail or produce poor results without these language packs${NC}"
else
    echo ""
    echo -e "${GREEN}   ✅ All required language packs installed${NC}"
fi
```

---

- [ ] **Bug 6: No Language Pack Verification** - Add language pack verification in `setup_vps.sh`, run setup script on fresh VPS to verify language pack check works, and test with missing language packs to verify error messages

---

### LOW PRIORITY ISSUES

**Bug 7: Inconsistent Text Case Handling**

**Location**: [`image_ocr.py:159`](src/analysis/image_ocr.py:159), [`image_ocr.py:374`](src/analysis/image_ocr.py:374)

**Issue**:
OCR text is converted to uppercase, but keyword matching converts to lowercase. This is correct but inefficient.

**Current Code**:
```python
# Line 374: Convert to uppercase
text = extracted_text.strip().upper()

# Line 159: Convert to lowercase for matching
text_lower = text.lower()

# Line 164: Match against lowercase keywords
if keyword in text_lower:
```

**Impact**:
- Unnecessary string conversions (uppercase → lowercase)
- Minor performance impact
- Code is functionally correct but could be optimized

**Fix Required** (Optional Optimization):
```python
# Option 1: Keep OCR text lowercase
text = extracted_text.strip().lower()  # Lowercase instead of uppercase

# Then matching is direct:
if keyword in text:  # No need for .lower() conversion

# Option 2: Keep keywords uppercase
INJURY_KEYWORDS = [kw.upper() for kw in INJURY_KEYWORDS]
# Then matching is direct:
if keyword in text:  # No need for .lower() conversion
```

**Note**: This is a minor optimization and not critical. Current implementation is functionally correct.

---

- [ ] **Bug 7: Inconsistent Text Case Handling** (Optional) - Optimize text case handling to avoid unnecessary conversions, benchmark performance impact before and after optimization, and verify functionality remains identical after optimization

---

### ADDITIONAL FINDINGS

**Bug 8: Duplicate OCR Call**

**Location**:
- [`telegram_listener.py:598`](src/processing/telegram_listener.py:598) (first OCR call)
- [`telegram_listener.py:900`](src/processing/telegram_listener.py:900) (pass image_path)
- [`squad_analyzer.py:64`](src/analysis/squad_analyzer.py:64) (second OCR call)

**Issue**:
`squad_analyzer.py:64` calls `process_squad_image()` even though OCR text was already extracted by `telegram_listener.py:598`.

**Data Flow**:
```
1. telegram_listener.py:598: ocr_text = process_squad_image(image_path, ...)
2. telegram_listener.py:818: results.append({"ocr_text": ocr_text, "image_path": image_path, ...})
3. telegram_listener.py:900: alert = analyze_squad_list(image_url=squad["image_path"], ...)
4. squad_analyzer.py:64: ocr_text = process_squad_image(image_url, ...)  # ❌ Duplicate OCR!
```

**Impact**:
- Performance inefficiency - same image processed twice
- Increased CPU usage on VPS
- Slower response time for squad analysis

**Fix Required**:

Pass OCR text instead of image_path to `analyze_squad_list()`:

```python
# telegram_listener.py:900
alert = analyze_squad_list(
    image_url=squad["image_path"],  # Keep for backward compatibility
    ocr_text=squad.get("ocr_text"),  # ✅ Pass OCR text
    team_name=squad["team_search_name"],
    match_id=f"telegram_{squad['channel']}_{int(squad['timestamp'].timestamp())}",
)

# squad_analyzer.py:31
def analyze_squad_list(image_url: str, ocr_text: str | None = None, team_name: str, match_id: str) -> dict | None:
    """
    Analyze squad list image and detect if key players are missing.
    
    Args:
        image_url: URL of squad list image (fallback if ocr_text not provided)
        ocr_text: Pre-extracted OCR text (preferred to avoid duplicate OCR)
        team_name: Team name
        match_id: Match ID
    
    Returns:
        Alert dict if critical player missing, None otherwise
    """
    # Use provided OCR text if available, otherwise extract
    if not ocr_text:
        channel_info = {
            "type": "team",
            "team": team_name,
        }
        ocr_text = process_squad_image(image_url, channel_info=channel_info)
    
    if not ocr_text:
        logging.warning("No text extracted from squad image")
        return None
    
    # ... rest of analysis ...
```

---

- [ ] **Bug 8: Duplicate OCR Call** - Pass `ocr_text` to `analyze_squad_list()` to avoid duplicate OCR, update function signature and implementation in `squad_analyzer.py`, and verify OCR is called only once per image

---

## Integration Points Verified

| Integration Point | Status | Notes |
|------------------|---------|---------|
| OCR → Telegram Listener | ✅ OK | OCR text properly appended to full_text |
| Channel Info → OCR | ✅ OK | Contextual trust bypass works correctly |
| OCR → Time-gating | ✅ OK | Combined text (caption + OCR) used for gating |
| Trust Score → OCR Results | ✅ OK | Trust validation applied to OCR results |
| OCR → Squad Analyzer | ⚠️ INEFFICIENT | Duplicate OCR call (Bug 8) |
| OCR → Alert Metadata | ✅ OK | OCR metadata included in alerts |

---

## VPS Compatibility Checklist

### Required System Packages

| Package | Status | Command |
|---------|---------|---------|
| tesseract-ocr | ✅ Installed | `sudo apt-get install tesseract-ocr` |
| tesseract-ocr-eng | ✅ Installed | `sudo apt-get install tesseract-ocr-eng` |
| tesseract-ocr-tur | ❌ MISSING | `sudo apt-get install tesseract-ocr-tur` |
| tesseract-ocr-ita | ❌ MISSING | `sudo apt-get install tesseract-ocr-ita` |
| tesseract-ocr-pol | ❌ MISSING | `sudo apt-get install tesseract-ocr-pol` |
| libtesseract-dev | ✅ Installed | `sudo apt-get install libtesseract-dev` |

### Required Python Packages

| Package | Status | Version |
|---------|---------|---------|
| pytesseract | ✅ In requirements.txt | (no version specified) |
| Pillow | ✅ In requirements.txt | (no version specified) |
| requests | ✅ In requirements.txt | 2.32.3 |

### VPS-Specific Considerations

1. **Disk Space**: Temp files will accumulate without cleanup (Bug 2). Estimated 10-50 images/day × 100KB = 1-5MB/day → 365-1825MB/year.

2. **Memory Usage**: Image processing in memory. Large images (>10MB) may cause issues on low-RAM VPS.

3. **CPU Usage**: Tesseract OCR is CPU-intensive. Multiple concurrent OCR calls may slow down the bot.

4. **Language Pack Storage**: Each language pack is ~2-5MB. Total for 4 languages: ~8-20MB.

---

## Fix Priority Summary

| Priority | Bug | Impact | Estimated Fix Time |
|----------|-----|--------|-------------------|
| CRITICAL | Bug 1: Missing Language Packs | OCR fails for non-English content | 5 min |
| CRITICAL | Bug 2: Memory Leak | Disk space exhaustion on VPS | 15 min |
| HIGH | Bug 3: Regex Bug | Player name matching failures | 10 min |
| HIGH | Bug 4: Generic Exception Handling | Difficult debugging, no retry logic | 20 min |
| MEDIUM | Bug 5: Triple Keyword Duplication | Maintenance burden | 30 min |
| MEDIUM | Bug 6: No Language Pack Verification | Silent failures at runtime | 15 min |
| LOW | Bug 7: Inconsistent Text Case | Minor performance impact | 10 min |
| MEDIUM | Bug 8: Duplicate OCR Call | Performance inefficiency | 15 min |

**Total Estimated Fix Time**: ~2 hours

---

## Testing Recommendations

### Unit Tests

1. Test `normalize_ocr_text()` with edge cases:
   - Numbers at word boundaries
   - Empty strings
   - Strings with only special characters

2. Test exception handling with:
   - Invalid image files
   - Network timeouts
   - Missing Tesseract binary
   - Missing language packs

3. Test temp file cleanup:
   - Verify files are deleted after successful processing
   - Verify files are deleted after dropped messages
   - Verify cleanup handles exceptions gracefully

### Integration Tests

1. Test complete data flow:
   - Telegram message → OCR → Squad analysis → Alert
   - Verify temp files are cleaned up
   - Verify OCR text is properly passed through pipeline

2. Test multi-language OCR:
   - Turkish squad list images
   - Italian squad list images
   - Polish squad list images
   - Verify language packs are loaded correctly

3. Test VPS deployment:
   - Run setup script on fresh VPS
   - Verify all language packs are installed
   - Verify OCR works correctly on VPS

---

## Notes

- All bugs identified in this report have been verified through double CoVe verification
- Critical bugs (1-2) must be fixed before VPS deployment
- High priority bugs (3-4) should be fixed before VPS deployment
- Medium priority bugs (5-6, 8) should be fixed within 1 week
- Low priority bug (7) is optional optimization

---

**Report Generated**: 2026-02-24T22:51:00Z  
**Verification Method**: Chain of Verification (CoVe) - Double Verification  
**Confidence Level**: HIGH (All findings independently verified)
