from flask import Flask
from sqlalchemy import text
from config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS
from models import data
from routes.nodes import nodes_bp
from routes.pods import pods_bp
from flask_migrate import Migrate
from services.monitor import DockerMonitor
import logging
import signal
import sys

# Configure Flask app
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

data.init_app(app)
docker_monitor = DockerMonitor(app)
app.config["DOCKER_MONITOR"] = docker_monitor
migrate = Migrate(app, data)

# Register blueprints
app.register_blueprint(nodes_bp, url_prefix="/nodes")
app.register_blueprint(pods_bp, url_prefix="/pods")


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


def graceful_exit(signal, frame):
    print("\nShutting down Kube-9 Container Orchestration System...")
    docker_monitor.stop()
    sys.exit(0)


# Register signal handler
signal.signal(signal.SIGINT, graceful_exit)

if __name__ == "__main__":
    print("Starting Kube-9 Container Orchestration System...")
    print("Initializing monitors and services...")
    docker_monitor.start()
    print("Starting web server on http://localhost:5000/")
    try:
        app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
    except KeyboardInterrupt:
        graceful_exit(None, None)
