from __future__ import annotations

import contextlib
import io
import json
import pickle
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np
import pytest

from radariq.cli import main
from radariq.data_inspect import InspectError, inspect_dataset

pytestmark = [pytest.mark.contract, pytest.mark.unit]


class DataInspectTests(unittest.TestCase):
    def test_npy_with_sidecar_metadata_and_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sample_path = root / "sample.npy"
            np.save(sample_path, np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32))
            sample_path.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "label": "car",
                        "snr_db": None,
                        "group_id": "vehicle-7",
                        "sequence_id": "seq-2",
                    }
                ),
                encoding="utf-8",
            )

            result = inspect_dataset("raddet", sample_path)

            self.assertEqual(result["shape"], [2, 2])
            self.assertEqual(result["dtype"], "float32")
            self.assertEqual(result["label"], "car")
            self.assertIsNone(result["snr_db"])
            self.assertEqual(result["group_id"], "vehicle-7")
            self.assertEqual(result["sequence_id"], "seq-2")
            self.assertEqual(result["statistics"]["mean"], 2.5)

    def test_radioml_2018_reads_label_snr_and_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_path = root / "radioml.h5"
            with h5py.File(data_path, "w") as handle:
                handle.create_dataset(
                    "X",
                    data=np.arange(24, dtype=np.float32).reshape(3, 4, 2),
                )
                handle.create_dataset(
                    "Y",
                    data=np.array([[1, 0], [0, 1], [1, 0]], dtype=np.int8),
                )
                handle.create_dataset("Z", data=np.array([[-20], [-18], [-16]]))
            (root / "classes.txt").write_text("BPSK\nQPSK\n", encoding="utf-8")

            result = inspect_dataset("radioml-2018.01a", data_path, sample_index=1)

            self.assertEqual(result["shape"], [4, 2])
            self.assertEqual(result["label"], {"index": 1, "name": "QPSK"})
            self.assertEqual(result["snr_db"], -18.0)

    def test_radarscenes_reads_structured_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sequence = Path(temp_dir) / "sequence_01"
            sequence.mkdir()
            data_path = sequence / "radar_data.h5"
            dtype = np.dtype(
                [
                    ("range_sc", "<f4"),
                    ("rcs", "<f4"),
                    ("track_id", "S16"),
                    ("label_id", "u1"),
                ]
            )
            detections = np.array([(12.5, -3.0, b"track-9", 7)], dtype=dtype)
            with h5py.File(data_path, "w") as handle:
                handle.create_dataset("radar_data", data=detections)

            result = inspect_dataset("radarscenes", sequence)

            self.assertEqual(result["dtype"]["kind"], "structured")
            self.assertEqual(result["label"], {"index": 7, "name": "pedestrian"})
            self.assertEqual(result["group_id"], "track-9")
            self.assertEqual(result["sequence_id"], "sequence_01")
            self.assertIsNone(result["snr_db"])
            self.assertIn("range_sc", result["statistics"]["fields"])

    def test_radioml_2016_requires_explicit_pickle_permission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "radio.pkl"
            with data_path.open("wb") as handle:
                pickle.dump(
                    {("BPSK", -10): np.ones((2, 2, 4), dtype=np.float32)},
                    handle,
                )

            with self.assertRaisesRegex(InspectError, "allow-unsafe-pickle"):
                inspect_dataset("radioml-2016.10a", data_path)

            result = inspect_dataset(
                "radioml-2016.10a",
                data_path,
                sample_index=1,
                allow_unsafe_pickle=True,
            )
            self.assertEqual(result["shape"], [2, 4])
            self.assertEqual(result["label"], "BPSK")
            self.assertEqual(result["snr_db"], -10.0)

    def test_cli_emits_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sample_path = Path(temp_dir) / "sample.npy"
            np.save(sample_path, np.array([1, 2, 3], dtype=np.int16))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "data",
                        "inspect",
                        "--dataset",
                        "npy",
                        "--path",
                        str(sample_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["shape"], [3])
            self.assertEqual(payload["statistics"]["max"], 3.0)


if __name__ == "__main__":
    unittest.main()
