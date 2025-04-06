import time
import threading
from flask import current_app
from models import data, Container, Pod, Node, data
from services.docker_service import DockerService
import requests



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

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

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
