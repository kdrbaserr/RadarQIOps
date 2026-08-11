from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pytest

from radariq.evaluation.pipeline import evaluate_from_config
from radariq.training.pipeline import train_from_config

pytestmark = [pytest.mark.integration, pytest.mark.artifact]


class PipelineTests(unittest.TestCase):
    def test_train_and_evaluate_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features = np.array(
                [[0, 0], [0, 1], [10, 10], [10, 11], [1, 0], [11, 10]], dtype=np.float32
            )
            labels = np.array([0, 0, 1, 1, 0, 1])
            np.save(root / "features.npy", features)
            np.save(root / "labels.npy", labels)
            (root / "data.yaml").write_text(
                json.dumps(
                    {
                        "features_path": str(root / "features.npy"),
                        "labels_path": str(root / "labels.npy"),
                        "test_fraction": 0.33,
                    }
                ),
                encoding="utf-8",
            )
            (root / "model.yaml").write_text(
                json.dumps({"artifact_path": str(root / "model.npz")}), encoding="utf-8"
            )
            (root / "train.yaml").write_text(
                json.dumps(
                    {
                        "seed": 4,
                        "data_config": str(root / "data.yaml"),
                        "model_config": str(root / "model.yaml"),
                        "output_dir": str(root),
                    }
                ),
                encoding="utf-8",
            )

            manifest = train_from_config(root / "train.yaml")
            self.assertEqual(manifest["train_samples"], 4)

            (root / "evaluate.yaml").write_text(
                json.dumps(
                    {
                        "model_path": str(root / "model.npz"),
                        "test_features_path": str(root / "test_features.npy"),
                        "test_labels_path": str(root / "test_labels.npy"),
                        "output_path": str(root / "evaluation.json"),
                    }
                ),
                encoding="utf-8",
            )
            report = evaluate_from_config(root / "evaluate.yaml")
            self.assertEqual(report["samples"], 2)
            self.assertIn("macro_f1", report)
            self.assertTrue((root / "evaluation.json").exists())


if __name__ == "__main__":
    unittest.main()
