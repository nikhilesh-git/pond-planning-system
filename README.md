# AquaPlan AI: Village Pond Planning & Catchment Delineation System

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Leaflet](https://img.shields.io/badge/Leaflet-1.9.4-199900?style=flat&logo=leaflet&logoColor=white)](https://leafletjs.com/)
[![NumPy](https://img.shields.io/badge/NumPy-1.26+-013243?style=flat&logo=numpy&logoColor=white)](https://numpy.org/)
[![SciPy](https://img.shields.io/badge/SciPy-1.12+-8CAAE6?style=flat&logo=scipy&logoColor=white)](https://scipy.org/)

**AquaPlan AI** is an AI-assisted rural water conservation and geospatial watershed analysis platform developed for **Computer Science and Design (CSD) Assignment 1** at **IIT Bhilai**. 

The system analyzes continuous digital elevation models (DEM) derived from topographic contour maps, delineates natural drainage catchment basins using D8 flow routing, calculates harvestable runoff volumes via the Rational Runoff Method using 30-year IMD rainfall normals, and provides civil hydraulic sizing specifications for rural community ponds.

---

## 🌐 Live Institutional Deployment

The platform is deployed under continuous supervisor watchdog monitoring across the IIT Bhilai campus network:

| Component | Network Access URL | Port Mapping | Purpose |
| :--- | :--- | :--- | :--- |
| **Interactive Web GIS Frontend** | **[http://10.1.75.51:6253](http://10.1.75.51:6253)** | `6253 -> 6000` | Full Leaflet web GIS application |
| **Interactive Swagger API Docs** | **[http://10.1.75.51:6253/docs](http://10.1.75.51:6253/docs)** | `6253 -> 6000` | Interactive OpenAPI documentation |
| **Backend REST API** | **[http://10.1.75.51:3253](http://10.1.75.51:3253)** | `3253 -> 3000` | Dedicated backend worker |
| **Health Monitor Endpoint** | **[http://10.1.75.51:6253/api/health](http://10.1.75.51:6253/api/health)** | `6253 -> 6000` | Health check & uptime telemetry |

---

## ✨ Key Capabilities & Features

### 1. Interactive Web GIS & Land Area Selection
- **Dual Base Tile Layers:** Seamless switching between high-resolution **Esri World Imagery (Satellite)** and **OpenStreetMap Carto**.
- **Interactive Land Area Selector:** Bounding-box drag-and-drop tool allowing field planners and panchayat officials to select custom land parcels.
- **Quick Preset Watersheds:** Instant analysis of canonical subregions (*IIT Bhilai Campus*, *North Watershed*, *Central Agrarian Basin*, *East Depression*).
- **Vector Contour Overlay:** 808 simplified topographic contour lines color-ramped by elevation (267 m to 298 m AMSL).

### 2. Hydrological & Geospatial Terrain Engine
- **D8 Deterministic Flow Routing:** Computes eight-directional surface runoff paths from steepest downward slopes.
- **Delaunay Triangulation DEM Interpolation:** Constructs continuous terrain elevation grids from discrete contour vertices.
- **River & Stream Channel Avoidance:** High-order flow accumulation filter ($97^{\text{th}}$ percentile threshold) ensuring ponds are sited in collection depressions rather than flood-prone main river channels.
- **Catchment Boundary Delineation:** Vector convex hull polygon generation mapping contributing drainage areas.
- **Multi-Criteria Site Scoring:** Weighted utility scoring combining elevation depth ($30\%$), contributing catchment area ($40\%$), and stream distance ($30\%$).

### 3. Hydrological Runoff & Water Volume Modeling
- **Rational Runoff Derivation:**
  $$V_{\text{annual}} = C \times \left(\frac{P_{\text{annual}}}{1000}\right) \times A_{\text{catchment}}$$
- **IMD Climate Normals:** Configured with 30-year meteorological normals for Bhilai / Durg AWS ($1,220\text{ mm}$ annual rainfall, $1,044.3\text{ mm}$ monsoon rainfall).
- **Soil Permeability Infiltration:** Support for varying runoff coefficients ($C = 0.25\text{--}0.45$) across Clayey/Black Cotton Soil, Agricultural Loam, and Sandy Loam.
- **Dynamic Parameter Recalculation:** Real-time frontend sliders updating water yield, household support capacity, and reservoir sizing in $< 16\text{ ms}$.

### 4. Civil Hydraulic Reservoir Sizing
- **Pond Footprint & Depth Sizing:** $3.5\text{ m}$ total depth ($2.5\text{ m}$ active storage, $0.5\text{ m}$ dead storage, $0.5\text{ m}$ safety freeboard).
- **Side Slopes:** $1.5:1\text{ (H:V)}$ embankment ratio for slope stability without masonry retaining walls.
- **Silt Trap Desilting Basin:** Dedicated $5\%$ sediment trap capacity preventing reservoir siltation.
- **Community Metric:** Calculation of rural household-days supported ($150\text{ L/household/day}$).

### 5. Memory-Safe Sub-Second Processing (< 65MB RAM)
- Optimized for resource-constrained environments (e.g., 512 MB cgroup containers) using **point cloud decimation** and **adaptive grid resolution**:
  $$\text{grid\_res} = \max\left(\frac{\text{max\_span}}{150},\, 3.0\right)\text{ meters}$$
- Parses, interpolates, routes, and delineates a complete 6.4 MB KML contour file in **$0.74\text{ seconds}$** with zero memory pressure.

---

## 📁 Repository Structure

```
pond-planning-system/
├── main.py                     # FastAPI REST API, routing & static file serving
├── terrain_analysis.py         # Hydrological engine (D8 routing, Delaunay DEM, Quickhull)
├── start_daemon.py             # Watchdog supervisor daemon (dual workers on 3000 & 6000)
├── contours_1m.kml             # 1-meter topographic contour dataset (6.4 MB)
├── requirements.txt            # Python dependencies (FastAPI, NumPy, SciPy, PyProj, lxml)
├── report.tex                  # ACM manuscript format LaTeX final technical report
├── test_contour.kml            # Sample verification contour file
├── static/                     # Web GIS Client assets
│   ├── index.html              # Modern glassmorphic GIS dashboard interface
│   ├── style.css               # CSS design system (tokens, animations, dark mode)
│   ├── app.js                  # Leaflet controller & client-side hydrological logic
│   ├── contours.geojson        # Vector contour lines for overlay visualization
│   ├── baseline_result.json    # Precomputed full study area baseline analysis
│   └── bounds.json             # Geographic study area metadata
└── README.md                   # Complete technical documentation
```

---

## 🚀 Local Installation & Quickstart

### Prerequisites
- Python 3.10 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/nikhilesh-git/pond-planning-system.git
cd pond-planning-system
```

### 2. Create and Activate Virtual Environment
```bash
python -m venv venv
# Linux / macOS:
source venv/bin/activate
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Development Server
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 6000 --reload
```

Open your browser at **`http://localhost:6000`** to access the interactive GIS platform.

---

## 📡 REST API Reference

| Method | Endpoint | Description |
| :---: | :--- | :--- |
| `GET` | `/` | Serves the main interactive GIS web dashboard |
| `GET` | `/api/health` | Health monitor reporting uptime and worker telemetry |
| `GET` | `/api/baseline` | Ultra-fast precomputed baseline analysis for full study area |
| `GET` | `/api/contours` | GeoJSON vector contour lines for client-side rendering |
| `GET` | `/api/rainfall` | IMD historical 30-year rainfall normals and soil parameters |
| `POST` | `/api/analyze-bounds` | Dynamic bounding-box analysis for user-selected map areas |
| `POST` | `/api/calculate-water-volume` | Instant recalculation on soil runoff and rainfall changes |
| `POST` | `/analyzeContour` | Multipart file upload for custom `.kml` or `.kmz` contour maps |

---

## 📄 Final Technical Report

The complete ACM technical report compliant with the required template is provided in [`report.tex`](report.tex). It includes:
- Problem definition & rural hydrology background
- Mathematical derivations for rational runoff and D8 flow routing
- Soil infiltration classification and civil pond sizing parameters
- Experimental evaluation, candidate site comparisons, and performance benchmarks
- Curriculum mappings to Computer Science and Design (CSD) courses

---

## 👥 Author & Attribution

- **Student:** Gowrabathuni Nikhilesh
- **Institution:** Department of Computer Science and Engineering, IIT Bhilai
- **Email:** gowrabathunin@iitbhilai.ac.in
- **Course:** Computer Science and Design (CSD) -- Assignment 1
