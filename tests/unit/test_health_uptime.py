"""Testes unitários para o endpoint GET /api/v1/health/uptime."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from dev_autonomo.control_plane import routers as _  # noqa: F401 – garante import path
from dev_autonomo.control_plane.routers import health as health_router


@pytest.fixture()
def client() -> TestClient:
    """TestClient com lifespan ativo para disparar set_startup_time()."""
    from dev_autonomo.control_plane.app import create_app

    app = create_app()
    # O TestClient com use_lifespan=True executa o lifespan handler,
    # garantindo que STARTUP_MONOTONIC seja definido antes dos requests.
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


class TestUptimeEndpoint:
    def test_status_200_and_json_shape(self, client: TestClient) -> None:
        """CA 1: responde HTTP 200 com shape {"uptime_seconds": <int>}."""
        response = client.get("/api/v1/health/uptime")
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {"uptime_seconds"}

    def test_uptime_seconds_is_int_and_non_negative(self, client: TestClient) -> None:
        """CA 1+dir: uptime_seconds deve ser int >= 0."""
        response = client.get("/api/v1/health/uptime")
        data = response.json()
        value = data["uptime_seconds"]
        assert isinstance(value, int), f"Esperado int, obteve {type(value)}"
        assert value >= 0, f"uptime_seconds deve ser >= 0, obteve {value}"

    def test_uptime_non_decreasing_between_calls(self, client: TestClient) -> None:
        """CA dir: duas chamadas subsequentes retornam valor não-decrescente."""
        first = client.get("/api/v1/health/uptime").json()["uptime_seconds"]
        time.sleep(0.01)  # garante delta mínimo
        second = client.get("/api/v1/health/uptime").json()["uptime_seconds"]
        assert second >= first, (
            f"uptime_seconds decresceu: {first} -> {second}"
        )

    def test_no_auth_required(self, client: TestClient) -> None:
        """CA 3: sem header de autenticação → 200 (não exige auth)."""
        response = client.get("/api/v1/health/uptime")  # sem Authorization
        assert response.status_code == 200

    def test_startup_monotonic_captured_once(self) -> None:
        """CA 2: set_startup_time() define STARTUP_MONOTONIC via time.monotonic()."""
        before = time.monotonic()
        health_router.set_startup_time()
        after = time.monotonic()
        assert before <= health_router.STARTUP_MONOTONIC <= after
