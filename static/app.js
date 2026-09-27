/**
 * AquaPlan AI - Client-side GIS & Hydrology Controller
 */

// Global State
const state = {
  map: null,
  layers: {
    satellite: null,
    streets: null,
    contours: null,
    catchment: null,
    pondMarkers: null,
    selection: null
  },
  studyAreaBounds: null,
  currentResult: null,
  isDrawing: false,
  drawStartLatLng: null,
  activeSoil: {
    name: "Clayey / Black Cotton Soil",
    coef: 0.38
  },
  rainfallAnnual: 1220.0
};

// Preset Land Area Boundaries (lat, lon)
const PRESETS = {
  full: {
    name: "IIT Bhilai Campus (Full Study Area)",
    bounds: [[21.23982, 81.28140], [21.26358, 81.31265]]
  },
  north: {
    name: "North Watershed & Upland Drainage",
    bounds: [[21.25400, 81.28800], [21.26350, 81.30800]]
  },
  central: {
    name: "Central Agrarian Basin",
    bounds: [[21.24700, 81.29400], [21.25700, 81.31100]]
  },
  east: {
    name: "East Valley & Natural Depression",
    bounds: [[21.24100, 81.30000], [21.25300, 81.31200]]
  }
};

// Color ramp for contours
function getContourColor(elevation) {
  // Elev range: 267m to 298m
  const minElev = 267.0;
  const maxElev = 298.0;
  const ratio = Math.max(0, Math.min(1, (elevation - minElev) / (maxElev - minElev)));
  
  if (ratio < 0.25) return "#00f2fe"; // Low elevation / valley
  if (ratio < 0.50) return "#10b981"; // Mid-low
  if (ratio < 0.75) return "#f59e0b"; // Mid-high
  return "#ef4444"; // Ridge / high ground
}

// Initialize Leaflet Map
function initMap() {
  const defaultCenter = [21.2517, 81.2970];
  const defaultZoom = 15;

  state.map = L.map('gis-map', {
    center: defaultCenter,
    zoom: defaultZoom,
    zoomControl: false
  });

  // Zoom control top right
  L.control.zoom({ position: 'bottomright' }).addTo(state.map);

  // Satellite Base Layer (Esri World Imagery)
  state.layers.satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    maxZoom: 19
  });

  // Street / Topo Base Layer (OpenStreetMap)
  state.layers.streets = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  });

  // Set default active base layer
  state.layers.satellite.addTo(state.map);

  // Layer groups for overlays
  state.layers.contours = L.layerGroup().addTo(state.map);
  state.layers.catchment = L.layerGroup().addTo(state.map);
  state.layers.pondMarkers = L.layerGroup().addTo(state.map);
  state.layers.selection = L.layerGroup().addTo(state.map);

  setupMapInteraction();
  loadContoursLayer();
  loadBaseline();
}

// Setup drawing & mouse interactions
function setupMapInteraction() {
  const map = state.map;

  map.on('mousedown', (e) => {
    if (!state.isDrawing) return;
    state.drawStartLatLng = e.latlng;
    map.dragging.disable();
  });

  map.on('mousemove', (e) => {
    if (!state.isDrawing || !state.drawStartLatLng) return;
    const currentLatLng = e.latlng;
    const bounds = L.latLngBounds(state.drawStartLatLng, currentLatLng);

    state.layers.selection.clearLayers();
    const rect = L.rectangle(bounds, {
      color: '#f59e0b',
      weight: 2,
      dashArray: '6, 6',
      fillColor: '#f59e0b',
      fillOpacity: 0.15
    });
    rect.addTo(state.layers.selection);
  });

  map.on('mouseup', (e) => {
    if (!state.isDrawing || !state.drawStartLatLng) return;
    const bounds = L.latLngBounds(state.drawStartLatLng, e.latlng);
    map.dragging.enable();
    state.isDrawing = false;
    state.drawStartLatLng = null;

    document.getElementById('btn-draw-area').classList.remove('active');
    document.getElementById('selection-banner').classList.add('hidden');

    // Only proceed if area is large enough
    const sw = bounds.getSouthWest();
    const ne = bounds.getNorthEast();
    if (Math.abs(ne.lat - sw.lat) > 0.001 && Math.abs(ne.lng - sw.lng) > 0.001) {
      analyzeCustomBounds(sw.lat, ne.lat, sw.lng, ne.lng, "User Selected Custom Parcel");
    }
  });
}

