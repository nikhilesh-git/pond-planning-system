import math
import time
import numpy as np
from pyproj import Transformer, CRS
from scipy.interpolate import griddata
from scipy.spatial import ConvexHull
from lxml import etree

DEFAULT_KML_PATH = "/home/student/pond-planning/contours_1m.kml"

def parse_kml(content: bytes):
    """Parses KML content and returns a list of (elevation, [ (lon, lat), ... ])"""
    contours = []
    
    root = etree.fromstring(content)
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
            
    return contours


def calculate_catchment(kml_content: bytes, bbox=None, runoff_coef=0.38, rainfall_annual_mm=1220.0):
    """
    High-performance, memory-safe catchment analysis designed for containerized environments (<512MB RAM).
    Uses adaptive grid resolution, point-cloud decimation, and vector flow routing.
    bbox: [min_lon, min_lat, max_lon, max_lat] or None.
    """
    t0 = time.time()
    contours = parse_kml(kml_content)
    if not contours:
        raise ValueError("No valid contours found in the KML.")
        
    # Filter contours if bbox provided
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        buffer = 0.0015  # ~150m buffer for edge effects
        filtered = []
        for elev, pts in contours:
            in_pts = [p for p in pts if (min_lon - buffer <= p[0] <= max_lon + buffer) and (min_lat - buffer <= p[1] <= max_lat + buffer)]
            if in_pts:
                filtered.append((elev, in_pts))
        if len(filtered) >= 5:
            contours = filtered
            print(f"Cropped to {len(contours)} contours inside user-selected land area.")
        
    # Flatten points
    lons = []
    lats = []
    elevs = []
    
    for elev, pts in contours:
        for lon, lat in pts:
            lons.append(lon)
            lats.append(lat)
            elevs.append(elev)
            
    lons = np.array(lons, dtype=np.float64)
    lats = np.array(lats, dtype=np.float64)
    elevs = np.array(elevs, dtype=np.float64)
    
    # Subsample points if too dense to keep Qhull Delaunay triangulation strictly <15MB RAM
    if len(lons) > 10000:
        step = max(len(lons) // 8000, 2)
        lons = lons[::step]
        lats = lats[::step]
        elevs = elevs[::step]
        print(f"Decimated point cloud to {len(lons)} points for memory-safe Delaunay triangulation.")
    
    # Project to UTM
    mean_lon = float(np.mean(lons))
    mean_lat = float(np.mean(lats))
    utm_zone = int(math.floor((mean_lon + 180) / 6) + 1)
    
    utm_crs = CRS.from_dict({
        'proj': 'utm',
        'zone': utm_zone,
        'south': (mean_lat < 0),
        'ellps': 'WGS84'
    })
    wgs84_crs = CRS.from_epsg(4326)
    
    transformer_to_utm = Transformer.from_crs(wgs84_crs, utm_crs, always_xy=True)
    transformer_to_wgs84 = Transformer.from_crs(utm_crs, wgs84_crs, always_xy=True)
    
    xs, ys = transformer_to_utm.transform(lons, lats)
    
    min_x, max_x = float(np.min(xs)), float(np.max(xs))
    min_y, max_y = float(np.min(ys)), float(np.max(ys))
    span_x = max(max_x - min_x, 10.0)
    span_y = max(max_y - min_y, 10.0)
    max_span = max(span_x, span_y)
    
    # Adaptive grid resolution:
    # Caps max dimensions to ~150 rows/cols (<=25,000 cells max)
    # Memory footprint for 25k cells is <250KB, Delaunay <15MB, Total RAM <45MB
    grid_res = max(round(max_span / 150.0, 1), 3.0)
    
    x_steps = np.arange(min_x, max_x + grid_res * 0.5, grid_res)
    y_steps = np.arange(min_y, max_y + grid_res * 0.5, grid_res)
    grid_x, grid_y = np.meshgrid(x_steps, y_steps, indexing='ij')
    rows, cols = grid_x.shape
    print(f"Adaptive Grid: {rows} x {cols} ({rows * cols} cells) at {grid_res:.1f}m resolution.")
    
    # Interpolate DEM
    points = np.column_stack((xs, ys))
    grid_z = griddata(points, elevs, (grid_x, grid_y), method='linear')
    
    nan_mask = np.isnan(grid_z)
    if np.any(nan_mask):
        grid_z_nearest = griddata(points, elevs, (grid_x, grid_y), method='nearest')
        grid_z[nan_mask] = grid_z_nearest[nan_mask]
        
    # D8 flow routing
    flow_to = np.arange(rows * cols, dtype=np.int32)
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
                    if grid_z[nr, nc] < min_z:
                        min_z = grid_z[nr, nc]
                        min_idx = nr * cols + nc
                        
            flow_to[idx] = min_idx
            
    # Resolve ultimate sinks with memoized path compression
    flow_sink = np.copy(flow_to)
    for i in range(len(flow_to)):
        curr = i
        path = []
        visited = set()
        while flow_sink[curr] != curr and curr not in visited:
            visited.add(curr)
            path.append(curr)
            curr = flow_sink[curr]
        for p in path:
            flow_sink[p] = curr
            
    # Sinks mapping
    unique_sinks, sink_counts = np.unique(flow_sink, return_counts=True)
    sinks = dict(zip(unique_sinks, sink_counts))
    
    # Flow accumulation
    flow_accum = np.ones(rows * cols, dtype=np.int32)
    flat_z = grid_z.ravel()
    sorted_indices = np.argsort(-flat_z)
    
    for idx in sorted_indices:
        target = flow_to[idx]
        if target != idx:
            flow_accum[target] += flow_accum[idx]
            
    flow_accum_grid = flow_accum.reshape(rows, cols)
    
    nonzero_accum = flow_accum[flow_accum > 1]
    if len(nonzero_accum) > 0:
        river_threshold = max(float(np.percentile(nonzero_accum, 97)), 50.0)
    else:
        river_threshold = 50.0
        
    grad_x = np.gradient(grid_z, grid_res, axis=0)
    grad_y = np.gradient(grid_z, grid_res, axis=1)
    gradient_mag = np.sqrt(grad_x**2 + grad_y**2)
    
    sorted_sinks = sorted(sinks.keys(), key=lambda k: sinks[k], reverse=True)
    map_min_elev = float(np.min(grid_z))
    map_max_elev = float(np.max(grid_z))
    map_elev_range = map_max_elev - map_min_elev
    river_elev_margin = max(map_elev_range * 0.10, 2.0)
    
    pre_filtered = []
    edge_buffer = max(min(rows // 15, cols // 15, 20), 4)
    min_catch_pixels = max(int(400.0 / (grid_res ** 2)), 2)
    
    for sink in sorted_sinks:
        sink_r = sink // cols
        sink_c = sink % cols
        sink_elev = float(grid_z[sink_r, sink_c])
        sink_catchment = sinks[sink]
        
        if sink_r < edge_buffer or sink_r >= rows - edge_buffer:
            continue
        if sink_c < edge_buffer or sink_c >= cols - edge_buffer:
            continue
        if sink_elev <= map_min_elev + river_elev_margin:
            continue
            
        sink_accum = flow_accum_grid[sink_r, sink_c]
        if sink_accum > river_threshold:
            continue
            
        neighborhood_r = max(int(30.0 / grid_res), 2)
        r_lo = max(0, sink_r - neighborhood_r)
        r_hi = min(rows, sink_r + neighborhood_r + 1)
        c_lo = max(0, sink_c - neighborhood_r)
        c_hi = min(cols, sink_c + neighborhood_r + 1)
        
        neighborhood_max_accum = np.max(flow_accum_grid[r_lo:r_hi, c_lo:c_hi])
        if neighborhood_max_accum > river_threshold * 4:
            continue
            
        if sink_catchment < min_catch_pixels:
            continue
            
        pre_filtered.append((sink, sink_r, sink_c, sink_elev, sink_catchment, sink_accum, r_lo, r_hi, c_lo, c_hi))
        
    candidate_scores = []
    max_catchment = sinks[sorted_sinks[0]] if sorted_sinks else 1
    
    for i, (sink, sink_r, sink_c, sink_elev, sink_catchment, sink_accum, r_lo, r_hi, c_lo, c_hi) in enumerate(pre_filtered[:50]):
        local_gradient = gradient_mag[r_lo:r_hi, c_lo:c_hi]
        mean_gradient = float(np.mean(local_gradient))
        if mean_gradient < 0.002:
            continue
            
        elev_score = (sink_elev - map_min_elev) / map_elev_range if map_elev_range > 0 else 0
        catchment_ratio = sink_catchment / max_catchment if max_catchment > 0 else 0
        catchment_score = catchment_ratio * (1.0 - catchment_ratio * 0.5)
        accum_score = 1.0 - min(sink_accum / river_threshold, 1.0)
        
        total_score = (elev_score * 0.3) + (catchment_score * 0.4) + (accum_score * 0.3)
        candidate_scores.append((sink, sink_catchment, total_score, sink_elev))
        
    if candidate_scores:
        candidate_scores.sort(key=lambda x: x[2], reverse=True)
        best_sink, catchment_size_pixels, best_score, best_elev = candidate_scores[0]
    else:
        best_sink = sorted_sinks[0]
        catchment_size_pixels = sinks[best_sink]
        best_score = 0.20
        best_elev = float(grid_z[best_sink // cols, best_sink % cols])
        
    catchment_area_sqm = float(catchment_size_pixels * (grid_res ** 2))
    
    best_sink_r = best_sink // cols
    best_sink_c = best_sink % cols
    best_x = grid_x[best_sink_r, best_sink_c]
    best_y = grid_y[best_sink_r, best_sink_c]
    best_lon, best_lat = transformer_to_wgs84.transform(best_x, best_y)
    
    # Catchment boundary delineation
    catchment_cells = np.where(flow_sink == best_sink)[0]
    if len(catchment_cells) >= 6:
        cr = catchment_cells // cols
        cc = catchment_cells % cols
        cx = grid_x[cr, cc]
        cy = grid_y[cr, cc]
        clon, clat = transformer_to_wgs84.transform(cx, cy)
        
        pts_2d = np.column_stack((clon, clat))
        try:
            hull = ConvexHull(pts_2d)
            hull_indices = hull.vertices
            hull_coords = [[float(pts_2d[idx, 0]), float(pts_2d[idx, 1])] for idx in hull_indices]
            hull_coords.append(hull_coords[0]) # close polygon
        except Exception:
            r_deg = (math.sqrt(max(catchment_area_sqm, 400.0) / math.pi) / 111000.0) * 1.2
            angles = np.linspace(0, 2*np.pi, 20)
            hull_coords = [[float(best_lon + r_deg * np.cos(a)), float(best_lat + r_deg * np.sin(a))] for a in angles]
    else:
        r_deg = (math.sqrt(max(catchment_area_sqm, 400.0) / math.pi) / 111000.0) * 1.2
        angles = np.linspace(0, 2*np.pi, 20)
        hull_coords = [[float(best_lon + r_deg * np.cos(a)), float(best_lat + r_deg * np.sin(a))] for a in angles]
        
    # Alternative Candidates (Top 4)
    candidates_list = []
    top_candidates = candidate_scores[:4] if candidate_scores else [(best_sink, catchment_size_pixels, best_score, best_elev)]
    for rank, (cand_sink, cand_catch, cand_score, cand_elev) in enumerate(top_candidates, 1):
        cr_idx = cand_sink // cols
        cc_idx = cand_sink % cols
        cx_val = grid_x[cr_idx, cc_idx]
        cy_val = grid_y[cr_idx, cc_idx]
        slon, slat = transformer_to_wgs84.transform(cx_val, cy_val)
        candidates_list.append({
            "rank": rank,
            "latitude": round(float(slat), 6),
            "longitude": round(float(slon), 6),
            "elevation": round(float(cand_elev), 1),
            "catchment_sqm": round(float(cand_catch * (grid_res ** 2)), 1),
            "score": round(float(cand_score), 3),
            "type": "Primary Recommended Site" if rank == 1 else f"Candidate Site #{rank}"
        })
        
    # Hydrology & Water volume calculations
    rainfall_annual_m = rainfall_annual_mm / 1000.0
    rainfall_monsoon_m = (rainfall_annual_mm * 0.856) / 1000.0
    
    annual_runoff_m3 = round(catchment_area_sqm * rainfall_annual_m * runoff_coef, 1)
    monsoon_runoff_m3 = round(catchment_area_sqm * rainfall_monsoon_m * runoff_coef, 1)
    
    design_depth_m = 3.5
    design_capacity_m3 = min(round(monsoon_runoff_m3 * 0.75, 1), 60000.0)
    surface_area_sqm = round(design_capacity_m3 / (design_depth_m - 0.5), 1)
    
    exec_time = round(time.time() - t0, 2)
    print(f"Catchment analysis completed successfully in {exec_time}s.")
    
    return {
        "status": "success",
        "execution_time_seconds": exec_time,
        "pond_location": {
            "latitude": round(float(best_lat), 6),
            "longitude": round(float(best_lon), 6),
            "elevation": round(float(grid_z[best_sink_r, best_sink_c]), 1)
        },
        "catchment_area_sqm": round(catchment_area_sqm, 1),
        "catchment": {
            "area_sqm": round(catchment_area_sqm, 1),
            "area_hectares": round(catchment_area_sqm / 10000.0, 3),
            "area_acres": round(catchment_area_sqm * 0.000247105, 3),
            "polygon_geojson": {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [hull_coords]
                },
                "properties": {
                    "name": "Catchment Basin",
                    "area_sqm": round(catchment_area_sqm, 1)
                }
            }
        },
        "candidates": candidates_list,
        "rainfall": {
            "station": "Bhilai / Durg AWS (IMD)",
            "annual_mm": rainfall_annual_mm,
            "monsoon_mm": round(rainfall_annual_mm * 0.856, 1),
            "runoff_coefficient": runoff_coef,
            "soil_type": "Clayey / Black Cotton Soil" if runoff_coef >= 0.40 else ("Agricultural Loam" if runoff_coef >= 0.30 else "Sandy Loam")
        },
        "water_volume": {
            "annual_runoff_m3": annual_runoff_m3,
            "monsoon_runoff_m3": monsoon_runoff_m3,
            "annual_liters": int(annual_runoff_m3 * 1000),
            "annual_million_liters": round(annual_runoff_m3 / 1000.0, 2),
            "household_days_supported": int((annual_runoff_m3 * 1000) / 150)
        },
        "pond_recommendations": {
            "recommended_depth_m": design_depth_m,
            "design_capacity_m3": design_capacity_m3,
            "design_capacity_million_liters": round(design_capacity_m3 / 1000.0, 2),
            "surface_area_sqm": surface_area_sqm,
            "side_slope": "1.5:1 (H:V)",
            "freeboard_m": 0.5,
            "dead_storage_depth_m": 0.5,
            "silt_trap_capacity_m3": round(design_capacity_m3 * 0.05, 1)
        }
    }
