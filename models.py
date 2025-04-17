from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import json

data = SQLAlchemy()


class Node(data.Model):
    __tablename__ = "nodes"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), unique=True, nullable=False)
    node_type = data.Column(data.String(20), default="worker")
    cpu_cores_avail = data.Column(data.Integer, nullable=False)
    cpu_cores_total = data.Column(data.Integer, nullable=False)  # Total cores
    health_status = data.Column(data.String(20), default="healthy")

    # Docker container representing the node
    docker_container_id = data.Column(data.String(64), nullable=True)
    node_ip = data.Column(data.String(15), nullable=True)
    node_port = data.Column(data.Integer, default=5000)

    # Node components status
    kubelet_status = data.Column(data.String(20), default="running")
    container_runtime_status = data.Column(data.String(20), default="running")
    kube_proxy_status = data.Column(data.String(20), default="running")
    node_agent_status = data.Column(data.String(20), default="running")

    # Master node specific components
    api_server_status = data.Column(data.String(20), nullable=True)
    scheduler_status = data.Column(data.String(20), nullable=True)
    controller_status = data.Column(data.String(20), nullable=True)
    etcd_status = data.Column(data.String(20), nullable=True)

    # Heartbeat tracking
    last_heartbeat = data.Column(data.DateTime)
    heartbeat_interval = data.Column(data.Integer, default=60)  # 1 minute
    max_heartbeat_interval = data.Column(
        data.Integer, default=120
    )  # 2 minutes 

    # Recovery tracking
    recovery_attempts = data.Column(data.Integer, default=0)
    max_recovery_attempts = data.Column(data.Integer, default=3)

    # Store pod_ids as JSON string
    _pod_ids = data.Column(data.Text, default="[]")

    # Relationship with pods
    pods = data.relationship(
        "Pod", backref="node", lazy=True, cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        super(Node, self).__init__(**kwargs)
        self.last_heartbeat = datetime.now(timezone.utc)
        self.health_status = "healthy"
        self.cpu_cores_total = kwargs.get("cpu_cores_avail", 0)
        self._pod_ids = "[]"

    @property
    def pod_ids(self):
        """Get list of pod IDs hosted on this node"""
        return json.loads(self._pod_ids)

    @pod_ids.setter
    def pod_ids(self, value):
        """Set list of pod IDs hosted on this node"""
        self._pod_ids = json.dumps(value)

    def add_pod(self, pod_id):
        """Add a pod ID to this node's pod list"""
        pods = self.pod_ids
        if pod_id not in pods:
            pods.append(pod_id)
            self.pod_ids = pods

    def remove_pod(self, pod_id):
        """Remove a pod ID from this node's pod list"""
        pods = self.pod_ids
        if pod_id in pods:
            pods.remove(pod_id)
            self.pod_ids = pods

    def update_heartbeat(self):
        """Update node heartbeat"""
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
