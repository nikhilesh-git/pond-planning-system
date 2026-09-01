import os
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from pyproj import Transformer, CRS
from scipy.interpolate import griddata
from lxml import etree

def generate_all_visualizations(kml_path="contours_1m.kml", output_dir="visualizations"):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Reading {kml_path}...")
    with open(kml_path, "rb") as f:
        content = f.read()

    # 1. Parse KML
    root = etree.fromstring(content)
    placemarks = root.xpath('//*[local-name()="Placemark"]')
    contours = []
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
        points = []
        for pt in coords_text.split():
            parts = pt.split(',')
            if len(parts) >= 2:
                points.append((float(parts[0]), float(parts[1])))
        if points:
            contours.append((elevation, points))

    # Coordinate projection
    lons, lats, elevs = [], [], []
    for elev, pts in contours:
        for lon, lat in pts:
            lons.append(lon)
            lats.append(lat)
            elevs.append(elev)

    lons = np.array(lons)
    lats = np.array(lats)
    elevs = np.array(elevs)

    mean_lon, mean_lat = np.mean(lons), np.mean(lats)
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

    # D8 Routing
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
        sinks[curr] = sinks.get(curr, 0) + 1

    # Flow accumulation
    flow_accum = np.ones(rows * cols, dtype=np.int64)
    sorted_indices = np.argsort(-grid_z.ravel())
    for idx in sorted_indices:
        target = flow_to[idx]
        if target != idx:
            flow_accum[target] += flow_accum[idx]
    flow_accum_grid = flow_accum.reshape(rows, cols)

    # Filter logic
    nonzero_accum = flow_accum[flow_accum > 1]
    river_threshold = max(np.percentile(nonzero_accum, 97), 200) if len(nonzero_accum) > 0 else 200
    sorted_sinks = sorted(sinks.keys(), key=lambda k: sinks[k], reverse=True)
    map_min_elev = np.min(grid_z)
    map_max_elev = np.max(grid_z)
    map_elev_range = map_max_elev - map_min_elev
    river_elev_margin = max(map_elev_range * 0.10, 3.0)

    pre_filtered = []
    for sink in sorted_sinks:
        sink_r = sink // cols
        sink_c = sink % cols
        sink_elev = grid_z[sink_r, sink_c]
        sink_catchment = sinks[sink]
        if sink_r < 100 or sink_r >= rows - 100 or sink_c < 100 or sink_c >= cols - 100:
            continue
        if sink_elev <= map_min_elev + river_elev_margin:
            continue
        sink_accum = flow_accum_grid[sink_r, sink_c]
        if sink_accum > river_threshold:
            continue
        neighborhood_r = 10
        r_lo = max(0, sink_r - neighborhood_r)
        r_hi = min(rows, sink_r + neighborhood_r + 1)
        c_lo = max(0, sink_c - neighborhood_r)
        c_hi = min(cols, sink_c + neighborhood_r + 1)
        if np.max(flow_accum_grid[r_lo:r_hi, c_lo:c_hi]) > river_threshold * 5:
            continue
        if sink_catchment < 100:
            continue
        pre_filtered.append((sink, sink_r, sink_c, sink_elev, sink_catchment, sink_accum, r_lo, r_hi, c_lo, c_hi))

    grad_x = np.gradient(grid_z, grid_res, axis=0)
    grad_y = np.gradient(grid_z, grid_res, axis=1)
    gradient_mag = np.sqrt(grad_x**2 + grad_y**2)

    candidate_scores = []
    max_catchment = sinks[sorted_sinks[0]]
    for sink, sink_r, sink_c, sink_elev, sink_catchment, sink_accum, r_lo, r_hi, c_lo, c_hi in pre_filtered[:50]:
        flat_area_pixels = 0
        visited_flat = set([(sink_r, sink_c)])
        queue = [(sink_r, sink_c)]
        while queue:
            curr_r, curr_c = queue.pop(0)
            flat_area_pixels += 1
            if flat_area_pixels > 300:
                break
            for d in range(8):
                nr = curr_r + dr[d]
                nc = curr_c + dc[d]
                if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited_flat:
                    if abs(grid_z[nr, nc] - sink_elev) < 0.1:
                        visited_flat.add((nr, nc))
                        queue.append((nr, nc))
        if flat_area_pixels > 300:
            continue
        if np.mean(gradient_mag[r_lo:r_hi, c_lo:c_hi]) < 0.005:
            continue

        elev_score = (sink_elev - map_min_elev) / map_elev_range if map_elev_range > 0 else 0
        catchment_ratio = sink_catchment / max_catchment
        catchment_score = catchment_ratio * (1 - catchment_ratio)
        accum_score = 1.0 - min(sink_accum / river_threshold, 1.0)
        total_score = (elev_score * 0.3) + (catchment_score * 0.4) + (accum_score * 0.3)
        candidate_scores.append((sink, sink_catchment, total_score, sink_elev, sink_r, sink_c))

    candidate_scores.sort(key=lambda x: x[2], reverse=True)
    best_sink, catchment_size_pixels, best_score, best_elev, best_r, best_c = candidate_scores[0]
    best_x, best_y = grid_x[best_r, best_c], grid_y[best_r, best_c]
    best_lon, best_lat = transformer_to_wgs84.transform(best_x, best_y)

    print(f"Selected pond at ({best_r}, {best_c}), Lat: {best_lat:.5f}, Lon: {best_lon:.5f}, Elev: {best_elev:.1f}m, Catchment: {catchment_size_pixels * (grid_res**2):.1f} sqm")

    # Catchment mask
    catchment_mask = (flow_to == best_sink).reshape(rows, cols)

    # ------------------ PLOT 1: Comprehensive 4-Panel Dashboard ------------------
    fig, axes = plt.subplots(2, 2, figsize=(16, 14), dpi=150)
    plt.subplots_adjust(wspace=0.25, hspace=0.25)
    
    # 1.1 Digital Elevation Model (DEM)
    ax1 = axes[0, 0]
    im1 = ax1.imshow(grid_z.T, origin='lower', cmap='terrain', extent=[0, rows*grid_res, 0, cols*grid_res])
    cbar1 = fig.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04)
    cbar1.set_label('Elevation (m)', fontsize=10)
    ax1.scatter([best_r * grid_res], [best_c * grid_res], color='red', marker='*', s=200, edgecolors='black', label='Pond Location (290m)', zorder=5)
    ax1.set_title("1. Digital Elevation Model (DEM) & Pond Location", fontsize=12, fontweight='bold', pad=10)
    ax1.set_xlabel("UTM Easting relative (m)")
    ax1.set_ylabel("UTM Northing relative (m)")
    ax1.legend(loc='upper right')

    # 1.2 Flow Accumulation & Stream Network
    ax2 = axes[0, 1]
    log_accum = np.log10(flow_accum_grid.T + 1)
    im2 = ax2.imshow(log_accum, origin='lower', cmap='Blues', extent=[0, rows*grid_res, 0, cols*grid_res])
    cbar2 = fig.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)
    cbar2.set_label('Log10 Flow Accumulation', fontsize=10)
    # Stream overlay
    stream_mask = flow_accum_grid > river_threshold
    ax2.contour(stream_mask.T, levels=[0.5], colors=['#0d47a1'], linewidths=1.2, extent=[0, rows*grid_res, 0, cols*grid_res])
    ax2.scatter([best_r * grid_res], [best_c * grid_res], color='red', marker='*', s=200, edgecolors='black', label='Pond (Away from Rivers)', zorder=5)
    ax2.set_title("2. Stream Network & River Exclusion Filtering", fontsize=12, fontweight='bold', pad=10)
    ax2.set_xlabel("UTM Easting relative (m)")
    ax2.set_ylabel("UTM Northing relative (m)")
    ax2.legend(loc='upper right')

    # 1.3 Catchment Basin Overlay
    ax3 = axes[1, 0]
    # Light shaded relief
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(grid_z, cmap=plt.cm.copper, vert_exag=0.1, blend_mode='overlay')
    ax3.imshow(np.swapaxes(rgb, 0, 1), origin='lower', extent=[0, rows*grid_res, 0, cols*grid_res])
    ax3.imshow(np.ma.masked_where(~catchment_mask.T, catchment_mask.T), origin='lower', cmap='spring', alpha=0.75, extent=[0, rows*grid_res, 0, cols*grid_res])
    ax3.scatter([best_r * grid_res], [best_c * grid_res], color='blue', marker='o', s=100, edgecolors='white', label=f'Pond Outlet ({catchment_size_pixels*4:.0f} m² Basin)', zorder=5)
    ax3.set_title("3. Drained Catchment Basin (Drainage Area)", fontsize=12, fontweight='bold', pad=10)
    ax3.set_xlabel("UTM Easting relative (m)")
    ax3.set_ylabel("UTM Northing relative (m)")
    ax3.legend(loc='upper right')

    # 1.4 Sink Scoring & Candidate Analysis
    ax4 = axes[1, 1]
    cand_elevs = [c[3] for c in candidate_scores[:15]]
    cand_areas = [c[1]*4 for c in candidate_scores[:15]]
    cand_scores = [c[2] for c in candidate_scores[:15]]
    indices = np.arange(len(cand_scores))
    bars = ax4.bar(indices, cand_scores, color=['#2e7d32' if i==0 else '#42a5f5' for i in range(len(indices))], edgecolor='black', alpha=0.85)
    ax4.set_title("4. Multi-Criteria Sink Candidate Ranking", fontsize=12, fontweight='bold', pad=10)
    ax4.set_xlabel("Candidate Rank (Rank 1 = Selected Pond)")
    ax4.set_ylabel("Composite Optimization Score")
    ax4.set_xticks(indices)
    ax4.set_xticklabels([f"#{i+1}\n({cand_elevs[i]:.0f}m)" for i in indices], fontsize=8)
    for bar, score in zip(bars, cand_scores):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01, f"{score:.2f}", ha='center', va='bottom', fontsize=8)

    plt.suptitle("Pond Planning & Catchment Hydrology Analysis Pipeline", fontsize=16, fontweight='bold', y=0.98)
    dashboard_path = os.path.join(output_dir, "pond_analysis_dashboard.png")
    fig.savefig(dashboard_path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {dashboard_path}")

    # ------------------ PLOT 2: High-Res 3D Terrain Visualization ------------------
    fig = plt.figure(figsize=(12, 9), dpi=150)
    ax_3d = fig.add_subplot(111, projection='3d')
    # Subsample for smooth 3D rendering
    step = 4
    X = grid_x[::step, ::step] - min_x
    Y = grid_y[::step, ::step] - min_y
    Z = grid_z[::step, ::step]
    
    surf = ax_3d.plot_surface(X, Y, Z, cmap='terrain', edgecolor='none', alpha=0.9, antialiased=True, rcount=100, ccount=100)
    # Highlight pond location
    pond_x_rel = best_x - min_x
    pond_y_rel = best_y - min_y
    ax_3d.scatter([pond_x_rel], [pond_y_rel], [best_elev + 2], color='red', s=250, marker='*', edgecolors='black', label=f'Optimal Pond Location (Elev: {best_elev:.1f}m)')
    
    ax_3d.set_title("3D Digital Elevation Model with Optimal Pond Placement", fontsize=14, fontweight='bold', pad=20)
    ax_3d.set_xlabel("Easting (m)", labelpad=10)
    ax_3d.set_ylabel("Northing (m)", labelpad=10)
    ax_3d.set_zlabel("Elevation (m)", labelpad=10)
    ax_3d.view_init(elev=38, azim=-55)
    fig.colorbar(surf, ax=ax_3d, shrink=0.5, aspect=10, label='Elevation (m)')
    ax_3d.legend(loc='upper left')
    
    terrain_3d_path = os.path.join(output_dir, "terrain_3d_pond.png")
    fig.savefig(terrain_3d_path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {terrain_3d_path}")

    # ------------------ PLOT 3: Detailed Local Catchment Zoom ------------------
    fig, ax_zoom = plt.subplots(figsize=(10, 8), dpi=150)
    zoom_r_lo = max(0, best_r - 60)
    zoom_r_hi = min(rows, best_r + 60)
    zoom_c_lo = max(0, best_c - 60)
    zoom_c_hi = min(cols, best_c + 60)

    zoom_dem = grid_z[zoom_r_lo:zoom_r_hi, zoom_c_lo:zoom_c_hi]
    zoom_mask = catchment_mask[zoom_r_lo:zoom_r_hi, zoom_c_lo:zoom_c_hi]

    extent_zoom = [zoom_r_lo * grid_res, zoom_r_hi * grid_res, zoom_c_lo * grid_res, zoom_c_hi * grid_res]
    
    im_zoom = ax_zoom.imshow(zoom_dem.T, origin='lower', cmap='YlGnBu_r', extent=extent_zoom)
    # Contours in zoom area
    cs = ax_zoom.contour(zoom_dem.T, levels=15, colors='white', alpha=0.5, linewidths=0.8, extent=extent_zoom)
    ax_zoom.clabel(cs, inline=True, fontsize=8, fmt='%.1f m')
    
    # Catchment overlay
    ax_zoom.imshow(np.ma.masked_where(~zoom_mask.T, zoom_mask.T), origin='lower', cmap='autumn', alpha=0.55, extent=extent_zoom)
    
    ax_zoom.scatter([best_r * grid_res], [best_c * grid_res], color='blue', marker='*', s=350, edgecolors='white', linewidth=1.5, label=f'Pond Depression ({best_lat:.5f}N, {best_lon:.5f}E)\nCatchment Area: {catchment_size_pixels*4:.0f} m²', zorder=6)
    
    ax_zoom.set_title("Localized Zoom: Pond Basin & Inflow Catchment Contours", fontsize=13, fontweight='bold', pad=12)
    ax_zoom.set_xlabel("UTM Easting relative (m)")
    ax_zoom.set_ylabel("UTM Northing relative (m)")
    fig.colorbar(im_zoom, ax=ax_zoom, label='Elevation (m)')
    ax_zoom.legend(loc='lower right', framealpha=0.9)

    zoom_path = os.path.join(output_dir, "catchment_zoom_detail.png")
    fig.savefig(zoom_path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {zoom_path}")

    print("All visualizations created successfully!")

if __name__ == "__main__":
    generate_all_visualizations()
