from __future__ import annotations

from pathlib import Path

import numpy as np


def fit_logistic_regression(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    learning_rate: float,
    epochs: int,
    l2: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Fit a small multiclass softmax classifier with full-batch gradient descent."""
    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(labels).reshape(-1)
    if x.ndim < 2 or len(x) != len(y) or len(x) < 2:
        raise ValueError("Baseline eğitimi için en az iki uyumlu örnek gerekir")
    if learning_rate <= 0 or epochs < 1 or l2 < 0:
        raise ValueError("learning_rate pozitif, epochs en az 1 ve l2 negatif olmayan olmalıdır")

    flat = x.reshape(len(x), -1)
    classes, encoded = np.unique(y, return_inverse=True)
    if len(classes) < 2:
        raise ValueError("Baseline eğitimi için en az iki sınıf gerekir")

    mean = flat.mean(axis=0)
    scale = flat.std(axis=0)
    scale[scale == 0] = 1.0
    normalized = (flat - mean) / scale
    weights = np.zeros((normalized.shape[1], len(classes)), dtype=np.float64)
    bias = np.zeros(len(classes), dtype=np.float64)
    targets = np.eye(len(classes), dtype=np.float64)[encoded]

    for _ in range(epochs):
        logits = normalized @ weights + bias
        logits -= logits.max(axis=1, keepdims=True)
        probabilities = np.exp(logits)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        error = (probabilities - targets) / len(normalized)
        weights -= learning_rate * (normalized.T @ error + l2 * weights)
        bias -= learning_rate * error.sum(axis=0)

    return (
        classes,
        weights.astype(np.float32),
        bias.astype(np.float32),
        mean.astype(np.float32),
        scale.astype(np.float32),
    )


def predict_logistic_regression(
    features: np.ndarray,
    classes: np.ndarray,
    weights: np.ndarray,
    bias: np.ndarray,
    mean: np.ndarray,
    scale: np.ndarray,
) -> np.ndarray:
    flat = np.asarray(features, dtype=np.float32).reshape(len(features), -1)
    normalized = (flat - mean) / scale
    return classes[np.argmax(normalized @ weights + bias, axis=1)]


def save_logistic_model(
    path: str | Path,
    classes: np.ndarray,
    weights: np.ndarray,
    bias: np.ndarray,
    mean: np.ndarray,
    scale: np.ndarray,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        target,
        model_type=np.array("logistic_regression"),
        classes=classes,
        weights=weights,
        bias=bias,
        mean=mean,
        scale=scale,
    )
    return target
