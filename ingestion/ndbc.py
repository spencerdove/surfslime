"""
Fetch real-time buoy data from NDBC (National Data Buoy Center).
Parses whitespace-delimited .txt (standard meteorological) and .spec (spectral) files.
"""

import requests
from datetime import datetime, timezone

NDBC_BASE = "https://www.ndbc.noaa.gov/data/realtime2"

# Stations used: 46086 (San Nicolas Island, offshore SoCal)
STATIONS = {
    "ndbc-46086": "46086",
}


def _fetch_text(url: str) -> list[list[str]]:
    """Fetch and parse whitespace-delimited NDBC file into rows."""
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    lines = r.text.strip().splitlines()
    # Skip header rows (start with #)
    data_lines = [l for l in lines if not l.startswith("#")]
    return [l.split() for l in data_lines if l.strip()]


def _parse_meteorological(station_id: str) -> dict:
    """Parse .txt standard meteorological file."""
    url = f"{NDBC_BASE}/{station_id}.txt"
    rows = _fetch_text(url)
    if not rows:
        return {}

    # First row is most recent observation
    row = rows[0]
    # Columns: YY MM DD hh mm WDIR WSPD GST WVHT DPD APD MWD PRES ATMP WTMP DEWP VIS PTDY TIDE
    try:
        result = {
            "WDIR": _safe_float(row[5]),   # Wind direction (deg)
            "WSPD": _safe_float(row[6]),   # Wind speed (m/s)
            "WVHT": _safe_float(row[8]),   # Significant wave height (m)
            "DPD":  _safe_float(row[9]),   # Dominant wave period (s)
            "APD":  _safe_float(row[10]),  # Average wave period (s)
            "MWD":  _safe_float(row[11]),  # Mean wave direction (deg)
        }
        # Timestamp
        yy, mm, dd, hh, mn = row[0], row[1], row[2], row[3], row[4]
        result["timestamp"] = f"20{yy}-{mm}-{dd}T{hh}:{mn}:00Z"
        return result
    except (IndexError, ValueError):
        return {}


def _parse_spectral(station_id: str) -> dict:
    """Parse .spec spectral summary file for additional wave info."""
    url = f"{NDBC_BASE}/{station_id}.spec"
    try:
        rows = _fetch_text(url)
        if not rows:
            return {}
        row = rows[0]
        # Columns: YY MM DD hh mm WVHT SwH SwP WWH WWP SwD WWD STEEPNESS APD MWD
        return {
            "WVHT": _safe_float(row[5]),   # Significant wave height (m)
            "SwH":  _safe_float(row[6]),   # Swell height (m)
            "SwP":  _safe_float(row[7]),   # Swell period (s)
            "WWH":  _safe_float(row[8]),   # Wind wave height (m)
            "WWP":  _safe_float(row[9]),   # Wind wave period (s)
            "SwD":  _safe_float(row[10]),  # Swell direction
            "WWD":  _safe_float(row[11]),  # Wind wave direction
            "MWD":  _safe_float(row[14]) if len(row) > 14 else None,
        }
    except Exception:
        return {}


def _safe_float(val: str):
    """Return float or None for NDBC missing values (MM, 999, 9999, etc.)."""
    try:
        f = float(val)
        if f in (999.0, 9999.0, 99.0, 9999.9):
            return None
        return f
    except (ValueError, TypeError):
        return None


def fetch(buoy_id: str) -> dict:
    """
    Fetch NDBC buoy data for a given buoy ID (e.g. 'ndbc-46086').
    Returns dict with keys: WVHT, DPD, MWD, WSPD, WDIR, SwH, SwP, SwD, timestamp
    Units: heights in meters, speeds in m/s, directions in degrees.
    """
    station_id = STATIONS.get(buoy_id)
    if not station_id:
        raise ValueError(f"Unknown NDBC buoy: {buoy_id}")

    met = _parse_meteorological(station_id)
    spec = _parse_spectral(station_id)

    # Merge, preferring spectral data for wave params
    result = {**met, **{k: v for k, v in spec.items() if v is not None}}
    result["buoy_id"] = buoy_id
    result["source"] = "ndbc"
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == "__main__":
    import json
    data = fetch("ndbc-46086")
    print(json.dumps(data, indent=2))
