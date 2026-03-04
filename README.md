# Surfslime 🌊

Real-time surf forecast for San Diego + Orange County. Zero-cost static site on GitHub Pages.

**Live:** [surfslime.com](https://surfslime.com) *(GitHub Pages — configure CNAME to activate)*

## Architecture

```
Public APIs → Python ingestion → JSON files → GitHub Pages → Vanilla JS frontend
```

- **No backend server.** All data is static JSON committed to `docs/data/`.
- **GitHub Actions** fetches fresh conditions every 2 hours and tides daily.
- **Free tier friendly:** ~360 runs/month at ~1 min each ≈ 360 min (free limit: 2000 min).

## Spots (13)

| County | Spots |
|--------|-------|
| Orange County | Trestles, Salt Creek, Huntington Pier, The Wedge, Doheny |
| San Diego | Blacks, Windansea, Ocean Beach, Pacific Beach, Sunset Cliffs, Swami's, Cardiff Reef, Del Mar |

## Data Sources

| Source | Data | Cost |
|--------|------|------|
| [NDBC](https://www.ndbc.noaa.gov) | Real-time buoy (wave height, period, direction, wind) | Free |
| [CDIP](https://cdip.ucsd.edu) | ERDDAP buoy data (SoCal-specific stations) | Free |
| [Open-Meteo](https://open-meteo.com) | 7-day marine + wind forecast | Free |
| [NOAA CO-OPS](https://tidesandcurrents.noaa.gov) | Tide predictions | Free |
| [NOAA NCEI](https://www.ncei.noaa.gov) | Bathymetry (ETOPO 2022) | Free |

## Setup

```bash
pip install -r requirements.txt

# Fetch conditions for all spots
python scripts/fetch_conditions.py

# Fetch tide predictions
python scripts/fetch_tides.py

# One-time: generate bathymetry GeoJSON (requires rasterio)
python scripts/setup_bathymetry.py
```

## Surf Rating Algorithm

Scores each hour 0–100:

| Factor | Points | Notes |
|--------|--------|-------|
| Wave height | 40 | 0 if flat or over-max; peaks at ideal mid-range |
| Swell period | 25 | Linear 6s→0, 25s→25 |
| Swell direction | 20 | Angular distance from spot's optimal direction |
| Wind | 15 | Offshore=15, cross=8, onshore=0; -1.5 per mph over 20 |

Labels: 0–20 flat, 21–40 poor, 41–60 fair, 61–80 good, 81–100 epic.

## GitHub Pages Setup

1. Go to repo Settings → Pages
2. Source: Deploy from branch, branch: `main`, folder: `/docs`
3. (Optional) Add CNAME file for custom domain

## GitHub Actions

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| `fetch_conditions.yml` | Every 2 hours | Update `conditions/*.json` |
| `fetch_tides.yml` | Daily 00:05 UTC | Update `tides/*.json` |
| `setup_bathymetry.yml` | Manual only | Generate `bathymetry/*.json` |
