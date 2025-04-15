from flask import Blueprint, request, jsonify, current_app
from models import data, Node
from services.docker_service import DockerService
from datetime import datetime, timezone
import threading
import time
import requests
import logging

nodes_bp = Blueprint("nodes", __name__)
docker_service = DockerService()

# Heartbeat settings
HEARTBEAT_INTERVAL = 60  # seconds
heartbeat_thread = None

@nodes_bp.route("/", methods=["POST"])
def create_node():
    """Create a new node with Docker container simulation"""
    try:
        payload = request.get_json()
        
        # Validate input
        if not payload.get("name"):
            return jsonify({"error": "Node name is required"}), 400
        if not payload.get("cpu_cores_avail") or payload["cpu_cores_avail"] <= 0:
            return jsonify({"error": "CPU cores must be a positive number"}), 400
            
        node_type = payload.get("node_type", "worker").lower()
        if node_type not in ["worker", "master"]:
            return jsonify({"error": "Node type must be 'worker' or 'master'"}), 400
            
        # Create node container
        node_container = docker_service.create_node_container(
            node_id=0,  # Temporary ID, will update after DB insert
            node_name=payload["name"],
            cpu_cores=payload["cpu_cores_avail"],
            node_type=node_type
        )
        
        # Create node in database
        node = Node(
            name=payload["name"],
            node_type=node_type,
            cpu_cores_avail=payload["cpu_cores_avail"],
            cpu_cores_total=payload["cpu_cores_avail"],
            health_status="initializing",
            docker_container_id=node_container["container_id"],
            node_ip=node_container["node_ip"],
            node_port=node_container["node_port"],
            last_heartbeat=datetime.now(timezone.utc)
        )
        
        data.session.add(node)
        data.session.commit()
        
        # Update the container with the correct node ID
        requests.post(
            f"http://{node_container['node_ip']}:5000/api/update_node_id",
            json={"node_id": node.id},
            timeout=5
        )
        
        return jsonify({
            "id": node.id,
            "name": node.name,
            "node_type": node.node_type,
            "cpu_cores": node.cpu_cores_avail,
            "status": node.health_status,
            "container_id": node.docker_container_id,
            "node_ip": node.node_ip
        }), 201
    
    except Exception as e:
        current_app.logger.error(f"Error creating node: {str(e)}")
        data.session.rollback()
        return jsonify({"error": f"Failed to create node: {str(e)}"}), 500

