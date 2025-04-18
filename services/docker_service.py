import docker
import logging
import os
import socket
import time
import requests
from typing import Dict, List, Optional


class DockerService:
    def __init__(self):
        self.client = docker.from_env()
        self.logger = logging.getLogger(__name__)
        self.node_network_name = "kube9-node-network"
        self._ensure_node_network()

    def _ensure_node_network(self):
        """Ensure the node network exists"""
        try:
            # Check if the network exists
            networks = self.client.networks.list(names=[self.node_network_name])
            if not networks:
                self.client.networks.create(
                    name=self.node_network_name, driver="bridge", check_duplicate=True
                )
                self.logger.info(f"Created network {self.node_network_name}")
            else:
                self.logger.info(f"Network {self.node_network_name} already exists")
        except Exception as e:
            self.logger.error(f"Failed to ensure node network: {str(e)}")

    def get_host_ip(self):
        """Get the host IP address to allow containers to connect back to API server"""
        try:
            hostname = socket.gethostname()
            host_ip = socket.gethostbyname(hostname)
            return host_ip
        except Exception:
            # Default to host.docker.internal for Docker Desktop on Windows/Mac
            return "host.docker.internal"

    def create_node_container(
        self, node_id, node_name, cpu_cores, node_type="worker", api_server="http://localhost:5000"
    ):
        """Create a Docker container to simulate a node"""
        try:
            # Change this line to:
            api_server = "http://host.docker.internal:5000"
            
            # Try to remove any existing containers with the same name
            container_name = f"kube9-node-{node_name}"
            try:
                existing = self.client.containers.get(container_name)
                self.logger.warning(
                    f"Found existing container named {container_name}, removing it"
                )
                existing.remove(force=True)
            except:
                pass  # Container doesn't exist, which is fine

            # Generate a unique host port for this node (5000 + node_id)
            host_port = 5000 + node_id

            # Build node simulator image if it doesn't exist
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

            # Create the container with proper port mapping
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
                ports={"5000/tcp": host_port},  # Map container's 5000 to host_port
                restart_policy={"Name": "unless-stopped"},
                cpu_quota=int(cpu_cores * 100000),  # Docker CPU quota in microseconds
                mem_limit=f"{cpu_cores * 512}m",  # 512MB per CPU core
                extra_hosts={
                    "host.docker.internal": "host-gateway"
                },  # Important for connectivity
            )

            # Wait a moment for the container to start
            time.sleep(2)

            # Use localhost and mapped port instead of container IP
            return container.id, "localhost", host_port  # Return container ID, localhost, and the mapped host port
        except Exception as e:
            self.logger.error(f"Failed to create node container: {str(e)}")
            raise

    def stop_node_container(self, container_id: str) -> bool:
        """Stop a node container"""
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=10)
            return True
        except Exception as e:
            self.logger.error(f"Failed to stop node container: {str(e)}")
            return False

    def remove_node_container(self, container_id: str) -> bool:
        """Remove a node container"""
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=True)
            return True
        except Exception as e:
            self.logger.error(f"Failed to remove node container: {str(e)}")
            return False

    # Original container methods
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

    def stop_container(self, container_id: str) -> bool:
        """Stop a Docker container"""
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=5)
            return True
        except Exception as e:
            self.logger.error(f"Detailed error: {type(e).__name__}: {str(e)}")
            return False

    def remove_container(self, container_id: str, force: bool = False) -> bool:
        """Remove a Docker container"""
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=force)
            return True
        except Exception as e:
            self.logger.error(f"Detailed error: {type(e).__name__}: {str(e)}")
            return False

    def create_network(self, name: str) -> str:
        """Create a Docker network for a pod, handling existing networks"""
        try:
            # Check if network already exists
            try:
                existing_networks = self.client.networks.list(names=[name])
                if existing_networks:
                    self.logger.info(
                        f"Network {name} already exists, removing it first"
                    )
                    for network in existing_networks:
                        try:
                            network.remove()
                        except Exception as e:
                            self.logger.warning(
                                f"Error removing existing network {name}: {str(e)}"
                            )
                    # Brief pause to ensure network is removed
                    time.sleep(1)
            except Exception as e:
                self.logger.warning(
                    f"Error checking for existing network {name}: {str(e)}"
                )

            # Create the network (with retry if needed)
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    network = self.client.networks.create(name, driver="bridge")
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

    def get_container_status(self, container_id: str) -> str:
        """Get container status safely"""
        if not container_id:
            return "unknown"

        try:
            container = self.client.containers.get(container_id)
            return container.status
        except Exception as e:
            self.logger.warning(
                f"Container {container_id} status check failed: {str(e)}"
            )
            return "unknown"

    def get_node_container_info(self, container_id: str) -> dict:
        """Get node container information"""
        try:
            container = self.client.containers.get(container_id)
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
            self.logger.error(f"Failed to get node container info: {str(e)}")
            return {"status": "unknown"}

    def container_exists(self, container_id):
        """Check if container exists more robustly"""
        if not container_id:
            return False

        try:
            self.client.containers.get(container_id)
            return True
        except Exception:
            return False

    def check_container_responsiveness(self, container_ip, timeout=2):
        """Check if a container is responsive by making an HTTP request"""
        try:
            response = requests.get(
                f"http://{container_ip}:5000/status", timeout=timeout
            )
            return response.status_code == 200
        except Exception:
            return False
