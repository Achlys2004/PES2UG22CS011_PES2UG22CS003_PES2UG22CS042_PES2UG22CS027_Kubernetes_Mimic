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

@nodes_bp.route('/health', methods=['GET'])
def get_nodes_health():
    nodes = Node.query.all()
    health_report = []
    for node in nodes:
        health_report.append({
            'node_id': node.id,
            'node_name': node.name,
            'health_status': node.health_status,
            'pods_count': len(node.pods)
        }) 
    return jsonify(health_report), 200

@nodes_bp.route('/<int:node_id>/health', methods=['PATCH'])
def update_node_health(node_id):
    data = request.get_json()
    new_status = data.get('health_status')
        
    if new_status not in ['healthy', 'failed']:
        return jsonify({
            'status': 'error',
        }), 400
            
    node = Node.query.get(node_id)
    if not node:
        return jsonify({
            'status': 'error',
        }), 404
            
    node.health_status = new_status
    data.session.commit()
        
    return jsonify({
        'message': f'Node {node_id} health updated to {new_status}',
        'data': {
            'node_id': node.id,
            'node_name': node.name,
            'health_status': node.health_status
        }
    }), 200
        