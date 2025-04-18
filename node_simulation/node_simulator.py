from flask import Flask, jsonify, request
import threading
import requests
import time
import os
import json
import logging
import signal
import sys
import subprocess

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("node-simulator")

# Node configuration from environment variables
NODE_ID = os.environ.get("NODE_ID", "0")
NODE_NAME = os.environ.get("NODE_NAME", "node-simulator")
CPU_CORES = int(os.environ.get("CPU_CORES", "4"))
NODE_TYPE = os.environ.get("NODE_TYPE", "worker")
API_SERVER = os.environ.get("API_SERVER", "http://localhost:5000")

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
        "node_agent": "running",
    },
}

# If master node, add control plane components
if NODE_TYPE == "master":
    node_state["components"].update(
        {
            "api_server": "running",
            "scheduler": "running",
            "controller": "running",
            "etcd": "running",
        }
    )

# Heartbeat configuration
HEARTBEAT_INTERVAL = 60  # seconds

# Global dictionary to track processes
pod_processes = {}


def send_heartbeat():
    """Send heartbeat to API server"""
    # Add initial delay before first heartbeat to allow container to fully initialize
    initial_delay = 30  # 30 seconds initial delay
    time.sleep(initial_delay)

    while True:
        try:
            # Skip heartbeat if node ID is 0 (not yet assigned)
            if NODE_ID != "0":
                logger.info(
                    f"Sending heartbeat to API server: {API_SERVER}/nodes/{NODE_ID}/heartbeat"
                )
                response = requests.post(
                    f"{API_SERVER}/nodes/{NODE_ID}/heartbeat",
                    json={
                        "pod_ids": node_state["pod_ids"],
                        "cpu_cores_avail": node_state["cpu_cores_avail"],
                        "health_status": node_state["health_status"],
                        "components": node_state["components"],
                    },
                    timeout=5,
                )
                if response.status_code == 200:
                    logger.info("Heartbeat acknowledged")
                else:
                    logger.error(
                        f"Heartbeat failed with status {response.status_code}: {response.text}"
                    )
            else:
                logger.info("Skipping heartbeat - node ID not yet assigned")
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
        logger.info(
            f"Added pod {pod_id} to node. Available CPU: {node_state['cpu_cores_avail']}"
        )

    return (
        jsonify(
            {"message": f"Pod {pod_id} added to node {NODE_NAME}", "pod_id": pod_id}
        ),
        200,
    )


@app.route("/pods/<pod_id>", methods=["DELETE"])
def remove_pod(pod_id):
    """Remove a pod from this node"""
    str_pod_id = str(pod_id)

    # Check if pod exists
    if str_pod_id not in pod_processes:
        return jsonify({"error": f"Pod {pod_id} not found on this node"}), 404

    # Get CPU cores to return
    try:
        pod_spec = pod_processes[str_pod_id]["spec"]
        cpu_cores_req = pod_spec.get("cpu_cores_req", 1)
    except:
        cpu_cores_req = 1

    # Terminate all processes in the pod
    for container in pod_processes[str_pod_id]["processes"]:
        try:
            if container.get("process"):
                container["process"].terminate()
                try:
                    container["process"].wait(timeout=5)
                except:
                    # Force kill if termination times out
                    container["process"].kill()

            logger.info(f"Terminated process for container {container['name']}")
        except Exception as e:
            logger.error(f"Error terminating container {container['name']}: {str(e)}")

    # Clean up pod directory
    try:
        import shutil

        pod_dir = pod_processes[str_pod_id]["directory"]
        shutil.rmtree(pod_dir, ignore_errors=True)
    except Exception as e:
        logger.error(f"Error removing pod directory: {str(e)}")

    # Remove pod from tracking
    del pod_processes[str_pod_id]

    # Update node state
    if pod_id in node_state["pod_ids"]:
        node_state["pod_ids"].remove(pod_id)

    node_state["cpu_cores_avail"] += cpu_cores_req

    logger.info(
        f"Removed pod {pod_id} from node. Available CPU: {node_state['cpu_cores_avail']}"
    )

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


