from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from radariq.configs import load_config
from radariq.models.centroid import fit_centroids, save_model


def train_from_config(config_path: str | Path) -> dict[str, Any]:
    config = load_config(config_path)
    data_config = load_config(config["data_config"])
    model_config = load_config(config["model_config"])
    features = np.load(data_config["features_path"], allow_pickle=False)
    labels = np.load(data_config["labels_path"], allow_pickle=False).reshape(-1)
    if len(features) != len(labels):
        raise ValueError("Özellik ve etiket sayıları eşit değil")

    rng = np.random.default_rng(int(config.get("seed", 42)))
    indices = rng.permutation(len(labels))
    test_size = max(1, int(round(len(labels) * float(data_config.get("test_fraction", 0.2)))))
    test_indices, train_indices = indices[:test_size], indices[test_size:]
    if not len(train_indices):
        raise ValueError("Eğitim için en az iki örnek gerekir")

    classes, centroids = fit_centroids(features[train_indices], labels[train_indices])
    output_dir = Path(config.get("output_dir", "artifacts"))
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = save_model(model_config.get("artifact_path", output_dir / "model.npz"), classes, centroids)
    np.save(output_dir / "test_features.npy", features[test_indices])
    np.save(output_dir / "test_labels.npy", labels[test_indices])
    manifest = {
        "model_type": "nearest_centroid",
        "model_path": str(model_path),
        "seed": int(config.get("seed", 42)),
        "train_samples": int(len(train_indices)),
        "test_samples": int(len(test_indices)),
        "classes": classes.tolist(),
    }
    (output_dir / "training.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
