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
    "latitude": 21.249752351679746,
    "longitude": 81.28933926800144,
    "elevation": 272.0
  },
  "catchment_area_sqm": 16808.0
}
```

## 3. Catchment Estimation Approach
The API follows a multi-step geospatial processing pipeline to estimate the catchment dynamically without any hard-coded coordinates:

1. **KML Parsing:** The provided file is parsed using the fast `lxml.etree` parser to extract LineStrings and elevations for each contour `Placemark`.
2. **Coordinate Projection:** The `pyproj` library is used to estimate the local UTM zone from the average longitude and latitude. The coordinates are then projected from WGS84 (Lat/Lon) to the UTM coordinate system (meters). This ensures that area and distance calculations are highly accurate.
3. **Digital Elevation Model (DEM) Generation:** A 2-meter resolution grid is created covering the bounding box of the contours. `scipy.interpolate.griddata` (Linear Interpolation) is used to assign elevation values to the grid from the scattered contour points. Any remaining NaNs are filled using nearest-neighbor interpolation.
4. **Hydrological Analysis (D8 Flow Routing):** A simple D8 flow routing algorithm calculates the steepest downward slope for each cell to one of its 8 neighbors. By tracing these flow paths, the algorithm identifies "sinks" (local depressions where water naturally accumulates).
5. **Catchment Identification:** The flow accumulation for every sink is computed. The sink with the largest number of contributing cells is selected as the optimal pond location. The area is calculated by multiplying the contributing cell count by the grid cell area (2m x 2m = 4 sq meters).

## 4. Demonstration using the provided contour map
Using the provided `contours_1m.kml`, the API returns the following output when tested:
- **Pond Location:** `Latitude 21.24975`, `Longitude 81.28933` (Elevation: 272.0m)
- **Catchment Area:** `16,808.0` square meters.

The backend dynamically derives this using the interpolation and flow routing logic detailed above and successfully responds in ~10-15 seconds for a 6.7MB file.

## Extensibility to Future Phases
The code is designed to be fully extensible:
- **No hard-coded values:** UTM zones are calculated dynamically based on input coordinates.
- **Modular Design:** Separation of concerns between FastAPI (`main.py`) and terrain logic (`terrain_analysis.py`).
- **Standardized Algorithm:** The D8 flow routing approach works universally across any DEM derived from an arbitrary contour map.
