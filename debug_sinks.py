import terrain_analysis
import numpy as np

# We'll monkey-patch calculate_catchment to just print the top sinks
with open("contours_1m.kml", "rb") as f:
    content = f.read()

# We need to run the grid creation to see the top sinks. Let's duplicate the logic here to inspect.
contours = terrain_analysis.parse_kml(content)

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

print(f"Min Elev: {np.min(elevs)}, Max Elev: {np.max(elevs)}")

# Re-run grid creation and routing exactly as in terrain_analysis
import math
from pyproj import Transformer, CRS
from scipy.interpolate import griddata

mean_lon = np.mean(lons)
mean_lat = np.mean(lats)
utm_zone = int(math.floor((mean_lon + 180) / 6) + 1)
is_south = mean_lat < 0
utm_crs = CRS.from_dict({'proj': 'utm', 'zone': utm_zone, 'south': is_south, 'ellps': 'WGS84'})
wgs84_crs = CRS.from_epsg(4326)
transformer_to_utm = Transformer.from_crs(wgs84_crs, utm_crs, always_xy=True)
transformer_to_wgs84 = Transformer.from_crs(utm_crs, wgs84_crs, always_xy=True)

xs, ys = transformer_to_utm.transform(lons, lats)
grid_res = 2.0
min_x, max_x = np.min(xs), np.max(xs)
min_y, max_y = np.min(ys), np.max(ys)
grid_x, grid_y = np.mgrid[min_x:max_x:grid_res, min_y:max_y:grid_res]

points = np.column_stack((xs, ys))
grid_z = griddata(points, elevs, (grid_x, grid_y), method='linear')
nan_mask = np.isnan(grid_z)
if np.any(nan_mask):
    grid_z_nearest = griddata(points, elevs, (grid_x, grid_y), method='nearest')
    grid_z[nan_mask] = grid_z_nearest[nan_mask]
    
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
    
sorted_sinks = sorted(sinks.keys(), key=lambda k: sinks[k], reverse=True)
map_min_elev = np.min(grid_z)
print(f"Map Min Elev in Grid: {map_min_elev}")

for i, sink in enumerate(sorted_sinks[:10]):
    sink_r = sink // cols
    sink_c = sink % cols
    sink_elev = grid_z[sink_r, sink_c]
    
    # calc flat area
    flat_area_pixels = 0
    visited_flat = set()
    queue = [(sink_r, sink_c)]
    visited_flat.add((sink_r, sink_c))
    
    while queue:
        curr_r, curr_c = queue.pop(0)
        flat_area_pixels += 1
        for d in range(8):
            nr = curr_r + dr[d]
            nc = curr_c + dc[d]
            if 0 <= nr < rows and 0 <= nc < cols:
                if (nr, nc) not in visited_flat:
                    if abs(grid_z[nr, nc] - sink_elev) < 0.05:
                        visited_flat.add((nr, nc))
                        queue.append((nr, nc))
                        
    area = sinks[sink] * 4.0
    x, y = grid_x[sink_r, sink_c], grid_y[sink_r, sink_c]
    lon, lat = transformer_to_wgs84.transform(x, y)
    print(f"Rank {i+1}: Elev={sink_elev:.1f}m, Area={area} sqm, Flat={flat_area_pixels*4} sqm, Pos=({sink_r},{sink_c}), Lat={lat:.5f}, Lon={lon:.5f}")
