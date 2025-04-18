from app import app
from models import data, Node

with app.app_context():
    # Get all nodes
    nodes = Node.query.all()
    for node in nodes:
        if node.id:
            # Set to localhost and calculate the port (5000 + node.id)
            node.node_ip = "localhost"
            node.node_port = 5000 + node.id
    
    # Commit changes
    data.session.commit()
    print("Updated all node connection information!")