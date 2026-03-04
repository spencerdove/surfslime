"""
Fetch current conditions and 7-day forecast for all surf spots.
Writes docs/data/conditions/{SPOT_ID}.json for each spot.

Usage:
    python scripts/fetch_conditions.py
    python scripts/fetch_conditions.py --spots trestles windansea
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow imports from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion import cdip, ndbc, open_meteo

SPOTS_FILE = Path(__file__).parent.parent / "docs/data/spots.json"
OUTPUT_DIR = Path(__file__).parent.parent / "docs/data/conditions"

# Meters to feet conversion
M_TO_FT = 3.28084
MS_TO_MPH = 2.23694
KMH_TO_MPH = 0.621371


def load_spots() -> list[dict]:
    with open(SPOTS_FILE) as f:
        return json.load(f)


def angular_distance(a: float, b: float) -> float:
    """Shortest angular distance between two bearings (0-360)."""
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def wind_label(wind_dir_deg: float, spot_best_wind: str) -> str:
    """
    Classify wind as offshore, cross, or onshore relative to the coast.
    Simplified: offshore = wind blowing from land toward sea.
    Uses spot's best wind direction as reference offshore direction.
    """
    # Offshore wind directions for SoCal coast (roughly E-NE-N)
    offshore_dirs = {"NE": 45, "N": 0, "E": 90, "NW": 315, "W": 270}
    best_dir = offshore_dirs.get(spot_best_wind, 45)
    dist = angular_distance(wind_dir_deg, best_dir)

    if dist <= 45:
        return "offshore"
    elif dist <= 90:
        return "cross"
    else:
        return "onshore"


def compute_rating(wave_height_ft, swell_period_s, swell_dir_deg, wind_speed_mph, wind_dir_deg, spot):
    """
    Compute 0-100 surf rating and label.

    Scoring:
    - Wave height (40pts): 0 if outside min/max, linear scale within ideal range
    - Swell period (25pts): 0-25 mapped from 6s to 25s
    - Swell direction (20pts): angular distance from optimal; 0 if >60° off
    - Wind (15pts): offshore=15, cross=8, onshore=0; penalty if >20mph
    """
    best = spot["best"]
    score = 0

    # Wave height (40pts)
    if wave_height_ft is not None:
        h_min = best["height_min_ft"]
        h_max = best["height_max_ft"]
        h_ideal = (h_min + h_max) / 2

        if wave_height_ft < 0.5:
            height_pts = 0  # flat
        elif wave_height_ft < h_min:
            # Below ideal, scale 0-30
            height_pts = int(30 * wave_height_ft / h_min)
        elif wave_height_ft <= h_max:
            # Within range — peak at ideal
            dist_from_ideal = abs(wave_height_ft - h_ideal) / (h_max - h_min) * 2
            height_pts = int(40 * (1 - dist_from_ideal * 0.3))
        else:
            # Over max — linearly decrease
            over = wave_height_ft - h_max
            height_pts = max(0, int(40 - over * 10))

        score += min(40, height_pts)

    # Swell period (25pts): 6s=0, 25s=25
    if swell_period_s is not None:
        p_min, p_max = 6, 25
        period_pts = int(25 * max(0, min(1, (swell_period_s - p_min) / (p_max - p_min))))
        score += period_pts

    # Swell direction (20pts)
    if swell_dir_deg is not None:
        optimal = best["swell_dir_deg"]
        tolerance = best["swell_dir_tolerance"]
        dist = angular_distance(swell_dir_deg, optimal)
        if dist <= tolerance:
            dir_pts = int(20 * (1 - dist / tolerance))
        else:
            dir_pts = 0
        score += dir_pts

    # Wind (15pts)
    if wind_speed_mph is not None and wind_dir_deg is not None:
        wlabel = wind_label(wind_dir_deg, best["wind"])
        if wlabel == "offshore":
            wind_pts = 15
        elif wlabel == "cross":
            wind_pts = 8
        else:
            wind_pts = 0

        # Penalty for strong wind
        if wind_speed_mph > 20:
            wind_pts = max(0, wind_pts - int((wind_speed_mph - 20) * 1.5))

        score += wind_pts

    score = max(0, min(100, score))

    # Label
    if score <= 20:
        label = "flat"
    elif score <= 40:
        label = "poor"
    elif score <= 60:
        label = "fair"
    elif score <= 80:
        label = "good"
    else:
        label = "epic"

    return score, label


def build_forecast_entries(forecast: dict, spot: dict) -> list[dict]:
    """Build hourly forecast array from Open-Meteo data."""
    h = forecast.get("hourly", {})
    times = h.get("time", [])
    entries = []

    for i, t in enumerate(times):
        def v(key):
            arr = h.get(key, [])
            return arr[i] if i < len(arr) else None

        wave_height_m = v("wave_height")
        swell_height_m = v("swell_wave_height")
        swell_period = v("swell_wave_period")
        swell_dir = v("swell_wave_direction")
        wind_speed = v("wind_speed_mph")
        wind_dir = v("wind_direction_deg")
        wind_gusts = v("wind_gusts_mph")

        factor = spot.get("local_height_factor", 1.0)
        wave_height_ft = round(wave_height_m * M_TO_FT * factor, 1) if wave_height_m is not None else None
        swell_height_ft = round(swell_height_m * M_TO_FT * factor, 1) if swell_height_m is not None else None

        rating_score, rating = compute_rating(
            wave_height_ft, swell_period, swell_dir, wind_speed, wind_dir, spot
        )

        wlabel = wind_label(wind_dir, spot["best"]["wind"]) if wind_dir is not None else None

        entries.append({
            "time": f"{t}:00Z" if "T" not in t else t + "Z",
            "wave_height_ft": wave_height_ft,
            "swell_height_ft": swell_height_ft,
            "swell_period_s": round(swell_period, 1) if swell_period else None,
            "swell_direction_deg": round(swell_dir) if swell_dir else None,
            "wind_speed_mph": round(wind_speed, 1) if wind_speed else None,
            "wind_direction_deg": round(wind_dir) if wind_dir else None,
            "wind_gusts_mph": round(wind_gusts, 1) if wind_gusts else None,
            "wind_label": wlabel,
            "rating": rating,
            "rating_score": rating_score,
        })

    return entries


def fetch_buoy_current(spot: dict) -> dict:
    """Fetch current buoy data for a spot, preferring CDIP then NDBC."""
    buoy_id = spot["primary_buoy"]

    try:
        if buoy_id.startswith("cdip-"):
            return cdip.fetch(buoy_id)
        elif buoy_id.startswith("ndbc-"):
            return ndbc.fetch(buoy_id)
    except Exception as e:
        print(f"[fetch_conditions] Buoy fetch failed for {buoy_id}: {e}")

    return {}


def process_spot(spot: dict) -> dict:
    """Build full conditions JSON for a spot."""
    print(f"  Processing {spot['name']}...")

    # Fetch 7-day forecast from Open-Meteo
    forecast = open_meteo.fetch(spot["lat"], spot["lon"])
    forecast_entries = build_forecast_entries(forecast, spot)

    # Fetch current buoy reading
    buoy = fetch_buoy_current(spot)

    # Current conditions: prefer buoy for wave data, forecast[0] for wind
    current_forecast = forecast_entries[0] if forecast_entries else {}

    # Buoy readings (convert m → ft, m/s → mph where needed)
    wvht_m = buoy.get("WVHT")
    swell_h_m = buoy.get("SwH") or buoy.get("WVHT")
    swell_p = buoy.get("SwP") or buoy.get("DPD")
    swell_d = buoy.get("SwD") or buoy.get("MWD")
    wind_spd_ms = buoy.get("WSPD")
    wind_dir = buoy.get("WDIR")

    factor = spot.get("local_height_factor", 1.0)
    wave_height_ft = round(wvht_m * M_TO_FT * factor, 1) if wvht_m else current_forecast.get("wave_height_ft")
    swell_height_ft = round(swell_h_m * M_TO_FT * factor, 1) if swell_h_m else current_forecast.get("swell_height_ft")
    swell_period_s = swell_p or current_forecast.get("swell_period_s")
    swell_dir_deg = swell_d or current_forecast.get("swell_direction_deg")
    wind_speed_mph = round(wind_spd_ms * MS_TO_MPH, 1) if wind_spd_ms else current_forecast.get("wind_speed_mph")
    wind_direction_deg = wind_dir or current_forecast.get("wind_direction_deg")

    wlabel = wind_label(wind_direction_deg, spot["best"]["wind"]) if wind_direction_deg else None
    rating_score, rating = compute_rating(
        wave_height_ft, swell_period_s, swell_dir_deg,
        wind_speed_mph, wind_direction_deg, spot
    )

    return {
        "spot_id": spot["id"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rating": rating,
        "rating_score": rating_score,
        "current": {
            "wave_height_ft": wave_height_ft,
            "swell_height_ft": swell_height_ft,
            "swell_period_s": round(swell_period_s, 1) if swell_period_s else None,
            "swell_direction_deg": round(swell_dir_deg) if swell_dir_deg else None,
            "wind_speed_mph": wind_speed_mph,
            "wind_direction_deg": round(wind_direction_deg) if wind_direction_deg else None,
            "wind_label": wlabel,
        },
        "buoy_id": spot["primary_buoy"],
        "buoy_timestamp": buoy.get("timestamp"),
        "forecast": forecast_entries,
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch surf conditions for all spots")
    parser.add_argument("--spots", nargs="+", help="Spot IDs to process (default: all)")
    args = parser.parse_args()

    spots = load_spots()
    if args.spots:
        spots = [s for s in spots if s["id"] in args.spots]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Fetching conditions for {len(spots)} spots...")
    errors = []

    for spot in spots:
        try:
            conditions = process_spot(spot)
            out_path = OUTPUT_DIR / f"{spot['id']}.json"
            with open(out_path, "w") as f:
                json.dump(conditions, f, indent=2)
            print(f"  -> {out_path.name} ({conditions['rating']}, score={conditions['rating_score']})")
        except Exception as e:
            print(f"  ERROR processing {spot['id']}: {e}")
            errors.append(spot["id"])

    print(f"\nDone. {len(spots) - len(errors)}/{len(spots)} spots written.")
    if errors:
        print(f"Errors: {errors}")
        sys.exit(1)


if __name__ == "__main__":
    main()
