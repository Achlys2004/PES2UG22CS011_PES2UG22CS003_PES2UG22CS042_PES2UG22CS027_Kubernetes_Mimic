from flask import Blueprint, request, jsonify, current_app
import random
import ipaddress
import requests
from models import data, Pod, Node, Container, Volume, ConfigItem
from services.docker_service import DockerService
import uuid

pods_bp = Blueprint("pods", __name__)
docker_service = DockerService()


def build_pod_spec(pod):
    """Build a pod specification to send to nodes"""
    pod_spec = {
        "name": pod.name,
        "cpu_cores_req": pod.cpu_cores_req,
        "ip_address": pod.ip_address,
        "containers": [],
        "environment": {},
    }

    for container in pod.containers:
        container_spec = {
            "name": container.name,
            "image": container.image,
            "command": container.command,
            "args": container.args,
            "cpu_req": container.cpu_req,
            "memory_req": container.memory_req,
        }
        pod_spec["containers"].append(container_spec)

    for config in pod.config_items:
        if config.config_type == "env":
            pod_spec["environment"][config.key] = config.value

    return pod_spec


@pods_bp.route("/", methods=["POST"])
def add_pod():
    """Create a new pod and schedule it on a node"""
    try:
        req_data = request.get_json()
        name = req_data.get("name")
        cpu_cores_req = req_data.get("cpu_cores_req")
        containers_data = req_data.get("containers", [])
        volumes_data = req_data.get("volumes", [])
        config_data = req_data.get("config", [])

        if not name:
            return jsonify({"error": "Name is missing or incorrect"}), 400
        elif not cpu_cores_req:
            return jsonify({"error": "cpu_cores_req is missing or incorrect"}), 400
        elif not containers_data:
            return jsonify({"error": "At least one container is required"}), 400

        eligible_nodes = Node.query.filter(
            Node.cpu_cores_avail >= cpu_cores_req,
            Node.health_status == "healthy",
            Node.node_type == "worker",
            Node.kubelet_status == "running",
            Node.container_runtime_status == "running",
        ).all()

        node = None
        if eligible_nodes:

            node = min(eligible_nodes, key=lambda n: n.cpu_cores_avail)

        if not node:
            return (
                jsonify(
                    {
                        "error": "No available worker node found with enough CPU resources or healthy components"
                    }
                ),
                400,
            )

        base_ip = "10.244.0.0"
        network = ipaddress.ip_network(f"{base_ip}/16")
        random_ip = str(random.choice(list(network.hosts())))

        pod_type = "multi-container" if len(containers_data) > 1 else "single-container"

        new_pod = Pod(
            name=name,
            cpu_cores_req=cpu_cores_req,
            node_id=node.id,
            health_status="pending",
            ip_address=random_ip,
            pod_type=pod_type,
            has_volumes=len(volumes_data) > 0,
            has_config=len(config_data) > 0,
        )
        data.session.add(new_pod)
        data.session.flush()

        for container_data in containers_data:
            container = Container(
                name=container_data.get(
                    "name", f"{name}-container-{random.randint(1000, 9999)}"
                ),
                image=container_data.get("image", "nginx:latest"),
                status="pending",
                pod_id=new_pod.id,
                cpu_req=container_data.get("cpu_req", 0.1),
                memory_req=container_data.get("memory_req", 128),
                command=container_data.get("command"),
                args=container_data.get("args"),
            )
            data.session.add(container)

        for volume_data in volumes_data:
            volume = Volume(
                name=volume_data.get(
                    "name", f"{name}-volume-{random.randint(1000, 9999)}"
                ),
                volume_type=volume_data.get("type", "emptyDir"),
                size=volume_data.get("size", 1),
                path=volume_data.get("path", "/data"),
                pod_id=new_pod.id,
            )
            data.session.add(volume)

        for config_item in config_data:
            config = ConfigItem(
                name=config_item.get(
                    "name", f"{name}-config-{random.randint(1000, 9999)}"
                ),
                config_type=config_item.get("type", "env"),
                key=config_item.get("key", "KEY"),
                value=config_item.get("value", "VALUE"),
                pod_id=new_pod.id,
            )
            data.session.add(config)

        node.cpu_cores_avail -= cpu_cores_req

        new_pod.health_status = "running"
        for container in new_pod.containers:
            container.status = "running"

        try:
            pod_spec = build_pod_spec(new_pod)

            if node.node_ip:
                response = requests.post(
                    f"http://{node.node_ip}:{node.node_port}/run_pod",
                    json={"pod_id": new_pod.id, "pod_spec": pod_spec},
                    timeout=10,
                )

                if response.status_code != 200:
                    raise Exception(
                        f"Node responded with status {response.status_code}: {response.text}"
                    )

                pod_status = response.json().get("pod_status", {})
                for container_status in pod_status.get("containers", []):
                    for container in new_pod.containers:
                        if container.name == container_status["name"]:
                            container.status = container_status["status"]
            else:
                raise Exception("Node IP address not available")

            node.add_pod(new_pod.id)

            data.session.commit()

        except Exception as e:

            current_app.logger.error(f"Error creating pod processes: {str(e)}")

            new_pod.health_status = "failed"
            data.session.commit()

            return jsonify({"error": f"Error creating pod processes: {str(e)}"}), 500

        return (
            jsonify(
                {
                    "message": f"Pod '{name}' assigned to node '{node.name}' successfully!",
                    "pod_details": {
                        "id": new_pod.id,
                        "name": new_pod.name,
                        "ip_address": new_pod.ip_address,
                        "node": node.name,
                        "type": new_pod.pod_type,
                        "status": new_pod.health_status,
                        "containers_count": len(new_pod.containers),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Error adding pod: {str(e)}")
        data.session.rollback()
        return jsonify({"error": f"Failed to add pod: {str(e)}"}), 500


@pods_bp.route("/", methods=["GET"])
def list_pods():
    """List all pods"""
    pods = Pod.query.all()
    result = []

    for pod in pods:
        node = Node.query.get(pod.node_id)

        containers = [
            {
                "id": container.id,
                "name": container.name,
                "image": container.image,
                "status": container.status,
                "cpu": container.cpu_req,
                "memory": container.memory_req,
            }
            for container in pod.containers
        ]

        volumes = (
            [
                {
                    "name": volume.name,
                    "type": volume.volume_type,
                    "size": volume.size,
                    "path": volume.path,
                }
                for volume in pod.volumes
            ]
            if hasattr(pod, "volumes")
            else []
        )

        configs = (
            [
                {
                    "name": config.name,
                    "type": config.config_type,
                    "key": config.key,
                    "value": (
                        config.value if config.config_type != "secret" else "******"
                    ),
                }
                for config in pod.config_items
            ]
            if hasattr(pod, "config_items")
            else []
        )

        pod_data = {
            "id": pod.id,
            "name": pod.name,
            "cpu_cores_req": pod.cpu_cores_req,
            "node": (
                {"id": node.id, "name": node.name, "type": node.node_type}
                if node
                else None
            ),
            "health_status": pod.health_status,
            "ip_address": pod.ip_address,
            "type": pod.pod_type,
            "containers": containers,
            "volumes": volumes,
            "config": configs,
        }

        result.append(pod_data)

    return jsonify(result), 200


@pods_bp.route("/<int:pod_id>", methods=["GET"])
def get_pod(pod_id):
    """Get details of a specific pod"""
    pod = Pod.query.get_or_404(pod_id)
    node = Node.query.get(pod.node_id)

    containers = [
        {
            "id": container.id,
            "name": container.name,
            "image": container.image,
            "status": container.status,
            "docker_status": container.docker_status,
            "cpu": container.cpu_req,
            "memory": container.memory_req,
            "docker_id": container.docker_container_id,
        }
        for container in pod.containers
    ]

    volumes = (
        [
            {
                "id": volume.id,
                "name": volume.name,
                "type": volume.volume_type,
                "size": volume.size,
                "path": volume.path,
                "docker_volume": volume.docker_volume_name,
            }
            for volume in pod.volumes
        ]
        if hasattr(pod, "volumes")
        else []
    )

    configs = (
        [
            {
                "id": config.id,
                "name": config.name,
                "type": config.config_type,
                "key": config.key,
                "value": (config.value if config.config_type != "secret" else "******"),
            }
            for config in pod.config_items
        ]
        if hasattr(pod, "config_items")
        else []
    )

    return (
        jsonify(
            {
                "id": pod.id,
                "name": pod.name,
                "cpu_cores_req": pod.cpu_cores_req,
                "node": (
                    {"id": node.id, "name": node.name, "type": node.node_type}
                    if node
                    else None
                ),
                "health_status": pod.health_status,
                "ip_address": pod.ip_address,
                "type": pod.pod_type,
                "docker_network_id": pod.docker_network_id,
                "containers": containers,
                "volumes": volumes,
                "config": configs,
            }
        ),
        200,
    )


@pods_bp.route("/<int:pod_id>", methods=["DELETE"])
def delete_pod(pod_id):
    """Delete a pod"""
    try:
        pod = Pod.query.get_or_404(pod_id)
        node = Node.query.get(pod.node_id)

        if not node:
            return jsonify({"error": "Associated node not found"}), 404

        try:
            if node.node_ip:
                response = requests.delete(
                    f"http://{node.node_ip}:5000/pods/{pod_id}", timeout=5
                )

                if response.status_code != 200:
                    current_app.logger.warning(
                        f"Node responded with status {response.status_code} when deleting pod: {response.text}"
                    )
        except Exception as e:
            current_app.logger.warning(
                f"Failed to notify node about pod deletion: {str(e)}"
            )

        node.cpu_cores_avail += pod.cpu_cores_req

        node.remove_pod(pod_id)

        data.session.delete(pod)
        data.session.commit()

        return jsonify({"message": f"Pod {pod_id} deleted successfully"}), 200

    except Exception as e:
        current_app.logger.error(f"Error deleting pod {pod_id}: {str(e)}")
        data.session.rollback()
        return jsonify({"error": str(e)}), 500


@pods_bp.route("/<int:pod_id>/health", methods=["GET"])
def check_pod_health(pod_id):
    """Check the health of a pod by querying the hosting node"""
    pod = Pod.query.get_or_404(pod_id)
    node = Node.query.get(pod.node_id)

    if not node:
        return jsonify({"error": "Associated node not found"}), 404

    try:
        if node.node_ip:
            response = requests.get(
                f"http://{node.node_ip}:5000/pods/{pod_id}/status", timeout=5
            )

            if response.status_code == 200:
                node_pod_status = response.json()

                if pod.health_status != node_pod_status["status"]:
                    pod.health_status = node_pod_status["status"]
                    data.session.commit()

                return jsonify(node_pod_status), 200
            else:
                return (
                    jsonify(
                        {
                            "pod_id": pod_id,
                            "pod_name": pod.name,
                            "overall_status": pod.health_status,
                            "error": f"Node returned status {response.status_code}",
                        }
                    ),
                    200,
                )
        else:
            return (
                jsonify(
                    {
                        "pod_id": pod_id,
                        "pod_name": pod.name,
                        "overall_status": pod.health_status,
                        "error": "Node IP address not available",
                    }
                ),
                200,
            )
    except Exception as e:
        current_app.logger.warning(f"Error checking pod status on node: {str(e)}")
        return (
            jsonify(
                {
                    "pod_id": pod_id,
                    "pod_name": pod.name,
                    "overall_status": pod.health_status,
                    "error": f"Communication error: {str(e)}",
                }
            ),
            200,
        )
