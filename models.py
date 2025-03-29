from enum import unique
from flask_sqlalchemy import SQLAlchemy
from numpy import unicode_

data = SQLAlchemy()


class Node(data.Model):
    __tablename__ = "nodes"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), unique=True, nullable=False)
    cpu_cores_avail = data.Column(data.Integer, nullable=False)
    health_status = data.Column(data.String(20), default="healthy") #Could be healthy or failed

    pods = data.relationship("Pod", backref="node", lazy=True)


class Pod(data.Model):
    __tablename__ = "pods"

    id = data.Column(data.Integer, primary_key=True)
    name = data.Column(data.String(40), unique=True, nullable=False)
    cpu_cores_req = data.Column(data.Integer, nullable=False)
    node_id = data.Column(data.Integer, data.ForeignKey("nodes.id"), nullable=False)
    health_status = data.Column(data.String(20), default="pending") #Could be running, pending or failed
