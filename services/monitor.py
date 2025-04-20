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


HEARTBEAT_INTERVAL = 60
MAX_HEARTBEAT_INTERVAL = 120
RECOVERY_INTERVAL = 62
RESCHEDULER_INTERVAL = 62


class DockerMonitor:
    def __init__(self, app=None):
        self.app = app
        self.docker_service = DockerService()
        self.running = False
        self.logger = self._setup_logger()
        self.startup_time = datetime.now(timezone.utc)
        self.STARTUP_GRACE_PERIOD = 30
        self.need_rescheduling = False

        self.container_thread = None
        self.health_thread = None
        self.recovery_thread = None
        self.reschedule_thread = None
        self.reap_thread = None

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

            self.container_thread = threading.Thread(target=self.monitor_containers)
            self.container_thread.daemon = True
            self.container_thread.start()
            self.logger.info("Container monitor started")

            self.health_thread = threading.Thread(target=self.monitor_node_health)
            self.health_thread.daemon = True
            self.health_thread.start()
            self.logger.info("Node health monitor started")

            self.recovery_thread = threading.Thread(target=self.attempt_node_recovery)
            self.recovery_thread.daemon = True
            self.recovery_thread.start()
            self.logger.info("Node recovery service started")

            self.reschedule_thread = threading.Thread(target=self.reschedule_pods)
            self.reschedule_thread.daemon = True
            self.reschedule_thread.start()
            self.logger.info("Pod rescheduling service started")

            # Start the reaper thread
            self.reap_thread = threading.Thread(target=self.reap_stale_containers)
            self.reap_thread.daemon = True
            self.reap_thread.start()
            self.logger.info("Container reaper service started")

    def stop(self):
        """Stop all monitoring threads"""
        self.running = False

        threads = [
            self.container_thread,
            self.health_thread,
            self.recovery_thread,
            self.reschedule_thread,
            self.reap_thread,
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

                    data.session.begin()

                    nodes = Node.query.filter(
                        Node.docker_container_id != None,
                        Node.health_status != "permanently_failed",
                    ).all()

                    for node in nodes:
                        try:

                            check_node = Node.query.get(node.id)
                            if check_node is None:
                                self.logger.debug(
                                    f"[MONITOR] Node {node.name} (ID: {node.id}) no longer exists, skipping"
                                )
                                continue

                            container_status = self.docker_service.get_container_info(
                                node.docker_container_id
                            )

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

                    data.session.commit()

                except Exception as e:
                    self.logger.error(f"[MONITOR] Error in container monitor: {str(e)}")
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

                    nodes = Node.query.all()

                    for node in nodes:
                        try:

                            check_node = Node.query.get(node.id)
                            if check_node is None:
                                self.logger.debug(
                                    f"Node ID {node.id} no longer exists, skipping health check"
                                )
                                continue

                            if (
                                node.health_status == "permanently_failed"
                                and len(node.pod_ids) > 0
                            ):
                                self.logger.info(
                                    f"Found permanently failed node {node.name} with pods - triggering rescheduling"
                                )
                                self.need_rescheduling = True
                                continue

                            if node.last_heartbeat is None:
                                continue

                            last_heartbeat = node.last_heartbeat
                            if last_heartbeat.tzinfo is None:
                                last_heartbeat = last_heartbeat.replace(
                                    tzinfo=timezone.utc
                                )

                            interval = (current_time - last_heartbeat).total_seconds()

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

                                if node.recovery_attempts >= node.max_recovery_attempts:
                                    self.logger.error(
                                        f"Node {node.name} marked as permanently failed after {node.recovery_attempts} attempts"
                                    )
                                    node.health_status = "permanently_failed"
                                    self.need_rescheduling = True

                                    if node.docker_container_id:
                                        try:
                                            self.logger.info(
                                                f"[RECOVERY] Stopping container for permanently failed node {node.name}"
                                            )
                                            self.docker_service.stop_container(
                                                node.docker_container_id
                                            )
                                        except Exception as e:
                                            self.logger.error(
                                                f"[RECOVERY] Failed to stop container for node {node.name}: {str(e)}"
                                            )

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
                    data.session.rollback()
                    data.session.expire_all()

                    max_attempts_reached_nodes = Node.query.filter(
                        Node.health_status == "failed",
                        Node.recovery_attempts >= Node.max_recovery_attempts,
                    ).all()

                    for node in max_attempts_reached_nodes:
                        self.logger.error(
                            f"[RECOVERY] Node {node.name} (ID: {node.id}) has reached max recovery attempts, marking as permanently failed"
                        )
                        node.health_status = "permanently_failed"
                        self.need_rescheduling = True

                        if node.docker_container_id:
                            try:
                                self.logger.info(
                                    f"[RECOVERY] Stopping container for permanently failed node {node.name}"
                                )
                                self.docker_service.stop_container(
                                    node.docker_container_id, force=True
                                )
                            except Exception as e:
                                self.logger.error(
                                    f"[RECOVERY] Failed to stop container for node {node.name}: {str(e)}"
                                )

                    if max_attempts_reached_nodes:
                        data.session.commit()

                    failed_nodes = Node.query.filter(
                        Node.health_status == "failed",
                        Node.recovery_attempts < Node.max_recovery_attempts,
                        Node.docker_container_id != None,
                    ).all()

                    if not failed_nodes:
                        time.sleep(10)
                        continue

                    self.logger.info(
                        f"[RECOVERY] Found {len(failed_nodes)} failed nodes to attempt recovery"
                    )

                    for node in failed_nodes:
                        try:

                            data.session.rollback()

                            data.session.begin()

                            check_node = Node.query.get(node.id)
                            if not check_node:
                                self.logger.info(
                                    f"[RECOVERY] Node {node.id} no longer exists, skipping recovery"
                                )
                                data.session.rollback()
                                continue

                            if check_node.health_status != "failed":
                                self.logger.info(
                                    f"[RECOVERY] Node {node.name} (ID: {node.id}) is no longer failed (now: {check_node.health_status}), skipping recovery"
                                )
                                data.session.rollback()
                                continue

                            node.recovery_attempts += 1

                            self.logger.info(
                                f"[RECOVERY] Attempting to recover node {node.name} (ID: {node.id}) - "
                                f"Attempt {node.recovery_attempts}/{node.max_recovery_attempts}"
                            )

                            container_status = self.docker_service.get_container_info(
                                node.docker_container_id
                            )

                            self.logger.info(
                                f"[RECOVERY] Node {node.name} container status is: {container_status}"
                            )

                            if container_status == "running":
                                self.logger.info(
                                    f"[RECOVERY] Node {node.name} container is actually running, marking as recovering and waiting for heartbeat"
                                )
                                node.health_status = "recovering"
                                data.session.commit()
                                continue
                            elif (
                                container_status == "exited"
                                or container_status == "stopped"
                            ):
                                self.logger.info(
                                    f"[RECOVERY] Node {node.name} container is {container_status}, attempting to restart"
                                )
                            else:
                                self.logger.info(
                                    f"[RECOVERY] Node {node.name} container is in state: {container_status}"
                                )

                            container_exists = self.docker_service.container_exists(
                                node.docker_container_id
                            )
                            if not container_exists:
                                self.logger.warning(
                                    f"[RECOVERY] Node {node.name} container does not exist"
                                )

                                if node.recovery_attempts >= node.max_recovery_attempts:
                                    self.logger.error(
                                        f"[RECOVERY] Node {node.name} marked as permanently failed after {node.recovery_attempts} attempts"
                                    )
                                    node.health_status = "permanently_failed"

                                    self.need_rescheduling = True

                                    if node.docker_container_id:
                                        try:
                                            self.logger.info(
                                                f"[RECOVERY] Stopping container for permanently failed node {node.name}"
                                            )
                                            self.docker_service.stop_container(
                                                node.docker_container_id
                                            )
                                        except Exception as e:
                                            self.logger.error(
                                                f"[RECOVERY] Failed to stop container for node {node.name}: {str(e)}"
                                            )

                                data.session.commit()
                                continue
                            else:
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

                                    if (
                                        node.recovery_attempts
                                        >= node.max_recovery_attempts
                                    ):
                                        self.logger.error(
                                            f"[RECOVERY] Node {node.name} marked as permanently failed after {node.recovery_attempts} attempts"
                                        )
                                        node.health_status = "permanently_failed"
                                        self.need_rescheduling = True

                                        if node.docker_container_id:
                                            try:
                                                self.logger.info(
                                                    f"[RECOVERY] Stopping container for permanently failed node {node.name}"
                                                )
                                                self.docker_service.stop_container(
                                                    node.docker_container_id
                                                )
                                            except Exception as e:
                                                self.logger.error(
                                                    f"[RECOVERY] Failed to stop container for node {node.name}: {str(e)}"
                                                )

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

                time.sleep(15)

    def trigger_pod_rescheduling(self):
        self.need_rescheduling = True
        self.logger.info("[RESCHEDULE] Pod rescheduling triggered manually")

    def reschedule_pods(self):
        """Reschedule pods from permanently failed nodes to healthy ones"""
        with self.app.app_context():
            while self.running:
                try:

                    if not self.need_rescheduling:
                        time.sleep(5)
                        continue

                    data.session.rollback()
                    data.session.expire_all()

                    self.logger.info("[RESCHEDULE] Starting pod rescheduling process")

                    failed_nodes = Node.query.filter(
                        Node.health_status == "permanently_failed"
                    ).all()

                    if not failed_nodes:
                        self.logger.info(
                            "[RESCHEDULE] No permanently failed nodes found, clearing rescheduling flag"
                        )
                        self.need_rescheduling = False
                        time.sleep(RESCHEDULER_INTERVAL)
                        continue

                    for failed_node in failed_nodes:

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

                        for pod in pods_to_reschedule:
                            try:

                                data.session.rollback()

                                data.session.begin()

                                current_pod = Pod.query.get(pod.id)
                                if not current_pod:
                                    self.logger.info(
                                        f"[RESCHEDULE] Pod {pod.id} no longer exists, skipping"
                                    )
                                    data.session.rollback()
                                    continue

                                eligible_nodes = Node.query.filter(
                                    Node.cpu_cores_avail >= pod.cpu_cores_req,
                                    Node.health_status == "healthy",
                                    Node.node_type == "worker",
                                    Node.kubelet_status == "running",
                                    Node.container_runtime_status == "running",
                                ).all()

                                if not eligible_nodes:
                                    self.logger.warning(
                                        f"[RESCHEDULE] No eligible nodes found for pod {pod.name} (ID: {pod.id}) requiring {pod.cpu_cores_req} CPU cores"
                                    )

                                    self.logger.info(
                                        f"[RESCHEDULE] Terminating pod {pod.name} (ID: {pod.id}) due to lack of eligible nodes"
                                    )

                                    try:
                                        try:
                                            for container in pod.containers:
                                                self.logger.info(
                                                    f"[RESCHEDULE] Cleaning up container {container.name} for pod {pod.name}"
                                                )

                                        except Exception as container_error:
                                            self.logger.error(
                                                f"[RESCHEDULE] Error cleaning up containers: {str(container_error)}"
                                            )

                                        failed_node.remove_pod(pod.id)

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

                                target_node = min(
                                    eligible_nodes, key=lambda n: n.cpu_cores_avail
                                )

                                self.logger.info(
                                    f"[RESCHEDULE] Selected node {target_node.name} for pod {pod.name} (ID: {pod.id})"
                                )

                                base_ip = "10.244.0.0"
                                network = ipaddress.ip_network(f"{base_ip}/16")
                                random_ip = str(random.choice(list(network.hosts())))

                                try:
                                    pod_spec = build_pod_spec(pod)
                                    pod_spec["ip_address"] = random_ip

                                    if target_node.node_ip:
                                        response = requests.post(
                                            f"http://{target_node.node_ip}:{target_node.node_port}/run_pod",
                                            json={
                                                "pod_id": pod.id,
                                                "pod_spec": pod_spec,
                                            },
                                            timeout=10,
                                        )

                                        if response.status_code != 200:
                                            raise Exception(
                                                f"Target node responded with status {response.status_code}"
                                            )

                                        self.logger.info(
                                            f"Successfully created pod processes on target node {target_node.name}"
                                        )
                                    else:
                                        raise Exception(
                                            "Target node IP address not available"
                                        )

                                except Exception as e:
                                    self.logger.error(
                                        f"Error creating pod processes on target node: {str(e)}"
                                    )
                                    data.session.rollback()
                                    continue

                                failed_node.remove_pod(pod.id)

                                target_node.add_pod(pod.id)

                                target_node.cpu_cores_avail -= pod.cpu_cores_req

                                pod.node_id = target_node.id
                                pod.health_status = "running"

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

                    for failed_node in failed_nodes:
                        if failed_node.docker_container_id:
                            try:
                                self.logger.info(
                                    f"[RESCHEDULE] Cleaning up container for permanently failed node {failed_node.name}"
                                )
                                self.docker_service.stop_container(
                                    failed_node.docker_container_id, is_node=True
                                )
                                time.sleep(2)
                                self.docker_service.remove_container(
                                    failed_node.docker_container_id,
                                    force=True,
                                    is_node=True,
                                )
                                failed_node.docker_container_id = None
                                data.session.commit()
                            except Exception as e:
                                self.logger.error(
                                    f"[RESCHEDULE] Failed to clean up container for node {failed_node.name}: {str(e)}"
                                )

                    self.need_rescheduling = False

                except Exception as e:
                    self.logger.error(
                        f"[RESCHEDULE] Error in pod rescheduling: {str(e)}"
                    )
                    data.session.rollback()

                time.sleep(RESCHEDULER_INTERVAL)

    def reap_stale_containers(self):
        """Periodically clean up containers from permanently failed nodes that weren't properly deleted"""
        with self.app.app_context():
            self.logger.info("[REAP] Container reaper service started")

            while self.running:
                try:
                    stale_nodes = Node.query.filter(
                        Node.health_status == "permanently_failed",
                        Node.docker_container_id != None,
                    ).all()

                    for node in stale_nodes:
                        self.logger.info(
                            f"[REAP] Found stale container for node {node.name}"
                        )

                        try:
                            if self.docker_service.container_exists(
                                node.docker_container_id
                            ):
                                self.logger.info(
                                    f"[REAP] Stopping container for node {node.name}"
                                )
                                self.docker_service.stop_container(
                                    node.docker_container_id, force=True, is_node=True
                                )

                                time.sleep(2)

                                self.logger.info(
                                    f"[REAP] Removing container for node {node.name}"
                                )
                                self.docker_service.remove_container(
                                    node.docker_container_id, force=True, is_node=True
                                )

                            node.docker_container_id = None
                            data.session.commit()
                            self.logger.info(
                                f"[REAP] Successfully cleaned up container for node {node.name}"
                            )

                        except Exception as e:
                            self.logger.error(
                                f"[REAP] Error cleaning up container for node {node.name}: {str(e)}"
                            )
                            data.session.rollback()

                except Exception as e:
                    self.logger.error(f"[REAP] Error in container reaper: {str(e)}")
                    data.session.rollback()

                time.sleep(15)
