from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from radariq.services.api.app import create_app

pytestmark = [pytest.mark.api, pytest.mark.contract, pytest.mark.integration]
TestClient = import_module("fastapi.testclient").TestClient


@pytest.fixture
def client():
    missing_model = Path("artifacts/__pytest_missing_model__.npz")
    return TestClient(create_app(model_path=missing_model))


@pytest.mark.smoke
def test_health_contract(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_missing_model(client) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["ready"] is False


def test_model_info_rejects_missing_artifact(client) -> None:
    response = client.get("/model-info")

    assert response.status_code == 503
    assert response.json()["detail"] == "Model artifact bulunamadı"
