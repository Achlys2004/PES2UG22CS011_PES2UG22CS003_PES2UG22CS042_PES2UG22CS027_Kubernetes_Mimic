from flask import Flask
from sqlalchemy import text
from config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS
from models import data, Node
from routes.nodes import nodes_bp, init_routes
from routes.pods import pods_bp
from flask_migrate import Migrate
from services.monitor import DockerMonitor
import logging
import signal
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


file_handler = logging.FileHandler("kube9.log")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)


logging.getLogger("").addHandler(file_handler)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS

data.init_app(app)
docker_monitor = DockerMonitor(app)
app.config["DOCKER_MONITOR"] = docker_monitor
migrate = Migrate(app, data)

app.register_blueprint(nodes_bp, url_prefix="/nodes")
app.register_blueprint(pods_bp, url_prefix="/pods")

with app.app_context():
    init_routes(app)


@app.route("/")
def home():
    return "Kube_9 API is running!"


@app.route("/test_db")
def test_db():
    try:
        with app.app_context():
            data.session.execute(text("SELECT 1"))
        return "Database Connected!"
    except Exception as e:
        return f"Database Connection failed: {str(e)}"


def cleanup_initializing_nodes():
    with app.app_context():
        try:

            nodes = Node.query.filter_by(health_status="permanently_failed").all()

            for node in nodes:

                if node.last_heartbeat is None:
                    app.logger.warning(
                        f"Removing node {node.name} that are permanently failed for a fresh start"
                    )

                    if node.docker_container_id:
                        try:
                            from services.docker_service import DockerService

                            docker_service = DockerService()
                            docker_service.stop_container(
                                node.docker_container_id, is_node=True
                            )
                            docker_service.remove_container(
                                node.docker_container_id, is_node=True, force=True
                            )
                        except Exception as e:
                            app.logger.warning(f"Error cleaning up container: {str(e)}")

                    data.session.delete(node)

            data.session.commit()
            app.logger.info("stale nodes cleanup complete")
        except Exception as e:
            app.logger.error(f"Error cleaning up stale nodes: {str(e)}")
            data.session.rollback()


def graceful_exit(signal, frame):
    print("\nShutting down Kube-9 Container Orchestration System...")
    docker_monitor.stop()
    with app.app_context():
        data.session.remove()
        data.engine.dispose()
    sys.exit(0)


signal.signal(signal.SIGINT, graceful_exit)

if __name__ == "__main__":
    print("Starting Kube-9 Container Orchestration System...")
    print("Cleaning up any stale nodes...")
    cleanup_initializing_nodes()
    print("Initializing monitors and services...")
    try:
        docker_monitor.start()
        print("Docker monitor started successfully")
    except Exception as e:
        print(f"Failed to start Docker monitor: {str(e)}")
    print("Starting web server on http://localhost:5000/")
    try:
        app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
    except KeyboardInterrupt:
        graceful_exit(None, None)
