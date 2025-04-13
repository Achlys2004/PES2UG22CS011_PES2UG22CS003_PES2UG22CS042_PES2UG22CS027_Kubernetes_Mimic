from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

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

    last_heartbeat = data.Column(data.DateTime)
    heartbeat_interval = data.Column(data.Integer, default=60)  # 1 minute
    pods = data.relationship(
        "Pod", backref="node", lazy=True, cascade="all, delete-orphan"
    )

    max_heartbeat_interval = data.Column(data.Integer, default=90)  # 1.5 minutes
    recovery_attempts = data.Column(data.Integer, default=0)
    max_recovery_attempts = data.Column(data.Integer, default=3)

    def __init__(self, **kwargs):
        super(Node, self).__init__(**kwargs)
        self.last_heartbeat = datetime.now(timezone.utc)
        self.health_status = "healthy"

    def update_heartbeat(self):
        """Update node heartbeat without nested transaction"""
        try:
            self.last_heartbeat = datetime.now(timezone.utc)
            self.health_status = "healthy"

            self.kubelet_status = "running"
            self.container_runtime_status = "running"
            self.kube_proxy_status = "running"
            self.node_agent_status = "running"

            if self.node_type == "master":
                self.api_server_status = "running"
                self.scheduler_status = "running"
                self.controller_status = "running"
                self.etcd_status = "running"
            data.session.commit()
        except Exception:
            data.session.rollback()
            raise

    def calculate_heartbeat_interval(self, current_time):
        if self.last_heartbeat is None:
            return float("inf")
        interval = (current_time - self.last_heartbeat).total_seconds()
        return interval


class Pod(data.Model):
    __tablename__ = "pods"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), unique=True, nullable=False)
    cpu_cores_req = data.Column(data.Integer, nullable=False)
    node_id = data.Column(data.Integer, data.ForeignKey("nodes.id"), nullable=False)
    health_status = data.Column(data.String(20), default="pending")

    ip_address = data.Column(data.String(15), nullable=True)

    pod_type = data.Column(data.String(20), default="single-container")

    has_volumes = data.Column(data.Boolean, default=False)
    has_config = data.Column(data.Boolean, default=False)

    docker_network_id = data.Column(data.String(64), nullable=True)

    containers = data.relationship(
        "Container", backref="pod", lazy=True, cascade="all, delete-orphan"
    )


class Container(data.Model):
    __tablename__ = "containers"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), nullable=False)
    image = data.Column(data.String(100), nullable=False)
    status = data.Column(data.String(20), default="pending")
    pod_id = data.Column(data.Integer, data.ForeignKey("pods.id"), nullable=False)

    cpu_req = data.Column(data.Float, default=0.1)
    memory_req = data.Column(data.Integer, default=128)

    command = data.Column(data.String(200), nullable=True)
    args = data.Column(data.String(200), nullable=True)

    docker_container_id = data.Column(data.String(64), nullable=True)
    docker_status = data.Column(data.String(20), nullable=True)
    exit_code = data.Column(data.Integer, nullable=True)


class Volume(data.Model):
    __tablename__ = "volumes"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), nullable=False)
    volume_type = data.Column(data.String(20), default="emptyDir")
    size = data.Column(data.Integer, default=1)
    path = data.Column(data.String(200), nullable=False)
    pod_id = data.Column(data.Integer, data.ForeignKey("pods.id"), nullable=False)

    docker_volume_name = data.Column(data.String(64), nullable=True)

    pod = data.relationship(
        "Pod",
        backref=data.backref("volumes", lazy=True, cascade="all, delete-orphan"),
        lazy=True,
    )


class ConfigItem(data.Model):
    __tablename__ = "config_items"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), nullable=False)
    config_type = data.Column(data.String(20), default="env")
    key = data.Column(data.String(100), nullable=False)
    value = data.Column(data.String(500), nullable=False)
    pod_id = data.Column(data.Integer, data.ForeignKey("pods.id"), nullable=False)

    pod = data.relationship(
        "Pod",
        backref=data.backref("config_items", lazy=True, cascade="all, delete-orphan"),
        lazy=True,
    )
