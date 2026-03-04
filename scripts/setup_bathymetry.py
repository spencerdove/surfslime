"""
One-time script to generate bathymetry contour GeoJSON for all surf spots.
Writes docs/data/bathymetry/{SPOT_ID}.json for each spot.

Usage:
    python scripts/setup_bathymetry.py
    python scripts/setup_bathymetry.py --spots trestles windansea
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.bathymetry import fetch_contours

SPOTS_FILE = Path(__file__).parent.parent / "docs/data/spots.json"
OUTPUT_DIR = Path(__file__).parent.parent / "docs/data/bathymetry"


def main():
    parser = argparse.ArgumentParser(description="Generate bathymetry GeoJSON for surf spots")
    parser.add_argument("--spots", nargs="+", help="Spot IDs to process (default: all)")
    parser.add_argument("--pad", type=float, default=0.3, help="Bounding box padding in degrees (default: 0.3)")
    args = parser.parse_args()

    with open(SPOTS_FILE) as f:
        spots = json.load(f)

    if args.spots:
        spots = [s for s in spots if s["id"] in args.spots]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating bathymetry for {len(spots)} spots (pad=±{args.pad}°)...")

    errors = []
    for spot in spots:
        print(f"  Processing {spot['name']} ({spot['lat']}, {spot['lon']})...")
        try:
            geojson = fetch_contours(spot["lat"], spot["lon"], pad=args.pad)
            out_path = OUTPUT_DIR / f"{spot['id']}.json"
            with open(out_path, "w") as f:
                json.dump(geojson, f)
            n = len(geojson.get("features", []))
            print(f"    -> {out_path.name} ({n} contour features)")
            if "error" in geojson:
                print(f"    Warning: {geojson['error']}")
        except Exception as e:
            print(f"    ERROR: {e}")
            errors.append(spot["id"])

    print(f"\nDone. {len(spots) - len(errors)}/{len(spots)} spots written.")
    if errors:
        print(f"Errors: {errors}")
        sys.exit(1)


if __name__ == "__main__":
    main()
