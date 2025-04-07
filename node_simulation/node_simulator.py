from flask import Flask, jsonify

app = Flask(__name__)

node_state = {
    "name": "node-1",
    "cpu_cores_avail": 4,
    "health_status": "healthy"
}
@app.route("/", methods=["GET"])
def home():
    return "Kube-9 Node Simulator is running!"

@app.route("/status", methods=["GET"])
def status():
    return jsonify(node_state)

@app.route("/simulate_failure", methods=["POST"])
def simulate_failure():
    node_state["health_status"] = "unhealthy"
    return jsonify({"msg": "Node marked unhealthy"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
