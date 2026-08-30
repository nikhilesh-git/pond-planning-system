import numpy as np
from bs4 import BeautifulSoup
from pyproj import Transformer, CRS
from scipy.interpolate import griddata
import math

from lxml import etree

def parse_kml(content: bytes):
    """Parses KML content and returns a list of (elevation, [ (lon, lat), ... ])"""
    print("Parsing KML with lxml...")
    contours = []
    
    # Use lxml for fast parsing
    root = etree.fromstring(content)
    # The KML has namespaces. We need to handle them or strip them.
    # A simple way is to use xpath with local-name()
    placemarks = root.xpath('//*[local-name()="Placemark"]')
    
    for pm in placemarks:
        name_tag = pm.xpath('*[local-name()="name"]')
        if not name_tag:
            continue
        try:
            elevation = float(name_tag[0].text)
        except (ValueError, TypeError):
            continue
            
        coords_tag = pm.xpath('.//*[local-name()="coordinates"]')
        if not coords_tag:
            continue
            
        coords_text = coords_tag[0].text.strip()
        coords_list = coords_text.split()
        
        points = []
        for pt in coords_list:
            parts = pt.split(',')
            if len(parts) >= 2:
                lon = float(parts[0])
                lat = float(parts[1])
                points.append((lon, lat))
                
        if points:
            contours.append((elevation, points))
            
    print(f"Extracted {len(contours)} contours.")
    return contours

def calculate_catchment(kml_content: bytes):
    contours = parse_kml(kml_content)
    if not contours:
        raise ValueError("No valid contours found in the KML.")
        
    # Flatten points
    lons = []
    lats = []
    elevs = []
    
    for elev, pts in contours:
        for lon, lat in pts:
            lons.append(lon)
            lats.append(lat)
            elevs.append(elev)
            
    lons = np.array(lons)
    lats = np.array(lats)
    elevs = np.array(elevs)
    
    print("Projecting coordinates...")
    mean_lon = np.mean(lons)
    mean_lat = np.mean(lats)
    utm_zone = int(math.floor((mean_lon + 180) / 6) + 1)
    
    is_south = mean_lat < 0
    utm_crs = CRS.from_dict({
        'proj': 'utm',
        'zone': utm_zone,
        'south': is_south,
        'ellps': 'WGS84'
    })
    wgs84_crs = CRS.from_epsg(4326) # lat, lon
    
    transformer_to_utm = Transformer.from_crs(wgs84_crs, utm_crs, always_xy=True)
    transformer_to_wgs84 = Transformer.from_crs(utm_crs, wgs84_crs, always_xy=True)
    
    xs, ys = transformer_to_utm.transform(lons, lats)
    
    print("Creating grid...")
    grid_res = 2.0 # 2 meters resolution
    min_x, max_x = np.min(xs), np.max(xs)
    min_y, max_y = np.min(ys), np.max(ys)
    
    grid_x, grid_y = np.mgrid[min_x:max_x:grid_res, min_y:max_y:grid_res]
    
    print(f"Grid size: {grid_x.shape}")
    print("Interpolating DEM...")
    points = np.column_stack((xs, ys))
    grid_z = griddata(points, elevs, (grid_x, grid_y), method='linear')
    
    nan_mask = np.isnan(grid_z)
    if np.any(nan_mask):
        print("Filling NaNs with nearest neighbor...")
        grid_z_nearest = griddata(points, elevs, (grid_x, grid_y), method='nearest')
        grid_z[nan_mask] = grid_z_nearest[nan_mask]
        
    print("Running D8 flow routing...")
    rows, cols = grid_z.shape
    
    flow_to = np.arange(rows * cols)
    
    dr = [-1, -1, -1, 0, 0, 1, 1, 1]
    dc = [-1, 0, 1, -1, 1, -1, 0, 1]
    
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            min_z = grid_z[r, c]
            min_idx = idx
            
            for d in range(8):
                nr = r + dr[d]
                nc = c + dc[d]
                
                if 0 <= nr < rows and 0 <= nc < cols:
                    n_idx = nr * cols + nc
                    if grid_z[nr, nc] < min_z:
                        min_z = grid_z[nr, nc]
                        min_idx = n_idx
                        
            flow_to[idx] = min_idx
            
    print("Resolving paths to find ultimate sinks...")
    sinks = {}
    
    for i in range(len(flow_to)):
        curr = i
        visited = set()
        while flow_to[curr] != curr and curr not in visited:
            visited.add(curr)
            curr = flow_to[curr]
            
        flow_to[i] = curr
        
        if curr not in sinks:
            sinks[curr] = 0
        sinks[curr] += 1
        
    print("Identifying main catchment...")
    best_sink = max(sinks.keys(), key=lambda k: sinks[k])
    catchment_size_pixels = sinks[best_sink]
    
    catchment_area_sqm = catchment_size_pixels * (grid_res ** 2)
    
    best_sink_r = best_sink // cols
    best_sink_c = best_sink % cols
    
    best_x = grid_x[best_sink_r, best_sink_c]
    best_y = grid_y[best_sink_r, best_sink_c]
    
    best_lon, best_lat = transformer_to_wgs84.transform(best_x, best_y)
    print("Analysis complete.")
    
    return {
        "pond_location": {
            "latitude": float(best_lat),
            "longitude": float(best_lon),
            "elevation": float(grid_z[best_sink_r, best_sink_c])
        },
        "catchment_area_sqm": float(catchment_area_sqm)
    }
