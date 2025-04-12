from flask import Flask, jsonify
import signal
import sys

app = Flask(__name__)

node_state = {"name": "node-1", "cpu_cores_avail": 4, "health_status": "healthy"}

HEARTBEAT_INTERVAL = 60  # seconds (was 10 seconds)


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


def graceful_exit(signal, frame):
    print("\nShutting down Kube-9 Node Simulator...")
    sys.exit(0)


signal.signal(signal.SIGINT, graceful_exit)

if __name__ == "__main__":
    print(
        f"Node simulator starting. Heartbeats handled by central service."
    )
    app.run(host="0.0.0.0", port=5000)
