from flask import Blueprint, request, jsonify
from models import data, Pod, Node

pods_bp = Blueprint("pods", __name__)


# Add a pod
@pods_bp.route("/pods", methods=["POST"])
def add_pod():
    req_data = request.get_json()
    name = req_data.get("name")
    cpu_cores_req = req_data.get("cpu_cores_req")

    if not name:
        return jsonify({"error": "Name is missing or incorrect"}), 400
    elif not cpu_cores_req:
        return jsonify({"error": "cpu_cores_req is missing or incorrect"}), 400

    # this finds a node with enough cores
    node = Node.query.filter(
        Node.cpu_cores_avail >= cpu_cores_req, Node.health_status == "healthy"
    ).first()

    if not node:
        return (
            jsonify({"error": "No available node found with enough CPU resources"}),
            400,
        )

    # makes teh pod if node is found with enough cores
    new_pod = Pod(
        name=name, cpu_cores_req=cpu_cores_req, node_id=node.id, health_status="running"
    )
    data.session.add(new_pod)

    # Reduce available CPU on the node for the next pod creation
    node.cpu_cores_avail -= cpu_cores_req

    data.session.commit()

    return (
        jsonify(
            {"message": f"Pod '{name}' assigned to node '{node.name}' successfully!"}
        ),
        200,
    )


# List all pods
@pods_bp.route("/pods", methods=["GET"])
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
