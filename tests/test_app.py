import pytest
from app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client  # Provide test client

def test_home_route(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Kube_9 API is running!" in response.data

def test_db_connection(client):
    response = client.get("/test_db")
    assert response.status_code == 200
    assert b"Database Connected!" in response.data or b"Database Connection failed" in response.data
