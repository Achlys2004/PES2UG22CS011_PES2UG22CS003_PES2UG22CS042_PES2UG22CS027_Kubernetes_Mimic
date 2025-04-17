import docker

client = docker.from_env()
networks = client.networks.list()

for network in networks:
    if network.name.startswith("pod-network-"):
        print(f"Removing stale network: {network.name}")
        try:
            network.remove()
        except Exception as e:
            print(f"Could not remove {network.name}: {str(e)}")
