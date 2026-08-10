from __future__ import annotations

from pathlib import Path

import numpy as np


def fit_centroids(features: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(features, dtype=np.float32)
    y = np.asarray(labels).reshape(-1)
    if x.ndim < 2 or len(x) != len(y) or len(x) == 0:
        raise ValueError("features ve labels uyumlu, boş olmayan örnekler içermelidir")
    flat = x.reshape(len(x), -1)
    classes = np.unique(y)
    centroids = np.stack([flat[y == label].mean(axis=0) for label in classes])
    return classes, centroids


def predict(features: np.ndarray, classes: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    x = np.asarray(features, dtype=np.float32)
    flat = x.reshape(len(x), -1)
    distances = ((flat[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
    return classes[np.argmin(distances, axis=1)]


def save_model(path: str | Path, classes: np.ndarray, centroids: np.ndarray) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target, classes=classes, centroids=centroids)
    return target


def load_model(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    with np.load(Path(path), allow_pickle=False) as artifact:
        return artifact["classes"], artifact["centroids"]
