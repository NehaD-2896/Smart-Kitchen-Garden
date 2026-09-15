"""
Quick local test tool: simulates all 4 sensor nodes posting readings to the
Flask server, without needing Wokwi or real ESP32 hardware running yet.

Usage:
    python simulate_nodes.py
    (make sure app.py is already running in another terminal)
"""

import random
import time
import requests

SERVER_URL = "http://127.0.0.1:5000/api/data"
NODE_IDS = ["node1", "node2", "node3", "node4"]


def fake_reading(node_id):
    return {
        "node_id": node_id,
        "soil_moisture": round(random.uniform(15, 60), 1),
        "tds": round(random.uniform(80, 900), 1),
        "temperature": round(random.uniform(22, 34), 1),
    }


def main():
    print(f"Sending simulated readings to {SERVER_URL} every 5s. Ctrl+C to stop.")
    while True:
        for node_id in NODE_IDS:
            payload = fake_reading(node_id)
            try:
                resp = requests.post(SERVER_URL, json=payload, timeout=5)
                print(f"{node_id}: sent {payload} -> {resp.json()}")
            except requests.RequestException as exc:
                print(f"{node_id}: failed to send ({exc})")
        time.sleep(5)


if __name__ == "__main__":
    main()
