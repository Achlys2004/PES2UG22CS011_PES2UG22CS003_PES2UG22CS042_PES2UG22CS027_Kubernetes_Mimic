from flask import Flask
from sqlalchemy import text
from config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS
from models import data
from routes.nodes import nodes_bp
from routes.pods import pods_bp

app = Flask(__name__)

# Load Configuration
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS


# Initialize Database
data.init_app(app)

# Register Blueprints with URL Prefixes
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
    app.run(debug=True)
