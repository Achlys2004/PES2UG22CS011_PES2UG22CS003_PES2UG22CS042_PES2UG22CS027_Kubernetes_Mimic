import docker
import logging
from typing import Dict, List, Optional


class DockerService:
    def __init__(self):
        self.client = docker.from_env()
        self.logger = logging.getLogger(__name__)

    def create_container(
        self,
        name: str,
        image: str,
        command: Optional[str] = None,
        environment: Dict[str, str] = None,
        volumes: List[Dict] = None,
        network: str = None,
        cpu_limit: float = 0.1,
        memory_limit: str = "128m",
    ) -> str:
        """Create a Docker container"""
        try:
            # Pull the image if it doesn't exist
            try:
                self.client.images.get(image)
            except docker.errors.ImageNotFound:
                self.logger.info(f"Pulling image {image}")
                self.client.images.pull(image)

            container = self.client.containers.create(
                image=image,
                name=name,
                command=command,
                environment=environment,
                volumes=volumes,
                network=network,
                cpu_quota=int(cpu_limit * 100000),  # Docker CPU quota in microseconds
                mem_limit=memory_limit,
            )

            return container.id
        except Exception as e:
            self.logger.error(f"Error creating container: {str(e)}")
            raise

    def start_container(self, container_id: str) -> bool:
        """Start a Docker container"""
        try:
            container = self.client.containers.get(container_id)
            container.start()
            return True
        except Exception as e:
            self.logger.error(f"Error starting container: {str(e)}")
            return False

    def stop_container(self, container_id: str) -> bool:
        """Stop a Docker container"""
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=5)
            return True
        except Exception as e:
            self.logger.error(f"Error stopping container: {str(e)}")
            return False

    def remove_container(self, container_id: str, force: bool = False) -> bool:
        """Remove a Docker container"""
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=force)
            return True
        except Exception as e:
            self.logger.error(f"Error removing container: {str(e)}")
            return False

    def create_network(self, name: str) -> str:
        """Create a Docker network for a pod"""
        try:
            network = self.client.networks.create(name, driver="bridge")
            return network.id
        except Exception as e:
            self.logger.error(f"Error creating network: {str(e)}")
            raise

    def remove_network(self, network_id: str) -> bool:
        """Remove a Docker network"""
        try:
            network = self.client.networks.get(network_id)
            network.remove()
            return True
        except Exception as e:
            self.logger.error(f"Error removing network: {str(e)}")
            return False

    def create_volume(self, name: str) -> str:
        """Create a Docker volume"""
        try:
            volume = self.client.volumes.create(name=name)
            return volume.name
        except Exception as e:
            self.logger.error(f"Error creating volume: {str(e)}")
            raise

    def get_container_status(self, container_id: str) -> str:
        """Get container status"""
        try:
            container = self.client.containers.get(container_id)
            return container.status
        except Exception as e:
            self.logger.error(f"Error getting container status: {str(e)}")
            return "unknown"
