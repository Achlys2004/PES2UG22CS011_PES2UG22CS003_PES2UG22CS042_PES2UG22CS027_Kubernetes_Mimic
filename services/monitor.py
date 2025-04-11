import time
import threading
from flask import current_app
from models import data, Container, Pod, Node, Volume, ConfigItem
from services.docker_service import DockerService
import requests
from datetime import datetime, timedelta
import random
import ipaddress
import logging
from random import randint

# Standardized timing intervals
HEARTBEAT_INTERVAL = 10  # seconds
MAX_HEARTBEAT_INTERVAL = 30  # seconds
RECOVERY_INTERVAL = 20  # seconds
RESCHEDULER_INTERVAL = 20  # seconds


class DockerMonitor:
    def __init__(self, app=None):
        self.app = app
        self.docker_service = DockerService()
        self.thread = None
        self.running = False
        self.logger = self._setup_logger()

        if app is not None:
            self.init_app(app)

    def _setup_logger(self):
        # Create a simple console logger
        logger = logging.getLogger("kube9.monitor")
        logger.setLevel(logging.INFO)

        # Clear existing handlers
        if logger.handlers:
            logger.handlers.clear()

        # Create console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Create simple formatter
        formatter = logging.Formatter("%(asctime)s - %(message)s", datefmt="%H:%M:%S")
        ch.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(ch)
        logger.propagate = False
        return logger

    def init_app(self, app):
        self.app = app

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.running = True

            # Start container monitor thread
            self.thread = threading.Thread(target=self.monitor_containers)
            self.thread.daemon = True
            self.thread.start()
            self.logger.info("Container monitor started")

            # Start node health monitor thread
            self.health_thread = threading.Thread(target=self.monitor_node_health)
            self.health_thread.daemon = True
            self.health_thread.start()
            self.logger.info("Node health monitor started")

            # Start node recovery thread
            self.recovery_thread = threading.Thread(target=self.attempt_node_recovery)
            self.recovery_thread.daemon = True
            self.recovery_thread.start()
            self.logger.info("Node recovery service started")

            # Start pod rescheduling thread
            self.reschedule_thread = threading.Thread(target=self.reschedule_pods)
            self.reschedule_thread.daemon = True
            self.reschedule_thread.start()
            self.logger.info("Pod rescheduling service started")

    def stop(self):
        self.running = False
        for thread in [
            self.thread,
            self.health_thread,
            self.recovery_thread,
            self.reschedule_thread,
        ]:
            if thread:
                thread.join(timeout=5)
        self.logger.info("Kube-9 monitor stopped")

    def monitor_containers(self):
        with self.app.app_context():
            while self.running:
                try:
                    containers = Container.query.filter(
                        Container.docker_container_id != None
                    ).all()

                    for container in containers:
                        docker_status = self.docker_service.get_container_status(
                            container.docker_container_id
                        )

                        if docker_status != container.docker_status:
                            self.logger.info(
                                f"Container {container.name} status changed: {container.docker_status} → {docker_status}"
                            )
                            container.docker_status = docker_status

                            if docker_status == "running":
                                container.status = "running"
                            elif docker_status in ["exited", "dead"]:
                                container.status = "failed"
                                pod = Pod.query.get(container.pod_id)
                                all_failed = all(
                                    c.status == "failed" for c in pod.containers
                                )
                                if all_failed:
                                    pod.health_status = "failed"
                                    self.logger.warning(
                                        f"Pod {pod.name} (ID: {pod.id}) marked as failed - All containers failed"
                                    )

                            data.session.commit()

                except Exception as e:
                    self.logger.error(f"Error in container monitor: {str(e)}")

                time.sleep(20)

    def monitor_node_health(self):
        with self.app.app_context():
            while self.running:
                try:
                    current_time = datetime.now()
                    nodes = Node.query.filter(
                        Node.health_status.in_(["healthy", "idle"])
                    ).all()

                    for node in nodes:
                        threshold = current_time - timedelta(
                            seconds=MAX_HEARTBEAT_INTERVAL
                        )
                        if not node.last_heartbeat or node.last_heartbeat < threshold:
                            self.logger.warning(
                                f"Node {node.name} (ID: {node.id}) marked as FAILED - Missing heartbeat"
                            )
                            node.health_status = "failed"
                            node.kubelet_status = "failed"
                            node.container_runtime_status = "failed"
                            node.kube_proxy_status = "failed"

                            if node.node_type == "master":
                                node.api_server_status = "failed"
                                node.scheduler_status = "failed"
                                node.controller_status = "failed"
                                node.etcd_status = "failed"

                    data.session.commit()
                except Exception as e:
                    self.logger.error(f"Error in node health monitor: {str(e)}")

                time.sleep(HEARTBEAT_INTERVAL)

    def attempt_node_recovery(self):
        with self.app.app_context():
            while self.running:
                try:
                    failed_nodes = Node.query.filter_by(health_status="failed").all()
                    for node in failed_nodes:
                        self.logger.info(
                            f"Attempting recovery for node {node.name} (ID: {node.id})"
                        )
                        node.recovery_attempts = (node.recovery_attempts or 0) + 1

                        if node.recovery_attempts >= (node.max_recovery_attempts or 5):
                            node.health_status = "permanently_failed"
                            self.logger.warning(
                                f"Node {node.name} (ID: {node.id}) marked as permanently failed after {node.recovery_attempts} attempts"
                            )
                        else:
                            self._recover_node(node)

                    data.session.commit()
                except Exception as e:
                    self.logger.error(f"Error in node recovery process: {str(e)}")

                time.sleep(RECOVERY_INTERVAL)

    def _recover_node(self, node):
        node.health_status = "healthy"
        node.recovery_attempts = 0
        node.last_heartbeat = datetime.utcnow()
        node.kubelet_status = "running"
        node.container_runtime_status = "running"
        node.kube_proxy_status = "running"
        node.node_agent_status = "running"

        if node.node_type == "master":
            node.api_server_status = "running"
            node.scheduler_status = "running"
            node.controller_status = "running"
            node.etcd_status = "running"

        data.session.commit()
        self.logger.info(f"Node {node.name} (ID: {node.id}) successfully recovered")

    def reschedule_pods(self):
        """Reschedule pods from failed nodes to healthy ones"""
        with self.app.app_context():
            while self.running:
                try:
                    pods_to_reschedule = (
                        Pod.query.join(Node)
                        .filter(
                            Node.health_status.in_(["failed", "permanently_failed"]),
                            Pod.health_status == "running",
                        )
                        .all()
                    )

                    for pod in pods_to_reschedule:
                        self.logger.info(
                            f"Found pod {pod.name} (ID: {pod.id}) on failed node - Scheduling for migration"
                        )
                        pod.health_status = "pending_reschedule"
                        data.session.commit()

                        try:
                            new_node = Node.query.filter(
                                Node.cpu_cores_avail >= pod.cpu_cores_req,
                                Node.health_status == "healthy",
                                Node.node_type == "worker",
                                Node.kubelet_status == "running",
                                Node.container_runtime_status == "running",
                            ).first()

                            if not new_node:
                                self.logger.warning(
                                    f"No suitable node found to reschedule pod {pod.id}"
                                )
                                continue

                            self.logger.info(
                                f"Rescheduling pod {pod.name} to node {new_node.name}"
                            )
                            pod_config = self.extract_pod_config(pod)
                            pod.health_status = "rescheduling"
                            data.session.commit()

                            new_pod = self._create_replacement_pod(pod_config, new_node)
                            pod.health_status = "rescheduled"
                            data.session.commit()
                            self.logger.info(
                                f"Pod {pod.name} successfully rescheduled as {new_pod.name} on node {new_node.name}"
                            )

                        except Exception as e:
                            pod.health_status = "reschedule_failed"
                            data.session.commit()
                            self.logger.error(
                                f"Failed to reschedule pod {pod.id}: {str(e)}"
                            )

                except Exception as e:
                    self.logger.error(f"Error in pod rescheduler: {str(e)}")

                time.sleep(RESCHEDULER_INTERVAL)

    def record_heartbeat(self, node_id, source="API"):
        """Record a heartbeat from a node"""
        with self.app.app_context():
            node = Node.query.get(node_id)
            if node:
                now = datetime.now()

                time_diff = None
                if node.last_heartbeat:
                    time_diff = (now - node.last_heartbeat).total_seconds()

                node.last_heartbeat = now
                data.session.commit()

                if time_diff:
                    self.logger.info(
                        f"Heartbeat received from Node {node.name} (ID: {node.id}) - Interval: {time_diff:.1f}s"
                    )
                else:
                    self.logger.info(
                        f"First heartbeat received from Node {node.name} (ID: {node.id})"
                    )

                return True
            else:
                self.logger.warning(
                    f"Heartbeat attempted for unknown node ID: {node_id}"
                )
                return False

    def extract_pod_config(self, pod):
        pod_config = {
            "name": f"{pod.name}-rescheduled-{randint(1000, 9999)}",
            "cpu_cores_req": pod.cpu_cores_req,
            "containers": [],
            "volumes": [],
            "config": [],
        }

        for container in pod.containers:
            pod_config["containers"].append(
                {
                    "name": container.name,
                    "image": container.image,
                    "cpu_req": container.cpu_req,
                    "memory_req": container.memory_req,
                    "command": container.command,
                    "args": container.args,
                }
            )

        for volume in getattr(pod, "volumes", []):
            pod_config["volumes"].append(
                {
                    "name": volume.name,
                    "type": volume.volume_type,
                    "size": volume.size,
                    "path": volume.path,
                }
            )

        for config in getattr(pod, "config_items", []):
            pod_config["config"].append(
                {
                    "name": config.name,
                    "type": config.config_type,
                    "key": config.key,
                    "value": config.value,
                }
            )

        return pod_config

    def _create_replacement_pod(self, pod_config, target_node):
        name = pod_config["name"]
        cpu_cores_req = pod_config["cpu_cores_req"]

        base_ip = "10.244.0.0"
        network = ipaddress.ip_network(f"{base_ip}/16")
        random_ip = str(random.choice(list(network.hosts())))

        pod_type = (
            "multi-container"
            if len(pod_config["containers"]) > 1
            else "single-container"
        )

        new_pod = Pod(
            name=name,
            cpu_cores_req=cpu_cores_req,
            node_id=target_node.id,
            health_status="pending",
            ip_address=random_ip,
            pod_type=pod_type,
            has_volumes=len(pod_config["volumes"]) > 0,
            has_config=len(pod_config["config"]) > 0,
        )
        data.session.add(new_pod)
        data.session.flush()

        for container_data in pod_config["containers"]:
            container = Container(
                name=container_data.get("name"),
                image=container_data.get("image"),
                status="pending",
                pod_id=new_pod.id,
                cpu_req=container_data.get("cpu_req", 0.1),
                memory_req=container_data.get("memory_req", 128),
                command=container_data.get("command"),
                args=container_data.get("args"),
            )
            data.session.add(container)

        for volume_data in pod_config["volumes"]:
            volume = Volume(
                name=volume_data.get("name"),
                volume_type=volume_data.get("type", "emptyDir"),
                size=volume_data.get("size", 1),
                path=volume_data.get("path", "/data"),
                pod_id=new_pod.id,
            )
            data.session.add(volume)

        for config_data in pod_config["config"]:
            config = ConfigItem(
                name=config_data.get("name"),
                config_type=config_data.get("type", "env"),
                key=config_data.get("key"),
                value=config_data.get("value"),
                pod_id=new_pod.id,
            )
            data.session.add(config)

        target_node.cpu_cores_avail -= cpu_cores_req
        data.session.flush()

        try:
            network_name = f"pod-network-{new_pod.id}"
            network_id = self.docker_service.create_network(network_name)
            new_pod.docker_network_id = network_id

            for volume in new_pod.volumes:
                volume_name = f"pod-{new_pod.id}-volume-{volume.id}"
                docker_volume = self.docker_service.create_volume(volume_name)
                volume.docker_volume_name = docker_volume

            for container in new_pod.containers:
                env_vars = {}
                for config in new_pod.config_items:
                    if config.config_type == "env":
                        env_vars[config.key] = config.value

                volume_mounts = {}
                for volume in new_pod.volumes:
                    volume_mounts[volume.docker_volume_name] = {
                        "bind": volume.path,
                        "mode": "rw",
                    }

                container_name = f"pod-{new_pod.id}-{container.name}"
                container_id = self.docker_service.create_container(
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
                self.docker_service.start_container(container_id)
                container.status = "running"
                container.docker_status = "running"

            new_pod.health_status = "running"
            data.session.commit()

        except Exception as e:
            self.logger.error(
                f"Error creating Docker resources for rescheduled pod: {str(e)}"
            )

            for container in new_pod.containers:
                if container.docker_container_id:
                    self.docker_service.remove_container(
                        container.docker_container_id, force=True
                    )

            if new_pod.docker_network_id:
                self.docker_service.remove_network(new_pod.docker_network_id)

            for volume in new_pod.volumes:
                if volume.docker_volume_name:
                    self.docker_service.remove_volume(volume.docker_volume_name)

            new_pod.health_status = "failed"
            data.session.commit()
            raise

        return new_pod
