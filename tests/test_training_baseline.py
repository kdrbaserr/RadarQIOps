from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from radariq.training.baseline import run_baseline_from_config


@pytest.mark.integration
def test_logistic_baseline_writes_reproducible_artifacts_and_metrics(tmp_path: Path) -> None:
    features = np.array(
        [[-3.0, -3.0], [-2.0, -2.0], [-1.0, -1.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0]],
        dtype=np.float32,
    )
    labels = np.array([0, 0, 0, 1, 1, 1])
    np.save(tmp_path / "features.npy", features)
    np.save(tmp_path / "labels.npy", labels)
    (tmp_path / "data.yaml").write_text(
        json.dumps(
            {
                "features_path": str(tmp_path / "features.npy"),
                "labels_path": str(tmp_path / "labels.npy"),
            }
        ),
        encoding="utf-8",
    )

    def run(output_dir: Path) -> dict[str, object]:
        config_path = output_dir.with_suffix(".yaml")
        config_path.write_text(
            json.dumps(
                {
                    "seed": 19,
                    "data_config": str(tmp_path / "data.yaml"),
                    "output_dir": str(output_dir),
                    "test_fraction": 0.33,
                    "learning_rate": 0.2,
                    "epochs": 300,
                }
            ),
            encoding="utf-8",
        )
        return run_baseline_from_config(config_path)

    first = run(tmp_path / "first")
    second = run(tmp_path / "second")

    assert first["seed"] == second["seed"] == 19
    assert first["metrics"] == second["metrics"]
    assert (tmp_path / "first" / "baseline.json").exists()
    assert (tmp_path / "first" / "model.npz").exists()
    assert (tmp_path / "first" / "split_indices.npz").exists()
    first_split = np.load(tmp_path / "first" / "split_indices.npz")
    second_split = np.load(tmp_path / "second" / "split_indices.npz")
    assert np.array_equal(first_split["train"], second_split["train"])
    assert np.array_equal(first_split["test"], second_split["test"])
    metrics = first["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["macro_f1"] == pytest.approx(1.0)
    assert metrics["confusion_matrix"] == {"labels": [0, 1], "matrix": [[1, 0], [0, 1]]}
