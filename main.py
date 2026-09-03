from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import terrain_analysis

app = FastAPI(title="Pond Catchment Analysis API",
              description="API to analyze contour maps and estimate catchment area for pond planning.")

@app.post("/analyzeContour")
async def analyze_contour(
    file: UploadFile = File(None),
    contour_map: UploadFile = File(None)
):
    # Pick whichever field was provided
    uploaded_file = file or contour_map
    
    if uploaded_file is None:
        raise HTTPException(
            status_code=422,
            detail="File is required. Please upload using key 'file' or 'contour_map'."
        )

    if not uploaded_file.filename.endswith(('.kml', '.kmz')):
        raise HTTPException(status_code=400, detail="Only KML and KMZ files are supported.")
        
    try:
        content = await uploaded_file.read()
        
        if uploaded_file.filename.endswith('.kmz'):
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
