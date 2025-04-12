from flask import Flask, jsonify
import threading
import time
import requests
import signal
import sys

app = Flask(__name__)

node_state = {"name": "node-1", "cpu_cores_avail": 4, "health_status": "healthy"}

# Standardized timing interval
HEARTBEAT_INTERVAL = 10  # seconds


@app.route("/", methods=["GET"])
def home():
    return "Kube-9 Node Simulator is running!"


@app.route("/status", methods=["GET"])
def status():
    return jsonify(node_state)


@app.route("/simulate_failure", methods=["POST"])
def simulate_failure():
    node_state["health_status"] = "unhealthy"
    return jsonify({"msg": "Node marked unhealthy"})


def send_heartbeats():
    while True:
        try:
            requests.post("http://localhost:5000/nodes/1/heartbeat")
            time.sleep(HEARTBEAT_INTERVAL)
        except Exception as e:
            print(f"Heartbeat failed: {str(e)}")


def graceful_exit(signal, frame):
    print("\nShutting down Kube-9 Node Simulator...")
    sys.exit(0)


signal.signal(signal.SIGINT, graceful_exit)

heartbeat_thread = threading.Thread(target=send_heartbeats)
heartbeat_thread.daemon = True
heartbeat_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
