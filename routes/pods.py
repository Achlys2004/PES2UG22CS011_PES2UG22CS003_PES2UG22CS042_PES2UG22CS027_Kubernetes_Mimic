from flask import Blueprint, request, jsonify, current_app
import random
import ipaddress
import requests
from models import data, Pod, Node, Container, Volume, ConfigItem
from services.docker_service import DockerService
import docker

pods_bp = Blueprint("pods", __name__)
docker_service = DockerService()

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

        # Validations
        if not name:
            return jsonify({"error": "Name is missing or incorrect"}), 400
        elif not cpu_cores_req:
            return jsonify({"error": "cpu_cores_req is missing or incorrect"}), 400
        elif not containers_data:
            return jsonify({"error": "At least one container is required"}), 400

        # Find eligible nodes using Best-Fit algorithm
        eligible_nodes = Node.query.filter(
            Node.cpu_cores_avail >= cpu_cores_req,
            Node.health_status == "healthy",
            Node.node_type == "worker",
            Node.kubelet_status == "running",
            Node.container_runtime_status == "running",
        ).all()

        node = None
        if eligible_nodes:
            # Best-Fit: Select node with minimum available resources
            node = min(eligible_nodes, key=lambda n: n.cpu_cores_avail)

        if not node:
            return (
                jsonify({
                    "error": "No available worker node found with enough CPU resources or healthy components"
                }),
                400,
            )

        # Generate IP address for the pod
        base_ip = "10.244.0.0"
        network = ipaddress.ip_network(f"{base_ip}/16")
        random_ip = str(random.choice(list(network.hosts())))

        # Determine pod type
        pod_type = "multi-container" if len(containers_data) > 1 else "single-container"

        # Create the pod in database
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
        data.session.flush()  # Get the pod ID without committing

        # Create containers
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

        # Create volumes
        for volume_data in volumes_data:
            volume = Volume(
                name=volume_data.get("name", f"{name}-volume-{random.randint(1000, 9999)}"),
                volume_type=volume_data.get("type", "emptyDir"),
                size=volume_data.get("size", 1),
                path=volume_data.get("path", "/data"),
                pod_id=new_pod.id,
            )
            data.session.add(volume)

        # Create config items
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

        # Set initial status
        new_pod.health_status = "running"
        for container in new_pod.containers:
            container.status = "running"

        # Create Docker resources
        try:
            # Create network for the pod
            network_name = f"pod-network-{new_pod.id}"
            network_id = docker_service.create_network(network_name)
            new_pod.docker_network_id = network_id

            # Create volumes
            for volume in new_pod.volumes:
                volume_name = f"pod-{new_pod.id}-volume-{volume.id}"
                docker_volume = docker_service.create_volume(volume_name)
                volume.docker_volume_name = docker_volume

            # Create and start containers
            for container in new_pod.containers:
                # Prepare environment variables
                env_vars = {}
                for config in new_pod.config_items:
                    if config.config_type == "env":
                        env_vars[config.key] = config.value

                # Prepare volume mounts
                volume_mounts = {}
                for volume in new_pod.volumes:
                    volume_mounts[volume.docker_volume_name] = {
                        "bind": volume.path,
                        "mode": "rw",
                    }

                # Create container
                container_name = f"pod-{new_pod.id}-{container.name}"
                container_id = docker_service.create_container(
                    name=container_name,
                    image=container.image,
                    command=container.command,
                    environment=env_vars,
                    volumes=volume_mounts if volume_mounts else None,
                    network=network_name,
                    cpu_limit=container.cpu_req,
                    memory_limit=f"{container.memory_req}m",
                )

                container.docker_container_id = container_id
                docker_service.start_container(container_id)
                container.status = "running"
                container.docker_status = "running"

            # Notify the node about the new pod
            try:
                if node.node_ip:
                    response = requests.post(
                        f"http://{node.node_ip}:5000/pods",
                        json={
                            "pod_id": new_pod.id,
                            "cpu_cores_req": cpu_cores_req,
                        },
                        timeout=5
                    )
                    
                    if response.status_code != 200:
                        current_app.logger.warning(
                            f"Node {node.name} responded with status {response.status_code} "
                            f"when adding pod: {response.text}"
                        )
            except Exception as e:
                current_app.logger.warning(f"Failed to notify node about new pod: {str(e)}")

            # Add pod ID to node's pod list
            node.add_pod(new_pod.id)
            
            # Commit all changes
            data.session.commit()
            
        except Exception as e:
            # Cleanup on failure
            current_app.logger.error(f"Error creating Docker resources: {str(e)}")
            
            # Clean up containers
            for container in new_pod.containers:
                if container.docker_container_id:
                    docker_service.remove_container(container.docker_container_id, force=True)

            # Clean up network
            if new_pod.docker_network_id:
                docker_service.remove_network(new_pod.docker_network_id)

            # Clean up volumes
            for volume in new_pod.volumes:
                if volume.docker_volume_name:
                    docker_service.remove_volume(volume.docker_volume_name)

            # Mark pod as failed
            new_pod.health_status = "failed"
            data.session.commit()

            # Return error to client
            return jsonify({"error": f"Error creating Docker resources: {str(e)}"}), 500

        # Return success response
        return (
            jsonify({
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
            }),
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
            "docker_id": container.docker_container_id
        }
        for container in pod.containers
    ]

    volumes = [
        {
            "id": volume.id,
            "name": volume.name,
            "type": volume.volume_type,
            "size": volume.size,
            "path": volume.path,
            "docker_volume": volume.docker_volume_name
        }
        for volume in pod.volumes
    ] if hasattr(pod, "volumes") else []

    configs = [
        {
            "id": config.id,
            "name": config.name,
            "type": config.config_type,
            "key": config.key,
            "value": (config.value if config.config_type != "secret" else "******"),
        }
        for config in pod.config_items
    ] if hasattr(pod, "config_items") else []

    return jsonify({
        "id": pod.id,
        "name": pod.name,
        "cpu_cores_req": pod.cpu_cores_req,
        "node": {
            "id": node.id,
            "name": node.name,
            "type": node.node_type
        } if node else None,
        "health_status": pod.health_status,
        "ip_address": pod.ip_address,
        "type": pod.pod_type,
        "docker_network_id": pod.docker_network_id,
        "containers": containers,
        "volumes": volumes,
        "config": configs,
    }), 200

