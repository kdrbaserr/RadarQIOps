from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from radariq.cli import main
from radariq.data.contracts import IQRepresentation
from radariq.data.eda import EDAConfig, EDAError, generate_eda_artifacts

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _fixture_npz(path: Path) -> None:
    samples = np.array(
        [
            [[1, 0, -1, 0], [0, 1, 0, -1]],
            [[2, 0, -2, 0], [0, 2, 0, -2]],
        ],
        dtype=np.float32,
    )
    np.savez(
        path,
        samples=samples,
        labels=np.array(["BPSK", "QPSK"]),
        snr_db=np.array([-10.0, 0.0]),
        sample_ids=np.array(["sample-b", "sample-a"]),
    )


def _config(input_path: Path, output_dir: Path) -> EDAConfig:
    return EDAConfig(
        input_path=input_path,
        output_dir=output_dir,
        representation=IQRepresentation.CHANNELS_FIRST,
        source_id="fixture-iq",
        source_revision="sha256:fixture-v1",
        max_spectra=2,
    )


def test_fixed_fixture_numeric_summary_snapshot(tmp_path: Path) -> None:
    input_path = tmp_path / "fixture.npz"
    _fixture_npz(input_path)

    result = generate_eda_artifacts(_config(input_path, tmp_path / "eda"))
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))

    assert {
        "class_distribution": summary["class_distribution"],
        "snr_distribution": summary["snr_distribution"],
        "signal_length_distribution": summary["signal_length_distribution"],
        "iq_statistics": summary["iq_statistics"],
        "power_statistics": summary["power_statistics"],
    } == {
        "class_distribution": [
            {"count": 1, "label": "BPSK"},
            {"count": 1, "label": "QPSK"},
        ],
        "snr_distribution": [
            {"count": 1, "snr_db": -10.0},
            {"count": 1, "snr_db": 0.0},
        ],
        "signal_length_distribution": [{"count": 2, "length": 4}],
        "iq_statistics": {
            "i": {"max": 2.0, "mean": 0.0, "min": -2.0, "std": np.sqrt(1.25)},
            "q": {"max": 2.0, "mean": 0.0, "min": -2.0, "std": np.sqrt(1.25)},
        },
        "power_statistics": {"max": 4.0, "mean": 2.5, "min": 1.0, "std": 1.5},
    }


def test_same_input_and_config_produce_identical_artifact_bytes(tmp_path: Path) -> None:
    input_path = tmp_path / "fixture.npz"
    _fixture_npz(input_path)
    first = generate_eda_artifacts(_config(input_path, tmp_path / "first"))
    second = generate_eda_artifacts(_config(input_path, tmp_path / "second"))

    assert first.run_id == second.run_id
    for filename in ("eda_summary.json", "eda_plot_data.json", "eda_report.html"):
        assert (first.output_dir / filename).read_bytes() == (
            second.output_dir / filename
        ).read_bytes()


def test_plot_sources_and_spectrum_selection_are_recorded(tmp_path: Path) -> None:
    input_path = tmp_path / "fixture.npz"
    _fixture_npz(input_path)
    result = generate_eda_artifacts(_config(input_path, tmp_path / "eda"))

    plot_data = json.loads(result.plot_data_path.read_text(encoding="utf-8"))
    report = result.report_path.read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert [item["sample_id"] for item in plot_data["sample_spectra"]] == [
        "sample-a",
        "sample-b",
    ]
    assert "eda_plot_data.json#/class_distribution" in report
    assert "eda_plot_data.json#/sample_spectra" in report
    assert manifest["run_id"] == result.run_id
    assert {item["path"] for item in manifest["artifacts"]} == {
        "eda_summary.json",
        "eda_plot_data.json",
        "eda_report.html",
    }


def test_cli_generates_eda_from_relative_config_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "fixture.npz"
    _fixture_npz(input_path)
    config_path = tmp_path / "eda.json"
    config_path.write_text(
        json.dumps(
            {
                "input_path": "fixture.npz",
                "output_dir": "artifacts/eda",
                "representation": "channels_first",
                "source_id": "fixture-iq",
                "source_revision": "sha256:fixture-v1",
                "max_spectra": 1,
            }
        ),
        encoding="utf-8",
    )

    assert main(["data", "eda", "--config", str(config_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"]
    assert (tmp_path / "artifacts" / "eda" / "eda_summary.json").is_file()


def test_mismatched_metadata_count_fails_closed(tmp_path: Path) -> None:
    input_path = tmp_path / "bad.npz"
    np.savez(
        input_path,
        samples=np.ones((2, 2, 4), dtype=np.float32),
        labels=np.array(["BPSK"]),
        snr_db=np.array([-10.0, 0.0]),
    )

    with pytest.raises(EDAError, match="kayıt sayıları eşit"):
        generate_eda_artifacts(_config(input_path, tmp_path / "eda"))


def test_noncanonical_dtype_fails_closed(tmp_path: Path) -> None:
    input_path = tmp_path / "bad-dtype.npz"
    np.savez(
        input_path,
        samples=np.ones((1, 2, 4), dtype=np.float64),
        labels=np.array(["BPSK"]),
        snr_db=np.array([-10.0]),
    )

    with pytest.raises(EDAError, match="dtype float32"):
        generate_eda_artifacts(_config(input_path, tmp_path / "eda"))