// Load Simplified Contours GeoJSON
async function loadContoursLayer() {
  try {
    const res = await fetch('/api/contours');
    if (!res.ok) return;
    const data = await res.json();

    state.layers.contours.clearLayers();

    L.geoJSON(data, {
      style: (feature) => {
        const elev = feature.properties.elevation;
        const isIndex = feature.properties.is_index;
        return {
          color: getContourColor(elev),
          weight: isIndex ? 2.0 : 1.0,
          opacity: isIndex ? 0.85 : 0.55
        };
      },
      onEachFeature: (feature, layer) => {
        layer.bindTooltip(`Elevation: <strong>${feature.properties.elevation}m</strong> AMSL`, {
          sticky: true,
          className: 'contour-tooltip'
        });
      }
    }).addTo(state.layers.contours);
  } catch (err) {
    console.warn("Contours could not be loaded:", err);
  }
}

// Load Baseline Analysis
async function loadBaseline() {
  showLoader(true);
  try {
    const res = await fetch('/api/baseline');
    if (!res.ok) throw new Error("Baseline not found");
    const data = await res.json();
    displayResults(data, "IIT Bhilai Campus (Full Study Area)");
  } catch (err) {
    console.error("Error loading baseline:", err);
  } finally {
    showLoader(false);
  }
}

// Analyze Custom Land Area Bounding Box
async function analyzeCustomBounds(min_lat, max_lat, min_lon, max_lon, regionName) {
  showLoader(true);
  try {
    const res = await fetch('/api/analyze-bounds', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        min_lat: min_lat,
        max_lat: max_lat,
        min_lon: min_lon,
        max_lon: max_lon,
        runoff_coef: state.activeSoil.coef,
        rainfall_annual_mm: state.rainfallAnnual
      })
    });

    if (!res.ok) throw new Error("Analysis failed");
    const data = await res.json();
    displayResults(data, regionName);
  } catch (err) {
    console.error("Bounds analysis error:", err);
    alert("Analysis failed: " + err.message);
  } finally {
    showLoader(false);
  }
}

