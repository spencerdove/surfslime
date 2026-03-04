"""
Fetch wave buoy data from CDIP (Coastal Data Information Program) via ERDDAP.
Uses the wave_agg aggregated dataset with station_id filtering.

Stations: 045 (Torrey Pines), 071 (Nearshore SD), 073 (Oceanside), 201 (Point Loma South)
"""

import requests
from datetime import datetime, timezone, timedelta

ERDDAP_BASE = "https://erddap.cdip.ucsd.edu/erddap/tabledap"
DATASET = "wave_agg"

# Map our buoy IDs to CDIP station_id values used in wave_agg
STATIONS = {
    "cdip-045": "045",
    "cdip-071": "071",
    "cdip-073": "073",
    "cdip-201": "201",
}


def fetch(buoy_id):
    """
    Fetch latest CDIP wave data for a given station ID (e.g. 'cdip-045').
    Returns dict with wave height (m), period (s), direction (deg), timestamp.
    """
    station_id = STATIONS.get(buoy_id)
    if not station_id:
        raise ValueError("Unknown CDIP buoy: {}".format(buoy_id))

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=6)
    start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")

    fields = "time,waveHs,waveTp,waveDp,waveTa"
    url = (
        "{base}/{dataset}.json"
        "?{fields}"
        "&station_id=%22{sid}%22"
        "&time>={start}"
        "&orderByLimit(%22time,1%22)"
    ).format(
        base=ERDDAP_BASE,
        dataset=DATASET,
        fields=fields,
        sid=station_id,
        start=start_str,
    )

    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()

        rows = data.get("table", {}).get("rows", [])
        col_names = data.get("table", {}).get("columnNames", [])

        if not rows:
            return _empty(buoy_id)

        row = rows[-1]
        row_dict = dict(zip(col_names, row))

        return {
            "buoy_id": buoy_id,
            "source": "cdip",
            "timestamp": row_dict.get("time"),
            "WVHT": _safe_float(row_dict.get("waveHs")),
            "DPD":  _safe_float(row_dict.get("waveTp")),
            "APD":  _safe_float(row_dict.get("waveTa")),
            "MWD":  _safe_float(row_dict.get("waveDp")),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print("[cdip] Error fetching {}: {}".format(buoy_id, e))
        return _empty(buoy_id)


def _safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _empty(buoy_id):
    return {
        "buoy_id": buoy_id,
        "source": "cdip",
        "timestamp": None,
        "WVHT": None,
        "DPD": None,
        "APD": None,
        "MWD": None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import json
    for bid in STATIONS:
        data = fetch(bid)
        print(json.dumps(data, indent=2))
