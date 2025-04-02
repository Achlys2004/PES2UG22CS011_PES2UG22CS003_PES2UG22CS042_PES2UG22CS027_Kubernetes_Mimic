from flask import Blueprint, request, jsonify
import random
import ipaddress
from models import data, Pod, Node, Container, Volume, ConfigItem

pods_bp = Blueprint("pods", __name__)


# Add a pod
@pods_bp.route("/", methods=["POST"])
def add_pod():
    req_data = request.get_json()
    name = req_data.get("name")
    cpu_cores_req = req_data.get("cpu_cores_req")
    containers_data = req_data.get("containers", [])
    volumes_data = req_data.get("volumes", [])
    config_data = req_data.get("config", [])

    # Validations
    if not name:
        return jsonify({"error": "Name is missing or incorrect"}), 400
    elif not cpu_cores_req:
        return jsonify({"error": "cpu_cores_req is missing or incorrect"}), 400
    elif not containers_data:
        return jsonify({"error": "At least one container is required"}), 400

    # Find a worker node with enough available cores and healthy components
    node = Node.query.filter(
        Node.cpu_cores_avail >= cpu_cores_req,
        Node.health_status == "healthy",
        Node.node_type == "worker",
        Node.kubelet_status == "running",
        Node.container_runtime_status == "running",
    ).first()

    if not node:
        return (
            jsonify(
                {
                    "error": "No available worker node found with enough CPU resources or healthy components"
                }
            ),
            400,
        )

    # Generate a simulated IP address for the pod
    base_ip = "10.244.0.0"
    network = ipaddress.ip_network(f"{base_ip}/16")
    random_ip = str(random.choice(list(network.hosts())))

    # Determine pod type based on number of containers
    pod_type = "multi-container" if len(containers_data) > 1 else "single-container"

    # Create the pod
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
    data.session.flush()  # To get the pod ID for relations

    # Add containers to the pod
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

    # Add volumes if specified
    for volume_data in volumes_data:
        volume = Volume(
            name=volume_data.get("name", f"{name}-volume-{random.randint(1000, 9999)}"),
            volume_type=volume_data.get("type", "emptyDir"),
            size=volume_data.get("size", 1),
            path=volume_data.get("path", "/data"),
            pod_id=new_pod.id,
        )
        data.session.add(volume)

    # Add configuration items if specified
    for config_item in config_data:
        config = ConfigItem(
            name=config_item.get("name", f"{name}-config-{random.randint(1000, 9999)}"),
            config_type=config_item.get("type", "env"),
            key=config_item.get("key", "KEY"),
            value=config_item.get("value", "VALUE"),
            pod_id=new_pod.id,
        )
        data.session.add(config)

    # Reduce available CPU on the node
    node.cpu_cores_avail -= cpu_cores_req

    # Change pod status to running once everything is set up
    new_pod.health_status = "running"
    for container in new_pod.containers:
        container.status = "running"

    data.session.commit()

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


# List all pods with detailed information
@pods_bp.route("/", methods=["GET"])
def list_pods():
    pods = Pod.query.all()
    result = []

    for pod in pods:
        # Get node info
        node = Node.query.get(pod.node_id)

        # Get container details
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

        # Get volume details
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

        # Get config details
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


# Get pod details by ID
@pods_bp.route("/<int:pod_id>", methods=["GET"])
def get_pod(pod_id):
    pod = Pod.query.get(pod_id)

    if not pod:
        return jsonify({"error": "Pod not found"}), 404

    # Get node info
    node = Node.query.get(pod.node_id)

    # Get container details
    containers = [
        {
            "id": container.id,
            "name": container.name,
            "image": container.image,
            "status": container.status,
            "cpu": container.cpu_req,
            "memory": container.memory_req,
            "command": container.command,
            "args": container.args,
        }
        for container in pod.containers
    ]

    # Get volume details
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

    # Get config details
    configs = (
        [
            {
                "name": config.name,
                "type": config.config_type,
                "key": config.key,
                "value": config.value if config.config_type != "secret" else "******",
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
            {"id": node.id, "name": node.name, "type": node.node_type} if node else None
        ),
        "health_status": pod.health_status,
        "ip_address": pod.ip_address,
        "type": pod.pod_type,
        "containers": containers,
        "volumes": volumes,
        "config": configs,
    }

    return jsonify(pod_data), 200


# Simulate pod crash and attempt to reschedule
@pods_bp.route("/<int:pod_id>/crash", methods=["POST"])
def crash_pod(pod_id):
    pod = Pod.query.get(pod_id)

    if not pod:
        return jsonify({"error": "Pod not found"}), 404

    # Update pod status to failed
    pod.health_status = "failed"

    # Update container statuses
    for container in pod.containers:
        container.status = "failed"

    data.session.commit()

    # Attempt to reschedule on another node
    try:
        # Free up CPU on current node
        current_node = Node.query.get(pod.node_id)
        if current_node:
            current_node.cpu_cores_avail += pod.cpu_cores_req

        # Find a new node
        new_node = Node.query.filter(
            Node.id != pod.node_id,
            Node.cpu_cores_avail >= pod.cpu_cores_req,
            Node.health_status == "healthy",
            Node.node_type == "worker",
            Node.kubelet_status == "running",
            Node.container_runtime_status == "running",
        ).first()

        if new_node:
            # Assign to new node
            pod.node_id = new_node.id
            pod.health_status = "running"

            # Update container statuses
            for container in pod.containers:
                container.status = "running"

            # Generate a new IP address
            base_ip = "10.244.0.0"
            network = ipaddress.ip_network(f"{base_ip}/16")
            pod.ip_address = str(random.choice(list(network.hosts())))

            # Reduce CPU on new node
            new_node.cpu_cores_avail -= pod.cpu_cores_req

            data.session.commit()

            return (
                jsonify(
                    {
                        "message": f"Pod {pod.name} crashed and was rescheduled to node {new_node.name}",
                        "pod_id": pod.id,
                        "new_node_id": new_node.id,
                        "new_node_name": new_node.name,
                        "new_ip": pod.ip_address,
                    }
                ),
                200,
            )
        else:
            # No available node found
            pod.health_status = "pending"
            data.session.commit()

            return (
                jsonify(
                    {
                        "message": f"Pod {pod.name} crashed but could not be rescheduled - no available nodes",
                        "pod_id": pod.id,
                        "status": "pending",
                    }
                ),
                200,
            )

    except Exception as e:
        return jsonify({"error": f"Error during rescheduling: {str(e)}"}), 500


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

    # Delete the pod (will cascade delete containers, volumes, configs)
    data.session.delete(pod)
    data.session.commit()

    return jsonify({"message": f"Pod {pod_id} deleted successfully"}), 200
