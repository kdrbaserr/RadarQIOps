import os
from pathlib import Path

import numpy as np

from radariq.models.centroid import load_model, predict


def create_app(model_path: str | Path | None = None):
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except ImportError as exc:
        raise RuntimeError("API için 'pip install -e .[api]' çalıştırın") from exc

    selected_model = model_path if model_path is not None else os.getenv("RADARIQ_MODEL_PATH", "artifacts/model.npz")
    selected_path = Path(selected_model)
    app = FastAPI(title="RadarIQops", version="0.1.0")

    class PredictionRequest(BaseModel):
        samples: list[list[float]]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, object]:
        return {"ready": selected_path.exists(), "model_path": str(selected_path)}

    @app.get("/model-info")
    def model_info() -> dict[str, object]:
        if not selected_path.exists():
            raise HTTPException(status_code=503, detail="Model artifact bulunamadı")
        classes, centroids = load_model(selected_path)
        return {"type": "nearest_centroid", "classes": classes.tolist(), "features": int(centroids.shape[1])}

    @app.post("/predict")
    def run_prediction(request: PredictionRequest) -> dict[str, object]:
        if not selected_path.exists():
            raise HTTPException(status_code=503, detail="Model artifact bulunamadı")
        classes, centroids = load_model(selected_path)
        try:
            output = predict(np.asarray(request.samples, dtype=np.float32), classes, centroids)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"predictions": output.tolist()}

    return app


app = create_app()
