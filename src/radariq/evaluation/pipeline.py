from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from radariq.configs import load_config
from radariq.models.centroid import load_model, predict


def evaluate_from_config(config_path: str | Path) -> dict[str, Any]:
    config = load_config(config_path)
    classes, centroids = load_model(config["model_path"])
    features = np.load(config["test_features_path"], allow_pickle=False)
    labels = np.load(config["test_labels_path"], allow_pickle=False).reshape(-1)
    predictions = predict(features, classes, centroids)
    class_metrics = {}
    for label in classes:
        true_positive = int(np.sum((labels == label) & (predictions == label)))
        false_positive = int(np.sum((labels != label) & (predictions == label)))
        false_negative = int(np.sum((labels == label) & (predictions != label)))
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else None
        f1 = 2 * precision * recall / (precision + recall) if recall is not None and precision + recall else 0.0
        class_metrics[str(label)] = {"precision": precision, "recall": recall, "f1": f1}
    present = [metrics for metrics in class_metrics.values() if metrics["recall"] is not None]
    report = {
        "schema_version": "1.0",
        "samples": int(len(labels)),
        "accuracy": float(np.mean(predictions == labels)),
        "macro_f1": float(np.mean([metrics["f1"] for metrics in present])) if present else None,
        "macro_recall": float(np.mean([metrics["recall"] for metrics in present])) if present else None,
        "class_metrics": class_metrics,
    }
    output = Path(config.get("output_path", "artifacts/evaluation.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
