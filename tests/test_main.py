"""
tests/test_main.py
Tests for the FastAPI application entry point.
"""

from httpx import AsyncClient


async def test_health_check(async_client: AsyncClient):
    """GET /health should return 200 with status ok."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_openapi_docs_available(async_client: AsyncClient):
    """GET /docs should return 200 (Swagger UI is reachable)."""
    response = await async_client.get("/docs")
    assert response.status_code == 200


async def test_openapi_json_available(async_client: AsyncClient):
    """GET /openapi.json should return a valid OpenAPI schema."""
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema
