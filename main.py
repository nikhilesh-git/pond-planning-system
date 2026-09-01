from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import terrain_analysis

app = FastAPI(title="Pond Catchment Analysis API",
              description="API to analyze contour maps and estimate catchment area for pond planning.")

@app.post("/analyzeContour")
async def analyze_contour(file: UploadFile = File(...)):
    if not file.filename.endswith(('.kml', '.kmz')):
        raise HTTPException(status_code=400, detail="Only KML and KMZ files are supported.")
        
    try:
        content = await file.read()
        
        # If KMZ, we would need to unzip and extract KML. For this assignment, 
        # we'll assume KML is uploaded directly as per the contours.kml file.
        if file.filename.endswith('.kmz'):
            import zipfile
            import io
            with zipfile.ZipFile(io.BytesIO(content)) as kmz:
                kml_filename = [name for name in kmz.namelist() if name.endswith('.kml')][0]
                content = kmz.read(kml_filename)
                
        result = terrain_analysis.calculate_catchment(content)
        
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
