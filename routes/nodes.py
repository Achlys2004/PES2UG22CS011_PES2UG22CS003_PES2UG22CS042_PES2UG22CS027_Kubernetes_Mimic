from platform import node
from flask import Blueprint, request, jsonify
from models import data, Node

nodes_bp = Blueprint("nodes", __name__)


# To add a new node
@nodes_bp.route("/", methods=["POST"])
def add_node():
    payload = request.get_json()
    name = payload.get("name")
    cpu_cores_avail = payload.get("cpu_cores_avail")

    if not name:
        return jsonify({"error": "Name is missing or incorrect"}), 400
    elif not cpu_cores_avail:
        return jsonify({"error": "Cpu core count is missing or incorrect"}), 400

    new_node = Node(name=name, cpu_cores_avail=cpu_cores_avail)
    data.session.add(new_node)
    data.session.commit()

    return jsonify({"message": "Node added Successfully!"}), 200


# To list all nodes
@nodes_bp.route("/", methods=["GET"])
def list_all_nodes():
    nodes = Node.query.all()
    nodes_list = [
        {
            "id": node.id,
            "name": node.name,
            "cpu_cores_avail": node.cpu_cores_avail,
            "health_status": node.health_status,
        }
        for node in nodes
    ]
    return jsonify(nodes_list), 200
