import docker
import logging
import os
import socket
import time
import requests
from typing import Dict, List, Optional, Union


class DockerService:
    def __init__(self):
        self.client = docker.from_env()
        self.logger = logging.getLogger(__name__)
        self.node_network_name = "kube9-node-network"
        self.create_network(self.node_network_name, ensure_exists=True)

    def get_host_ip(self):
        """Get the host IP address to allow containers to connect back to API server"""
        try:
            hostname = socket.gethostname()
            host_ip = socket.gethostbyname(hostname)
            return host_ip
        except Exception:
            return "host.docker.internal"

    def create_node_container(
        self,
        node_id,
        node_name,
        cpu_cores,
        node_type="worker",
        api_server="http://localhost:5000",
    ):
        """Create a Docker container to simulate a node"""
        try:

            api_server = "http://host.docker.internal:5000"

            container_name = f"kube9-node-{node_name}"
            try:
                existing = self.client.containers.get(container_name)
                self.logger.warning(
                    f"Found existing container named {container_name}, removing it"
                )
                existing.remove(force=True)
            except:
                pass

            host_port = 5000 + node_id

            try:
                self.client.images.get("kube9-node-simulator")
                self.logger.info("Using existing kube9-node-simulator image")
            except docker.errors.ImageNotFound:
                self.logger.info("Building kube9-node-simulator image...")
                node_sim_dir = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), "node_simulation"
                )
                self.client.images.build(
                    path=node_sim_dir, tag="kube9-node-simulator", rm=True
                )
                self.logger.info("kube9-node-simulator image built successfully")

            container = self.client.containers.run(
                image="kube9-node-simulator",
                name=container_name,
                detach=True,
                environment={
                    "NODE_ID": str(node_id),
                    "NODE_NAME": node_name,
                    "CPU_CORES": str(cpu_cores),
                    "NODE_TYPE": node_type,
                    "API_SERVER": api_server,
                },
                network=self.node_network_name,
                ports={"5000/tcp": host_port},
                restart_policy={"Name": "unless-stopped"},
                cpu_quota=int(cpu_cores * 100000),
                mem_limit=f"{cpu_cores * 512}m",
                extra_hosts={"host.docker.internal": "host-gateway"},
            )

            time.sleep(2)

            return container.id, "localhost", host_port
        except Exception as e:
            self.logger.error(f"Failed to create node container: {str(e)}")
            raise

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
                cpu_quota=int(cpu_limit * 100000),
                mem_limit=memory_limit,
            )

            return container.id
        except Exception as e:
            self.logger.error(f"Detailed error: {type(e).__name__}: {str(e)}")
            raise

    def start_container(self, container_id: str) -> bool:
        """Start a Docker container"""
        try:
            container = self.client.containers.get(container_id)
            container.start()
            return True
        except Exception as e:
            self.logger.error(f"Detailed error: {type(e).__name__}: {str(e)}")
            return False

    def stop_container(
        self, container_id: str, force: bool = False, is_node: bool = False
    ) -> bool:
        if not container_id:
            return False

        try:
            container = self.client.containers.get(container_id)

            if container.status == "exited":
                self.logger.info(f"Container {container_id} is already stopped")
                return True

            # Stop the container with a timeout
            timeout = 1 if force else 10
            container.stop(timeout=timeout)

            container_type = "node container" if is_node else "container"
            self.logger.info(f"Stopped {container_type} {container_id}")
            return True
        except Exception as e:
            container_type = "node container" if is_node else "container"
            self.logger.error(f"Failed to stop {container_type}: {str(e)}")
            return False

    def remove_container(
        self, container_id: str, force: bool = False, is_node: bool = False
    ) -> bool:

        if not container_id:
            return False

        try:
            container = self.client.containers.get(container_id)

            force_remove = True if is_node else force
            container.remove(force=force_remove)

            container_type = "node container" if is_node else "container"
            self.logger.info(f"Removed {container_type} {container_id}")
            return True
        except Exception as e:
            container_type = "node container" if is_node else "container"
            self.logger.error(f"Failed to remove {container_type}: {str(e)}")
            return False

    def create_network(self, name: str, ensure_exists: bool = False) -> str:

        try:

            existing_networks = self.client.networks.list(names=[name])

            if existing_networks:
                if ensure_exists:
                    self.logger.info(f"Network {name} already exists")
                    return existing_networks[0].id

                self.logger.info(f"Network {name} already exists, removing it first")
                for network in existing_networks:
                    try:
                        network.remove()
                    except Exception as e:
                        self.logger.warning(
                            f"Error removing existing network {name}: {str(e)}"
                        )

                time.sleep(1)

            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    network = self.client.networks.create(name, driver="bridge")
                    self.logger.info(f"Created network {name}")
                    return network.id
                except docker.errors.APIError as e:
                    if "already exists" in str(e) and attempt < max_attempts - 1:
                        self.logger.warning(
                            f"Network {name} still exists, retrying after delay..."
                        )
                        time.sleep(2)
                    else:
                        raise
        except Exception as e:
            self.logger.error(f"Failed to create network {name}: {str(e)}")
            raise

    def remove_network(self, network_id: str) -> bool:
        """Remove a Docker network"""
        try:
            network = self.client.networks.get(network_id)
            network.remove()
            return True
        except Exception as e:
            self.logger.error(f"Detailed error: {type(e).__name__}: {str(e)}")
            return False

    def create_volume(self, name: str) -> str:
        """Create a Docker volume"""
        try:
            volume = self.client.volumes.create(name=name)
            return volume.name
        except Exception as e:
            self.logger.error(f"Detailed error: {type(e).__name__}: {str(e)}")
            raise

    def remove_volume(self, volume_name: str) -> bool:
        """Remove a Docker volume"""
        try:
            volume = self.client.volumes.get(volume_name)
            volume.remove()
            return True
        except Exception as e:
            self.logger.error(f"Detailed error: {type(e).__name__}: {str(e)}")
            return False

    def container_exists(self, container_id):
        """Check if container exists"""
        if not container_id:
            return False
        return self.get_container_info(container_id) != "unknown"

    def check_container_responsiveness(self, container_ip, timeout=2):
        """Check if a container is responsive by making an HTTP request"""
        try:
            response = requests.get(
                f"http://{container_ip}:5000/status", timeout=timeout
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_container_info(
        self, container_id: str, detailed: bool = False
    ) -> Union[str, dict]:

        if not container_id:
            return "unknown" if not detailed else {"status": "unknown"}

        try:
            container = self.client.containers.get(container_id)

            if not detailed:
                return container.status

            container.reload()

            network_settings = container.attrs["NetworkSettings"]["Networks"]
            if self.node_network_name in network_settings:
                ip = network_settings[self.node_network_name]["IPAddress"]
            else:
                ip = next(iter(network_settings.values()))["IPAddress"]

            port_bindings = container.attrs["NetworkSettings"]["Ports"].get(
                "5000/tcp", []
            )
            port = int(port_bindings[0]["HostPort"]) if port_bindings else 5000

            return {
                "container_id": container.id,
                "status": container.status,
                "ip": ip,
                "port": port,
            }
        except Exception as e:
            self.logger.warning(f"Container {container_id} info check failed: {str(e)}")
            return "unknown" if not detailed else {"status": "unknown"}
