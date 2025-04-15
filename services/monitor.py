import time
import threading
import requests
from models import data, Container, Pod, Node, Volume, ConfigItem
from services.docker_service import DockerService
from datetime import datetime, timedelta, timezone
import random
import ipaddress
import logging
from random import randint

# Standardized timing intervals
HEARTBEAT_INTERVAL = 60  # seconds
MAX_HEARTBEAT_INTERVAL = 90  # seconds
RECOVERY_INTERVAL = 62  # seconds
RESCHEDULER_INTERVAL = 62  # seconds


class DockerMonitor:
    def __init__(self, app=None):
        self.app = app
        self.docker_service = DockerService()
        self.running = False
        self.logger = self._setup_logger()
        self.startup_time = datetime.now(timezone.utc)
        self.STARTUP_GRACE_PERIOD = 30
        self.need_rescheduling = False

        # Initialize threads
        self.container_thread = None
        self.health_thread = None
        self.recovery_thread = None
        self.reschedule_thread = None

        if app is not None:
            self.init_app(app)

    def _setup_logger(self):
        logger = logging.getLogger("kube9.monitor")
        logger.setLevel(logging.INFO)

        if logger.handlers:
            logger.handlers.clear()

        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        formatter = logging.Formatter("%(asctime)s - %(message)s", datefmt="%H:%M:%S")
        ch.setFormatter(formatter)

        logger.addHandler(ch)
        logger.propagate = False
        return logger

    def init_app(self, app):
        self.app = app

    def start(self):
        """Start all monitoring threads"""
        if not self.running:
            self.running = True

            # Start container monitor thread
            self.container_thread = threading.Thread(target=self.monitor_containers)
            self.container_thread.daemon = True
            self.container_thread.start()
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
        """Stop all monitoring threads"""
        self.running = False

        threads = [
            self.container_thread,
            self.health_thread,
            self.recovery_thread,
            self.reschedule_thread,
        ]

        for thread in threads:
            if thread and thread.is_alive():
                thread.join(timeout=5)

        self.logger.info("Kube-9 monitor stopped")

    def monitor_containers(self):
        """Monitor the status of all containers in pods"""
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
                    data.session.rollback()

                time.sleep(60)

    def monitor_node_health(self):
        """Monitor the health of nodes based on heartbeats"""
        with self.app.app_context():
            while self.running:
                try:
                    data.session.expire_all()

                    current_time = datetime.now(timezone.utc)
                    if (
                        current_time - self.startup_time
                    ).total_seconds() < self.STARTUP_GRACE_PERIOD:
                        time.sleep(5)
                        continue

                    nodes = Node.query.filter(
                        Node.health_status != "permanently_failed"
                    ).all()

                    for node in nodes:
                        if node.last_heartbeat is None:
                            continue

                        data.session.refresh(node)

                        last_heartbeat = node.last_heartbeat
                        if last_heartbeat.tzinfo is None:
                            last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)

                        interval = (current_time - last_heartbeat).total_seconds()

                        # Check node Docker container status
                        if node.docker_container_id:
                            container_status = self.docker_service.get_container_status(
                                node.docker_container_id
                            )
                            if container_status not in ["running", "created"]:
                                self.logger.warning(
                                    f"Node {node.name} container not running: {container_status}"
                                )
                                if node.health_status == "healthy":
                                    node.health_status = "failed"
                                    node.recovery_attempts += 1
                                    self.need_rescheduling = True
                                    data.session.commit()

                        # Check heartbeat interval
                        if (
                            interval > node.max_heartbeat_interval
                            and node.health_status == "healthy"
                        ):
                            self.logger.warning(
                                f"Node {node.name} missed heartbeat for {interval:.1f}s, marking as failed"
                            )
                            node.health_status = "failed"
                            node.recovery_attempts += 1
                            self.need_rescheduling = True
                            data.session.commit()

                except Exception as e:
                    self.logger.error(f"Error monitoring node health: {str(e)}")
                    data.session.rollback()

                time.sleep(
                    MAX_HEARTBEAT_INTERVAL / 3
                )  # Check multiple times within max interval

    def attempt_node_recovery(self):
        """Attempt to recover failed nodes by restarting their containers"""
        with self.app.app_context():
            while self.running:
                try:
                    # Find failed nodes with recovery attempts less than max
                    failed_nodes = Node.query.filter(
                        Node.health_status == "failed",
                        Node.recovery_attempts <= Node.max_recovery_attempts,
                    ).all()

                    for node in failed_nodes:
                        self.logger.info(
                            f"Attempting to recover node {node.name} (Attempt {node.recovery_attempts})"
                        )

                        # Check if node container exists
                        if node.docker_container_id:
                            # Try to restart the container
                            success = self.docker_service.start_container(
                                node.docker_container_id
                            )

                            if success:
                                self.logger.info(
                                    f"Node {node.name} container restarted successfully"
                                )
                                # Reset heartbeat to give it time to report in
                                node.last_heartbeat = datetime.now(timezone.utc)
                                node.health_status = "recovering"
                                data.session.commit()
                            else:
                                self.logger.warning(
                                    f"Failed to restart node {node.name} container"
                                )
                                node.recovery_attempts += 1
                                if node.recovery_attempts > node.max_recovery_attempts:
                                    node.health_status = "permanently_failed"
                                    self.logger.error(
                                        f"Node {node.name} marked as permanently failed after {node.recovery_attempts} attempts"
                                    )
                                    self.need_rescheduling = True
                                data.session.commit()
                        else:
                            # No container ID, can't recover
                            self.logger.error(
                                f"Node {node.name} has no container ID, can't recover"
                            )
                            node.health_status = "permanently_failed"
                            self.need_rescheduling = True
                            data.session.commit()

                except Exception as e:
                    self.logger.error(f"Error in node recovery: {str(e)}")
                    data.session.rollback()

                time.sleep(RECOVERY_INTERVAL)

    def trigger_pod_rescheduling(self):
        """Trigger pod rescheduling from external components"""
        self.need_rescheduling = True
        self.logger.info("Pod rescheduling triggered")

    def reschedule_pods(self):
        """Reschedule pods from failed nodes to healthy ones"""
        with self.app.app_context():
            while self.running:
                try:
                    if not self.need_rescheduling:
                        time.sleep(5)  # Short sleep if no rescheduling needed
                        continue

                    self.logger.info("Starting pod rescheduling process")

                    # Find failed/permanently failed nodes with pods
                    failed_nodes = Node.query.filter(
                        Node.health_status.in_(["failed", "permanently_failed"]),
                    ).all()

                    for failed_node in failed_nodes:
                        # Get pods on the failed node
                        pods_to_reschedule = Pod.query.filter(
                            Pod.node_id == failed_node.id,
                            ~Pod.health_status.in_(["terminated", "failed"]),
                        ).all()

                        if not pods_to_reschedule:
                            continue

                        self.logger.info(
                            f"Found {len(pods_to_reschedule)} pods to reschedule from node {failed_node.name}"
                        )

                        # Find healthy nodes with sufficient resources
                        healthy_nodes = Node.query.filter(
                            Node.health_status == "healthy",
                            Node.node_type == "worker",
                            Node.kubelet_status == "running",
                            Node.container_runtime_status == "running",
                        ).all()

                        # Sort healthy nodes by available CPU (most to least)
                        healthy_nodes.sort(
                            key=lambda n: n.cpu_cores_avail, reverse=True
                        )

                        # Reschedule each pod
                        for pod in pods_to_reschedule:
                            self.logger.info(
                                f"Rescheduling pod {pod.name} (requires {pod.cpu_cores_req} CPU cores)"
                            )

                            # Find node with enough resources
                            target_node = None
                            for node in healthy_nodes:
                                if node.cpu_cores_avail >= pod.cpu_cores_req:
                                    target_node = node
                                    break

                            if not target_node:
                                self.logger.warning(
                                    f"No suitable node found to reschedule pod {pod.name}"
                                )
                                continue

                            self.logger.info(
                                f"Rescheduling pod {pod.name} to node {target_node.name}"
                            )

                            # Update node resource tracking
                            old_node_id = pod.node_id

                            # Return resources to failed node for accounting purposes
                            failed_node.cpu_cores_avail += pod.cpu_cores_req

                            # Update resources on target node
                            target_node.cpu_cores_avail -= pod.cpu_cores_req

                            # Update pod's node ID
                            pod.node_id = target_node.id
                            pod.health_status = "rescheduled"

                            # Update node's pod lists
                            if pod.id in failed_node.pod_ids:
                                failed_node.remove_pod(pod.id)
                            target_node.add_pod(pod.id)

                            # Notify the new node about pod assignment
                            if target_node.node_ip:
                                try:
                                    requests.post(
                                        f"http://{target_node.node_ip}:5000/pods",
                                        json={
                                            "pod_id": pod.id,
                                            "cpu_cores_req": pod.cpu_cores_req,
                                        },
                                        timeout=5,
                                    )
                                    self.logger.info(
                                        f"Notified node {target_node.name} about new pod assignment"
                                    )
                                except Exception as e:
                                    self.logger.warning(
                                        f"Failed to notify target node about pod assignment: {str(e)}"
                                    )

                            self.logger.info(
                                f"Pod {pod.name} (ID: {pod.id}) rescheduled: "
                                f"Node {old_node_id} → Node {target_node.id}"
                            )

                            data.session.commit()

                    self.need_rescheduling = False  # Reset flag after processing

                except Exception as e:
                    self.logger.error(f"Error in pod rescheduling: {str(e)}")
                    data.session.rollback()

                time.sleep(RESCHEDULER_INTERVAL)
