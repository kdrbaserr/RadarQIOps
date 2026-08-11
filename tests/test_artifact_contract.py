from __future__ import annotations

import numpy as np
import pytest

from radariq.models.centroid import fit_centroids, load_model, predict, save_model

pytestmark = [pytest.mark.artifact, pytest.mark.contract, pytest.mark.integration]


def test_centroid_artifact_round_trip(tmp_path, rng: np.random.Generator) -> None:
    class_zero = rng.normal(-1.0, 0.05, size=(8, 2, 4)).astype(np.float32)
    class_one = rng.normal(1.0, 0.05, size=(8, 2, 4)).astype(np.float32)
    features = np.concatenate([class_zero, class_one])
    labels = np.array([0] * len(class_zero) + [1] * len(class_one))

    classes, centroids = fit_centroids(features, labels)
    artifact_path = save_model(tmp_path / "model.npz", classes, centroids)
    loaded_classes, loaded_centroids = load_model(artifact_path)
    predictions = predict(features, loaded_classes, loaded_centroids)

    assert artifact_path.is_file()
    np.testing.assert_array_equal(loaded_classes, classes)
    np.testing.assert_allclose(loaded_centroids, centroids)
    np.testing.assert_array_equal(predictions, labels)
