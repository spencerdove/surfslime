"""
Fetch 7-day tide predictions from NOAA Tides & Currents API (CO-OPS).
Free, no API key required.
"""

import requests
from datetime import datetime, timezone, timedelta

COOPS_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

# Tide stations used
STATIONS = {
    "9410230": {"name": "Oceanside, CA", "lat": 33.2150, "lon": -117.3914},
    "9410660": {"name": "Los Angeles (Outer Harbor), CA", "lat": 33.7200, "lon": -118.2717},
}


def fetch(station_id: str, days: int = 7) -> dict:
    """
    Fetch tide predictions for next N days at given NOAA station.
    Returns dict with predictions list [{t, v, type}] for hi/lo only.
    """
    now = datetime.now(timezone.utc)
    begin = now.strftime("%Y%m%d")
    end = (now + timedelta(days=days)).strftime("%Y%m%d")

    params = {
        "product": "predictions",
        "application": "surfslime",
        "begin_date": begin,
        "end_date": end,
        "datum": "MLLW",
        "station": station_id,
        "time_zone": "GMT",
        "interval": "hilo",
        "units": "english",
        "format": "json",
    }

    try:
        r = requests.get(COOPS_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        predictions = data.get("predictions", [])
        return {
            "station": station_id,
            "station_name": STATIONS.get(station_id, {}).get("name", ""),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "datum": "MLLW",
            "units": "ft",
            "predictions": predictions,
        }
    except Exception as e:
        print(f"[tides] Error fetching station {station_id}: {e}")
        return {
            "station": station_id,
            "station_name": STATIONS.get(station_id, {}).get("name", ""),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "datum": "MLLW",
            "units": "ft",
            "predictions": [],
        }


def get_current_tide_height(predictions):
    # type: (list) -> tuple
    """
    Estimate current tide height and label (rising/falling/high/low)
    by interpolating between hi/lo predictions.
    """
    now = datetime.now(timezone.utc)

    def parse_t(t_str: str) -> datetime:
        return datetime.strptime(t_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)

    parsed = []
    for p in predictions:
        try:
            parsed.append({"t": parse_t(p["t"]), "v": float(p["v"]), "type": p.get("type", "")})
        except (ValueError, KeyError):
            continue

    if not parsed:
        return None, "unknown"

    # Find surrounding hi/lo
    before = [p for p in parsed if p["t"] <= now]
    after = [p for p in parsed if p["t"] > now]

    if not before or not after:
        return None, "unknown"

    prev = before[-1]
    nxt = after[0]

    # Linear interpolation
    total_sec = (nxt["t"] - prev["t"]).total_seconds()
    elapsed_sec = (now - prev["t"]).total_seconds()
    frac = elapsed_sec / total_sec if total_sec > 0 else 0
    height = prev["v"] + frac * (nxt["v"] - prev["v"])

    label = "rising" if nxt["v"] > prev["v"] else "falling"
    return round(height, 2), label


if __name__ == "__main__":
    import json
    for sid in STATIONS:
        data = fetch(sid)
        print(f"\nStation {sid}: {len(data['predictions'])} hi/lo predictions")
        if data["predictions"]:
            print(f"First: {data['predictions'][0]}")
        h, label = get_current_tide_height(data["predictions"])
        print(f"Current height: {h} ft ({label})")