// Display Results on Map & Dashboard
function displayResults(data, regionName) {
  state.currentResult = data;

  // 1. Update Map Overlays
  state.layers.catchment.clearLayers();
  state.layers.pondMarkers.clearLayers();

  const pond = data.pond_location;
  const catchment = data.catchment;

  // Add Catchment Polygon
  if (catchment && catchment.polygon_geojson) {
    const catchmentGeoJSON = L.geoJSON(catchment.polygon_geojson, {
      style: {
        color: '#00f2fe',
        weight: 2.5,
        fillColor: '#00f2fe',
        fillOpacity: 0.22,
        dashArray: '4, 4'
      }
    }).addTo(state.layers.catchment);

    catchmentGeoJSON.bindPopup(`
      <div style="font-family: 'Inter', sans-serif; font-size: 13px;">
        <strong style="color: #00f2fe;">Catchment Basin</strong><br>
        Contributing Area: <strong>${catchment.area_sqm.toLocaleString()} m²</strong><br>
        (${catchment.area_hectares} ha / ${catchment.area_acres} acres)
      </div>
    `);
  }

  // Add Custom Pulsing Marker for Primary Pond
  const pulseIcon = L.divIcon({
    className: 'pond-pulse-wrapper',
    html: `
      <div class="pond-pulse-marker">
        <div class="wave"></div>
        <div class="core"></div>
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14]
  });

  const pondMarker = L.marker([pond.latitude, pond.longitude], { icon: pulseIcon }).addTo(state.layers.pondMarkers);
  pondMarker.bindPopup(`
    <div style="font-family: 'Inter', sans-serif; font-size: 13px; line-height: 1.5;">
      <h4 style="margin: 0 0 4px 0; color: #00f2fe; font-size: 14px;">Recommended Pond Location</h4>
      <strong>Coordinates:</strong> ${pond.latitude.toFixed(5)}°N, ${pond.longitude.toFixed(5)}°E<br>
      <strong>Elevation:</strong> ${pond.elevation.toFixed(1)} m AMSL<br>
      <strong>Catchment Area:</strong> ${data.catchment_area_sqm.toLocaleString()} m²<br>
      <strong>Expected Volume:</strong> ${data.water_volume.annual_runoff_m3.toLocaleString()} m³
    </div>
  `).openPopup();

  // Add Alternative Candidates Pins
  if (data.candidates && data.candidates.length > 1) {
    data.candidates.slice(1).forEach(c => {
      const pinIcon = L.divIcon({
        className: 'candidate-pin',
        html: `<div style="background: rgba(16, 185, 129, 0.9); color: #080d1a; font-weight: bold; font-size: 11px; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; border: 2px solid white; box-shadow: 0 0 8px rgba(0,0,0,0.5);">${c.rank}</div>`,
        iconSize: [22, 22],
        iconAnchor: [11, 11]
      });

      const candMarker = L.marker([c.latitude, c.longitude], { icon: pinIcon }).addTo(state.layers.pondMarkers);
      candMarker.bindPopup(`
        <div style="font-family: 'Inter', sans-serif; font-size: 12px;">
          <strong>Candidate Site #${c.rank}</strong><br>
          Elev: ${c.elevation}m | Catchment: ${c.catchment_sqm} m²<br>
          Suitability Score: <strong>${c.score}</strong>
        </div>
      `);
    });
  }

  // 2. Update Dashboard UI Cards
  document.getElementById('card-region-name').textContent = regionName || "Analyzed Region";
  const exTime = data.execution_time_seconds ? `${data.execution_time_seconds}s` : '0.05s';
  document.getElementById('card-analysis-time').innerHTML = `D8 Flow Analysis: <span class="text-cyan">${exTime}</span>`;

  // KPI 1: Location
  document.getElementById('kpi-pond-coords').textContent = `${pond.latitude.toFixed(5)}° N, ${pond.longitude.toFixed(5)}° E`;
  document.getElementById('kpi-pond-elev').innerHTML = `Elevation: <strong>${pond.elevation.toFixed(1)} m</strong> AMSL`;

  // KPI 2: Catchment
  const cArea = data.catchment_area_sqm;
  document.getElementById('kpi-catchment-sqm').textContent = `${cArea.toLocaleString()} m²`;
  document.getElementById('kpi-catchment-hectares').textContent = `${(cArea / 10000).toFixed(3)} Hectares | ${(cArea * 0.0002471).toFixed(3)} Acres`;

  // KPI 3: Water Volume
  const wv = data.water_volume;
  document.getElementById('kpi-water-volume').textContent = `${wv.annual_runoff_m3.toLocaleString()} m³`;
  document.getElementById('kpi-water-liters').textContent = `${wv.annual_liters.toLocaleString()} Liters (${wv.annual_million_liters} ML)`;

  // KPI 4: Recommended Depth
  const rec = data.pond_recommendations;
  document.getElementById('kpi-pond-depth').textContent = `${rec.recommended_depth_m} m Depth`;
  document.getElementById('kpi-pond-surface').innerHTML = `Footprint: <strong>${rec.surface_area_sqm} m²</strong> | ${rec.side_slope}`;

  // Water Security Impact
  document.getElementById('stat-households').textContent = wv.household_days_supported.toLocaleString();
  document.getElementById('stat-monsoon').textContent = `${wv.monsoon_runoff_m3.toLocaleString()} m³`;

  // Civil Spec Tab
  document.getElementById('spec-depth').textContent = `${rec.recommended_depth_m} m`;
  document.getElementById('spec-footprint').textContent = `${rec.surface_area_sqm} m²`;
  document.getElementById('spec-silttrap').textContent = `${rec.silt_trap_capacity_m3} m³`;

  // Candidates Tab
  renderCandidatesList(data.candidates);

  // Render Rainfall Chart
  renderRainfallBars();
}

// Render Candidate Comparison List
function renderCandidatesList(candidates) {
  const container = document.getElementById('candidates-container');
  container.innerHTML = '';

  if (!candidates || candidates.length === 0) {
    container.innerHTML = '<p class="section-desc">No candidate sites identified in this subregion.</p>';
    return;
  }

  candidates.forEach(c => {
    const item = document.createElement('div');
    item.className = `candidate-item ${c.rank === 1 ? 'active' : ''}`;
    item.innerHTML = `
      <div class="candidate-header">
        <span class="candidate-rank">
          <i class="fa-solid fa-location-dot ${c.rank === 1 ? 'text-cyan' : 'text-emerald'}"></i>
          Site #${c.rank} (${c.type})
        </span>
        <span class="candidate-score">Score: ${c.score}</span>
      </div>
      <div class="candidate-details">
        <div>Coordinates: ${c.latitude.toFixed(5)}, ${c.longitude.toFixed(5)}</div>
        <div>Elevation: <strong>${c.elevation} m</strong></div>
        <div>Catchment: <strong>${c.catchment_sqm.toLocaleString()} m²</strong></div>
        <div>Status: <span class="text-emerald">Optimal Sink</span></div>
      </div>
    `;

    // Click candidate to center map
    item.addEventListener('click', () => {
      document.querySelectorAll('.candidate-item').forEach(el => el.classList.remove('active'));
      item.classList.add('active');
      state.map.flyTo([c.latitude, c.longitude], 17, { duration: 1.2 });
    });

    container.appendChild(item);
  });
}

// Render Monthly Rainfall Bars
function renderRainfallBars() {
  const months = [
    { name: "Jan", val: 12 }, { name: "Feb", val: 18 }, { name: "Mar", val: 15 },
    { name: "Apr", val: 14 }, { name: "May", val: 22 }, { name: "Jun", val: 195, monsoon: true },
    { name: "Jul", val: 380, monsoon: true }, { name: "Aug", val: 345, monsoon: true },
    { name: "Sep", val: 180, monsoon: true }, { name: "Oct", val: 45 }, { name: "Nov", val: 10 }, { name: "Dec", val: 5 }
  ];

  const maxVal = 380;
  const container = document.getElementById('rainfall-bars');
  container.innerHTML = '';

  months.forEach(m => {
    const col = document.createElement('div');
    col.className = 'bar-col';
    const pct = (m.val / maxVal) * 100;

    col.innerHTML = `
      <div class="bar-val">${m.val}</div>
      <div class="bar-fill ${m.monsoon ? 'monsoon' : ''}" style="height: ${pct}%;"></div>
      <div class="bar-label">${m.name}</div>
    `;
    container.appendChild(col);
  });
}

// Dynamic Recalculation via Sliders & Soil Selection
async function recalculateVolume() {
  if (!state.currentResult) return;
  const cArea = state.currentResult.catchment_area_sqm || (state.currentResult.catchment && state.currentResult.catchment.area_sqm) || 780.0;

  try {
    const res = await fetch('/api/calculate-water-volume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        catchment_area_sqm: parseFloat(cArea),
        runoff_coef: parseFloat(state.activeSoil.coef) || 0.38,
        rainfall_annual_mm: parseFloat(state.rainfallAnnual) || 1220.0,
        depth_m: 3.5
      })
    });

    if (!res.ok) return;
    const vol = await res.json();

    document.getElementById('kpi-water-volume').textContent = `${vol.annual_runoff_m3.toLocaleString()} m³`;
    document.getElementById('kpi-water-liters').textContent = `${vol.annual_liters.toLocaleString()} Liters (${vol.annual_million_liters} ML)`;
    document.getElementById('stat-households').textContent = vol.household_days_supported.toLocaleString();
    document.getElementById('stat-monsoon').textContent = `${vol.monsoon_runoff_m3.toLocaleString()} m³`;

    document.getElementById('kpi-pond-surface').innerHTML = `Footprint: <strong>${vol.pond_dimensions.surface_area_sqm} m²</strong> | ${vol.pond_dimensions.side_slope}`;
    document.getElementById('spec-footprint').textContent = `${vol.pond_dimensions.surface_area_sqm} m²`;
    document.getElementById('spec-silttrap').textContent = `${vol.pond_dimensions.silt_trap_m3} m³`;
  } catch (err) {
    console.error("Recalculate error:", err);
  }
}

// Event Listeners Setup
function setupEventListeners() {
  // Draw Area Button
  const btnDraw = document.getElementById('btn-draw-area');
  const banner = document.getElementById('selection-banner');
  const btnCancelDraw = document.getElementById('btn-cancel-draw');

  btnDraw.addEventListener('click', () => {
    state.isDrawing = !state.isDrawing;
    btnDraw.classList.toggle('active', state.isDrawing);
    banner.classList.toggle('hidden', !state.isDrawing);
  });

  btnCancelDraw.addEventListener('click', () => {
    state.isDrawing = false;
    btnDraw.classList.remove('active');
    banner.classList.add('hidden');
    state.layers.selection.clearLayers();
  });

  // Full Study Area Button
  document.getElementById('btn-full-study').addEventListener('click', () => {
    state.layers.selection.clearLayers();
    document.querySelectorAll('.zone-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.zone-btn[data-preset="full"]').classList.add('active');
    loadBaseline();
    state.map.flyToBounds(PRESETS.full.bounds, { duration: 1.0 });
  });

  // Preset Buttons
  document.querySelectorAll('.zone-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.zone-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const presetKey = btn.getAttribute('data-preset');
      const preset = PRESETS[presetKey];
      if (!preset) return;

      const sw = preset.bounds[0];
      const ne = preset.bounds[1];

      // Draw dashed selection rectangle
      state.layers.selection.clearLayers();
      L.rectangle(preset.bounds, {
        color: '#f59e0b',
        weight: 2,
        dashArray: '6, 6',
        fillColor: '#f59e0b',
        fillOpacity: 0.12
      }).addTo(state.layers.selection);

      state.map.flyToBounds(preset.bounds, { duration: 1.0 });

      if (presetKey === 'full') {
        loadBaseline();
      } else {
        analyzeCustomBounds(sw[0], ne[0], sw[1], ne[1], preset.name);
      }
    });
  });

  // Layer Toggles
  document.getElementById('layer-satellite').addEventListener('change', (e) => {
    if (e.target.checked) {
      state.map.addLayer(state.layers.satellite);
      state.map.removeLayer(state.layers.streets);
    } else {
      state.map.removeLayer(state.layers.satellite);
      state.map.addLayer(state.layers.streets);
    }
  });

  document.getElementById('layer-contours').addEventListener('change', (e) => {
    if (e.target.checked) state.map.addLayer(state.layers.contours);
    else state.map.removeLayer(state.layers.contours);
  });

  document.getElementById('layer-catchment').addEventListener('change', (e) => {
    if (e.target.checked) state.map.addLayer(state.layers.catchment);
    else state.map.removeLayer(state.layers.catchment);
  });

  document.getElementById('layer-pond').addEventListener('change', (e) => {
    if (e.target.checked) state.map.addLayer(state.layers.pondMarkers);
    else state.map.removeLayer(state.layers.pondMarkers);
  });

  // Dashboard Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const tabId = `tab-${btn.getAttribute('data-tab')}`;
      const pane = document.getElementById(tabId);
      if (pane) pane.classList.add('active');
    });
  });

  // Slider Events
  const sliderC = document.getElementById('slider-c');
  const sliderRain = document.getElementById('slider-rain');

  sliderC.addEventListener('input', (e) => {
    state.activeSoil.coef = parseFloat(e.target.value);
    document.getElementById('lbl-c-val').textContent = e.target.value;
    document.getElementById('current-soil-tag').textContent = `Runoff C = ${e.target.value}`;
    recalculateVolume();
  });

  sliderRain.addEventListener('input', (e) => {
    state.rainfallAnnual = parseFloat(e.target.value);
    document.getElementById('lbl-rain-val').textContent = `${e.target.value} mm`;
    recalculateVolume();
  });

  // Soil Cards Selection
  document.querySelectorAll('.soil-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.soil-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');

      const coef = parseFloat(card.getAttribute('data-coef'));
      const soil = card.getAttribute('data-soil');

      state.activeSoil = { name: soil, coef: coef };
      sliderC.value = coef;
      document.getElementById('lbl-c-val').textContent = coef;
      document.getElementById('current-soil-tag').textContent = `${soil} (C = ${coef})`;
      recalculateVolume();
    });
  });

  // Modal Upload Handlers
  const modal = document.getElementById('modal-upload');
  document.getElementById('btn-upload-kml').addEventListener('click', () => modal.classList.remove('hidden'));
  document.getElementById('btn-close-modal').addEventListener('click', () => modal.classList.add('hidden'));

  // File Upload Handling
  const fileInput = document.getElementById('kml-file-input');
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      uploadKMLFile(e.target.files[0]);
    }
  });

  // Export / Print Report
  document.getElementById('btn-export-report').addEventListener('click', () => {
    window.print();
  });
}

// Upload KML File
async function uploadKMLFile(file) {
  const statusDiv = document.getElementById('upload-status');
  statusDiv.classList.remove('hidden');
  statusDiv.innerHTML = `<span class="text-cyan"><i class="fa-solid fa-spinner fa-spin"></i> Uploading & parsing ${file.name}...</span>`;

  const formData = new FormData();
  formData.append('contour_map', file);

  try {
    const res = await fetch('/analyzeContour', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Analysis failed");
    }

    const data = await res.json();
    statusDiv.innerHTML = `<span class="text-emerald"><i class="fa-solid fa-check"></i> Analysis Complete! Loading results...</span>`;

    setTimeout(() => {
      document.getElementById('modal-upload').classList.add('hidden');
      displayResults(data, `Uploaded File: ${file.name}`);
      state.map.flyTo([data.pond_location.latitude, data.pond_location.longitude], 16);
    }, 1000);

  } catch (err) {
    statusDiv.innerHTML = `<span class="text-amber"><i class="fa-solid fa-triangle-exclamation"></i> ${err.message}</span>`;
  }
}

// Show/Hide Map Loader
function showLoader(show) {
  const loader = document.getElementById('map-loader');
  if (show) loader.classList.remove('hidden');
  else loader.classList.add('hidden');
}

// Bootstrap Application
document.addEventListener('DOMContentLoaded', () => {
  initMap();
  setupEventListeners();
});
