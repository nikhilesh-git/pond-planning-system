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
        
    print("Building flow accumulation grid to detect rivers...")
    
    # --- Step 1: Build flow accumulation grid ---
    # Flow accumulation counts how many upstream cells drain through each cell.
    # River/stream cells have very high accumulation; upland depressions have low accumulation.
    flow_accum = np.ones(rows * cols, dtype=np.int64)
    
    # Topological sort: process cells from highest to lowest elevation
    flat_z = grid_z.ravel()
    sorted_indices = np.argsort(-flat_z)  # descending elevation
    
    for idx in sorted_indices:
        target = flow_to[idx]
        if target != idx:
            flow_accum[target] += flow_accum[idx]
    
    flow_accum_grid = flow_accum.reshape(rows, cols)
    
    # River threshold: cells with accumulation above this are part of a river/stream network.
    # Use a percentile-based approach so it adapts to different map sizes.
    nonzero_accum = flow_accum[flow_accum > 1]
    if len(nonzero_accum) > 0:
        river_threshold = max(np.percentile(nonzero_accum, 97), 200)
    else:
        river_threshold = 200
    
    print(f"River accumulation threshold: {river_threshold}")
    
    # --- Step 2: Compute local gradient magnitude at each cell ---
    grad_x = np.gradient(grid_z, grid_res, axis=0)
    grad_y = np.gradient(grid_z, grid_res, axis=1)
    gradient_mag = np.sqrt(grad_x**2 + grad_y**2)
    
    print("Identifying valid pond locations (excluding rivers and waterbodies)...")
    
    # Sort sinks by catchment size (descending)
    sorted_sinks = sorted(sinks.keys(), key=lambda k: sinks[k], reverse=True)
    
    # Pre-compute map statistics for filtering
    map_min_elev = np.min(grid_z)
    map_max_elev = np.max(grid_z)
    map_elev_range = map_max_elev - map_min_elev
    
    # The river elevation band: anything within the bottom 10% of the elevation range
    # (or 3m, whichever is larger) is considered river-zone elevation.
    river_elev_margin = max(map_elev_range * 0.10, 3.0)
    
    best_sink = None
    catchment_size_pixels = 0
    
    # --- PASS 1: Fast pre-filtering with cheap checks only ---
    # Apply edge, elevation, flow accumulation, and minimum catchment filters
    # These are all O(1) per sink, so iterating all sinks is fast.
    print(f"  Pre-filtering {len(sorted_sinks)} sinks with fast checks...")
    pre_filtered = []
    
    for sink in sorted_sinks:
        sink_r = sink // cols
        sink_c = sink % cols
        sink_elev = grid_z[sink_r, sink_c]
        sink_catchment = sinks[sink]
        
        # Filter 1: Generous edge exclusion (100 pixels = 200m buffer)
        edge_buffer = 100
        if sink_r < edge_buffer or sink_r >= rows - edge_buffer:
            continue
        if sink_c < edge_buffer or sink_c >= cols - edge_buffer:
            continue
        
        # Filter 2: Exclude low-elevation river channel zone
        if sink_elev <= map_min_elev + river_elev_margin:
            continue
        
        # Filter 3: Exclude sinks at high flow-accumulation cells (river channels)
        sink_accum = flow_accum_grid[sink_r, sink_c]
        if sink_accum > river_threshold:
            continue
        
        # Filter 3b: Neighborhood river proximity check
        neighborhood_r = 10
        r_lo = max(0, sink_r - neighborhood_r)
        r_hi = min(rows, sink_r + neighborhood_r + 1)
        c_lo = max(0, sink_c - neighborhood_r)
        c_hi = min(cols, sink_c + neighborhood_r + 1)
        
        neighborhood_max_accum = np.max(flow_accum_grid[r_lo:r_hi, c_lo:c_hi])
        if neighborhood_max_accum > river_threshold * 5:
            continue
        
        # Filter 4: Minimum catchment size (pond needs meaningful catchment)
        if sink_catchment < 100:
            continue
        
        pre_filtered.append((sink, sink_r, sink_c, sink_elev, sink_catchment, sink_accum, r_lo, r_hi, c_lo, c_hi))
    
    print(f"  {len(pre_filtered)} sinks passed pre-filtering. Running detailed checks on top 50...")
    
    # --- PASS 2: Expensive checks (BFS, gradient) on top candidates only ---
    # Limit to top 50 by catchment size to avoid spending minutes on BFS
    candidate_scores = []
    max_catchment = sinks[sorted_sinks[0]]
    
    for i, (sink, sink_r, sink_c, sink_elev, sink_catchment, sink_accum, r_lo, r_hi, c_lo, c_hi) in enumerate(pre_filtered[:50]):
        # Filter 5: Exclude existing flat waterbodies (BFS for contiguous flat area)
        flat_area_pixels = 0
        visited_flat = set()
        queue = [(sink_r, sink_c)]
        visited_flat.add((sink_r, sink_c))
        
        while queue:
            curr_r, curr_c = queue.pop(0)
            flat_area_pixels += 1
            
            # Early termination
            if flat_area_pixels > 300:
                break
            
            for d in range(8):
                nr = curr_r + dr[d]
                nc = curr_c + dc[d]
                if 0 <= nr < rows and 0 <= nc < cols:
                    if (nr, nc) not in visited_flat:
                        if abs(grid_z[nr, nc] - sink_elev) < 0.1:
                            visited_flat.add((nr, nc))
                            queue.append((nr, nc))
        
        if flat_area_pixels > 300:
            continue
        
        # Filter 6: Check local gradient
        local_gradient = gradient_mag[r_lo:r_hi, c_lo:c_hi]
        mean_gradient = np.mean(local_gradient)
        
        if mean_gradient < 0.005:
            continue
        
        # --- Scoring: prefer upland depressions with good catchment ---
        elev_score = (sink_elev - map_min_elev) / map_elev_range if map_elev_range > 0 else 0
        
        catchment_ratio = sink_catchment / max_catchment
        catchment_score = catchment_ratio * (1 - catchment_ratio)
        
        accum_score = 1.0 - min(sink_accum / river_threshold, 1.0)
        
        total_score = (elev_score * 0.3) + (catchment_score * 0.4) + (accum_score * 0.3)
        
        candidate_scores.append((sink, sink_catchment, total_score, sink_elev))
    
    if candidate_scores:
        # Sort candidates by score (descending) and pick the best
        candidate_scores.sort(key=lambda x: x[2], reverse=True)
        best_sink, catchment_size_pixels, best_score, best_elev = candidate_scores[0]
        print(f"Selected pond site: score={best_score:.3f}, elev={best_elev:.1f}m, "
              f"catchment={catchment_size_pixels * grid_res**2:.0f} sqm")
        
        # Log top 3 candidates for debugging
        for i, (s, cp, sc, se) in enumerate(candidate_scores[:3]):
            sr, scol = s // cols, s % cols
            sx, sy = grid_x[sr, scol], grid_y[sr, scol]
            slon, slat = transformer_to_wgs84.transform(sx, sy)
            print(f"  Candidate {i+1}: score={sc:.3f}, elev={se:.1f}m, "
                  f"catchment={cp * grid_res**2:.0f} sqm, "
                  f"lat={slat:.5f}, lon={slon:.5f}")
    else:
        # Fallback: use the largest interior sink if all candidates were rejected
        print("WARNING: All candidates were filtered out. Using fallback.")
        edge_buffer = 50
        for sink in sorted_sinks:
            sink_r = sink // cols
            sink_c = sink % cols
            if (edge_buffer <= sink_r < rows - edge_buffer and
                    edge_buffer <= sink_c < cols - edge_buffer):
                best_sink = sink
                catchment_size_pixels = sinks[sink]
                break
        if best_sink is None:
            best_sink = sorted_sinks[0]
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
