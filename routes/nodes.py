from flask import Blueprint, request, jsonify
from models import data, Node
from datetime import datetime, timezone
from flask import current_app
import threading
import time
import requests

HEARTBEAT_INTERVAL = 60  # Interval in seconds for sending heartbeats

nodes_bp = Blueprint("nodes", __name__)


# To add a new node
@nodes_bp.route("/", methods=["POST"])
def create_node():
    payload = request.get_json()

    node = Node(
        name=payload["name"],
        node_type=payload.get("node_type", "worker"),
        cpu_cores_avail=payload["cpu_cores_avail"],
        health_status="healthy",
        last_heartbeat=datetime.now(timezone.utc),
    )

    data.session.add(node)
    data.session.commit()

    return jsonify({"id": node.id, "name": node.name}), 200


# To list all nodes
@nodes_bp.route("/", methods=["GET"])
def list_all_nodes():
    nodes = Node.query.all()
    nodes_list = []

    for node in nodes:
        node_data = {
            "id": node.id,
            "name": node.name,
            "node_type": node.node_type,
            "cpu_cores_avail": node.cpu_cores_avail,
            "health_status": node.health_status,
            "components": {
                "kubelet": node.kubelet_status,
                "container_runtime": node.container_runtime_status,
                "kube_proxy": node.kube_proxy_status,
                "node_agent": node.node_agent_status,
            },
        }

        # Master node
        if node.node_type == "master":
            node_data["components"].update(
                {
                    "api_server": node.api_server_status,
                    "scheduler": node.scheduler_status,
                    "controller": node.controller_status,
                    "etcd": node.etcd_status,
                }
            )

        nodes_list.append(node_data)

    return jsonify(nodes_list), 200


@nodes_bp.route("/health", methods=["GET"])
def get_nodes_health():
    nodes = Node.query.all()
    health_report = []
    for node in nodes:
        node_report = {
            "node_id": node.id,
            "node_name": node.name,
            "node_type": node.node_type,
            "health_status": node.health_status,
            "pods_count": len(node.pods),
            "component_status": {
                "kubelet": node.kubelet_status,
                "container_runtime": node.container_runtime_status,
                "kube_proxy": node.kube_proxy_status,
                "node_agent": node.node_agent_status,
            },
        }

        if node.node_type == "master":
            node_report["component_status"].update(
                {
                    "api_server": node.api_server_status,
                    "scheduler": node.scheduler_status,
                    "controller_manager": node.controller_status,
                    "etcd": node.etcd_status,
                }
            )

        health_report.append(node_report)

    return jsonify(health_report), 200


@nodes_bp.route("/<int:node_id>/health", methods=["PATCH"])
def update_node_health(node_id):
    payload = request.get_json()
    new_status = payload.get("health_status")

    if new_status not in ["healthy", "failed"]:
        return jsonify({"status": "error", "message": "Invalid health status"}), 400

    node = Node.query.get(node_id)
    if not node:
        return jsonify({"status": "error", "message": "Node not found"}), 404

    node.health_status = new_status
    data.session.commit()

    return (
        jsonify(
            {
                "message": f"Node {node_id} health updated to {new_status}",
                "data": {
                    "node_id": node.id,
                    "node_name": node.name,
                    "node_type": node.node_type,
                    "health_status": node.health_status,
                },
            }
        ),
        200,
    )


@nodes_bp.route("/<int:node_id>/components", methods=["PATCH"])
def update_component_status(node_id):
    payload = request.get_json()
    component_name = payload.get("component")
    new_status = payload.get("status")

    if new_status not in ["running", "stopped", "failed"]:
        return jsonify({"status": "error", "message": "Invalid component status"}), 400

    node = Node.query.get(node_id)
    if not node:
        return jsonify({"status": "error", "message": "Node not found"}), 404

    # Map of valid components for each node type
    valid_components = {
        "worker": ["kubelet", "container_runtime", "kube_proxy", "node_agent"],
        "master": [
            "kubelet",
            "container_runtime",
            "kube_proxy",
            "node_agent",
            "api_server",
            "scheduler",
            "controller",
            "etcd",
        ],
    }

    # Check if the component is valid for this node type
    node_type = node.node_type
    if component_name not in valid_components.get(node_type, []):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Invalid component for {node_type} node. Valid components: {', '.join(valid_components.get(node_type, []))}",
                }
            ),
            400,
        )

    # Update the component status
    if component_name == "kubelet":
        node.kubelet_status = new_status
    elif component_name == "container_runtime":
        node.container_runtime_status = new_status
    elif component_name == "kube_proxy":
        node.kube_proxy_status = new_status
    elif component_name == "node_agent":
        node.node_agent_status = new_status
    elif component_name == "api_server":
        node.api_server_status = new_status
    elif component_name == "scheduler":
        node.scheduler_status = new_status
    elif component_name == "controller":
        node.controller_status = new_status
    elif component_name == "etcd":
        node.etcd_status = new_status

    data.session.commit()

    return (
        jsonify(
            {
                "message": f"Component {component_name} on node {node.name} updated to {new_status}",
                "node_id": node.id,
                "node_name": node.name,
                "node_type": node.node_type,
                "component": component_name,
                "status": new_status,
            }
        ),
        200,
    )


