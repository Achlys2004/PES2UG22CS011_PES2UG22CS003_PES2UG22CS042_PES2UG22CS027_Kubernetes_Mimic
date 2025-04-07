import time
import threading
from flask import current_app
from models import data, Container, Pod, Node, data
from services.docker_service import DockerService
import requests
from datetime import datetime, timedelta



class DockerMonitor:
    def __init__(self, app=None):
        self.app = app
        self.docker_service = DockerService()
        self.thread = None
        self.running = False

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.app = app

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.running = True
            self.thread = threading.Thread(target=self._monitor_containers)
            self.thread.daemon = True
            self.thread.start()
            self.health_thread = threading.Thread(target=self._monitor_node_health)
            self.health_thread.daemon = True
            self.health_thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        if self.health_thread:
            self.health_thread.join(timeout=5)

    def _monitor_containers(self):
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

                            data.session.commit()

                except Exception as e:
                    current_app.logger.error(f"Error in container monitor: {str(e)}")

                time.sleep(10)

    def _monitor_node_health(self):
        with self.app.app_context():
            while self.running:
                try:
                    threshold = datetime.now() - timedelta(seconds=90)
                    stale_nodes = Node.query.filter(
                        (Node.last_heartbeat < threshold) |
                        (Node.last_heartbeat == None)
                    ).all()

                    for node in stale_nodes:
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
                    current_app.logger.error(f"Error in node health monitor: {str(e)}")
                time.sleep(60)
    
    def send_heartbeat(self, node_id):
        with self.app.app_context():
            node = Node.query.get(node_id)
            if node:
                node.last_heartbeat = datetime.now()
                data.session.commit()
                return True
            return False