@nodes_bp.route("/", methods=["GET"])
def list_all_nodes():
    """List all nodes in the cluster"""
    nodes = Node.query.all()
    nodes_list = []

    for node in nodes:
        node_data = {
            "id": node.id,
            "name": node.name,
            "node_type": node.node_type,
            "cpu_cores_total": node.cpu_cores_total,
            "cpu_cores_avail": node.cpu_cores_avail,
            "health_status": node.health_status,
            "hosted_pods": len(node.pod_ids),
            "components": {
                "kubelet": node.kubelet_status,
                "container_runtime": node.container_runtime_status,
                "kube_proxy": node.kube_proxy_status,
                "node_agent": node.node_agent_status,
            },
        }

        # Master node components
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
    """Get health status of all nodes"""
    nodes = Node.query.all()
    health_report = []
    for node in nodes:
        node_report = {
            "node_id": node.id,
            "node_name": node.name,
            "node_type": node.node_type,
            "health_status": node.health_status,
            "pods_count": len(node.pod_ids),
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

@nodes_bp.route("/<int:node_id>/heartbeat", methods=["POST"])
def update_node_heartbeat(node_id):
    """Process heartbeat from a node"""
    try:
        node = Node.query.get_or_404(node_id)
        
        # Get heartbeat data
        payload = request.get_json() or {}
        pod_ids = payload.get("pod_ids", [])
        cpu_cores_avail = payload.get("cpu_cores_avail")
        health_status = payload.get("health_status", "healthy")
        components = payload.get("components", {})
        
        # Update node information
        node.last_heartbeat = datetime.now(timezone.utc)
        node.health_status = health_status
        
        # Update components status
        if "kubelet" in components:
            node.kubelet_status = components["kubelet"]
        if "container_runtime" in components:
            node.container_runtime_status = components["container_runtime"]
        if "kube_proxy" in components:
            node.kube_proxy_status = components["kube_proxy"]
        if "node_agent" in components:
            node.node_agent_status = components["node_agent"]
            
        # Master node components
        if node.node_type == "master":
            if "api_server" in components:
                node.api_server_status = components["api_server"]
            if "scheduler" in components:
                node.scheduler_status = components["scheduler"]
            if "controller" in components:
                node.controller_status = components["controller"] 
            if "etcd" in components:
                node.etcd_status = components["etcd"]
        
        # Update pod list if provided
        if pod_ids is not None:
            node.pod_ids = pod_ids
            
        # Update CPU usage if provided
        if cpu_cores_avail is not None:
            node.cpu_cores_avail = cpu_cores_avail
            
        data.session.commit()
        current_app.logger.info(f"Heartbeat received from Node {node.name} (ID: {node.id})")
        
        return jsonify({"message": "Heartbeat updated successfully"}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error updating heartbeat for Node {node_id}: {str(e)}")
        data.session.rollback()
        return jsonify({"error": str(e)}), 500

@nodes_bp.route("/<int:node_id>", methods=["GET"])
def get_node(node_id):
    """Get node details"""
    node = Node.query.get_or_404(node_id)
    
    # Get container status
    container_info = {"status": "unknown"}
    if node.docker_container_id:
        container_info = docker_service.get_node_container_info(node.docker_container_id)
    
    return jsonify({
        "id": node.id,
        "name": node.name,
        "node_type": node.node_type,
        "cpu_cores_total": node.cpu_cores_total,
        "cpu_cores_avail": node.cpu_cores_avail,
        "health_status": node.health_status,
        "last_heartbeat": node.last_heartbeat.isoformat() if node.last_heartbeat else None,
        "container": {
            "id": node.docker_container_id,
            "status": container_info.get("status"),
            "ip": node.node_ip,
            "port": node.node_port
        },
        "pod_ids": node.pod_ids,
        "components": {
            "kubelet": node.kubelet_status,
            "container_runtime": node.container_runtime_status,
            "kube_proxy": node.kube_proxy_status,
            "node_agent": node.node_agent_status,
        }
    }), 200

@nodes_bp.route("/<int:node_id>", methods=["DELETE"])
def delete_node(node_id):
    """Delete a node"""
    try:
        node = Node.query.get_or_404(node_id)
        
        # Check if node has pods
        if node.pods:
            return jsonify({
                "error": "Cannot delete node with running pods. Reschedule or delete pods first."
            }), 400
            
        # Remove node container
        if node.docker_container_id:
            docker_service.stop_node_container(node.docker_container_id)
            docker_service.remove_node_container(node.docker_container_id)
            
        # Delete node from database
        data.session.delete(node)
        data.session.commit()
        
        return jsonify({"message": f"Node {node.name} (ID: {node_id}) deleted successfully"}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error deleting node {node_id}: {str(e)}")
        data.session.rollback()
        return jsonify({"error": str(e)}), 500

@nodes_bp.route("/<int:node_id>/simulate/failure", methods=["POST"])
def simulate_node_failure(node_id):
    """Simulate node failure"""
    try:
        node = Node.query.get_or_404(node_id)
        
        # Send failure simulation request to node container
        if node.docker_container_id and node.node_ip:
            try:
                requests.post(
                    f"http://{node.node_ip}:5000/simulate/failure",
                    timeout=5
                )
            except Exception as e:
                current_app.logger.warning(f"Failed to send failure simulation to node container: {str(e)}")
                
        # Update node status
        node.health_status = "failed"
        data.session.commit()
        
        return jsonify({"message": f"Node {node.name} (ID: {node_id}) failure simulated"}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error simulating node failure: {str(e)}")
        data.session.rollback()
        return jsonify({"error": str(e)}), 500

def send_heartbeats(app):
    """Background task to monitor node heartbeats"""
    with app.app_context():
        while True:
            try:
                # Check nodes that haven't sent heartbeats
                current_time = datetime.now(timezone.utc)
                nodes = Node.query.all()
                
                for node in nodes:
                    # Skip if no last heartbeat (new node)
                    if not node.last_heartbeat:
                        continue
                        
                    # Calculate time since last heartbeat
                    interval = (current_time - node.last_heartbeat).total_seconds()
                    
                    # If heartbeat missed, mark node as failed
                    if interval > node.max_heartbeat_interval and node.health_status == "healthy":
                        app.logger.warning(
                            f"Node {node.name} (ID: {node.id}) marked as failed - "
                            f"Missing heartbeat for {interval:.1f}s"
                        )
                        node.health_status = "failed"
                        node.recovery_attempts += 1
                        data.session.commit()
                        
                        # Trigger pod rescheduling
                        if app.config.get("DOCKER_MONITOR"):
                            app.config["DOCKER_MONITOR"].trigger_pod_rescheduling()
            
            except Exception as e:
                app.logger.error(f"Error in heartbeat monitor: {str(e)}")
                
            # Sleep until next check
            time.sleep(HEARTBEAT_INTERVAL / 2)  # Check twice per interval

def init_heartbeat_thread(app):
    """Start the heartbeat thread"""
    global heartbeat_thread
    if heartbeat_thread is None or not heartbeat_thread.is_alive():
        heartbeat_thread = threading.Thread(target=send_heartbeats, args=(app,), daemon=True)
        heartbeat_thread.start()
        app.logger.info("Node heartbeat monitor started")
    return heartbeat_thread

def init_routes(app):
    """Initialize routes and start heartbeat thread"""
    init_heartbeat_thread(app)