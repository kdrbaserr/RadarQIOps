"""Deterministic, notebook-independent EDA artifacts for canonical I/Q batches."""

from __future__ import annotations

import hashlib
import html
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from radariq.configs import load_config
from radariq.data.contracts import IQRepresentation

EDA_SCHEMA_VERSION = "1.0"


class EDAError(ValueError):
    """Raised when EDA input or configuration is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class EDAConfig:
    input_path: Path
    output_dir: Path
    representation: IQRepresentation
    source_id: str
    source_revision: str
    max_spectra: int = 3

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], base_dir: Path = Path(".")) -> EDAConfig:
        input_path = _required_path(value, "input_path", base_dir)
        output_dir = _required_path(value, "output_dir", base_dir)
        representation_value = value.get("representation")
        if not isinstance(representation_value, str):
            raise EDAError("representation channels_first veya complex olmalıdır")
        try:
            representation = IQRepresentation(representation_value)
        except (TypeError, ValueError) as exc:
            raise EDAError("representation channels_first veya complex olmalıdır") from exc

        max_spectra = value.get("max_spectra", 3)
        if isinstance(max_spectra, bool) or not isinstance(max_spectra, int) or max_spectra < 0:
            raise EDAError("max_spectra sıfır veya daha büyük integer olmalıdır")
        return cls(
            input_path=input_path,
            output_dir=output_dir,
            representation=representation,
            source_id=_required_string(value, "source_id"),
            source_revision=_required_string(value, "source_revision"),
            max_spectra=max_spectra,
        )

    def semantic_parameters(self) -> dict[str, Any]:
        return {
            "representation": self.representation.value,
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "max_spectra": self.max_spectra,
        }


@dataclass(frozen=True, slots=True)
class EDAArtifactResult:
    output_dir: Path
    run_id: str
    summary_path: Path
    plot_data_path: Path
    report_path: Path
    manifest_path: Path

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "output_dir": str(self.output_dir),
            "summary_path": str(self.summary_path),
            "plot_data_path": str(self.plot_data_path),
            "report_path": str(self.report_path),
            "manifest_path": str(self.manifest_path),
        }


def generate_eda_from_config(config_path: str | Path) -> EDAArtifactResult:
    path = Path(config_path)
    config = EDAConfig.from_mapping(load_config(path), path.parent)
    return generate_eda_artifacts(config)


def generate_eda_artifacts(config: EDAConfig) -> EDAArtifactResult:
    if not config.input_path.is_file():
        raise EDAError(f"EDA input dosyası bulunamadı: {config.input_path}")
    input_sha256 = _file_sha256(config.input_path)
    config_sha256 = _json_sha256(config.semantic_parameters())
    run_id = _json_sha256({"input_sha256": input_sha256, "config_sha256": config_sha256})[:16]

    samples, labels, snr_values, sample_ids = _load_npz(config)
    i_values, q_values = _iq_components(samples, config.representation)
    powers = np.mean(np.square(i_values) + np.square(q_values), axis=1, dtype=np.float64)

    run_metadata = {
        "schema_version": EDA_SCHEMA_VERSION,
        "run_id": run_id,
        "source_id": config.source_id,
        "source_revision": config.source_revision,
        "input_file": config.input_path.name,
        "input_sha256": input_sha256,
        "config_sha256": config_sha256,
        "representation": config.representation.value,
        "sample_count": int(samples.shape[0]),
    }
    class_distribution = _value_distribution(labels, "label")
    snr_distribution = _snr_distribution(snr_values)
    length_distribution = [{"length": int(samples.shape[-1]), "count": int(samples.shape[0])}]
    summary = {
        "schema_version": EDA_SCHEMA_VERSION,
        "run_metadata": run_metadata,
        "class_distribution": class_distribution,
        "snr_distribution": snr_distribution,
        "signal_length_distribution": length_distribution,
        "iq_statistics": {
            "i": _numeric_summary(i_values),
            "q": _numeric_summary(q_values),
        },
        "power_statistics": _numeric_summary(powers),
    }
    spectra = _spectra(i_values, q_values, labels, snr_values, sample_ids, config.max_spectra)
    plot_data = {
        "schema_version": EDA_SCHEMA_VERSION,
        "run_id": run_id,
        "source": {
            "summary": "eda_summary.json",
            "input_sha256": input_sha256,
        },
        "class_distribution": class_distribution,
        "snr_distribution": snr_distribution,
        "signal_length_distribution": length_distribution,
        "sample_spectra": spectra,
    }

    config.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = config.output_dir / "eda_summary.json"
    plot_data_path = config.output_dir / "eda_plot_data.json"
    report_path = config.output_dir / "eda_report.html"
    manifest_path = config.output_dir / "eda_artifacts.json"
    _write_json(summary_path, summary)
    _write_json(plot_data_path, plot_data)
    report_path.write_text(_render_report(summary, plot_data), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": EDA_SCHEMA_VERSION,
        "run_id": run_id,
        "source": {
            "source_id": config.source_id,
            "source_revision": config.source_revision,
            "input_sha256": input_sha256,
        },
        "artifacts": [
            {"path": path.name, "sha256": _file_sha256(path)}
            for path in (summary_path, plot_data_path, report_path)
        ],
    }
    _write_json(manifest_path, manifest)
    return EDAArtifactResult(
        output_dir=config.output_dir,
        run_id=run_id,
        summary_path=summary_path,
        plot_data_path=plot_data_path,
        report_path=report_path,
        manifest_path=manifest_path,
    )


def _load_npz(
    config: EDAConfig,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any], tuple[str, ...]]:
    try:
        with np.load(config.input_path, allow_pickle=False) as payload:
            missing = sorted({"samples", "labels", "snr_db"} - set(payload.files))
            if missing:
                raise EDAError("EDA NPZ alanları eksik: " + ", ".join(missing))
            samples = np.asarray(payload["samples"])
            labels = np.asarray(payload["labels"]).reshape(-1)
            snr_values = np.asarray(payload["snr_db"], dtype=np.float64).reshape(-1)
            raw_ids = (
                np.asarray(payload["sample_ids"]).reshape(-1) if "sample_ids" in payload else None
            )
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, EDAError):
            raise
        raise EDAError(f"EDA NPZ okunamadı: {config.input_path}: {exc}") from exc

    expected_shape = (
        samples.ndim == 3 and samples.shape[1] == 2
        if config.representation is IQRepresentation.CHANNELS_FIRST
        else samples.ndim == 2 and np.iscomplexobj(samples)
    )
    if not expected_shape or samples.shape[0] == 0 or samples.shape[-1] == 0:
        raise EDAError(f"representation ile uyumsuz veya boş samples shape: {list(samples.shape)}")
    expected_dtype = (
        np.dtype(np.float32)
        if config.representation is IQRepresentation.CHANNELS_FIRST
        else np.dtype(np.complex64)
    )
    if samples.dtype != expected_dtype:
        raise EDAError(
            f"{config.representation.value} için samples dtype {expected_dtype} olmalıdır"
        )
    if not np.all(np.isfinite(samples)):
        raise EDAError("EDA input samples NaN veya Inf içeremez")
    sample_count = samples.shape[0]
    if labels.size != sample_count or snr_values.size != sample_count:
        raise EDAError("samples, labels ve snr_db kayıt sayıları eşit olmalıdır")
    if raw_ids is None:
        sample_ids = tuple(f"sample-{index:06d}" for index in range(sample_count))
    else:
        sample_ids = tuple(str(value) for value in raw_ids.tolist())
        if len(sample_ids) != sample_count or any(not value.strip() for value in sample_ids):
            raise EDAError("sample_ids boş olmayan ve samples ile eşit sayıda olmalıdır")
        if len(set(sample_ids)) != len(sample_ids):
            raise EDAError("sample_ids benzersiz olmalıdır")
    return samples, labels, snr_values, sample_ids


def _iq_components(
    samples: np.ndarray[Any, Any], representation: IQRepresentation
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    if representation is IQRepresentation.CHANNELS_FIRST:
        return samples[:, 0, :].astype(np.float64), samples[:, 1, :].astype(np.float64)
    return samples.real.astype(np.float64), samples.imag.astype(np.float64)


def _value_distribution(values: np.ndarray[Any, Any], key: str) -> list[dict[str, Any]]:
    normalized = [_json_scalar(value) for value in values.tolist()]
    counts = Counter((type(value).__name__, str(value)) for value in normalized)
    representatives = {(type(value).__name__, str(value)): value for value in normalized}
    return [
        {key: representatives[identity], "count": counts[identity]} for identity in sorted(counts)
    ]


def _snr_distribution(values: np.ndarray[Any, Any]) -> list[dict[str, Any]]:
    finite = values[np.isfinite(values)]
    counts = Counter(float(value) for value in finite.tolist())
    result: list[dict[str, Any]] = [
        {"snr_db": value, "count": counts[value]} for value in sorted(counts)
    ]
    missing_count = int(values.size - finite.size)
    if missing_count:
        result.append({"snr_db": None, "count": missing_count})
    return result


def _numeric_summary(values: np.ndarray[Any, Any]) -> dict[str, float]:
    flattened = np.asarray(values, dtype=np.float64).reshape(-1)
    return {
        "min": float(np.min(flattened)),
        "max": float(np.max(flattened)),
        "mean": float(np.mean(flattened)),
        "std": float(np.std(flattened)),
    }


def _spectra(
    i_values: np.ndarray[Any, Any],
    q_values: np.ndarray[Any, Any],
    labels: np.ndarray[Any, Any],
    snr_values: np.ndarray[Any, Any],
    sample_ids: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    selected = sorted(range(len(sample_ids)), key=lambda index: sample_ids[index])[:limit]
    frequencies = np.fft.fftshift(np.fft.fftfreq(i_values.shape[1])).tolist()
    result: list[dict[str, Any]] = []
    for index in selected:
        spectrum = np.fft.fftshift(np.fft.fft(i_values[index] + 1j * q_values[index]))
        power = np.square(np.abs(spectrum), dtype=np.float64) / i_values.shape[1]
        result.append(
            {
                "sample_id": sample_ids[index],
                "label": _json_scalar(labels[index]),
                "snr_db": float(snr_values[index]) if np.isfinite(snr_values[index]) else None,
                "frequency_normalized": frequencies,
                "power": power.tolist(),
            }
        )
    return result


def _render_report(summary: dict[str, Any], plot_data: dict[str, Any]) -> str:
    metadata = summary["run_metadata"]
    charts = [
        _bar_chart(
            "Sınıf dağılımı",
            [str(item["label"]) for item in plot_data["class_distribution"]],
            [item["count"] for item in plot_data["class_distribution"]],
            "eda_plot_data.json#/class_distribution",
        ),
        _bar_chart(
            "SNR dağılımı",
            [str(item["snr_db"]) for item in plot_data["snr_distribution"]],
            [item["count"] for item in plot_data["snr_distribution"]],
            "eda_plot_data.json#/snr_distribution",
        ),
    ]
    for spectrum in plot_data["sample_spectra"]:
        charts.append(
            _line_chart(
                f"Spektrum: {spectrum['sample_id']}",
                spectrum["power"],
                "eda_plot_data.json#/sample_spectra",
            )
        )
    stats = html.escape(
        json.dumps(
            {
                "iq_statistics": summary["iq_statistics"],
                "power_statistics": summary["power_statistics"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return (
        '<!doctype html>\n<meta charset="utf-8">\n'
        "<title>RadarIQ EDA</title>\n"
        "<style>body{font:14px system-ui;max-width:960px;margin:2rem auto;color:#172033}"
        "section{border:1px solid #ccd4e0;border-radius:8px;padding:1rem;margin:1rem 0}"
        "svg{width:100%;height:220px}small{color:#526173}pre{background:#f4f6f8;padding:1rem}</style>\n"
        f"<h1>RadarIQ EDA</h1><p>Run <code>{html.escape(metadata['run_id'])}</code> · "
        f"kaynak <code>{html.escape(metadata['source_id'])}@{html.escape(metadata['source_revision'])}</code></p>"
        + "".join(charts)
        + f"<section><h2>Sayısal özet</h2><pre>{stats}</pre>"
        "<small>Kaynak: eda_summary.json#/iq_statistics ve #/power_statistics</small></section>\n"
    )


def _bar_chart(title: str, labels: list[str], values: list[int], source: str) -> str:
    width, height, margin = 800, 180, 35
    maximum = max(values, default=1)
    slot = (width - 2 * margin) / max(len(values), 1)
    bars: list[str] = []
    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        bar_height = (height - 2 * margin) * value / maximum
        x = margin + index * slot + slot * 0.15
        y = height - margin - bar_height
        bars.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{slot * 0.7:.2f}" height="{bar_height:.2f}" fill="#2864dc"/>'
            f'<text x="{x + slot * 0.35:.2f}" y="{height - 12}" text-anchor="middle">{html.escape(label)}</text>'
            f'<text x="{x + slot * 0.35:.2f}" y="{max(y - 5, 12):.2f}" text-anchor="middle">{value}</text>'
        )
    return f'<section><h2>{html.escape(title)}</h2><svg viewBox="0 0 {width} {height}">{"".join(bars)}</svg><small>Kaynak: {html.escape(source)}</small></section>'


def _line_chart(title: str, values: list[float], source: str) -> str:
    width, height, margin = 800, 180, 25
    maximum = max(values, default=1.0) or 1.0
    divisor = max(len(values) - 1, 1)
    points = " ".join(
        f"{margin + index * (width - 2 * margin) / divisor:.2f},{height - margin - value * (height - 2 * margin) / maximum:.2f}"
        for index, value in enumerate(values)
    )
    return f'<section><h2>{html.escape(title)}</h2><svg viewBox="0 0 {width} {height}"><polyline fill="none" stroke="#d63b66" stroke-width="2" points="{points}"/></svg><small>Kaynak: {html.escape(source)}</small></section>'


def _required_path(value: Mapping[str, Any], field: str, base_dir: Path) -> Path:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise EDAError(f"{field} boş olmayan path string olmalıdır")
    path = Path(raw)
    return path if path.is_absolute() else base_dir / path


def _required_string(value: Mapping[str, Any], field: str) -> str:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise EDAError(f"{field} boş olmayan string olmalıdır")
    return raw.strip()


def _json_scalar(value: Any) -> Any:
    return value.item() if isinstance(value, np.generic) else value


def _json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    path.write_text(payload + "\n", encoding="utf-8", newline="\n")
