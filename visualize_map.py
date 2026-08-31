import requests
import sys
import webbrowser
import os

try:
    import folium
except ImportError:
    print("Installing folium...")
    os.system(f"{sys.executable} -m pip install folium")
    import folium

def visualize():
    url = "http://127.0.0.1:8000/analyzeContour"
    file_path = "contours_1m.kml"
    
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return
        
    print(f"Sending {file_path} to API...")
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, "application/vnd.google-earth.kml+xml")}
            response = requests.post(url, files=files)
            
        if response.status_code == 200:
            data = response.json()
            lat = data['pond_location']['latitude']
            lon = data['pond_location']['longitude']
            area = data['catchment_area_sqm']
            
            print(f"Success! Creating map at Lat: {lat}, Lon: {lon}")
            
            # Create a folium map centered on the pond
            m = folium.Map(location=[lat, lon], zoom_start=18)
            
            # Add Satellite imagery (Google Satellite) so we can see the terrain
            folium.TileLayer(
                tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                attr='Google',
                name='Google Satellite',
                overlay=False,
                control=True
            ).add_to(m)
            
            # Add a marker for the pond location
            popup_text = f"<b>Recommended Pond Location</b><br>Catchment Area: {area:,.0f} sqm"
            folium.Marker(
                [lat, lon],
                popup=popup_text,
                icon=folium.Icon(color="blue", icon="info-sign")
            ).add_to(m)
            
            folium.LayerControl().add_to(m)
            
            # Save the map to an HTML file
            map_file = "pond_map.html"
            m.save(map_file)
            
            # Open it automatically in the default web browser
            print(f"Map saved to {map_file}. Opening in browser...")
            webbrowser.open('file://' + os.path.realpath(map_file))
        else:
            print(f"Error from API: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print(f"Failed to connect to {url}. Is the FastAPI server running?")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    visualize()
