from flask import Flask, jsonify, request
import threading
import requests
import time
import os
import json
import logging
import signal
import sys

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("node-simulator")

# Node configuration from environment variables
NODE_ID = os.environ.get('NODE_ID', '0')
NODE_NAME = os.environ.get('NODE_NAME', 'node-simulator')
CPU_CORES = int(os.environ.get('CPU_CORES', '4'))
NODE_TYPE = os.environ.get('NODE_TYPE', 'worker')
API_SERVER = os.environ.get('API_SERVER', 'http://localhost:5000')

# Node state
node_state = {
    "id": NODE_ID,
    "name": NODE_NAME,
    "node_type": NODE_TYPE,
    "cpu_cores_total": CPU_CORES,
    "cpu_cores_avail": CPU_CORES,
    "health_status": "healthy",
    "pod_ids": [],
    "components": {
        "kubelet": "running",
        "container_runtime": "running",
        "kube_proxy": "running", 
        "node_agent": "running"
    }
}

# If master node, add control plane components
if NODE_TYPE == "master":
    node_state["components"].update({
        "api_server": "running",
        "scheduler": "running",
        "controller": "running",
        "etcd": "running"
    })

# Heartbeat configuration
HEARTBEAT_INTERVAL = 60  # seconds

def send_heartbeat():
    """Send heartbeat to API server"""
    while True:
        try:
            logger.info(f"Sending heartbeat to API server: {API_SERVER}/nodes/{NODE_ID}/heartbeat")
            response = requests.post(
                f"{API_SERVER}/nodes/{NODE_ID}/heartbeat",
                json={
                    "pod_ids": node_state["pod_ids"],
                    "cpu_cores_avail": node_state["cpu_cores_avail"],
                    "health_status": node_state["health_status"],
                    "components": node_state["components"]
                },
                timeout=5
            )
            if response.status_code == 200:
                logger.info("Heartbeat acknowledged")
            else:
                logger.error(f"Heartbeat failed with status {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Error sending heartbeat: {str(e)}")
        
        # Sleep until next heartbeat interval
        time.sleep(HEARTBEAT_INTERVAL)

@app.route("/", methods=["GET"])
def home():
    return "Kube-9 Node Simulator is running!"

@app.route("/status", methods=["GET"])
def status():
    return jsonify(node_state)

@app.route("/api/update_node_id", methods=["POST"])
def update_node_id():
    """Update node ID after database registration"""
    data = request.get_json()
    if "node_id" in data:
        global NODE_ID
        NODE_ID = str(data["node_id"])
        node_state["id"] = NODE_ID
        logger.info(f"Updated node ID to {NODE_ID}")
        return jsonify({"message": f"Node ID updated to {NODE_ID}"}), 200
    else:
        return jsonify({"error": "Missing node_id"}), 400

@app.route("/pods", methods=["GET"])
def get_pods():
    return jsonify({"pod_ids": node_state["pod_ids"]})

@app.route("/pods", methods=["POST"])
def add_pod():
    """Add a pod to this node"""
    data = request.get_json()
    pod_id = data.get("pod_id")
    cpu_cores_req = data.get("cpu_cores_req", 1)
    
    # Validate input
    if not pod_id:
        return jsonify({"error": "Missing pod_id"}), 400
        
    # Check resource availability
    if node_state["cpu_cores_avail"] < cpu_cores_req:
        return jsonify({"error": "Insufficient CPU resources"}), 400
    
    # Add pod to node
    if pod_id not in node_state["pod_ids"]:
        node_state["pod_ids"].append(pod_id)
        node_state["cpu_cores_avail"] -= cpu_cores_req
        logger.info(f"Added pod {pod_id} to node. Available CPU: {node_state['cpu_cores_avail']}")
        
    return jsonify({"message": f"Pod {pod_id} added to node {NODE_NAME}", "pod_id": pod_id}), 200

@app.route("/pods/<pod_id>", methods=["DELETE"])
def remove_pod(pod_id):
    """Remove a pod from this node"""
    if pod_id not in node_state["pod_ids"]:
        return jsonify({"error": "Pod not found on this node"}), 404
        
    # Get CPU cores to return
    try:
        response = requests.get(f"{API_SERVER}/pods/{pod_id}")
        if response.status_code == 200:
            pod_data = response.json()
            cpu_cores_req = pod_data.get("cpu_cores_req", 1)
        else:
            # Default if pod information can't be retrieved
            cpu_cores_req = 1
    except Exception:
        cpu_cores_req = 1
    
    # Remove pod from node
    node_state["pod_ids"].remove(pod_id)
    node_state["cpu_cores_avail"] += cpu_cores_req
    logger.info(f"Removed pod {pod_id} from node. Available CPU: {node_state['cpu_cores_avail']}")
    
    return jsonify({"message": f"Pod {pod_id} removed from node {NODE_NAME}"}), 200

@app.route("/components/<component>", methods=["PATCH"])
def update_component(component):
    """Update component status"""
    data = request.get_json()
    status = data.get("status")
    
    if not status:
        return jsonify({"error": "Missing status"}), 400
        
    if component in node_state["components"]:
        node_state["components"][component] = status
        logger.info(f"Updated {component} status to {status}")
        return jsonify({"message": f"{component} status updated to {status}"}), 200
    else:
        return jsonify({"error": f"Component {component} not found"}), 404

@app.route("/simulate/failure", methods=["POST"])
def simulate_failure():
    """Simulate node failure"""
    node_state["health_status"] = "failed"
    logger.warning("Node failure simulated!")
    return jsonify({"message": "Node failure simulated"}), 200

@app.route("/simulate/recovery", methods=["POST"])
def simulate_recovery():
    """Simulate node recovery"""
    node_state["health_status"] = "healthy"
    logger.info("Node recovery simulated!")
    return jsonify({"message": "Node recovery simulated"}), 200

def graceful_shutdown(sig, frame):
    """Handle graceful shutdown"""
    logger.info("Shutting down node simulator...")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

# Start heartbeat thread
heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)

if __name__ == "__main__":
    # Start heartbeat thread
    heartbeat_thread.start()
    logger.info(f"Node simulator starting: {NODE_NAME} (ID: {NODE_ID})")
    logger.info(f"CPU Cores: {CPU_CORES}, Type: {NODE_TYPE}")
    logger.info(f"API Server: {API_SERVER}")
    logger.info(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
    
    # Run Flask app
    app.run(host="0.0.0.0", port=5000)