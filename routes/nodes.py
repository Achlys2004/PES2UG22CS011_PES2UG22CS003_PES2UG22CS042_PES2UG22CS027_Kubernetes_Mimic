from flask import Blueprint, request, jsonify
from models import data, Node
from datetime import datetime
nodes_bp = Blueprint("nodes", __name__)


# To add a new node
@nodes_bp.route("/", methods=["POST"])
def add_node():
    payload = request.get_json()
    name = payload.get("name")
    cpu_cores_avail = payload.get("cpu_cores_avail")
    node_type = payload.get("node_type", "worker") 

    if not name:
        return jsonify({"error": "Name is missing or incorrect"}), 400
    elif not cpu_cores_avail:
        return jsonify({"error": "Cpu core count is missing or incorrect"}), 400

    if node_type not in ["master", "worker"]:
        return jsonify({"error": "Node type must be either 'master' or 'worker'"}), 400

    new_node = Node(
        name=name,
        cpu_cores_avail=cpu_cores_avail,
        node_type=node_type,
        kubelet_status="running",
        container_runtime_status="running",
        kube_proxy_status="running",
        node_agent_status="running",
    )

    # Initialize master node components if applicable
    if node_type == "master":
        new_node.api_server_status = "running"
        new_node.scheduler_status = "running"
        new_node.controller_status = "running"
        new_node.etcd_status = "running"

    data.session.add(new_node)
    data.session.commit()

    return (
        jsonify({"message": f"{node_type.capitalize()} node added successfully!"}),
        200,
    )


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
def receive_heartbeat(node_id):
    node = Node.query.get(node_id)
    if not node:
        return jsonify({"status": "error", "message": "Node not found"}), 404
    
    node.last_heartbeat = datetime.utcnow()
    data.session.commit()
    
    return (
        jsonify(
            {
            "status": "success",
            "message": "Heartbeat received",
            "next_heartbeat_in": node.heartbeat_interval
            }
        ), 
        200,
    )