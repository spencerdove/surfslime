"use strict";

// ===== CONFIG =====
const DATA_BASE = "data";
const ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const ESRI_ATTR = "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community";
const RATING_COLORS = {
  epic: "#ff6b35",
  good: "#4caf50",
  fair: "#ffc107",
  poor: "#9e9e9e",
  flat: "#455a64",
};

// ===== STATE =====
let spots = [];
let selectedSpotId = null;
let markers = {};
let conditionsCache = {};
let tidesCache = {};
let bathyLayers = {};
let depthLayerGroup = null;
let depthVisible = false;
let osmLayer = null;
let esriLayer = null;
let satelliteMode = false;
let forecastChart = null;
let tideChart = null;
let map = null;
let activeCounty = "all";

// ===== INIT =====
async function init() {
  initMap();
  await loadSpots();
  checkUrlParam();
}

// ===== MAP =====
function initMap() {
  map = L.map("map", {
    center: [33.1, -117.4],
    zoom: 10,
    zoomControl: true,
  });

  osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
  });
  osmLayer.addTo(map);

  depthLayerGroup = L.layerGroup().addTo(map);

  document.getElementById("satellite-toggle").addEventListener("click", toggleSatellite);
  document.getElementById("depth-toggle").addEventListener("click", toggleDepth);
}

// ===== SPOTS =====
async function loadSpots() {
  const res = await fetch(`${DATA_BASE}/spots.json`);
  spots = await res.json();
  renderMarkers();

  // Kick off conditions fetch for all spots
  spots.forEach(fetchConditions);
}

function renderMarkers() {
  const filtered = activeCounty === "all"
    ? spots
    : spots.filter(s => s.county === activeCounty);

  // Remove old markers not in filtered set
  const filteredIds = new Set(filtered.map(s => s.id));
  Object.entries(markers).forEach(([id, m]) => {
    if (!filteredIds.has(id)) {
      m.remove();
      delete markers[id];
    }
  });

  filtered.forEach(spot => {
    if (!markers[spot.id]) {
      const el = document.createElement("div");
      el.className = "surf-marker loading";
      el.setAttribute("data-id", spot.id);

      const label = document.createElement("span");
      label.className = "marker-label";
      label.textContent = spot.name;
      el.appendChild(label);

      // Score display (filled once conditions load)
      const scoreSpan = document.createElement("span");
      scoreSpan.className = "marker-score";
      scoreSpan.textContent = "—";
      el.appendChild(scoreSpan);

      const icon = L.divIcon({ html: el, className: "", iconSize: [36, 36], iconAnchor: [18, 18] });
      const marker = L.marker([spot.lat, spot.lon], { icon }).addTo(map);
      marker.on("click", () => selectSpot(spot.id));
      markers[spot.id] = marker;
    }
  });
}

function updateMarker(spotId, rating, score) {
  const marker = markers[spotId];
  if (!marker) return;

  const el = marker.getElement();
  if (!el) return;

  const div = el.querySelector(".surf-marker") || el;
  div.className = `surf-marker ${rating}`;

  const scoreSpan = div.querySelector(".marker-score");
  if (scoreSpan) scoreSpan.textContent = score;
}

// ===== CONDITIONS =====
async function fetchConditions(spot) {
  try {
    const res = await fetch(`${DATA_BASE}/conditions/${spot.id}.json`);
    if (!res.ok) return;
    const data = await res.json();
    conditionsCache[spot.id] = data;
    updateMarker(spot.id, data.rating, data.rating_score);

    if (selectedSpotId === spot.id) {
      renderSidebar(spot.id);
    }

    updateLastUpdated();
  } catch (e) {
    console.warn(`[surfslime] Failed to fetch conditions for ${spot.id}:`, e);
  }
}

// ===== TIDES =====
async function fetchTides(stationId) {
  if (tidesCache[stationId]) return tidesCache[stationId];
  try {
    const res = await fetch(`${DATA_BASE}/tides/${stationId}.json`);
    if (!res.ok) return null;
    const data = await res.json();
    tidesCache[stationId] = data;
    return data;
  } catch (e) {
    return null;
  }
}

// ===== SPOT SELECTION =====
function selectSpot(spotId) {
  selectedSpotId = spotId;

  // Update URL
  const url = new URL(window.location);
  url.searchParams.set("spot", spotId);
  window.history.replaceState({}, "", url);

  // Deselect previous marker
  document.querySelectorAll(".surf-marker.selected").forEach(el => el.classList.remove("selected"));

  // Select new marker
  const marker = markers[spotId];
  if (marker) {
    const el = marker.getElement();
    if (el) {
      const div = el.querySelector(".surf-marker") || el;
      div.classList.add("selected");
    }
    map.panTo(marker.getLatLng());
  }

  renderSidebar(spotId);
}

function checkUrlParam() {
  const params = new URLSearchParams(window.location.search);
  const spotParam = params.get("spot");
  if (spotParam && spots.find(s => s.id === spotParam)) {
    selectSpot(spotParam);
  }
}

