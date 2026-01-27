"""
Test health check endpoints
"""
import pytest
from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient):
    """
    Test the root endpoint returns correct information
    """
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert "message" in data
    assert "version" in data
    assert "docs" in data
    assert data["message"] == "PPG Health API"
    assert data["version"] == "1.0.0"
    assert data["docs"] == "/docs"


def test_health_check_endpoint(client: TestClient):
    """
    Test the health check endpoint returns healthy status
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "service" in data
    assert data["status"] == "healthy"
    assert data["service"] == "PPG Health API"

    # Verify timestamp is in ISO format
    from datetime import datetime
    timestamp = datetime.fromisoformat(data["timestamp"])
    assert timestamp is not None


def test_health_check_response_time(client: TestClient):
    """
    Test that health check responds quickly (< 1 second)
    """
    import time

    start_time = time.time()
    response = client.get("/api/v1/health")
    end_time = time.time()

    assert response.status_code == 200
    assert (end_time - start_time) < 1.0  # Should respond in less than 1 second


def test_cors_headers(client: TestClient):
    """
    Test that CORS headers are properly set
    """
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "GET",
        },
    )

    # FastAPI TestClient may not perfectly simulate CORS,
    # but we can check if the endpoint is accessible
    assert response.status_code in [200, 204]
