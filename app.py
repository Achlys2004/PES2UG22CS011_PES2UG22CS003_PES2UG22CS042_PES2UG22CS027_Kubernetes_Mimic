from flask import Flask
from sqlalchemy import text
from config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS
from models import data
from routes.nodes import nodes_bp
from routes.pods import pods_bp
from flask_migrate import Migrate
from services.monitor import DockerMonitor

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS

data.init_app(app)

docker_monitor = DockerMonitor(app)

migrate = Migrate(app, data)

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


if __name__ == "__main__":
    docker_monitor.start()
    app.run(debug=True)
    docker_monitor.stop()