// ===== SIDEBAR =====
async function renderSidebar(spotId) {
  const spot = spots.find(s => s.id === spotId);
  if (!spot) return;

  const conditions = conditionsCache[spotId];

  document.getElementById("sidebar-empty").classList.add("hidden");
  document.getElementById("sidebar-content").classList.remove("hidden");

  // Header
  document.getElementById("spot-name").textContent = spot.name;
  document.getElementById("spot-meta").textContent = `${spot.county} · ${formatBreakType(spot.break_type)}`;

  // Rating badge
  const badge = document.getElementById("spot-rating-badge");
  const rating = conditions?.rating || "loading";
  const score = conditions?.rating_score ?? "—";
  badge.className = `${rating}`;
  document.getElementById("rating-label").textContent = rating;
  document.getElementById("rating-score").textContent = score;

  // Current conditions
  if (conditions?.current) {
    const c = conditions.current;
    setCondCell("cond-wave-height", c.wave_height_ft != null ? `${c.wave_height_ft} ft` : "—");
    setCondCell("cond-swell-period", c.swell_period_s != null ? `${c.swell_period_s}s` : "—");
    setCondCell("cond-swell-dir", c.swell_direction_deg != null ? `${c.swell_direction_deg}° ${degToCardinal(c.swell_direction_deg)}` : "—");
    setCondCell("cond-wind", c.wind_speed_mph != null ? `${c.wind_speed_mph} mph` : "—");

    const windLabelEl = document.getElementById("cond-wind-label");
    windLabelEl.textContent = c.wind_label || "—";
    windLabelEl.className = `cond-sublabel ${c.wind_label || ""}`;
  }

  // Spot details
  document.getElementById("detail-break-type").textContent = formatBreakType(spot.break_type);
  document.getElementById("detail-best-swell").textContent =
    `${spot.best.swell_dir_deg}° ±${spot.best.swell_dir_tolerance}°`;
  document.getElementById("detail-best-height").textContent =
    `${spot.best.height_min_ft}–${spot.best.height_max_ft} ft`;
  document.getElementById("detail-best-period").textContent = `${spot.best.period_min_s}s+`;
  document.getElementById("detail-best-wind").textContent = spot.best.wind;
  document.getElementById("detail-best-tide").textContent = spot.best.tide;

  // Buoy attribution
  document.getElementById("buoy-attribution").textContent =
    `Buoy: ${spot.primary_buoy} · Updated: ${conditions?.updated_at ? formatTime(conditions.updated_at) : "—"}`;

  // Charts
  if (conditions?.forecast?.length) {
    renderForecastChart(conditions.forecast);
  }

  // Tides
  const tideData = await fetchTides(spot.tide_station);
  if (tideData) {
    renderTideChart(tideData);
  }

  // Bathymetry
  loadBathymetry(spotId);
}

function setCondCell(id, value) {
  document.getElementById(id).textContent = value;
}

// ===== FORECAST CHART =====
function renderForecastChart(forecast) {
  const canvas = document.getElementById("forecast-chart");
  if (forecastChart) forecastChart.destroy();

  // Show next 7 days at 6-hour intervals
  const entries = forecast.filter((_, i) => i % 6 === 0).slice(0, 28);

  const labels = entries.map(e => {
    const d = new Date(e.time);
    return d.toLocaleDateString("en-US", { weekday: "short", month: "numeric", day: "numeric" });
  });

  const heights = entries.map(e => e.wave_height_ft ?? 0);
  const ratings = entries.map(e => e.rating || "flat");

  const bgColors = ratings.map(r => RATING_COLORS[r] + "66");
  const borderColors = ratings.map(r => RATING_COLORS[r]);

  forecastChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Wave Height (ft)",
        data: heights,
        backgroundColor: bgColors,
        borderColor: borderColors,
        borderWidth: 1,
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterLabel: (ctx) => {
              const e = entries[ctx.dataIndex];
              return [
                `Period: ${e.swell_period_s ?? "—"}s`,
                `Wind: ${e.wind_speed_mph ?? "—"} mph ${e.wind_label || ""}`,
                `Rating: ${e.rating}`,
              ].join("\n");
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#7a8494", font: { size: 10 }, maxRotation: 45 },
          grid: { color: "#2a3040" },
        },
        y: {
          ticks: { color: "#7a8494", font: { size: 10 }, callback: v => `${v}ft` },
          grid: { color: "#2a3040" },
          beginAtZero: true,
        },
      },
    },
  });
}

