import subprocess
import time
import requests
import os

with open("test_out.txt", "w") as f:
    f.write("Starting test...\n")

# Start uvicorn
server = subprocess.Popen(["uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"])
time.sleep(4)

try:
    with open("test_out.txt", "a") as f:
        # Get device
        try:
            d_res = requests.get("http://127.0.0.1:8000/devices/")
            f.write(f"Devices status: {d_res.status_code}\n")
            device_id = d_res.json()[0]['id']
        except Exception as e:
            f.write(f"Device error: {e}\n")
            device_id = "test"
            
        payload = {
            "device_id": device_id,
            "features": {
                "cpu": 80.0,
                "memory": 60.0,
                "network_in": 1000.0,
                "network_out": 500.0
            }
        }
        f.write(f"Testing inference...\n")
        try:
            r = requests.post("http://127.0.0.1:8000/monitor/ingest", json=payload)
            f.write(f"Status Code: {r.status_code}\n")
            f.write(f"Response: {r.text}\n")
        except Exception as e:
            f.write(f"Error: {e}\n")
finally:
    server.terminate()
    server.wait()
