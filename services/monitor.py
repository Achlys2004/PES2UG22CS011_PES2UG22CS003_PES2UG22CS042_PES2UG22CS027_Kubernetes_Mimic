import time
import threading
import requests
from models import data, Pod, Node, Volume, ConfigItem
from services.docker_service import DockerService
from datetime import datetime, timezone
import random
import ipaddress
import logging
from routes.pods import build_pod_spec

# Standardized timing intervals
HEARTBEAT_INTERVAL = 60  # seconds
MAX_HEARTBEAT_INTERVAL = 120  # seconds
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
        """Monitor the status of all containers and nodes"""
        with self.app.app_context():
            self.logger.info("[MONITOR] Container monitor started")

            while self.running:
                try:
                    # Create a new session for each check to avoid transaction issues
                    data.session.begin()

                    # First check node containers
                    nodes = Node.query.filter(
                        Node.docker_container_id != None,
                        Node.health_status != "permanently_failed",
                    ).all()

                    for node in nodes:
                        try:
                            # Always verify node still exists before processing
                            check_node = Node.query.get(node.id)
                            if check_node is None:
                                self.logger.debug(
                                    f"[MONITOR] Node {node.name} (ID: {node.id}) no longer exists, skipping"
                                )
                                continue

                            container_status = self.docker_service.get_container_status(
                                node.docker_container_id
                            )

                            # Process container status
                            if container_status == "unknown":
                                if node.health_status == "healthy":
                                    self.logger.warning(
                                        f"[MONITOR] Node {node.name} (ID: {node.id}) container not found, marking as failed"
                                    )
                                    node.health_status = "failed"
                                    node.recovery_attempts += 1
                                    self.need_rescheduling = True

                            elif (
                                container_status != "running"
                                and node.health_status == "healthy"
                            ):
                                self.logger.warning(
                                    f"[MONITOR] Node {node.name} (ID: {node.id}) container is {container_status}, marking as failed"
                                )
                                node.health_status = "failed"
                                node.recovery_attempts += 1
                                self.need_rescheduling = True

                        except Exception as e:
                            self.logger.error(
                                f"[MONITOR] Error checking node container: {str(e)}"
                            )

                    # Commit all changes in a single transaction
                    data.session.commit()

                except Exception as e:
                    self.logger.error(f"[MONITOR] Error in container monitor: {str(e)}")
                    data.session.rollback()

                # Brief pause to avoid excessive database querying
                time.sleep(60)

    def monitor_node_health(self):
        """Monitor the health of nodes based on heartbeats"""
        with self.app.app_context():
            while self.running:
                try:
                    # Ensure we're working with fresh data
                    data.session.expire_all()

                    # Skip during startup grace period
                    current_time = datetime.now(timezone.utc)
                    if (
                        current_time - self.startup_time
                    ).total_seconds() < self.STARTUP_GRACE_PERIOD:
                        time.sleep(5)
                        continue

                    # Get all nodes
                    nodes = Node.query.all()

                    for node in nodes:
                        try:
                            # Verify node still exists in database (in case it was deleted)
                            check_node = Node.query.get(node.id)
                            if check_node is None:
                                self.logger.debug(
                                    f"Node ID {node.id} no longer exists, skipping health check"
                                )
                                continue

                            # Check if node is permanently failed and trigger rescheduling if needed
                            if node.health_status == "permanently_failed" and len(node.pod_ids) > 0:
                                self.logger.info(
                                    f"Found permanently failed node {node.name} with pods - triggering rescheduling"
                                )
                                self.need_rescheduling = True
                                continue

                            # Skip early if no heartbeat data
                            if node.last_heartbeat is None:
                                continue

                            last_heartbeat = node.last_heartbeat
                            if last_heartbeat.tzinfo is None:
                                last_heartbeat = last_heartbeat.replace(
                                    tzinfo=timezone.utc
                                )

                            interval = (current_time - last_heartbeat).total_seconds()

                            # Check heartbeat interval
                            if (
                                interval > node.max_heartbeat_interval
                                and node.health_status == "healthy"
                            ):
                                self.logger.warning(
                                    f"Node {node.name} missed heartbeat for {interval:.1f}s, marking as failed"
                                )
                                node.health_status = "failed"
                                
                                # Increment recovery attempts instead of resetting to 1
                                if node.recovery_attempts is None or node.recovery_attempts == 0:
                                    node.recovery_attempts = 1
                                else:
                                    node.recovery_attempts += 1
                                
                                data.session.commit()

                        except Exception as e:
                            self.logger.error(
                                f"Error checking node {node.id}: {str(e)}"
                            )

                except Exception as e:
                    self.logger.error(f"Error monitoring node health: {str(e)}")
                    data.session.rollback()

                time.sleep(MAX_HEARTBEAT_INTERVAL / 3)

    def attempt_node_recovery(self):
        """Attempt to recover failed nodes by restarting their containers"""
        with self.app.app_context():
            self.logger.info("[RECOVERY] Node recovery service started")

            while self.running:
                try:
                    # Make sure we're not in a transaction
                    data.session.rollback()

                    # Immediately get fresh data on each loop
                    data.session.expire_all()

                    # Find failed nodes that haven't exceeded max recovery attempts
                    failed_nodes = Node.query.filter(
                        Node.health_status == "failed",
                        Node.recovery_attempts < Node.max_recovery_attempts,
                        Node.docker_container_id != None,
                    ).all()

                    if not failed_nodes:
                        time.sleep(10)  # Check more frequently (was RECOVERY_INTERVAL)
                        continue

                    self.logger.info(
                        f"[RECOVERY] Found {len(failed_nodes)} failed nodes to attempt recovery"
                    )

                    # Process each node in its own transaction
                    for node in failed_nodes:
                        try:
                            # Ensure we're not in a transaction
                            data.session.rollback()
                            # Now start a new transaction
                            data.session.begin()

                            # Verify node still exists and is still failed
                            check_node = Node.query.get(node.id)
                            if not check_node:
                                self.logger.info(
                                    f"[RECOVERY] Node {node.id} no longer exists, skipping recovery"
                                )
                                data.session.rollback()
                                continue

                            # Check if node has recovered on its own (e.g., manual intervention)
                            if check_node.health_status != "failed":
                                self.logger.info(
                                    f"[RECOVERY] Node {node.name} (ID: {node.id}) is no longer failed (now: {check_node.health_status}), skipping recovery"
                                )
                                data.session.rollback()
                                continue

                            # Display recovery attempt number starting from 1 instead of 0
                            self.logger.info(
                                f"[RECOVERY] Attempting to recover node {node.name} (ID: {node.id}) - "
                                f"Attempt {node.recovery_attempts}/{node.max_recovery_attempts}"
                            )

                            # Check container status first before attempting recovery
                            container_status = self.docker_service.get_container_status(
                                node.docker_container_id
                            )

                            # If container is actually running, maybe the node just needs time to send heartbeat
                            if container_status == "running":
                                self.logger.info(
                                    f"[RECOVERY] Node {node.name} container is actually running, marking as recovering and waiting for heartbeat"
                                )
                                node.health_status = "recovering"
                                data.session.commit()
                                continue

                            # Check if container exists
                            container_exists = self.docker_service.container_exists(
                                node.docker_container_id
                            )
                            if not container_exists:
                                self.logger.warning(
                                    f"[RECOVERY] Node {node.name} container does not exist"
                                )
                                node.recovery_attempts += 1

                                if node.recovery_attempts >= node.max_recovery_attempts:
                                    self.logger.error(
                                        f"[RECOVERY] Node {node.name} marked as permanently failed after {node.recovery_attempts} attempts"
                                    )
                                    node.health_status = "permanently_failed"
                                    # Only set need_rescheduling when marked permanently failed
                                    self.need_rescheduling = True

                                data.session.commit()
                                continue

                            # Try to restart the container
                            success = self.docker_service.start_container(
                                node.docker_container_id
                            )

                            if success:
                                self.logger.info(
                                    f"[RECOVERY] Node {node.name} container restarted successfully"
                                )
                                node.last_heartbeat = datetime.now(timezone.utc)
                                node.health_status = "recovering"
                                data.session.commit()
                            else:
                                self.logger.warning(
                                    f"[RECOVERY] Failed to restart node {node.name} container"
                                )
                                node.recovery_attempts += 1

                                if node.recovery_attempts >= node.max_recovery_attempts:
                                    self.logger.error(
                                        f"[RECOVERY] Node {node.name} marked as permanently failed"
                                    )
                                    node.health_status = "permanently_failed"
                                    # Only set need_rescheduling when marked permanently failed
                                    self.need_rescheduling = True

                                data.session.commit()

                        except Exception as e:
                            self.logger.error(
                                f"[RECOVERY] Error recovering node: {str(e)}"
                            )
                            data.session.rollback()

                except Exception as e:
                    self.logger.error(
                        f"[RECOVERY] Error in node recovery service: {str(e)}"
                    )
                    try:
                        data.session.rollback()
                    except:
                        pass

                # Check more frequently for faster response
                time.sleep(15)  # Was RECOVERY_INTERVAL (62 seconds)

    def trigger_pod_rescheduling(self):
        """Trigger pod rescheduling from external components"""
        self.need_rescheduling = True
        self.logger.info("Pod rescheduling triggered")

    def reschedule_pods(self):
        """Reschedule pods from permanently failed nodes to healthy ones"""
        with self.app.app_context():
            while self.running:
                try:
                    # If no rescheduling needed, sleep and continue
                    if not self.need_rescheduling:
                        time.sleep(5)
                        continue

                    # Refresh database session and ensure no active transaction
                    data.session.rollback()
                    data.session.expire_all()

                    self.logger.info("[RESCHEDULE] Starting pod rescheduling process")

                    # Only reschedule from permanently failed nodes (not temporarily failed)
                    failed_nodes = Node.query.filter(
                        Node.health_status == "permanently_failed"
                    ).all()

                    # Check if any failed nodes still exist
                    if not failed_nodes:
                        self.logger.info(
                            "[RESCHEDULE] No permanently failed nodes found, clearing rescheduling flag"
                        )
                        self.need_rescheduling = False
                        time.sleep(RESCHEDULER_INTERVAL)
                        continue

                    # Process each failed node
                    for failed_node in failed_nodes:
                        # Get pods on the failed node
                        pods_to_reschedule = Pod.query.filter_by(
                            node_id=failed_node.id
                        ).all()

                        if not pods_to_reschedule:
                            self.logger.info(
                                f"[RESCHEDULE] No pods found on failed node {failed_node.name} (ID: {failed_node.id})"
                            )
                            continue

                        self.logger.info(
                            f"[RESCHEDULE] Found {len(pods_to_reschedule)} pods to reschedule from node {failed_node.name}"
                        )

                        # Process each pod that needs rescheduling
                        for pod in pods_to_reschedule:
                            try:
                                # Ensure any previous transaction is closed
                                data.session.rollback()
                                
                                # Start a new transaction for each pod
                                data.session.begin()

                                # Verify pod still exists and needs rescheduling
                                current_pod = Pod.query.get(pod.id)
                                if not current_pod:
                                    self.logger.info(
                                        f"[RESCHEDULE] Pod {pod.id} no longer exists, skipping"
                                    )
                                    data.session.rollback()
                                    continue

                                # Find eligible nodes with Best-Fit algorithm (same as initial scheduling)
                                eligible_nodes = Node.query.filter(
                                    Node.cpu_cores_avail >= pod.cpu_cores_req,
                                    Node.health_status == "healthy",
                                    Node.node_type == "worker",
                                    Node.kubelet_status == "running",
                                    Node.container_runtime_status == "running",
                                ).all()

                                # Skip if no eligible node found
                                if not eligible_nodes:
                                    self.logger.warning(
                                        f"[RESCHEDULE] No eligible nodes found for pod {pod.name} (ID: {pod.id}) requiring {pod.cpu_cores_req} CPU cores"
                                    )
                                    
                                    # Since no eligible nodes are available, terminate the pod completely
                                    self.logger.info(
                                        f"[RESCHEDULE] Terminating pod {pod.name} (ID: {pod.id}) due to lack of eligible nodes"
                                    )
                                    
                                    try:
                                        try:
                                            for container in pod.containers:
                                                self.logger.info(f"[RESCHEDULE] Cleaning up container {container.name} for pod {pod.name}")
                                                # If we had container IDs stored, we would stop them here
                                        except Exception as container_error:
                                            self.logger.error(f"[RESCHEDULE] Error cleaning up containers: {str(container_error)}")
                                        
                                        # Remove pod from failed node's pod list
                                        failed_node.remove_pod(pod.id)
                                        
                                        # Delete the pod from database (cascade will handle related entities)
                                        data.session.delete(pod)
                                        data.session.commit()
                                        
                                        self.logger.info(
                                            f"[RESCHEDULE] Successfully terminated pod {pod.name} (ID: {pod.id}) due to lack of available nodes"
                                        )
                                    except Exception as delete_error:
                                        self.logger.error(
                                            f"[RESCHEDULE] Error terminating pod {pod.id}: {str(delete_error)}"
                                        )
                                        data.session.rollback()
                                    
                                    continue

                                # Best-Fit: Select node with minimum available resources
                                target_node = min(
                                    eligible_nodes, key=lambda n: n.cpu_cores_avail
                                )

                                self.logger.info(
                                    f"[RESCHEDULE] Selected node {target_node.name} for pod {pod.name} (ID: {pod.id})"
                                )

                                # Generate new IP address for the pod
                                base_ip = "10.244.0.0"
                                network = ipaddress.ip_network(f"{base_ip}/16")
                                random_ip = str(random.choice(list(network.hosts())))

                                # Create pod specification to send to target node
                                try:
                                    pod_spec = build_pod_spec(pod)
                                    pod_spec["ip_address"] = random_ip

                                    # Send request to target node to run pod as processes
                                    if target_node.node_ip:
                                        response = requests.post(
                                            f"http://{target_node.node_ip}:{target_node.node_port}/run_pod",
                                            json={
                                                "pod_id": pod.id,
                                                "pod_spec": pod_spec
                                            },
                                            timeout=10
                                        )
                                        
                                        if response.status_code != 200:
                                            raise Exception(f"Target node responded with status {response.status_code}")
                                        
                                        self.logger.info(f"Successfully created pod processes on target node {target_node.name}")
                                    else:
                                        raise Exception("Target node IP address not available")
                                
                                except Exception as e:
                                    self.logger.error(f"Error creating pod processes on target node: {str(e)}")
                                    data.session.rollback()
                                    continue

                                # Update node assignments
                                # Remove from failed node's pod list
                                failed_node.remove_pod(pod.id)

                                # Add to target node's pod list
                                target_node.add_pod(pod.id)

                                # Update resource allocations
                                target_node.cpu_cores_avail -= pod.cpu_cores_req

                                # Update pod's node assignment
                                pod.node_id = target_node.id
                                pod.health_status = "running"

                                # Notify the target node about the new pod if possible
                                try:
                                    if target_node.node_ip:
                                        requests.post(
                                            f"http://{target_node.node_ip}:5000/pods",
                                            json={
                                                "pod_id": pod.id,
                                                "cpu_cores_req": pod.cpu_cores_req,
                                            },
                                            timeout=5,
                                        )
                                except Exception as e:
                                    self.logger.warning(
                                        f"[RESCHEDULE] Failed to notify target node: {str(e)}"
                                    )

                                # Commit changes for this pod
                                data.session.commit()

                                self.logger.info(
                                    f"[RESCHEDULE] Successfully rescheduled pod {pod.name} (ID: {pod.id}) from node "
                                    f"{failed_node.name} to node {target_node.name}"
                                )

                            except Exception as e:
                                self.logger.error(
                                    f"[RESCHEDULE] Error rescheduling pod {pod.id}: {str(e)}"
                                )
                                data.session.rollback()

                    # Clear rescheduling flag once all failed nodes are processed
                    self.need_rescheduling = False

                except Exception as e:
                    self.logger.error(
                        f"[RESCHEDULE] Error in pod rescheduling: {str(e)}"
                    )
                    data.session.rollback()

                time.sleep(RESCHEDULER_INTERVAL)

    def trigger_pod_rescheduling(self):
        """Directly trigger the pod rescheduling process"""
        self.need_rescheduling = True
        self.logger.info("[RESCHEDULE] Pod rescheduling triggered manually")
