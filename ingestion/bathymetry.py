"""
Generate bathymetry contour GeoJSON for each surf spot.
Uses NOAA NCEI Coastal Relief Model (Southern California, 3 arc-second resolution).

Data source: https://www.ncei.noaa.gov/maps/bathymetry/
Download tile via THREDDS/OPeNDAP or direct HTTP.

Requires: rasterio, numpy, shapely, requests
"""

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import requests

try:
    import rasterio
    from rasterio.transform import from_bounds
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.contour import QuadContourSet
    from shapely.geometry import mapping, LineString, MultiLineString
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False
    print("[bathymetry] Warning: rasterio/matplotlib/shapely not installed")

# NOAA Southern California Coastal Relief Model
# OPeNDAP endpoint for on-the-fly subsetting
NOAA_CRM_URL = (
    "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/"
    "DEM_global_mosaic_hillshade/ImageServer/exportImage"
)

# Depth contours to generate (negative = below sea level, in meters)
CONTOUR_DEPTHS_M = [-5, -10, -20, -50]
CONTOUR_COLORS = {
    -5:  "#00d4ff",
    -10: "#0099cc",
    -20: "#0080ff",
    -50: "#003380",
}
CONTOUR_LABELS = {
    -5:  "16 ft",
    -10: "33 ft",
    -20: "66 ft",
    -50: "164 ft",
}


def _fetch_etopo_tile(lat: float, lon: float, pad: float = 0.5) -> tuple:
    """
    Fetch bathymetry data from GEBCO/ETOPO via open-topography or NOAA WCS.
    Returns (elevation_array_m, transform, crs) or None on failure.

    Uses NOAA ERDDAP gridded bathymetry as fallback.
    """
    # NOAA ERDDAP gridded dataset (ETOPO 2022)
    lat_min = lat - pad
    lat_max = lat + pad
    lon_min = lon - pad
    lon_max = lon + pad

    # Use NOAA NCEI ERDDAP for ETOPO 2022 1 arc-minute data
    url = (
        "https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.json"
        f"?altitude%5B({lat_min}):({lat_max})%5D%5B({lon_min}):({lon_max})%5D"
    )

    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()

        table = data.get("table", {})
        col_names = table.get("columnNames", [])
        rows = table.get("rows", [])

        if not rows:
            return None

        lat_idx = col_names.index("latitude")
        lon_idx = col_names.index("longitude")
        alt_idx = col_names.index("altitude")

        lats = sorted(set(row[lat_idx] for row in rows))
        lons = sorted(set(row[lon_idx] for row in rows))

        grid = np.full((len(lats), len(lons)), np.nan)
        lat_map = {v: i for i, v in enumerate(lats)}
        lon_map = {v: i for i, v in enumerate(lons)}

        for row in rows:
            i = lat_map[row[lat_idx]]
            j = lon_map[row[lon_idx]]
            grid[i, j] = row[alt_idx]

        return grid, lats, lons

    except Exception as e:
        print(f"[bathymetry] ERDDAP fetch failed: {e}")
        return None


def _generate_contours(grid: np.ndarray, lats: list, lons: list, depths: list) -> list:
    """Generate contour lines from grid data at given depth levels."""
    features = []

    lon_grid, lat_grid = np.meshgrid(lons, lats)

    fig, ax = plt.subplots()
    cs = ax.contour(lon_grid, lat_grid, grid, levels=sorted(depths))

    for level, collection in zip(cs.levels, cs.collections):
        if level not in depths:
            continue

        depth_m = int(level)
        depth_ft = abs(int(level * 3.28084))
        lines = []

        for path in collection.get_paths():
            coords = path.vertices.tolist()
            if len(coords) >= 2:
                lines.append(coords)

        if not lines:
            continue

        geom = MultiLineString(lines) if len(lines) > 1 else LineString(lines[0])
        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "depth_m": depth_m,
                "depth_ft": depth_ft,
                "label": CONTOUR_LABELS.get(level, f"{abs(level)}m"),
                "color": CONTOUR_COLORS.get(level, "#888888"),
            }
        })

    plt.close(fig)
    return features


def fetch_contours(lat: float, lon: float, pad: float = 0.3) -> dict:
    """
    Generate bathymetry contour GeoJSON for a spot location.
    Returns GeoJSON FeatureCollection.
    """
    if not RASTERIO_AVAILABLE:
        return {"type": "FeatureCollection", "features": [], "error": "rasterio not installed"}

    result = _fetch_etopo_tile(lat, lon, pad)
    if result is None:
        return {"type": "FeatureCollection", "features": [], "error": "data fetch failed"}

    grid, lats, lons = result

    # Only use cells below sea level (negative values)
    ocean_grid = np.where(grid < 0, grid, np.nan)

    features = _generate_contours(ocean_grid, lats, lons, CONTOUR_DEPTHS_M)

    return {
        "type": "FeatureCollection",
        "bbox": [lon - pad, lat - pad, lon + pad, lat + pad],
        "features": features,
    }


if __name__ == "__main__":
    # Test with Trestles
    result = fetch_contours(33.3719, -117.5892)
    print(f"Generated {len(result['features'])} contour features")
    if result["features"]:
        print(f"First feature depth: {result['features'][0]['properties']['depth_m']}m")
