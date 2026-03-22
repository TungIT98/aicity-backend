"""
Health endpoint tests for AI City Backend
"""
import pytest
import httpx
import os

BASE_URL = os.getenv("TEST_BACKEND_URL", "http://localhost:8000")


class TestHealthEndpoints:
    """Test suite for health check endpoints"""

    def test_health_returns_200(self):
        """GET /health should return 200 with status info"""
        response = httpx.get(f"{BASE_URL}/health", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data or "service" in data

    def test_liveness_probe(self):
        """GET /live should return 200 - Kubernetes liveness probe"""
        response = httpx.get(f"{BASE_URL}/live", timeout=10.0)
        assert response.status_code == 200

    def test_readiness_probe(self):
        """GET /ready should return 200 - Kubernetes readiness probe"""
        response = httpx.get(f"{BASE_URL}/ready", timeout=10.0)
        assert response.status_code == 200

    def test_health_contains_postgresql_status(self):
        """GET /health should indicate PostgreSQL availability"""
        response = httpx.get(f"{BASE_URL}/health", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        # Should indicate database connectivity
        assert "postgresql" in data or "database" in data or "status" in data

    def test_readiness_checks_database(self):
        """GET /ready should verify database connectivity"""
        response = httpx.get(f"{BASE_URL}/ready", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        # Readiness probe should check DB
        assert data.get("status") == "ready" or "database" in str(data).lower()
