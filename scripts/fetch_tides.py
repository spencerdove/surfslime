"""
Fetch 7-day tide predictions for NOAA tide stations used by surf spots.
Writes docs/data/tides/{STATION_ID}.json for each station.

Usage:
    python scripts/fetch_tides.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.tides import STATIONS, fetch

OUTPUT_DIR = Path(__file__).parent.parent / "docs/data/tides"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching tides for {len(STATIONS)} stations...")

    errors = []
    for station_id in STATIONS:
        try:
            data = fetch(station_id)
            out_path = OUTPUT_DIR / f"{station_id}.json"
            with open(out_path, "w") as f:
                json.dump(data, f, indent=2)
            n = len(data["predictions"])
            print(f"  -> {out_path.name} ({n} hi/lo predictions)")
        except Exception as e:
            print(f"  ERROR station {station_id}: {e}")
            errors.append(station_id)

    print(f"\nDone. {len(STATIONS) - len(errors)}/{len(STATIONS)} stations written.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
