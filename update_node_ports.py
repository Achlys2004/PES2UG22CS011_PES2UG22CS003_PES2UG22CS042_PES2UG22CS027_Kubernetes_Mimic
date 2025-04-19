from app import app
from models import data, Node

with app.app_context():
    
    nodes = Node.query.all()
    for node in nodes:
        if node.id:
            
            node.node_ip = "localhost"
            node.node_port = 5000 + node.id
    
    
    data.session.commit()
    print("Updated all node connection information!")