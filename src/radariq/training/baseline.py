from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from radariq.configs import load_config
from radariq.models.logistic import (
    fit_logistic_regression,
    predict_logistic_regression,
    save_logistic_model,
)


def _json_value(value: Any) -> Any:
    return value.item() if isinstance(value, np.generic) else value


def _classification_report(
    labels: np.ndarray, predictions: np.ndarray, classes: np.ndarray
) -> dict[str, Any]:
    matrix = np.zeros((len(classes), len(classes)), dtype=np.int64)
    class_indexes = {_json_value(label): index for index, label in enumerate(classes)}
    for actual, predicted in zip(labels, predictions, strict=True):
        matrix[class_indexes[_json_value(actual)], class_indexes[_json_value(predicted)]] += 1

    per_class: dict[str, dict[str, int | float]] = {}
    f1_scores: list[float] = []
    for index, label in enumerate(classes):
        true_positive = int(matrix[index, index])
        false_positive = int(matrix[:, index].sum() - true_positive)
        support = int(matrix[index, :].sum())
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = true_positive / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1_scores.append(f1)
        per_class[str(_json_value(label))] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
    return {
        "accuracy": float(np.mean(labels == predictions)),
        "macro_f1": float(np.mean(f1_scores)),
        "class_metrics": per_class,
        "confusion_matrix": {
            "labels": [_json_value(label) for label in classes],
            "matrix": matrix.tolist(),
        },
    }


def run_baseline_from_config(config_path: str | Path) -> dict[str, Any]:
    """Train and evaluate the reproducible classical baseline from a JSON-compatible YAML config."""
    config = load_config(config_path)
    data_config = load_config(config["data_config"])
    features = np.load(data_config["features_path"], allow_pickle=False)
    labels = np.load(data_config["labels_path"], allow_pickle=False).reshape(-1)
    if len(features) != len(labels):
        raise ValueError("Özellik ve etiket sayıları eşit değil")

    seed = int(config.get("seed", 42))
    test_fraction = float(config.get("test_fraction", data_config.get("test_fraction", 0.2)))
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction 0 ile 1 arasında olmalıdır")
    indices = np.random.default_rng(seed).permutation(len(labels))
    test_size = max(1, round(len(labels) * test_fraction))
    test_indices, train_indices = indices[:test_size], indices[test_size:]
    if not len(train_indices):
        raise ValueError("Eğitim için en az bir örnek kalmalıdır")

    classes, weights, bias, mean, scale = fit_logistic_regression(
        features[train_indices],
        labels[train_indices],
        learning_rate=float(config.get("learning_rate", 0.1)),
        epochs=int(config.get("epochs", 200)),
        l2=float(config.get("l2", 0.0)),
    )
    predictions = predict_logistic_regression(
        features[test_indices], classes, weights, bias, mean, scale
    )
    output_dir = Path(config.get("output_dir", "artifacts/baseline"))
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = save_logistic_model(output_dir / "model.npz", classes, weights, bias, mean, scale)
    np.savez_compressed(output_dir / "split_indices.npz", train=train_indices, test=test_indices)
    report = _classification_report(labels[test_indices], predictions, classes)
    manifest = {
        "schema_version": "1.0",
        "model_type": "logistic_regression",
        "seed": seed,
        "data_config": str(config["data_config"]),
        "model_path": str(model_path),
        "split_path": str(output_dir / "split_indices.npz"),
        "train_samples": len(train_indices),
        "test_samples": len(test_indices),
        "metrics": report,
    }
    (output_dir / "baseline.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
