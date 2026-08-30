import requests
import sys

def test_api():
    url = "http://127.0.0.1:8000/analyzeContour"
    file_path = "contours_1m.kml"
    
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, "application/vnd.google-earth.kml+xml")}
            print(f"Sending {file_path} to {url}...")
            response = requests.post(url, files=files)
            
        print(f"Status Code: {response.status_code}")
        try:
            print("Response JSON:")
            print(response.json())
        except:
            print("Response text:")
            print(response.text)
            
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"Failed to connect to {url}. Is the server running?")
        sys.exit(1)

if __name__ == "__main__":
    test_api()
