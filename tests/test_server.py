import pytest
import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT_DIR)
from app import app


@pytest.fixture
def client():
    with app.test_client() as client:
        yield client


def test_index_route(client):
    response = client.get('/')
    assert response.status_code == 200


def test_strava_login(client, monkeypatch):
    # Mocking os.getenv to simulate environment variables
    monkeypatch.setenv('STRAVA_CLIENT_ID', 'your_fake_client_id')
    response = client.get('/strava-login')
    assert response.status_code == 302  # Ensure the redirect happens


# def test_refresh_route(client):
#     response = client.get('/refresh')
#     assert response.status_code == 302  # Check if it redirects to the index


def test_logout_route(client):
    response = client.get('/logout')
    assert response.status_code == 302  # Ensure redirect to the index


# def test_strava_callback(client, monkeypatch):
#     # Mocking os.getenv to simulate environment variables
#     monkeypatch.setenv('STRAVA_CLIENT_ID', 'your_fake_client_id')
#     response = client.get('/strava-callback')
#     assert response.status_code == 302  # Ensure redirect to dashboard or index


def test_dashboard_route(client, monkeypatch):
    # Mocking session variables for an authenticated user
    with client.session_transaction() as sess:
        sess['access_token'] = 'fake_access_token'
        sess['state'] = 'fake_state'

    # Mocking os.getenv to simulate environment variables
    monkeypatch.setenv('STRAVA_CLIENT_ID', 'your_fake_client_id')

    response = client.get('/dashboard')
    assert response.status_code == 302  # Check if the dashboard redirects


# Add more specific test cases as needed for each route or functionality
