# Pond Catchment Analysis Backend

A high-performance geospatial backend API developed for automated **Pond Planning & Catchment Hydrology Analysis**. The API accepts contour elevation maps (in KML/KMZ format), dynamically constructs a Digital Elevation Model (DEM), performs D8 hydrological routing and river-channel exclusion, identifies the optimal upland depression (sink), and computes its catchment drainage area.

---

## Features
- **Dynamic Terrain Analysis**: Calculates UTM projections dynamically from coordinates without hardcoding.
- **Fast KML/KMZ Parsing**: Uses `lxml` for rapid extraction of contour lines and elevation metadata.
- **Metric Coordinate Projection**: Automatically projects WGS84 (Lat/Lon) to the local UTM zone via `pyproj` for accurate metric area calculations.
- **2m DEM Generation**: Rasterizes contour points into a 2-meter resolution Digital Elevation Model (DEM) using SciPy linear and nearest-neighbor interpolation.
- **Hydrological D8 Routing & Flow Accumulation**: Traces water flow direction across 8-neighbor cells and calculates upstream contributing flow accumulation.
- **Multi-Stage River & Waterbody Exclusion Pipeline**:
  - **Edge Rejection**: 200m buffer exclusion from map boundaries.
  - **Elevation Band Filter**: Rejects sinks in the bottom 10% elevation band (river valleys/channels).
  - **Flow Accumulation Threshold**: Excludes cells with high upstream accumulation to prevent placing ponds inside rivers/streams.
  - **Flat Waterbody & Floodplain Filter**: Uses Breadth-First Search (BFS) to detect and reject existing lakes and low-gradient flat areas (>1200 m²).
  - **Multi-Criteria Scoring**: Ranks candidate upland sinks using a composite score of elevation, balanced catchment size, and stream distance.
- **Interactive Visualizations**: Generates 2D hydrological dashboards, 3D terrain models, and interactive Leaflet/Folium satellite maps.

---

## Tech Stack
- **Language**: Python 3.10+
- **API Framework**: FastAPI, Uvicorn
- **Geospatial & Numerics**: NumPy, SciPy, PyProj, Shapely, lxml
- **Visualization & GIS**: Matplotlib, Folium

---

## Project Structure
```
pond-planning/
├── main.py                           # FastAPI application entry point (port 3000)
├── terrain_analysis.py               # Core DEM interpolation, D8 routing & filtering logic
├── generate_visualizations.py        # Generates 2D DEM, 3D terrain mesh & hydrology dashboards
├── visualize_map.py                  # Generates interactive Folium satellite map (pond_map.html)
├── test_api.py                       # Automated API integration test script
├── contours_1m.kml                   # Sample 1-meter contour elevation dataset
├── Report.md                         # Markdown technical documentation & methodology
├── Pond_Catchment_Analysis_Report.docx# Formatted formal technical submission report
├── pond_map.html                     # Generated interactive satellite map
├── visualizations/                   # High-res output figures (DEM, 3D Mesh, Catchment Zoom)
│   ├── pond_analysis_dashboard.png
│   ├── terrain_3d_pond.png
│   └── catchment_zoom_detail.png
├── requirements.txt                  # Python package dependencies
└── README.md                         # Project documentation
```

---

## Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/nikhilesh-git/pond-planning-system.git
   cd pond-planning-system
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Windows (PowerShell):
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # macOS / Linux:
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## Running the API Server

Start the backend server using `uvicorn` or run `main.py`:
```bash
python main.py
```
*Or via Uvicorn CLI directly:*
```bash
uvicorn main:app --host 0.0.0.0 --port 3000 --reload
```

The API will be live at `http://127.0.0.1:3000`.

---

## API Documentation & Usage

Interactive Swagger UI documentation is available at:
- **Swagger UI**: [http://127.0.0.1:3000/docs](http://127.0.0.1:3000/docs)
- **ReDoc**: [http://127.0.0.1:3000/redoc](http://127.0.0.1:3000/redoc)

### Endpoint: `POST /analyzeContour`
- **Content-Type**: `multipart/form-data`
- **Request Body**:
  - `file`: KML or KMZ file containing contour placemarks.

#### Sample Request (cURL):
```bash
curl -X POST "http://127.0.0.1:3000/analyzeContour" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@contours_1m.kml"
```

#### Sample Response:
```json
{
  "pond_location": {
    "latitude": 21.252048140122685,
    "longitude": 81.30923688499112,
    "elevation": 290.0
  },
  "catchment_area_sqm": 772.0
}
```

---

## Testing & Visualizations

### 1. Test API Endpoint
Run the automated test script against the running server:
```bash
python test_api.py
```

### 2. Generate Visualizations (2D, 3D & Hydrology)
Generate high-resolution PNG plots of the DEM, 3D terrain surface, stream networks, and catchment basin:
```bash
python generate_visualizations.py
```
Output figures are saved in the `visualizations/` folder.

### 3. Open Interactive Satellite Map
Create and launch the interactive Folium map on Google Satellite imagery:
```bash
python visualize_map.py
```
This opens `pond_map.html` in your default browser.