@nodes_bp.route("/<int:node_id>/heartbeat", methods=["POST"])
def update_node_heartbeat(node_id):
    try:
        node = Node.query.get_or_404(node_id)
        node.update_heartbeat()
        data.session.commit()
        current_app.logger.info(
            f"Heartbeat successfully updated for Node {node.name} (ID: {node.id})"
        )
        return jsonify({"message": "Heartbeat updated successfully"})
    except Exception as e:
        current_app.logger.error(
            f"Error updating heartbeat for Node {node_id}: {str(e)}"
        )
        data.session.rollback()
        return jsonify({"error": str(e)}), 500


@nodes_bp.route("/<int:node_id>", methods=["GET"])
def get_node(node_id):
    node = Node.query.get(node_id)
    if not node:
        return jsonify({"error": "Node not found"}), 404
    return (
        jsonify(
            {
                "id": node.id,
                "last_heartbeat": node.last_heartbeat,
                "health_status": node.health_status,
            }
        ),
        200,
    )


@nodes_bp.route("/<int:node_id>/thresholds", methods=["PATCH"])
def update_node_thresholds(node_id):
    payload = request.get_json()
    max_heartbeat_interval = payload.get("max_heartbeat_interval")
    heartbeat_interval = payload.get("heartbeat_interval")
    max_recovery_attempts = payload.get("max_recovery_attempts")

    node = Node.query.get(node_id)
    if not node:
        return jsonify({"status": "error", "message": "Node not found"}), 404

    if max_heartbeat_interval is not None:
        if not isinstance(max_heartbeat_interval, int) or max_heartbeat_interval < 30:
            return (
                jsonify(
                    {"status": "error", "message": "Invalid max_heartbeat_interval"}
                ),
                400,
            )
        node.max_heartbeat_interval = max_heartbeat_interval

    if heartbeat_interval is not None:
        if not isinstance(heartbeat_interval, int) or heartbeat_interval < 10:
            return (
                jsonify({"status": "error", "message": "Invalid heartbeat_interval"}),
                400,
            )
        node.heartbeat_interval = heartbeat_interval

    if max_recovery_attempts is not None:
        if not isinstance(max_recovery_attempts, int) or max_recovery_attempts < 1:
            return (
                jsonify(
                    {"status": "error", "message": "Invalid max_recovery_attempts"}
                ),
                400,
            )
        node.max_recovery_attempts = max_recovery_attempts

    data.session.commit()

    return (
        jsonify(
            {
                "message": "Node thresholds updated successfully",
                "node_id": node.id,
                "thresholds": {
                    "heartbeat_interval": node.heartbeat_interval,
                    "max_heartbeat_interval": node.max_heartbeat_interval,
                    "max_recovery_attempts": node.max_recovery_attempts,
                },
            }
        ),
        200,
    )


def send_heartbeats(app):
    """Send heartbeat checks for all nodes in the system."""
    while True:
        last_run = time.time()
        try:
            with app.app_context():
                nodes = Node.query.all()  # Send to ALL nodes
                for node in nodes:
                    try:
                        response = requests.post(
                            f"http://localhost:5000/nodes/{node.id}/heartbeat"
                        )
                        if response.status_code == 200:
                            app.logger.info(
                                f"Heartbeat sent for Node {node.name} (ID: {node.id})"
                            )
                    except requests.exceptions.RequestException as e:
                        app.logger.error(f"Request failed for node {node.id}: {str(e)}")
        except Exception as e:
            print(f"Error sending heartbeats: {str(e)}")

        # Maintain consistent interval
        elapsed = time.time() - last_run
        sleep_time = max(0.1, HEARTBEAT_INTERVAL - elapsed)
        time.sleep(sleep_time)


def init_heartbeat_thread(app):
    """Initialize the heartbeat thread with app context"""
    thread = threading.Thread(target=send_heartbeats, args=(app,))
    thread.daemon = True
    thread.start()
    return thread


def init_routes(app):
    """Initialize routes and start heartbeat thread"""
    global heartbeat_thread
    heartbeat_thread = init_heartbeat_thread(app)
