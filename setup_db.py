from models import data
from app import app

with app.app_context():
    data.create_all()
    print("Database tables created!")
