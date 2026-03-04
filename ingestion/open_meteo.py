"""
Fetch 7-day marine + weather forecast from Open-Meteo (free, no API key required).
Marine API: https://marine-api.open-meteo.com
Weather API: https://api.open-meteo.com
"""

import requests
from datetime import datetime, timezone

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

MARINE_VARS = [
    "wave_height",
    "wave_direction",
    "wave_period",
    "swell_wave_height",
    "swell_wave_direction",
    "swell_wave_period",
    "wind_wave_height",
    "wind_wave_direction",
    "wind_wave_period",
]

WEATHER_VARS = [
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
]


def fetch(lat: float, lon: float) -> dict:
    """
    Fetch 7-day hourly marine + wind forecast for a lat/lon point.
    Returns dict with 'hourly' key containing arrays of forecast data.
    All heights in meters, periods in seconds, directions in degrees, wind in km/h.
    """
    marine_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(MARINE_VARS),
        "forecast_days": 7,
        "timezone": "UTC",
    }
    weather_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(WEATHER_VARS),
        "forecast_days": 7,
        "timezone": "UTC",
        "wind_speed_unit": "mph",
    }

    try:
        marine_r = requests.get(MARINE_URL, params=marine_params, timeout=15)
        marine_r.raise_for_status()
        marine_data = marine_r.json()

        weather_r = requests.get(WEATHER_URL, params=weather_params, timeout=15)
        weather_r.raise_for_status()
        weather_data = weather_r.json()

        hourly = marine_data.get("hourly", {})
        w_hourly = weather_data.get("hourly", {})

        # Merge wind data into hourly
        hourly["wind_speed_mph"] = w_hourly.get("wind_speed_10m", [])
        hourly["wind_direction_deg"] = w_hourly.get("wind_direction_10m", [])
        hourly["wind_gusts_mph"] = w_hourly.get("wind_gusts_10m", [])

        return {
            "lat": lat,
            "lon": lon,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "hourly_units": {
                **marine_data.get("hourly_units", {}),
                "wind_speed_mph": "mph",
                "wind_direction_deg": "°",
            },
            "hourly": hourly,
        }
    except Exception as e:
        print(f"[open_meteo] Error fetching ({lat}, {lon}): {e}")
        return {
            "lat": lat,
            "lon": lon,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "hourly": {},
        }


def get_current(forecast: dict, time_index: int = 0) -> dict:
    """Extract current conditions from forecast hourly arrays at given index."""
    h = forecast.get("hourly", {})
    times = h.get("time", [])
    idx = min(time_index, len(times) - 1) if times else 0

    def val(key):
        arr = h.get(key, [])
        return arr[idx] if idx < len(arr) else None

    return {
        "time": times[idx] if idx < len(times) else None,
        "wave_height": val("wave_height"),
        "wave_period": val("wave_period"),
        "wave_direction": val("wave_direction"),
        "swell_height": val("swell_wave_height"),
        "swell_period": val("swell_wave_period"),
        "swell_direction": val("swell_wave_direction"),
        "wind_wave_height": val("wind_wave_height"),
        "wind_speed_mph": val("wind_speed_mph"),
        "wind_direction_deg": val("wind_direction_deg"),
        "wind_gusts_mph": val("wind_gusts_mph"),
    }


if __name__ == "__main__":
    import json
    # Test with Trestles coordinates
    data = fetch(33.3719, -117.5892)
    print(json.dumps(get_current(data), indent=2))
    print(f"Got {len(data['hourly'].get('time', []))} hourly forecasts")
