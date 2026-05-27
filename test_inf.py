import requests

# First get a valid device
devices = requests.get("http://127.0.0.1:8000/devices/")
device_id = None
if devices.status_code == 200 and len(devices.json()) > 0:
    device_id = devices.json()[0]['id']
else:
    device_id = "temp-device-id"

payload = {
    "device_id": device_id,
    "features": {
        "cpu": 80.0,
        "memory": 60.0,
        "network_in": 1000.0,
        "network_out": 500.0
    }
}

print(f"Sending to device: {device_id}")
print(f"Payload: {payload}")

try:
    r = requests.post("http://127.0.0.1:8000/monitor/ingest", json=payload)
    print(f"Status Code: {r.status_code}")
    print(f"Response: {r.text}")
except Exception as e:
    print(f"Error: {e}")
