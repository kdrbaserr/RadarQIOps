from __future__ import annotations

import warnings
from pathlib import Path

from starlette.exceptions import StarletteDeprecationWarning

warnings.filterwarnings("ignore", category=StarletteDeprecationWarning)

from fastapi.testclient import TestClient

from radariq.services.api.app import create_app


def main() -> None:
    missing_model = Path("artifacts/__api_smoke_missing_model__.npz")
    client = TestClient(create_app(model_path=missing_model))

    health = client.get("/health")
    assert health.status_code == 200, health.text
    assert health.json() == {"status": "ok"}

    ready = client.get("/ready")
    assert ready.status_code == 200, ready.text
    assert ready.json()["ready"] is False

    model_info = client.get("/model-info")
    assert model_info.status_code == 503, model_info.text

    print("api-smoke OK: health=200 ready=false model-info=503")


if __name__ == "__main__":
    main()
