from flask import Blueprint, request, jsonify
from models import data, Pod, Node

pods_bp = Blueprint("pods", __name__)

# Add a pod
@pods_bp.route("/", methods=["POST"])
def add_pod():
    req_data = request.get_json()
    name = req_data.get("name")
    cpu_cores_req = req_data.get("cpu_cores_req")

    if not name:
        return jsonify({"error": "Name is missing or incorrect"}), 400
    elif not cpu_cores_req:
        return jsonify({"error": "cpu_cores_req is missing or incorrect"}), 400

    # Find a node with enough available cores
    node = Node.query.filter(
        Node.cpu_cores_avail >= cpu_cores_req, Node.health_status == "healthy"
    ).first()

    if not node:
        return (
            jsonify({"error": "No available node found with enough CPU resources"}),
            400,
        )

    # Create the pod
    new_pod = Pod(
        name=name, cpu_cores_req=cpu_cores_req, node_id=node.id, health_status="running"
    )
    data.session.add(new_pod)

    # Reduce available CPU on the node
    node.cpu_cores_avail -= cpu_cores_req

    data.session.commit()

    return (
        jsonify(
            {"message": f"Pod '{name}' assigned to node '{node.name}' successfully!"}
        ),
        200,
    )

# List all pods
@pods_bp.route("/", methods=["GET"])
def list_pods():
    pods = Pod.query.all()
    result = [
        {
            "id": pod.id,
            "name": pod.name,
            "cpu_cores_req": pod.cpu_cores_req,
            "node_id": pod.node_id,
            "health_status": pod.health_status,
        }
        for pod in pods
    ]
    return jsonify(result), 200

# Delete a pod
@pods_bp.route("/<int:pod_id>", methods=["DELETE"])
def delete_pod(pod_id):
    pod = Pod.query.get(pod_id)
    
    if not pod:
        return jsonify({"error": "Pod not found"}), 404

    node = Node.query.get(pod.node_id)

    # Free up CPU resources on the node
    if node:
        node.cpu_cores_avail += pod.cpu_cores_req

        # Check if the node becomes idle
        if not Pod.query.filter_by(node_id=node.id).count():
            node.health_status = "idle"

    # Delete the pod
    data.session.delete(pod)
    data.session.commit()

    return jsonify({"message": f"Pod {pod_id} deleted successfully"}), 200
