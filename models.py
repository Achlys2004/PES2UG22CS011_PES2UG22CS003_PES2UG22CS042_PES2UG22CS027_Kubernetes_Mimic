from flask_sqlalchemy import SQLAlchemy

data = SQLAlchemy()


class Node(data.Model):
    __tablename__ = "nodes"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), unique=True, nullable=False)
    node_type = data.Column(data.String(20), default="worker")
    cpu_cores_avail = data.Column(data.Integer, nullable=False)
    health_status = data.Column(data.String(20), default="healthy")

    kubelet_status = data.Column(data.String(20), default="running")
    container_runtime_status = data.Column(data.String(20), default="running")
    kube_proxy_status = data.Column(data.String(20), default="running")
    node_agent_status = data.Column(data.String(20), default="running")

    api_server_status = data.Column(data.String(20), nullable=True)
    scheduler_status = data.Column(data.String(20), nullable=True)
    controller_status = data.Column(data.String(20), nullable=True)
    etcd_status = data.Column(data.String(20), nullable=True)

    pods = data.relationship("Pod", backref="node", lazy=True)


class Pod(data.Model):
    __tablename__ = "pods"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), unique=True, nullable=False)
    cpu_cores_req = data.Column(data.Integer, nullable=False)
    node_id = data.Column(data.Integer, data.ForeignKey("nodes.id"), nullable=False)
    health_status = data.Column(data.String(20), default="pending")

    # Pod networking
    ip_address = data.Column(data.String(15), nullable=True)  # Internal IP address

    # Pod type
    pod_type = data.Column(
        data.String(20), default="single-container"
    )  # single-container or multi-container

    # Pod storage and configuration flags
    has_volumes = data.Column(data.Boolean, default=False)
    has_config = data.Column(data.Boolean, default=False)

    # Relationship to containers
    containers = data.relationship(
        "Container", backref="pod", lazy=True, cascade="all, delete-orphan"
    )


class Container(data.Model):
    __tablename__ = "containers"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), nullable=False)
    image = data.Column(data.String(100), nullable=False)  # Docker image name
    status = data.Column(
        data.String(20), default="pending"
    )  # pending, running, failed, etc.
    pod_id = data.Column(data.Integer, data.ForeignKey("pods.id"), nullable=False)

    # Container resources
    cpu_req = data.Column(data.Float, default=0.1)  # CPU cores requested
    memory_req = data.Column(data.Integer, default=128) 

    # Container startup properties
    command = data.Column(data.String(200), nullable=True)
    args = data.Column(data.String(200), nullable=True)


class Volume(data.Model):
    __tablename__ = "volumes"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), nullable=False)
    volume_type = data.Column(
        data.String(20), default="emptyDir"
    )  # emptyDir, hostPath, configMap, etc.
    size = data.Column(data.Integer, default=1)  # Size in GB
    path = data.Column(data.String(200), nullable=False)  # Mount path in container
    pod_id = data.Column(data.Integer, data.ForeignKey("pods.id"), nullable=False)

    # Relationship
    pod = data.relationship("Pod", backref="volumes", lazy=True)


class ConfigItem(data.Model):
    __tablename__ = "config_items"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), nullable=False)
    config_type = data.Column(data.String(20), default="env")  # env, secret, configMap
    key = data.Column(data.String(100), nullable=False)
    value = data.Column(data.String(500), nullable=False)
    pod_id = data.Column(data.Integer, data.ForeignKey("pods.id"), nullable=False)

    # Relationship
    pod = data.relationship("Pod", backref="config_items", lazy=True)