@pods_bp.route("/<int:pod_id>", methods=["DELETE"])
def delete_pod(pod_id):
    """Delete a pod"""
    try:
        pod = Pod.query.get_or_404(pod_id)
        node = Node.query.get(pod.node_id)
        
        if not node:
            return jsonify({"error": "Associated node not found"}), 404
            
        # Clean up Docker resources
        try:
            # Stop and remove containers
            for container in pod.containers:
                if container.docker_container_id:
                    docker_service.stop_container(container.docker_container_id)
                    docker_service.remove_container(
                        container.docker_container_id, force=True
                    )

            # Remove network
            if pod.docker_network_id:
                docker_service.remove_network(pod.docker_network_id)

            # Remove volumes
            for volume in pod.volumes:
                if volume.docker_volume_name:
                    docker_service.remove_volume(volume.docker_volume_name)
        
        except Exception as e:
            current_app.logger.error(f"Error removing Docker resources: {str(e)}")
            # Continue with pod deletion even if Docker resources cleanup fails
        
        # Notify the node about pod removal
        try:
            if node.node_ip:
                requests.delete(
                    f"http://{node.node_ip}:5000/pods/{pod_id}",
                    timeout=5
                )
        except Exception as e:
            current_app.logger.warning(f"Failed to notify node about pod deletion: {str(e)}")
        
        # Return CPU resources to the node
        node.cpu_cores_avail += pod.cpu_cores_req
        
        # Remove pod ID from node's pod list
        node.remove_pod(pod_id)
        
        # Delete the pod from database
        data.session.delete(pod)
        data.session.commit()
        
        return jsonify({"message": f"Pod {pod_id} deleted successfully"}), 200
    
    except Exception as e:
        current_app.logger.error(f"Error deleting pod {pod_id}: {str(e)}")
        data.session.rollback()
        return jsonify({"error": str(e)}), 500

@pods_bp.route("/<int:pod_id>/health", methods=["GET"])
def check_pod_health(pod_id):
    """Check the health of a pod"""
    pod = Pod.query.get_or_404(pod_id)

    container_statuses = []
    for container in pod.containers:
        if container.docker_container_id:
            current_status = docker_service.get_container_status(
                container.docker_container_id
            )
            container_statuses.append({
                "container_id": container.id,
                "name": container.name,
                "image": container.image,
                "docker_status": current_status,
                "app_status": container.status,
            })

    health_data = {
        "pod_id": pod.id,
        "pod_name": pod.name,
        "overall_status": pod.health_status,
        "node_id": pod.node_id,
        "node_name": pod.node.name if pod.node else "Unknown",
        "containers": container_statuses,
    }

    return jsonify(health_data), 200