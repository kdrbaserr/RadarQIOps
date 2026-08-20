"""Train-fitted, leakage-safe preprocessing for canonical I/Q batches."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from radariq.configs import load_config
from radariq.data.contracts import IQRepresentation

PREPROCESSING_SCHEMA_VERSION = "1.0"


class PreprocessingError(ValueError):
    """Raised when preprocessing would be unsafe, ambiguous, or leaky."""


class NormalizationMode(StrEnum):
    NONE = "none"
    TRAIN_RMS_POWER = "train_rms_power"
    TRAIN_PEAK_AMPLITUDE = "train_peak_amplitude"


class PreprocessingArtifactStatus(StrEnum):
    CREATED = "created"
    REUSED = "reused"


@dataclass(frozen=True, slots=True)
class PreprocessingPolicy:
    representation: IQRepresentation
    remove_dc_offset: bool = True
    normalization: NormalizationMode = NormalizationMode.TRAIN_RMS_POWER
    zero_power_epsilon: float = 1e-12
    max_input_amplitude: float = 100.0
    reject_zero_power: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.representation, IQRepresentation):
            raise PreprocessingError("representation desteklenen bir IQRepresentation olmalıdır")
        if not isinstance(self.remove_dc_offset, bool):
            raise PreprocessingError("remove_dc_offset boolean olmalıdır")
        if not isinstance(self.normalization, NormalizationMode):
            raise PreprocessingError("normalization desteklenen bir mod olmalıdır")
        if not isinstance(self.reject_zero_power, bool):
            raise PreprocessingError("reject_zero_power boolean olmalıdır")
        _require_positive_finite(self.zero_power_epsilon, "zero_power_epsilon")
        _require_positive_finite(self.max_input_amplitude, "max_input_amplitude")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> PreprocessingPolicy:
        raw_representation = value.get("representation")
        raw_normalization = value.get("normalization", "train_rms_power")
        if not isinstance(raw_representation, str):
            raise PreprocessingError("representation channels_first veya complex olmalıdır")
        if not isinstance(raw_normalization, str):
            raise PreprocessingError("normalization geçerli bir mod olmalıdır")
        try:
            representation = IQRepresentation(raw_representation)
            normalization = NormalizationMode(raw_normalization)
        except ValueError as exc:
            raise PreprocessingError(
                "representation veya normalization modu desteklenmiyor"
            ) from exc
        return cls(
            representation=representation,
            remove_dc_offset=value.get("remove_dc_offset", True),
            normalization=normalization,
            zero_power_epsilon=value.get("zero_power_epsilon", 1e-12),
            max_input_amplitude=value.get("max_input_amplitude", 100.0),
            reject_zero_power=value.get("reject_zero_power", True),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "representation": self.representation.value,
            "remove_dc_offset": self.remove_dc_offset,
            "normalization": self.normalization.value,
            "zero_power_epsilon": self.zero_power_epsilon,
            "max_input_amplitude": self.max_input_amplitude,
            "reject_zero_power": self.reject_zero_power,
        }


@dataclass(frozen=True, slots=True)
class PreprocessingLineage:
    source_revision: str
    input_sha256: str
    train_indices_sha256: str
    train_sample_count: int
    fit_split: str = "train"

    def __post_init__(self) -> None:
        if not isinstance(self.source_revision, str) or not self.source_revision.strip():
            raise PreprocessingError("source_revision boş olmayan string olmalıdır")
        _require_sha256(self.input_sha256, "input_sha256")
        _require_sha256(self.train_indices_sha256, "train_indices_sha256")
        if self.fit_split != "train":
            raise PreprocessingError("preprocessing yalnız train split üzerinde fit edilebilir")
        if (
            isinstance(self.train_sample_count, bool)
            or not isinstance(self.train_sample_count, int)
            or self.train_sample_count <= 0
        ):
            raise PreprocessingError("train_sample_count pozitif integer olmalıdır")

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_revision": self.source_revision,
            "input_sha256": self.input_sha256,
            "train_indices_sha256": self.train_indices_sha256,
            "train_sample_count": self.train_sample_count,
            "fit_split": self.fit_split,
        }


@dataclass(frozen=True, slots=True)
class FittedPreprocessor:
    policy: PreprocessingPolicy
    lineage: PreprocessingLineage
    dc_i: float
    dc_q: float
    scale: float

    def __post_init__(self) -> None:
        for field in ("dc_i", "dc_q", "scale"):
            value = getattr(self, field)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise PreprocessingError(f"{field} sonlu number olmalıdır")
        if self.scale <= 0:
            raise PreprocessingError("scale sıfırdan büyük olmalıdır")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PREPROCESSING_SCHEMA_VERSION,
            "policy": self.policy.as_dict(),
            "fit_lineage": self.lineage.as_dict(),
            "fitted_statistics": {
                "dc_offset": {"i": self.dc_i, "q": self.dc_q},
                "scale": self.scale,
            },
        }

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.as_dict())

    def transform(self, samples: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """Apply train-fitted values without learning from the transformed batch."""

        i_values, q_values = _validate_and_extract(samples, self.policy, enforce_safety=True)
        transformed_i = (i_values - self.dc_i) / self.scale
        transformed_q = (q_values - self.dc_q) / self.scale
        return _assemble(transformed_i, transformed_q, self.policy.representation)

    def inverse_transform(self, samples: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """Reverse the affine transform for parity and debugging checks."""

        i_values, q_values = _validate_and_extract(samples, self.policy, enforce_safety=False)
        restored_i = i_values * self.scale + self.dc_i
        restored_q = q_values * self.scale + self.dc_q
        return _assemble(restored_i, restored_q, self.policy.representation)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> FittedPreprocessor:
        if value.get("schema_version") != PREPROCESSING_SCHEMA_VERSION:
            raise PreprocessingError("preprocessing artifact schema_version desteklenmiyor")
        policy_value = value.get("policy")
        lineage_value = value.get("fit_lineage")
        statistics = value.get("fitted_statistics")
        if not isinstance(policy_value, Mapping) or not isinstance(lineage_value, Mapping):
            raise PreprocessingError("preprocessing artifact policy veya lineage eksik")
        if not isinstance(statistics, Mapping):
            raise PreprocessingError("preprocessing artifact fitted_statistics eksik")
        dc_offset = statistics.get("dc_offset")
        if not isinstance(dc_offset, Mapping):
            raise PreprocessingError("preprocessing artifact dc_offset eksik")
        return cls(
            policy=PreprocessingPolicy.from_mapping(policy_value),
            lineage=PreprocessingLineage(
                source_revision=_required_string(lineage_value, "source_revision"),
                input_sha256=_required_sha256(lineage_value, "input_sha256"),
                train_indices_sha256=_required_sha256(lineage_value, "train_indices_sha256"),
                train_sample_count=_required_positive_int(lineage_value, "train_sample_count"),
                fit_split=_required_string(lineage_value, "fit_split"),
            ),
            dc_i=_required_finite_float(dc_offset, "i"),
            dc_q=_required_finite_float(dc_offset, "q"),
            scale=_required_finite_float(statistics, "scale"),
        )


@dataclass(frozen=True, slots=True)
class PreprocessingArtifactResult:
    status: PreprocessingArtifactStatus
    output_directory: Path
    preprocessor_sha256: str
    file_sha256: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "output_directory": str(self.output_directory),
            "preprocessor_sha256": self.preprocessor_sha256,
            "file_sha256": dict(sorted(self.file_sha256.items())),
        }


def fit_preprocessor(
    train_samples: np.ndarray[Any, Any],
    policy: PreprocessingPolicy,
    lineage: PreprocessingLineage,
) -> FittedPreprocessor:
    """Fit global I/Q offsets and one scale using train samples only."""

    if lineage.fit_split != "train":
        raise PreprocessingError("preprocessing yalnız train split üzerinde fit edilebilir")
    if train_samples.shape[0] != lineage.train_sample_count:
        raise PreprocessingError("train_sample_count fit batch büyüklüğüyle eşleşmiyor")
    i_values, q_values = _validate_and_extract(train_samples, policy, enforce_safety=True)
    dc_i = float(np.mean(i_values)) if policy.remove_dc_offset else 0.0
    dc_q = float(np.mean(q_values)) if policy.remove_dc_offset else 0.0
    centered_i = i_values - dc_i
    centered_q = q_values - dc_q

    if policy.normalization is NormalizationMode.NONE:
        scale = 1.0
    elif policy.normalization is NormalizationMode.TRAIN_RMS_POWER:
        mean_power = float(np.mean(np.square(centered_i) + np.square(centered_q)))
        scale = math.sqrt(mean_power)
    else:
        scale = float(np.max(np.hypot(centered_i, centered_q)))
    if scale <= policy.zero_power_epsilon:
        raise PreprocessingError("train fit sonrası normalizasyon scale zero-power sınırında")
    return FittedPreprocessor(policy, lineage, dc_i, dc_q, scale)


def preprocess_from_config(config_path: str | Path) -> PreprocessingArtifactResult:
    """Fit on explicit train indices and atomically publish transformed artifacts."""

    path = Path(config_path)
    value = load_config(path)
    base_dir = path.parent
    input_path = _required_path(value, "input_path", base_dir)
    train_indices_path = _required_path(value, "train_indices_path", base_dir)
    output_directory = _required_path(value, "output_dir", base_dir)
    source_revision = _required_string(value, "source_revision")
    policy_value = value.get("preprocessing")
    if not isinstance(policy_value, Mapping):
        raise PreprocessingError("preprocessing config nesnesi zorunludur")
    policy = PreprocessingPolicy.from_mapping(policy_value)

    arrays = _load_npz_arrays(input_path)
    if "samples" not in arrays:
        raise PreprocessingError("input NPZ samples alanı içermelidir")
    samples = arrays["samples"]
    indices = _load_train_indices(train_indices_path, int(samples.shape[0]))
    lineage = PreprocessingLineage(
        source_revision=source_revision,
        input_sha256=_file_sha256(input_path),
        train_indices_sha256=_file_sha256(train_indices_path),
        train_sample_count=int(indices.size),
    )
    preprocessor = fit_preprocessor(samples[indices], policy, lineage)
    transformed = preprocessor.transform(samples)
    output_arrays = {**arrays, "samples": transformed}
    payloads = _artifact_payloads(preprocessor, output_arrays)
    return _write_artifacts(output_directory, preprocessor, payloads)


def _validate_and_extract(
    samples: np.ndarray[Any, Any],
    policy: PreprocessingPolicy,
    *,
    enforce_safety: bool,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    if not isinstance(samples, np.ndarray):
        raise PreprocessingError("samples NumPy ndarray olmalıdır")
    if policy.representation is IQRepresentation.CHANNELS_FIRST:
        if samples.ndim != 3 or samples.shape[1] != 2:
            raise PreprocessingError("channels_first samples shape [N, 2, L] olmalıdır")
        expected_dtype: np.dtype[Any] = np.dtype(np.float32)
        i_values = samples[:, 0, :].astype(np.float64)
        q_values = samples[:, 1, :].astype(np.float64)
    else:
        if samples.ndim != 2:
            raise PreprocessingError("complex samples shape [N, L] olmalıdır")
        expected_dtype = np.dtype(np.complex64)
        i_values = samples.real.astype(np.float64)
        q_values = samples.imag.astype(np.float64)
    if samples.shape[0] == 0 or samples.shape[-1] == 0:
        raise PreprocessingError("samples N ve L sıfırdan büyük olmalıdır")
    if samples.dtype != expected_dtype:
        raise PreprocessingError(
            f"{policy.representation.value} samples dtype {expected_dtype} olmalıdır"
        )
    if not np.all(np.isfinite(samples)):
        raise PreprocessingError("samples NaN veya Inf içeremez")
    if enforce_safety:
        amplitudes = np.hypot(i_values, q_values)
        if float(np.max(amplitudes)) > policy.max_input_amplitude:
            raise PreprocessingError("samples max_input_amplitude sınırını aşıyor")
        sample_powers = np.mean(np.square(i_values) + np.square(q_values), axis=1)
        if policy.reject_zero_power and np.any(sample_powers <= policy.zero_power_epsilon):
            raise PreprocessingError("samples zero-power kayıt içeriyor")
    return i_values, q_values


def _assemble(
    i_values: np.ndarray[Any, Any],
    q_values: np.ndarray[Any, Any],
    representation: IQRepresentation,
) -> np.ndarray[Any, Any]:
    if representation is IQRepresentation.CHANNELS_FIRST:
        return np.stack((i_values, q_values), axis=1).astype(np.float32)
    return (i_values + 1j * q_values).astype(np.complex64)


def _load_npz_arrays(path: Path) -> dict[str, np.ndarray[Any, Any]]:
    if not path.is_file():
        raise PreprocessingError(f"preprocessing input bulunamadı: {path}")
    try:
        with np.load(path, allow_pickle=False) as payload:
            return {name: np.asarray(payload[name]) for name in payload.files}
    except (OSError, TypeError, ValueError) as exc:
        raise PreprocessingError(f"preprocessing NPZ okunamadı: {path}: {exc}") from exc


def _load_train_indices(path: Path, sample_count: int) -> np.ndarray[Any, Any]:
    if not path.is_file():
        raise PreprocessingError(f"train indices bulunamadı: {path}")
    try:
        indices = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise PreprocessingError(f"train indices okunamadı: {path}: {exc}") from exc
    if not isinstance(indices, np.ndarray) or indices.ndim != 1:
        raise PreprocessingError("train indices tek boyutlu NumPy array olmalıdır")
    if not np.issubdtype(indices.dtype, np.integer):
        raise PreprocessingError("train indices integer dtype olmalıdır")
    if indices.size == 0:
        raise PreprocessingError("train indices boş olamaz")
    normalized = indices.astype(np.int64)
    if len(set(normalized.tolist())) != normalized.size:
        raise PreprocessingError("train indices benzersiz olmalıdır")
    if normalized.size > 1 and np.any(normalized[1:] <= normalized[:-1]):
        raise PreprocessingError("train indices deterministik artan sırada olmalıdır")
    if np.any(normalized < 0) or np.any(normalized >= sample_count):
        raise PreprocessingError("train indices samples aralığı dışında")
    return normalized


def _artifact_payloads(
    preprocessor: FittedPreprocessor,
    output_arrays: Mapping[str, np.ndarray[Any, Any]],
) -> dict[str, bytes]:
    preprocessor_payload = _json_bytes(preprocessor.as_dict())
    processed_payload = _deterministic_npz(output_arrays)
    manifest = {
        "schema_version": PREPROCESSING_SCHEMA_VERSION,
        "preprocessor_sha256": preprocessor.sha256,
        "lineage": preprocessor.lineage.as_dict(),
        "files": {
            "preprocessor.json": hashlib.sha256(preprocessor_payload).hexdigest(),
            "processed_iq.npz": hashlib.sha256(processed_payload).hexdigest(),
        },
    }
    return {
        "preprocessor.json": preprocessor_payload,
        "processed_iq.npz": processed_payload,
        "preprocessing_artifacts.json": _json_bytes(manifest),
    }


def _write_artifacts(
    destination: Path,
    preprocessor: FittedPreprocessor,
    payloads: Mapping[str, bytes],
) -> PreprocessingArtifactResult:
    destination = destination.expanduser().resolve()
    if destination.exists():
        _verify_existing(destination, payloads)
        return _artifact_result(
            PreprocessingArtifactStatus.REUSED, destination, preprocessor, payloads
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".part")
    )
    try:
        for name, payload in payloads.items():
            _write_fsync(temporary / name, payload)
        try:
            temporary.rename(destination)
        except FileExistsError:
            _verify_existing(destination, payloads)
            return _artifact_result(
                PreprocessingArtifactStatus.REUSED, destination, preprocessor, payloads
            )
        return _artifact_result(
            PreprocessingArtifactStatus.CREATED, destination, preprocessor, payloads
        )
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _verify_existing(destination: Path, payloads: Mapping[str, bytes]) -> None:
    if not destination.is_dir():
        raise PreprocessingError("preprocessing artifact hedefi dizin olmalıdır")
    entries = list(destination.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise PreprocessingError("preprocessing artifact dizini yalnız normal dosya içerebilir")
    if {path.name for path in entries} != set(payloads):
        raise PreprocessingError("mevcut preprocessing artifact dosya kümesi farklı")
    if any((destination / name).read_bytes() != payload for name, payload in payloads.items()):
        raise PreprocessingError("preprocessing artifact farklı içerikle yerinde değiştirilemez")


def _artifact_result(
    status: PreprocessingArtifactStatus,
    destination: Path,
    preprocessor: FittedPreprocessor,
    payloads: Mapping[str, bytes],
) -> PreprocessingArtifactResult:
    return PreprocessingArtifactResult(
        status=status,
        output_directory=destination,
        preprocessor_sha256=preprocessor.sha256,
        file_sha256={
            name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()
        },
    )


def _deterministic_npz(arrays: Mapping[str, np.ndarray[Any, Any]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(arrays):
            array_output = io.BytesIO()
            np.lib.format.write_array(array_output, np.asarray(arrays[name]), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o600 << 16
            archive.writestr(info, array_output.getvalue())
    return output.getvalue()


def _required_path(value: Mapping[str, Any], field: str, base_dir: Path) -> Path:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise PreprocessingError(f"{field} boş olmayan path string olmalıdır")
    path = Path(raw)
    return path if path.is_absolute() else base_dir / path


def _required_string(value: Mapping[str, Any], field: str) -> str:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise PreprocessingError(f"{field} boş olmayan string olmalıdır")
    return raw.strip()


def _required_sha256(value: Mapping[str, Any], field: str) -> str:
    raw = value.get(field)
    _require_sha256(raw, field)
    assert isinstance(raw, str)
    return raw


def _required_positive_int(value: Mapping[str, Any], field: str) -> int:
    raw = value.get(field)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise PreprocessingError(f"{field} pozitif integer olmalıdır")
    return raw


def _required_finite_float(value: Mapping[str, Any], field: str) -> float:
    raw = value.get(field)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise PreprocessingError(f"{field} sonlu number olmalıdır")
    return float(raw)


def _require_positive_finite(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PreprocessingError(f"{field} pozitif ve sonlu number olmalıdır")
    if not math.isfinite(float(value)) or float(value) <= 0:
        raise PreprocessingError(f"{field} pozitif ve sonlu number olmalıdır")


def _require_sha256(value: Any, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PreprocessingError(f"{field} geçerli küçük harf SHA-256 olmalıdır")


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    return (payload + "\n").encode("utf-8")


def _write_fsync(path: Path, payload: bytes) -> None:
    with path.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
