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


HEARTBEAT_INTERVAL = 60


@nodes_bp.route("/", methods=["POST"])
def create_node():
    """Create a new node with Docker container simulation"""
    try:
        payload = request.get_json()

        if not payload.get("name"):
            return jsonify({"error": "Node name is required"}), 400
        if not payload.get("cpu_cores_avail") or payload["cpu_cores_avail"] <= 0:
            return jsonify({"error": "CPU cores must be a positive number"}), 400

        node_type = payload.get("node_type", "worker").lower()
        if node_type not in ["worker", "master"]:
            return jsonify({"error": "Node type must be 'worker' or 'master'"}), 400

        existing = Node.query.filter_by(name=payload["name"]).first()
        if existing:
            return (
                jsonify(
                    {"error": f"Node with name '{payload['name']}' already exists"}
                ),
                400,
            )

        node = Node(
            name=payload["name"],
            node_type=node_type,
            cpu_cores_avail=payload["cpu_cores_avail"],
            cpu_cores_total=payload["cpu_cores_avail"],
            health_status="initializing",
        )

        data.session.add(node)
        data.session.flush()

        container_id, node_ip, node_port = docker_service.create_node_container(
            node.id, node.name, node.cpu_cores_total, node.node_type
        )

        node.docker_container_id = container_id
        node.node_ip = node_ip
        node.node_port = node_port

        data.session.commit()

        return (
            jsonify(
                {
                    "id": node.id,
                    "name": node.name,
                    "node_type": node.node_type,
                    "cpu_cores": node.cpu_cores_avail,
                    "status": node.health_status,
                    "container_id": node.docker_container_id,
                    "node_ip": node.node_ip,
                    "message": "Node created successfully. Initialization in progress.",
                }
            ),
            201,
        )

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
def update_heartbeat(node_id):
    try:
        node = Node.query.get(node_id)
        if not node:
            current_app.logger.warning(
                f"[HEARTBEAT] Received heartbeat for non-existent node ID: {node_id}"
            )
            return (
                jsonify(
                    {
                        "error": f"Node with ID {node_id} not found",
                        "node_status": "non_existent",
                        "should_stop_heartbeat": True,
                    }
                ),
                404,
            )

        payload = request.get_json() or {}

        node.last_heartbeat = datetime.now(timezone.utc)

        health_status = payload.get("health_status", "healthy")

        # Check if node is permanently failed - don't update status but respond
        if node.health_status == "permanently_failed":
            current_app.logger.info(
                f"[HEARTBEAT] Ignoring heartbeat status update for permanently failed node {node.name} (ID: {node.id})"
            )

            # If the node is permanently failed but still has a container, clean it up
            if node.docker_container_id:
                try:
                    from services.docker_service import DockerService

                    docker_service = DockerService()

                    current_app.logger.info(
                        f"[HEARTBEAT] Cleaning up container for permanently failed node {node.name}"
                    )

                    # Force stop and remove the container
                    docker_service.stop_container(
                        node.docker_container_id, force=True, is_node=True
                    )
                    time.sleep(1)
                    docker_service.remove_container(
                        node.docker_container_id, force=True, is_node=True
                    )

                    # Update the node record
                    node.docker_container_id = None
                    data.session.commit()

                except Exception as e:
                    current_app.logger.error(
                        f"[HEARTBEAT] Error cleaning up container: {str(e)}"
                    )

            # Tell the node to stop sending heartbeats
            return (
                jsonify(
                    {
                        "message": "Node is permanently failed, no further heartbeats needed",
                        "node_status": "permanently_failed",
                        "should_stop_heartbeat": True,
                        "should_terminate": True,  # Add this flag to tell the node to exit
                    }
                ),
                200,
            )

        # Normal heartbeat processing for healthy nodes
        node.health_status = health_status

        if health_status == "permanently_failed":
            current_app.logger.info(
                f"[HEARTBEAT] Node {node.name} (ID: {node.id}) reported itself as permanently_failed, triggering pod rescheduler"
            )

            if node.docker_container_id:
                try:
                    from services.docker_service import DockerService

                    docker_service = DockerService()
                    current_app.logger.info(
                        f"[HEARTBEAT] Stopping container for permanently failed node {node.name}"
                    )
                    docker_service.stop_container(node.docker_container_id)
                except Exception as e:
                    current_app.logger.error(
                        f"[HEARTBEAT] Failed to stop container for node {node.name}: {str(e)}"
                    )

            monitor = current_app.config.get("DOCKER_MONITOR")
            if monitor:
                monitor.need_rescheduling = True

        components = payload.get("components", {})
        if "kubelet" in components:
            node.kubelet_status = components["kubelet"]
        if "container_runtime" in components:
            node.container_runtime_status = components["container_runtime"]
        if "kube_proxy" in components:
            node.kube_proxy_status = components["kube_proxy"]
        if "node_agent" in components:
            node.node_agent_status = components["node_agent"]

        if "cpu_cores_avail" in payload:
            node.cpu_cores_avail = payload["cpu_cores_avail"]

        if "pod_ids" in payload and node.health_status != "permanently_failed":
            node.pod_ids = payload["pod_ids"]

        data.session.commit()
        current_app.logger.info(
            f"[HEARTBEAT] Received from Node {node.name} (ID: {node.id}) - Status: {node.health_status}"
        )

        # Return the current node status in the response
        return (
            jsonify(
                {
                    "message": "Heartbeat updated successfully",
                    "node_status": node.health_status,
                    "should_stop_heartbeat": node.health_status == "permanently_failed",
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(
            f"[HEARTBEAT] Error updating heartbeat for Node {node_id}: {str(e)}"
        )
        data.session.rollback()
        return jsonify({"error": str(e)}), 500


@nodes_bp.route("/<int:node_id>", methods=["GET"])
def get_node(node_id):
    """Get node details"""
    node = Node.query.get_or_404(node_id)

    container_info = docker_service.get_container_info(
        node.docker_container_id, detailed=True
    )

    return (
        jsonify(
            {
                "id": node.id,
                "name": node.name,
                "node_type": node.node_type,
                "cpu_cores_total": node.cpu_cores_total,
                "cpu_cores_avail": node.cpu_cores_avail,
                "health_status": node.health_status,
                "last_heartbeat": (
                    node.last_heartbeat.isoformat() if node.last_heartbeat else None
                ),
                "container": {
                    "id": node.docker_container_id,
                    "status": container_info.get("status"),
                    "ip": node.node_ip,
                    "port": node.node_port,
                },
                "pod_ids": node.pod_ids,
                "components": {
                    "kubelet": node.kubelet_status,
                    "container_runtime": node.container_runtime_status,
                    "kube_proxy": node.kube_proxy_status,
                    "node_agent": node.node_agent_status,
                },
            }
        ),
        200,
    )


@nodes_bp.route("/<int:node_id>", methods=["DELETE"])
def delete_node(node_id):
    """Delete a node"""
    try:
        node = Node.query.get_or_404(node_id)

        if node.health_status != "permanently_failed":
            pod_count = len(node.pod_ids)
            if pod_count > 0:
                return (
                    jsonify(
                        {
                            "error": f"Cannot delete node with {pod_count} running pods. Reschedule or delete pods first."
                        }
                    ),
                    400,
                )

        if node.docker_container_id:
            try:
                docker_service.stop_container(node.docker_container_id, is_node=True)
                time.sleep(1)
                docker_service.remove_container(node.docker_container_id, is_node=True)
            except Exception as e:
                current_app.logger.warning(f"Failed to remove container: {str(e)}")

        data.session.delete(node)
        data.session.commit()

        return (
            jsonify(
                {"message": f"Node {node.name} (ID: {node_id}) deleted successfully"}
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Error deleting node {node_id}: {str(e)}")
        data.session.rollback()
        return jsonify({"error": str(e)}), 500


@nodes_bp.route("/<int:node_id>/simulate/failure", methods=["POST"])
def simulate_node_failure(node_id):
    """Simulate node failure"""
    try:
        node = Node.query.get_or_404(node_id)

        if node.docker_container_id and node.node_ip:
            try:
                requests.post(f"http://{node.node_ip}:5000/simulate/failure", timeout=5)
            except Exception as e:
                current_app.logger.warning(
                    f"Failed to send failure simulation to node container: {str(e)}"
                )

        node.health_status = "failed"
        data.session.commit()

        return (
            jsonify({"message": f"Node {node.name} (ID: {node_id}) failure simulated"}),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Error simulating node failure: {str(e)}")
        data.session.rollback()
        return jsonify({"error": str(e)}), 500


@nodes_bp.route("/<int:node_id>/deregister", methods=["POST"])
def deregister_node(node_id):
    """Deregister a node - called when a node container is shutting down"""
    try:
        node = Node.query.get(node_id)
        if not node:
            return jsonify({"error": f"Node with ID {node_id} not found"}), 404

        current_app.logger.info(
            f"[DEREGISTER] Node {node.name} (ID: {node_id}) is deregistering"
        )

        if node.pod_ids:
            monitor = current_app.config.get("DOCKER_MONITOR")
            if monitor:
                monitor.need_rescheduling = True
                current_app.logger.info(
                    f"[DEREGISTER] Triggering pod rescheduler for deregistering node {node.name}"
                )

        node.health_status = "permanently_failed"
        data.session.commit()

        return jsonify({"message": "Node deregistered successfully"}), 200

    except Exception as e:
        current_app.logger.error(
            f"[DEREGISTER] Error deregistering node {node_id}: {str(e)}"
        )
        data.session.rollback()
        return jsonify({"error": str(e)}), 500


@nodes_bp.route("/<int:node_id>/force_cleanup", methods=["POST"])
def force_cleanup_node(node_id):
    """Force cleanup of a permanently failed node's container"""
    try:
        node = Node.query.get_or_404(node_id)

        if node.health_status != "permanently_failed":
            return (
                jsonify({"error": "Can only force cleanup permanently failed nodes"}),
                400,
            )

        if node.docker_container_id:
            try:
                from services.docker_service import DockerService

                docker_service = DockerService()

                current_app.logger.info(
                    f"[CLEANUP] Forcing cleanup of container for node {node.name}"
                )

                docker_service.stop_container(
                    node.docker_container_id, force=True, is_node=True
                )
                time.sleep(2)

                docker_service.remove_container(
                    node.docker_container_id, force=True, is_node=True
                )

                node.docker_container_id = None
                data.session.commit()

                return (
                    jsonify(
                        {
                            "message": f"Container for node {node.name} has been forcefully cleaned up"
                        }
                    ),
                    200,
                )
            except Exception as e:
                current_app.logger.error(
                    f"[CLEANUP] Error cleaning up container: {str(e)}"
                )
                data.session.rollback()
                return (
                    jsonify({"error": f"Failed to clean up container: {str(e)}"}),
                    500,
                )
        else:
            return (
                jsonify({"message": "Node has no container ID, already cleaned up"}),
                200,
            )

    except Exception as e:
        current_app.logger.error(f"[CLEANUP] Error in force cleanup: {str(e)}")
        data.session.rollback()
        return jsonify({"error": str(e)}), 500


def send_heartbeats(app):
    logger = app.logger
    logger.info("[HEARTBEAT] Node heartbeat monitor starting")

    with app.app_context():
        while True:
            try:

                data.session.begin()

                current_time = datetime.now(timezone.utc)

                monitored_nodes = Node.query.filter(
                    Node.health_status.in_(
                        ["healthy", "recovering", "failed", "initializing"]
                    ),
                ).all()

                updated_nodes = []

                for node in monitored_nodes:
                    try:

                        check_node = Node.query.get(node.id)
                        if not check_node:
                            logger.debug(
                                f"[HEARTBEAT] Node ID {node.id} no longer exists, skipping"
                            )
                            continue

                        if not node.last_heartbeat:
                            continue

                        last_heartbeat = node.last_heartbeat
                        if last_heartbeat.tzinfo is None:
                            last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)

                        interval = (current_time - last_heartbeat).total_seconds()

                        if (
                            node.health_status == "healthy"
                            and interval > node.max_heartbeat_interval
                        ):
                            logger.warning(
                                f"[HEARTBEAT] Node {node.name} (ID: {node.id}) marked as failed - "
                                f"Missing heartbeat for {interval:.1f}s (max: {node.max_heartbeat_interval}s)"
                            )
                            node.health_status = "failed"
                            # node.recovery_attempts += 1
                            updated_nodes.append(node.id)

                        elif node.health_status == "recovering":
                            logger.info(
                                f"[HEARTBEAT] Node {node.name} (ID: {node.id}) in recovery - "
                                f"Last heartbeat: {interval:.1f}s ago"
                            )

                        elif node.health_status == "healthy" and interval > (
                            node.max_heartbeat_interval * 0.7
                        ):
                            logger.info(
                                f"[HEARTBEAT] Node {node.name} (ID: {node.id}) heartbeat is delayed - "
                                f"Last seen {interval:.1f}s ago (max: {node.max_heartbeat_interval}s)"
                            )
                    except Exception as e:
                        logger.error(
                            f"[HEARTBEAT] Error processing node {node.name}: {str(e)}"
                        )

                if updated_nodes:
                    data.session.commit()
                    logger.info(
                        f"[HEARTBEAT] Updated status for nodes: {updated_nodes}"
                    )
                else:

                    data.session.rollback()

            except Exception as e:
                logger.error(f"[HEARTBEAT] Error in heartbeat monitor: {str(e)}")
                try:
                    data.session.rollback()
                except:
                    pass

            time.sleep(HEARTBEAT_INTERVAL / 2)


def init_heartbeat_thread(app):
    heartbeat_thread = threading.Thread(
        target=send_heartbeats, args=(app,), daemon=True
    )
    heartbeat_thread.start()
    app.logger.info("Node heartbeat monitor started")
    return heartbeat_thread


def init_routes(app):
    init_heartbeat_thread(app)