// ===== TIDE CHART =====
function renderTideChart(tideData) {
  const canvas = document.getElementById("tide-chart");
  if (tideChart) tideChart.destroy();

  const predictions = tideData.predictions || [];
  // Show next 48h
  const now = Date.now();
  const cutoff = now + 48 * 3600 * 1000;

  const filtered = predictions.filter(p => {
    const t = new Date(p.t).getTime();
    return t >= now - 3600000 && t <= cutoff;
  });

  if (!filtered.length) return;

  const labels = filtered.map(p => {
    const d = new Date(p.t);
    return d.toLocaleTimeString("en-US", { hour: "numeric", hour12: true });
  });
  const values = filtered.map(p => parseFloat(p.v));

  // Current tide height (interpolate)
  const currentHeight = interpolateTide(predictions, now);
  if (currentHeight != null) {
    const heightStr = `${currentHeight.toFixed(1)} ft`;
    document.getElementById("tide-height-display").textContent = heightStr;
  }

  tideChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Tide (ft)",
        data: values,
        borderColor: "#00d4ff",
        backgroundColor: "rgba(0, 212, 255, 0.1)",
        borderWidth: 2,
        pointRadius: 4,
        pointBackgroundColor: filtered.map(p =>
          p.type === "H" ? "#4caf50" : p.type === "L" ? "#ff6b35" : "#00d4ff"
        ),
        tension: 0.4,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              const p = filtered[ctx.dataIndex];
              const typeLabel = p.type === "H" ? " (High)" : p.type === "L" ? " (Low)" : "";
              return `${ctx.parsed.y.toFixed(2)} ft${typeLabel}`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#7a8494", font: { size: 10 }, maxTicksLimit: 8 },
          grid: { color: "#2a3040" },
        },
        y: {
          ticks: { color: "#7a8494", font: { size: 10 }, callback: v => `${v}ft` },
          grid: { color: "#2a3040" },
        },
      },
    },
  });
}

function interpolateTide(predictions, nowMs) {
  const parsed = predictions.map(p => ({
    t: new Date(p.t).getTime(),
    v: parseFloat(p.v),
  })).filter(p => !isNaN(p.t) && !isNaN(p.v));

  const before = parsed.filter(p => p.t <= nowMs);
  const after = parsed.filter(p => p.t > nowMs);

  if (!before.length || !after.length) return null;

  const prev = before[before.length - 1];
  const next = after[0];
  const frac = (nowMs - prev.t) / (next.t - prev.t);
  return prev.v + frac * (next.v - prev.v);
}

// ===== BATHYMETRY =====
async function loadBathymetry(spotId) {
  if (bathyLayers[spotId]) return; // already loaded

  try {
    const res = await fetch(`${DATA_BASE}/bathymetry/${spotId}.json`);
    if (!res.ok) return;
    const geojson = await res.json();

    if (!geojson.features?.length) return;

    const layer = L.geoJSON(geojson, {
      style: feature => ({
        color: feature.properties.color || "#00d4ff",
        weight: 1,
        opacity: 0.7,
        fill: false,
      }),
      onEachFeature: (feature, layer) => {
        layer.bindTooltip(
          `${feature.properties.label || ""} (${feature.properties.depth_ft || "?"}ft)`,
          { sticky: true, className: "depth-tooltip" }
        );
      },
    });

    bathyLayers[spotId] = layer;

    if (depthVisible) {
      depthLayerGroup.addLayer(layer);
    }
  } catch (e) {
    // Bathymetry is optional — silently skip
  }
}

function toggleSatellite() {
  const btn = document.getElementById("satellite-toggle");
  satelliteMode = !satelliteMode;
  if (satelliteMode) {
    if (!esriLayer) esriLayer = L.tileLayer(ESRI_URL, { maxZoom: 19, attribution: ESRI_ATTR });
    osmLayer.remove();
    esriLayer.addTo(map);
    map.getContainer().classList.add("satellite-mode");
    btn.classList.add("active");
  } else {
    esriLayer.remove();
    osmLayer.addTo(map);
    map.getContainer().classList.remove("satellite-mode");
    btn.classList.remove("active");
  }
}

function toggleDepth() {
  const btn = document.getElementById("depth-toggle");
  depthVisible = !depthVisible;
  btn.classList.toggle("active", depthVisible);
  btn.textContent = depthVisible ? "Hide Depth" : "Show Depth";

  depthLayerGroup.clearLayers();

  if (depthVisible && selectedSpotId && bathyLayers[selectedSpotId]) {
    depthLayerGroup.addLayer(bathyLayers[selectedSpotId]);
  }
}

// ===== FILTERS =====
document.querySelectorAll(".filter-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeCounty = btn.dataset.county;
    renderMarkers();
  });
});

// ===== UTILS =====
function formatBreakType(t) {
  return t?.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase()) || "—";
}

function degToCardinal(deg) {
  if (deg == null) return "";
  const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return dirs[Math.round(deg / 22.5) % 16];
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit", hour12: true,
    });
  } catch {
    return iso;
  }
}

function updateLastUpdated() {
  const times = Object.values(conditionsCache)
    .map(c => c.updated_at)
    .filter(Boolean)
    .map(t => new Date(t).getTime())
    .filter(t => !isNaN(t));

  if (!times.length) return;
  const latest = new Date(Math.max(...times));
  document.getElementById("last-updated").textContent =
    `Updated ${formatTime(latest.toISOString())}`;
}

// ===== START =====
init();
