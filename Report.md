# Pond Catchment Analysis Backend - Assignment Report

**Student Name:** Shivam Kushwaha
**GitHub Repository:** [Insert Link Here]

## 1. Working API Route URL
**Local URL:** `http://127.0.0.1:8000/analyzeContour`

## 2. API Documentation
The backend exposes a single endpoint to process KML/KMZ files.

### Endpoint: `POST /analyzeContour`
- **Description:** Accepts a KML/KMZ file containing contour lines, generates a Digital Elevation Model (DEM), performs a hydrological analysis to find the largest sink (depression), and calculates its catchment area.
- **Content-Type:** `multipart/form-data`
- **Form Field:** `file` (The uploaded KML or KMZ file)
- **Response Format:** `application/json`

**Example Response:**
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

## 3. Catchment Estimation Approach
The API follows a multi-step geospatial processing pipeline to estimate the catchment dynamically without any hard-coded coordinates:

1. **KML Parsing:** The provided file is parsed using the fast `lxml.etree` parser to extract LineStrings and elevations for each contour `Placemark`.
2. **Coordinate Projection:** The `pyproj` library is used to estimate the local UTM zone from the average longitude and latitude. The coordinates are then projected from WGS84 (Lat/Lon) to the UTM coordinate system (meters). This ensures that area and distance calculations are highly accurate.
3. **Digital Elevation Model (DEM) Generation:** A 2-meter resolution grid is created covering the bounding box of the contours. `scipy.interpolate.griddata` (Linear Interpolation) is used to assign elevation values to the grid from the scattered contour points. Any remaining NaNs are filled using nearest-neighbor interpolation.
4. **Hydrological Analysis (D8 Flow Routing):** A simple D8 flow routing algorithm calculates the steepest downward slope for each cell to one of its 8 neighbors. By tracing these flow paths, the algorithm identifies "sinks" (local depressions where water naturally accumulates).
5. **River & Waterbody Exclusion:** The algorithm builds a **flow accumulation grid** to identify river/stream channels (cells with high upstream contributing area). It then evaluates all detected sinks through a multi-stage filtering pipeline:
   - **Edge Rejection:** Sinks within a 200m buffer of the map boundary are excluded.
   - **Elevation Band Exclusion:** Sinks in the bottom 10% of the elevation range are excluded as river-channel zones.
   - **Flow Accumulation Filter:** Sinks at or near high-accumulation cells (rivers/streams) are excluded. This is the key filter that prevents pond placement in rivers.
   - **Flat Waterbody Rejection:** Contiguous flat areas > 1200 sqm are identified as existing lakes/rivers.
   - **Gradient Analysis:** Perfectly flat areas (floodplains) are excluded.
   - **Scoring System:** Remaining candidates are scored based on elevation (prefer upland), catchment balance (prefer moderate over extreme), and low flow accumulation (prefer true depressions). The highest-scoring candidate is selected.

## 4. Demonstration using the provided contour map
Using the provided `contours_1m.kml`, the API returns the following output when tested:
- **Pond Location:** `Latitude 21.25205`, `Longitude 81.30924` (Elevation: 290.0m)
- **Catchment Area:** `772.0` square meters.

The pond is correctly placed at an upland depression (290m elevation), well above the river channel zone. The flow accumulation-based river detection successfully prevents the pond from being located in or near rivers/streams.

## Extensibility to Future Phases
The code is designed to be fully extensible:
- **No hard-coded values:** UTM zones are calculated dynamically based on input coordinates.
- **Modular Design:** Separation of concerns between FastAPI (`main.py`) and terrain logic (`terrain_analysis.py`).
- **Standardized Algorithm:** The D8 flow routing approach works universally across any DEM derived from an arbitrary contour map.
