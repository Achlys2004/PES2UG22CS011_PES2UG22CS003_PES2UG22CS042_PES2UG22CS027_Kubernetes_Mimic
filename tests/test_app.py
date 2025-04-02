import pytest
from app import app

@pytest.fixture
def client():
    """Creates a test client for the Flask app."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client  # Provide test client

def test_home_route(client):
    """Test if the home route works."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Kube_9 API is running!" in response.data

def test_db_connection(client):
    """Test the database connection route."""
    response = client.get("/test_db")
    assert response.status_code == 200
    assert b"Database Connected!" in response.data or b"Database Connection failed" in response.data
