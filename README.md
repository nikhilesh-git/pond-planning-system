# Pond Catchment Analysis Backend

This repository contains a backend API route developed for the "Pond Planning" assignment. The API accepts a contour map (in KML/KMZ format), dynamically analyzes the terrain, identifies a suitable pond location (sink), and estimates the corresponding catchment area.

## Features
- **Dynamic Terrain Analysis**: Does not rely on hard-coded locations.
- **Fast KML Parsing**: Uses `lxml` for rapid extraction of contour lines and elevations.
- **Coordinate Projection**: Automatically estimates and projects WGS84 (Lat/Lon) to the correct UTM zone for accurate metric area calculations.
- **DEM Generation**: Rasterizes scattered contour points into a 2m resolution Digital Elevation Model (DEM) using SciPy interpolation.
- **Hydrological Routing**: Uses a D8 Flow Routing algorithm to trace water descent and accumulate flow into local depressions (sinks).
- **Waterbody Avoidance Logic**: Includes edge-case checks to prevent placing ponds inside existing lakes or rivers (rejects sinks on grid boundaries or within massive flat regions).

## Tech Stack
- **Python 3**
- **FastAPI** (Backend framework)
- **NumPy & SciPy** (Grid generation and interpolation)
- **PyProj** (Coordinate reference system transformations)
- **lxml** (Fast XML parsing)

## Installation

1. **Clone the repository**:
   ```bash
   git clone <your-repository-url>
   cd pond-catchment-analysis
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Running the API Server

Start the FastAPI server using Uvicorn:
```bash
python -m uvicorn main:app --reload
```
The server will start running on `http://127.0.0.1:8000`.

## API Documentation
Once the server is running, you can view the auto-generated Swagger UI documentation at:
- [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Endpoint: `POST /analyzeContour`
- **Request:** `multipart/form-data` with a `file` field containing a `.kml` or `.kmz` file.
- **Response:** JSON containing the identified `pond_location` and `catchment_area_sqm`.

## Testing the API
A test script is included in this repository. Ensure the backend server is running, then open a second terminal and run:

```bash
python test_api.py
```
This will automatically submit `contours_1m.kml` to the API and print the resulting JSON.
