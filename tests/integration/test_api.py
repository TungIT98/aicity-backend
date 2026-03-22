"""
Integration tests for AI City Backend API
These tests run against a live database and require proper environment setup.
"""
import pytest
import httpx
import os

BASE_URL = os.getenv("TEST_BACKEND_URL", "http://localhost:8000")


class TestDemoBooking:
    """Test suite for demo booking API"""

    def test_demo_booking_creates_lead(self):
        """POST /api/demo should create a lead successfully"""
        payload = {
            "name": "Test User",
            "email": f"test_{os.urandom(4).hex()}@example.com",
            "company": "Test Company",
            "phone": "+84912345678",
            "message": "Integration test booking"
        }
        response = httpx.post(f"{BASE_URL}/api/demo", json=payload, timeout=10.0)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "status" in data or "id" in data or "success" in data

    def test_demo_booking_validates_required_fields(self):
        """POST /api/demo should validate required fields"""
        payload = {
            "name": "Test User",
            # Missing email, company, phone
        }
        response = httpx.post(f"{BASE_URL}/api/demo", json=payload, timeout=10.0)
        # Should return 422 (validation error) or 400 (bad request)
        assert response.status_code in [400, 422]

    def test_demo_booking_invalid_email(self):
        """POST /api/demo should reject invalid email format"""
        payload = {
            "name": "Test User",
            "email": "not-an-email",
            "company": "Test Company",
            "phone": "+84912345678"
        }
        response = httpx.post(f"{BASE_URL}/api/demo", json=payload, timeout=10.0)
        assert response.status_code in [400, 422]


class TestAnalyticsEndpoints:
    """Test suite for analytics API"""

    def test_analytics_overview(self):
        """GET /analytics/overview should return analytics data"""
        response = httpx.get(f"{BASE_URL}/analytics/overview", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (dict, list))

    def test_analytics_requires_auth(self):
        """Some analytics endpoints may require authentication"""
        response = httpx.get(f"{BASE_URL}/analytics/dashboard", timeout=10.0)
        # Should either return 200 (public) or 401 (auth required)
        assert response.status_code in [200, 401]


class TestAPIDocumentation:
    """Test suite for API documentation endpoints"""

    def test_swagger_docs_accessible(self):
        """GET /api/docs should serve Swagger UI"""
        response = httpx.get(f"{BASE_URL}/api/docs", timeout=10.0)
        assert response.status_code == 200

    def test_openapi_schema(self):
        """GET /openapi.json should return OpenAPI schema"""
        response = httpx.get(f"{BASE_URL}/openapi.json", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data


class TestCORS:
    """Test CORS configuration"""

    def test_cors_allows_api_access(self):
        """API should be accessible with CORS headers"""
        response = httpx.options(
            f"{BASE_URL}/health",
            headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
            timeout=10.0
        )
        # Should return 200 or actual CORS headers
        assert response.status_code in [200, 204]
