from flask import Blueprint, request, jsonify
from models import data, Pod

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

    new_pod = Pod(name=name, cpu_cores_req=cpu_cores_req)
    data.session.add(new_pod)
    data.session.commit()

    return jsonify({"message": "Pod added successfully!"}), 200


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
            "status": pod.status,
        }
        for pod in pods
    ]
    return jsonify(result), 200
