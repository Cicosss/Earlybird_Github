"""
Weather Provider for EarlyBird
Fetches weather forecasts from Open-Meteo API (Free, no API key required).

Weather conditions impact betting markets:
- SNOW: Extreme Under, Random Outcome
- HIGH WIND (>30km/h): Under Goals, Long Balls ineffective
- HEAVY RAIN (>4mm/h): Over Cards (sliding tackles), Mistakes

Safety: Returns None if coordinates invalid or API fails.
"""
import requests
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Weather thresholds for betting impact
# V4.6 FIX: Adjusted thresholds based on sports science research
# - Wind: 40 km/h is when long balls become significantly affected
# - Rain: 5 mm/h is heavy rain that affects ball control
SNOW_THRESHOLD = 0.0  # Any snowfall is significant
WIND_HIGH_THRESHOLD = 40.0  # km/h (was 30, too sensitive)
RAIN_HEAVY_THRESHOLD = 5.0  # mm/h (was 4, slightly increased)


def validate_coordinates(lat: float, lon: float) -> bool:
    """
    Validate latitude and longitude values.
    
    Args:
        lat: Latitude (-90 to 90)
        lon: Longitude (-180 to 180)
        
    Returns:
        True if valid, False otherwise
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        
        # Check valid ranges
        if not (-90 <= lat_f <= 90):
            return False
        if not (-180 <= lon_f <= 180):
            return False
        
        # Reject null island (0,0) - likely missing data
        if lat_f == 0.0 and lon_f == 0.0:
            return False
        
        return True
    except (TypeError, ValueError):
        return False


def get_weather_forecast(
    lat: float,
    lon: float,
    match_time: datetime
) -> Optional[Dict]:
    """
    Fetch weather forecast for specific location and time.
    
    Args:
        lat: Stadium latitude
        lon: Stadium longitude
        match_time: Match kickoff time (datetime)
        
    Returns:
        Dict with weather data or None if unavailable
    """
    # Validate coordinates
    if not validate_coordinates(lat, lon):
        logger.debug(f"Invalid coordinates: lat={lat}, lon={lon}")
        return None
    
    try:
        # Format time for API (ISO format, hour precision)
        start_date = match_time.strftime("%Y-%m-%d")
        
        # Open-Meteo API call
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "precipitation,snowfall,windspeed_10m,temperature_2m",
            "start_date": start_date,
            "end_date": start_date,
            "timezone": "UTC"
        }
        
        resp = requests.get(url, params=params, timeout=10)
        
        if resp.status_code != 200:
            logger.warning(f"Open-Meteo API returned {resp.status_code}")
            return None
        
        data = resp.json()
        
        # Extract hourly data
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        precipitation = hourly.get("precipitation", [])
        snowfall = hourly.get("snowfall", [])
        windspeed = hourly.get("windspeed_10m", [])
        temperature = hourly.get("temperature_2m", [])
        
        if not times:
            return None
        
        # Find the hour closest to match time
        # V4.6 FIX: Ensure target_idx is always valid (non-negative)
        # Previously, if times was empty after the check above, len(times)-1 = -1
        # which would cause incorrect array access
        match_hour = match_time.hour
        target_idx = min(match_hour, len(times) - 1)
        target_idx = max(0, target_idx)  # Ensure non-negative index
        
        # V4.6: Additional safety check - verify index is within bounds for all arrays
        def safe_get(arr, idx, default=0):
            """Safely get array element with bounds checking."""
            if arr and 0 <= idx < len(arr):
                return arr[idx]
            return default
        
        # Get values for match hour
        result = {
            "time": safe_get(times, target_idx, None),
            "precipitation_mm": safe_get(precipitation, target_idx, 0),
            "snowfall_cm": safe_get(snowfall, target_idx, 0),
            "wind_kmh": safe_get(windspeed, target_idx, 0),
            "temperature_c": safe_get(temperature, target_idx, None),
            "lat": lat,
            "lon": lon
        }
        
        return result
        
    except requests.RequestException as e:
        logger.warning(f"Weather API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Weather fetch error: {e}")
        return None


def analyze_weather_impact(weather_data: Dict) -> Optional[Dict]:
    """
    Analyze weather conditions and determine betting impact.
    
    Args:
        weather_data: Raw weather data from get_weather_forecast
        
    Returns:
        Dict with status, impact, and betting advice, or None if good weather
    """
    if not weather_data:
        return None
    
    snow = weather_data.get("snowfall_cm", 0) or 0
    rain = weather_data.get("precipitation_mm", 0) or 0
    wind = weather_data.get("wind_kmh", 0) or 0
    temp = weather_data.get("temperature_c")
    
    conditions = []
    impacts = []
    betting_advice = []
    severity = "NORMAL"
    
    # Check SNOW (highest priority)
    if snow > SNOW_THRESHOLD:
        conditions.append(f"SNOW ({snow:.1f}cm)")
        impacts.append("Extreme conditions - unpredictable outcome")
        betting_advice.append("Strong Under Goals signal")
        betting_advice.append("Avoid match or bet Under")
        severity = "EXTREME"
    
    # Check HIGH WIND
    if wind > WIND_HIGH_THRESHOLD:
        conditions.append(f"HIGH WIND ({wind:.0f}km/h)")
        impacts.append("Long balls ineffective, crossing difficult")
        betting_advice.append("Under Goals likely")
        betting_advice.append("Avoid Over Corners")
        if severity != "EXTREME":
            severity = "HIGH"
    
    # Check HEAVY RAIN
    if rain > RAIN_HEAVY_THRESHOLD:
        conditions.append(f"HEAVY RAIN ({rain:.1f}mm/h)")
        impacts.append("Slippery pitch, sliding tackles, mistakes")
        betting_advice.append("Over Cards more likely")
        betting_advice.append("Defensive errors possible")
        if severity == "NORMAL":
            severity = "MEDIUM"
    
    # If no bad conditions, return None (good weather is irrelevant)
    if severity == "NORMAL":
        return None
    
    # Build result
    result = {
        "status": severity,
        "conditions": conditions,
        "impacts": impacts,
        "betting_advice": betting_advice,
        "raw": {
            "snow_cm": snow,
            "rain_mm": rain,
            "wind_kmh": wind,
            "temp_c": temp
        }
    }
    
    # Build summary string for AI prompt
    condition_str = ", ".join(conditions)
    advice_str = "; ".join(betting_advice)
    result["summary"] = f"⚠️ WEATHER ALERT [{severity}]: {condition_str}. {advice_str}"
    
    # V4.6 FIX: Changed from INFO to DEBUG to reduce log spam
    # The caller (main.py) already logs the weather alert at WARNING level
    # Having both creates duplicate log entries
    logger.debug(f"🌦️ Weather Impact: {result['summary']}")
    
    return result


def get_match_weather(
    lat: float,
    lon: float,
    match_time: datetime
) -> Optional[Dict]:
    """
    Main entry point: Get weather analysis for a match.
    Returns None if coordinates invalid or weather is good.
    
    Args:
        lat: Stadium latitude
        lon: Stadium longitude
        match_time: Match kickoff time
        
    Returns:
        Weather impact dict or None
    """
    # Validate inputs
    if not validate_coordinates(lat, lon):
        return None
    
    if not isinstance(match_time, datetime):
        try:
            # Try to parse if string
            if isinstance(match_time, str):
                match_time = datetime.fromisoformat(match_time.replace('Z', '+00:00'))
            else:
                return None
        except Exception as e:
            logger.debug(f"Could not parse match_time: {e}")
            return None
    
    # Fetch forecast
    forecast = get_weather_forecast(lat, lon, match_time)
    if not forecast:
        return None
    
    # Analyze impact (returns None if good weather)
    return analyze_weather_impact(forecast)
