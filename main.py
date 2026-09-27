import os
import json
import time
import zipfile
import io
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Body
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import terrain_analysis

app = FastAPI(
    title="Village Pond Planning & Catchment Delineation API",
    description="CSD Assignment 1 - AI-Assisted Rural Water Conservation & Geospatial Watershed Analysis System",
    version="2.0.0"
)

# Enable CORS for external access across campus network
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DEFAULT_KML = os.path.join(BASE_DIR, "contours_1m.kml")

# Ensure static directory exists
os.makedirs(STATIC_DIR, exist_ok=True)

# Mount static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

START_TIME = time.time()


class BoundsRequest(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    runoff_coef: Optional[float] = 0.38
    rainfall_annual_mm: Optional[float] = 1220.0
    soil_type: Optional[str] = "Clayey / Black Cotton Soil"


class VolumeCalcRequest(BaseModel):
    catchment_area_sqm: float
    runoff_coef: float = 0.38
    rainfall_annual_mm: float = 1220.0
    depth_m: float = 3.5


@app.get("/")
async def root():
    """Serves the main interactive GIS frontend."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"message": "AquaPlan AI Village Pond Planning System", "status": "online"})


@app.get("/api/health")
async def health_check():
    """Health check endpoint reporting uptime and system status."""
    uptime = time.time() - START_TIME
    return {
        "status": "healthy",
        "service": "AquaPlan AI - Village Pond Planning Engine",
        "uptime_seconds": round(uptime, 1),
        "allotted_system": "10.1.75.51:2253",
        "network_access_url": "http://10.1.75.51:6253",
        "backend_url": "http://10.1.75.51:3253",
        "ports": {
            "web_frontend_port": 6000,
            "api_backend_port": 3000
        }
    }


@app.get("/api/info")
async def get_study_area_info():
    """Returns geospatial boundaries, elevation profile, and metadata of study area."""
    bounds_file = os.path.join(STATIC_DIR, "bounds.json")
    if os.path.exists(bounds_file):
        with open(bounds_file, "r") as f:
            return json.load(f)
    return {
        "min_lon": 81.2814,
        "max_lon": 81.3126,
        "min_lat": 21.2398,
        "max_lat": 21.2636,
        "min_elev": 267.0,
        "max_elev": 298.0,
        "center_lat": 21.2517,
        "center_lon": 81.2970,
        "total_contours": 2710
    }


@app.get("/api/contours")
async def get_contours():
    """Returns simplified GeoJSON contour lines for client-side rendering."""
    geojson_file = os.path.join(STATIC_DIR, "contours.geojson")
    if os.path.exists(geojson_file):
        return FileResponse(geojson_file, media_type="application/geo+json")
    raise HTTPException(status_code=404, detail="Contours GeoJSON not found.")


@app.get("/api/baseline")
async def get_baseline_results():
    """Returns ultra-fast precomputed baseline analysis for full study area."""
    baseline_file = os.path.join(STATIC_DIR, "baseline_result.json")
    if os.path.exists(baseline_file):
        with open(baseline_file, "r") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Baseline result not found.")


@app.get("/api/rainfall")
async def get_rainfall_data():
    """Returns IMD historical rainfall data and soil runoff parameters."""
    return {
        "station": "Bhilai / Durg AWS (Chhattisgarh)",
        "coordinates": {"lat": 21.2167, "lon": 81.3833},
        "annual_mean_mm": 1220.0,
        "monsoon_mean_mm": 1045.0,
        "historical_period": "1991-2025 (IMD 30-year Normals)",
        "soil_types": [
            {"id": "clay", "name": "Clay / Black Cotton Soil", "runoff_coef": 0.45, "infiltration_rate": "Very Low (<2 mm/hr)", "suitability": "Ideal for Pond without Lining"},
            {"id": "loam", "name": "Agricultural Loam / Mixed Alluvium", "runoff_coef": 0.35, "infiltration_rate": "Moderate (5-15 mm/hr)", "suitability": "Good; Mild Compaction Advised"},
            {"id": "sandy", "name": "Sandy Loam / Coarse Soil", "runoff_coef": 0.25, "infiltration_rate": "High (>25 mm/hr)", "suitability": "Bentonite / Clay Blanket Required"}
        ],
        "monthly_distribution_mm": {
            "Jan": 12.0, "Feb": 18.0, "Mar": 15.0, "Apr": 14.0, "May": 22.0,
            "Jun": 195.0, "Jul": 380.0, "Aug": 345.0, "Sep": 180.0,
            "Oct": 45.0, "Nov": 10.0, "Dec": 5.0
        }
    }


@app.post("/api/analyze-bounds")
async def analyze_selected_bounds(req: BoundsRequest):
    """
    Analyzes user-selected land area bounding box on the map.
    Returns optimal pond site, delineated catchment area polygon, and collectible water volume.
    """
    t_start = time.time()
    try:
        # Check if bounds match the full study area roughly
        bbox = [req.min_lon, req.min_lat, req.max_lon, req.max_lat]
        
        # Read default KML
        if not os.path.exists(DEFAULT_KML):
            raise HTTPException(status_code=500, detail="Default contour KML file missing on server.")
            
        with open(DEFAULT_KML, "rb") as f:
            kml_bytes = f.read()
            
        result = terrain_analysis.calculate_catchment(
            kml_bytes,
            bbox=bbox,
            runoff_coef=req.runoff_coef or 0.38,
            rainfall_annual_mm=req.rainfall_annual_mm or 1220.0
        )
        
        result["execution_time_seconds"] = round(time.time() - t_start, 2)
        result["selected_bounds"] = {
            "min_lat": req.min_lat, "max_lat": req.max_lat,
            "min_lon": req.min_lon, "max_lon": req.max_lon
        }
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calculate-water-volume")
async def calculate_water_volume(req: VolumeCalcRequest):
    """Dynamically recalculates expected water volume and civil sizing when user adjusts parameters."""
    A = req.catchment_area_sqm
    P_ann = req.rainfall_annual_mm / 1000.0
    P_mon = (req.rainfall_annual_mm * 0.856) / 1000.0
    C = req.runoff_coef
    
    annual_m3 = round(A * P_ann * C, 1)
    monsoon_m3 = round(A * P_mon * C, 1)
    
    design_vol = min(round(monsoon_m3 * 0.75, 1), 75000.0)
    effective_depth = max(req.depth_m - 0.5, 1.0)
    surface_area = round(design_vol / effective_depth, 1)
    
    return {
        "annual_runoff_m3": annual_m3,
        "monsoon_runoff_m3": monsoon_m3,
        "annual_liters": int(annual_m3 * 1000),
        "annual_million_liters": round(annual_m3 / 1000.0, 2),
        "household_days_supported": int((annual_m3 * 1000) / 150),
        "pond_dimensions": {
            "depth_m": req.depth_m,
            "design_capacity_m3": design_vol,
            "design_capacity_million_liters": round(design_vol / 1000.0, 2),
            "surface_area_sqm": surface_area,
            "side_slope": "1.5:1 (H:V)",
            "silt_trap_m3": round(design_vol * 0.05, 1)
        }
    }


@app.post("/analyzeContour")
async def analyze_contour(
    contour_map: UploadFile = File(...)
):
    """Original assignment endpoint accepting KML/KMZ upload."""
    if not contour_map.filename.lower().endswith((".kml", ".kmz")):
        raise HTTPException(status_code=400, detail="Only KML and KMZ files are supported.")

    try:
        content = await contour_map.read()

        if contour_map.filename.lower().endswith(".kmz"):
            with zipfile.ZipFile(io.BytesIO(content)) as kmz:
                kml_files = [n for n in kmz.namelist() if n.lower().endswith(".kml")]
                if not kml_files:
                    raise HTTPException(status_code=400, detail="No KML file found inside KMZ.")
                content = kmz.read(kml_files[0])

        result = terrain_analysis.calculate_catchment(content)
        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    uvicorn.run(app, host="0.0.0.0", port=port)