@app.route("/run_pod", methods=["POST"])
def run_pod():
    """Run a pod as one or more processes inside this node container"""
    data = request.get_json()
    pod_id = data.get("pod_id")
    pod_spec = data.get("pod_spec")

    if not pod_id or not pod_spec:
        return jsonify({"error": "Missing pod_id or pod_spec"}), 400

    # Check if we have enough resources
    cpu_cores_req = pod_spec.get("cpu_cores_req", 1)
    if node_state["cpu_cores_avail"] < cpu_cores_req:
        return jsonify({"error": "Insufficient CPU resources"}), 400

    # Create a unique working directory for the pod
    pod_dir = f"/tmp/pod-{pod_id}"
    os.makedirs(pod_dir, exist_ok=True)

    # Start processes for each container in the pod
    processes = []
    pod_status = {"containers": []}

    for container_spec in pod_spec.get("containers", []):
        container_name = container_spec.get("name", f"container-{pod_id}")
        container_id = f"{pod_id}-{container_name}"
        image = container_spec.get("image", "busybox")
        command = container_spec.get("command", "sleep infinity")

        # Prepare environment variables
        env_vars = os.environ.copy()
        for key, value in pod_spec.get("environment", {}).items():
            env_vars[key] = value

        # Add container-specific environment variables
        env_vars["CONTAINER_NAME"] = container_name
        env_vars["POD_ID"] = str(pod_id)
        env_vars["POD_IP"] = pod_spec.get("ip_address", "10.244.0.1")

        # Create log file for the container
        log_file = open(f"{pod_dir}/{container_name}.log", "w")

        try:
            logger.info(f"Starting container {container_name} with command: {command}")

            # Choose process behavior based on simulated image
            if "nginx" in image:
                process_thread = threading.Thread(
                    target=simulate_container,
                    args=(container_name, "nginx", pod_dir, log_file, env_vars),
                )
                process_thread.daemon = True
                process_thread.start()

                container_status = "running"

            elif "redis" in image:
                process_thread = threading.Thread(
                    target=simulate_container,
                    args=(container_name, "redis", pod_dir, log_file, env_vars),
                )
                process_thread.daemon = True
                process_thread.start()

                container_status = "running"

            else:
                # For other images, just run sleep to simulate a process
                proc = subprocess.Popen(
                    ["sleep", "infinity"],
                    stdout=log_file,
                    stderr=log_file,
                    env=env_vars,
                )
                process_thread = None
                container_status = "running"

            # Store process information
            process_info = {
                "process": proc if "proc" in locals() else None,
                "thread": process_thread,
                "name": container_name,
                "image": image,
                "start_time": time.time(),
                "status": container_status,
                "log_file": log_file.name,
            }

            pod_status["containers"].append(
                {"name": container_name, "image": image, "status": container_status}
            )

            processes.append(process_info)
            logger.info(f"Container {container_name} started")

        except Exception as e:
            logger.error(f"Failed to start container {container_name}: {str(e)}")
            log_file.write(f"Error starting container: {str(e)}\n")
            log_file.close()

            # Clean up any processes we already started
            for p in processes:
                try:
                    if p.get("process"):
                        p["process"].terminate()
                    if p.get("thread") and p["thread"].is_alive():
                        pass  # Can't easily terminate threads
                except:
                    pass

            return jsonify(
                {"error": f"Failed to start container {container_name}: {str(e)}"}
            ), 500

    # Store pod information
    pod_processes[str(pod_id)] = {
        "processes": processes,
        "spec": pod_spec,
        "status": "running",
        "start_time": time.time(),
        "directory": pod_dir,
    }

    # Add pod to node's list and update resources
    if pod_id not in node_state["pod_ids"]:
        node_state["pod_ids"].append(pod_id)

    node_state["cpu_cores_avail"] -= cpu_cores_req

    return (
        jsonify(
            {
                "status": "success",
                "message": f"Pod {pod_id} started with {len(processes)} containers",
                "pod_status": pod_status,
            }
        ),
        200,
    )


def simulate_container(container_name, container_type, pod_dir, log_file, env_vars):
    """Simulate container process behavior"""
    try:
        # Write startup message
        log_file.write(f"Starting {container_type} container simulation\n")
        log_file.flush()

        # Simulate running container
        while True:
            # Write periodic message to simulate activity
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_file.write(f"[{timestamp}] {container_type} simulation heartbeat\n")
            log_file.flush()

            # Different simulated behavior based on container type
            if container_type == "nginx":
                log_file.write(
                    f"[{timestamp}] Simulated nginx: Handling HTTP request\n"
                )
            elif container_type == "redis":
                log_file.write(f"[{timestamp}] Simulated redis: Cache operation\n")

            time.sleep(10)
    except Exception as e:
        log_file.write(f"Error in container simulation: {str(e)}\n")
    finally:
        log_file.write("Container simulation terminated\n")
        log_file.close()


@app.route("/pods/<pod_id>/status", methods=["GET"])
def get_pod_status(pod_id):
    """Get status of a pod's processes"""
    str_pod_id = str(pod_id)

    if str_pod_id not in pod_processes:
        return jsonify({"error": f"Pod {pod_id} not found on this node"}), 404

    pod = pod_processes[str_pod_id]
    containers = []
    all_running = True

    for container in pod["processes"]:
        # Check if process is still running
        is_running = True

        if container.get("process"):
            is_running = container["process"].poll() is None

        status = "running" if is_running else "exited"
        all_running = all_running and is_running

        containers.append(
            {
                "name": container["name"],
                "image": container["image"],
                "status": status,
                "start_time": container["start_time"],
            }
        )

    overall_status = "running" if all_running else "failed"

    return (
        jsonify(
            {"pod_id": pod_id, "status": overall_status, "containers": containers}
        ),
        200,
    )


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
