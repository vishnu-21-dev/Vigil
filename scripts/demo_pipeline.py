import subprocess
import time
import requests
import json
import pandas as pd
import sys

def run_demo():
    print("starting uvicorn server...")
    server = subprocess.Popen(["uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    
    with open("demo_output.txt", "w") as f:
        try:
            # Create a device
            res = requests.post("http://127.0.0.1:8000/devices/", json={
                "name": "Test Device", "ip_address": "10.0.0.1", "zone": "Test"
            })
            device_id = res.json()["id"]
            
            f.write("\n--- TEST 1: The 'cpu/memory' Payload ---\n")
            payload1 = {
                "device_id": device_id,
                "features": {"cpu": 80.0, "memory": 60.0, "network_in": 1000.0, "network_out": 500.0}
            }
            res1 = requests.post("http://127.0.0.1:8000/monitor/ingest", json=payload1)
            f.write(f"Status Code: {res1.status_code}\n")
            f.write(f"Response: {res1.text[:200]}\n")
            
            f.write("\n--- TEST 2: The 'N-BaIoT' Benign CSV Payload ---\n")
            df_benign = pd.read_csv("data/1.benign.csv", nrows=1)
            payload2 = {
                "device_id": device_id,
                "features": df_benign.iloc[0].to_dict()
            }
            res2 = requests.post("http://127.0.0.1:8000/monitor/ingest", json=payload2)
            f.write(f"Status Code: {res2.status_code}\n")
            f.write(f"Response: {json.dumps(res2.json(), indent=2)}\n")

        except Exception as e:
            f.write(f"Exception: {e}\n")
        finally:
            server.terminate()
            server.wait()

if __name__ == "__main__":
    run_demo()
