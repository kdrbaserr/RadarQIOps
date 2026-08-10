from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Iterable

import h5py
import numpy as np


DATASET_CHOICES = (
    "radioml-2016.10a",
    "radioml-2018.01a",
    "radarscenes",
    "carrada",
    "raddet",
    "k-radar",
    "npy",
)

RADARSCENES_LABELS = {
    0: "car",
    1: "large_vehicle",
    2: "truck",
    3: "bus",
    4: "train",
    5: "bicycle",
    6: "motorized_two_wheeler",
    7: "pedestrian",
    8: "pedestrian_group",
    9: "animal",
    10: "other",
    11: "static",
}


class InspectError(RuntimeError):
    """Raised when a dataset sample cannot be inspected safely."""


def inspect_dataset(
    dataset: str,
    path: Path,
    sample_index: int = 0,
    metadata_path: Path | None = None,
    allow_unsafe_pickle: bool = False,
) -> dict[str, Any]:
    if sample_index < 0:
        raise InspectError("sample-index sıfır veya daha büyük olmalıdır")

    source = path.expanduser()
    if not source.exists():
        raise InspectError(f"Veri yolu bulunamadı: {source}")

    if dataset == "radioml-2016.10a":
        inspected = _inspect_radioml_2016(source, sample_index, allow_unsafe_pickle)
    elif dataset == "radioml-2018.01a":
        inspected = _inspect_radioml_2018(source, sample_index)
    elif dataset == "radarscenes":
        inspected = _inspect_radarscenes(source, sample_index)
    elif dataset in {"carrada", "raddet", "k-radar", "npy"}:
        inspected = _inspect_npy(source, sample_index, metadata_path)
    else:
        raise InspectError(f"Desteklenmeyen veri seti: {dataset}")

    sample = inspected.pop("sample")
    return {
        "schema_version": "1.0",
        "dataset": dataset,
        "source": str(inspected.pop("source").resolve()),
        "sample_index": sample_index,
        "shape": list(np.asarray(sample).shape),
        "dtype": _describe_dtype(np.asarray(sample).dtype),
        "label": _json_safe(inspected.pop("label", None)),
        "snr_db": _json_safe(inspected.pop("snr_db", None)),
        "group_id": _json_safe(inspected.pop("group_id", None)),
        "sequence_id": _json_safe(inspected.pop("sequence_id", None)),
        "statistics": _statistics(sample),
        **{key: _json_safe(value) for key, value in inspected.items()},
    }


def _inspect_radioml_2016(
    path: Path, sample_index: int, allow_unsafe_pickle: bool
) -> dict[str, Any]:
    if not allow_unsafe_pickle:
        raise InspectError(
            "RadioML 2016 pickle dosyaları güvenilmeyen kod çalıştırabilir. "
            "Kaynağı ve checksum'u doğruladıktan sonra --allow-unsafe-pickle kullanın."
        )
    file_path = _resolve_file(path, ("*.pkl", "*.pickle", "*.dat"))
    with file_path.open("rb") as handle:
        try:
            payload = pickle.load(handle, encoding="latin1")
        except TypeError:
            handle.seek(0)
            payload = pickle.load(handle)

    if not isinstance(payload, dict):
        raise InspectError("RadioML 2016 dosyasında sözlük yapısı bekleniyordu")

    cursor = 0
    for key in sorted(payload, key=lambda item: str(item)):
        block = np.asarray(payload[key])
        if block.ndim == 0:
            continue
        next_cursor = cursor + len(block)
        if sample_index < next_cursor:
            local_index = sample_index - cursor
            label, snr = _radioml_key(key)
            return {
                "source": file_path,
                "sample": block[local_index],
                "label": label,
                "snr_db": snr,
                "group_id": None,
                "sequence_id": file_path.stem,
                "local_index": local_index,
            }
        cursor = next_cursor

    raise InspectError(f"sample-index veri seti dışında: {sample_index} (toplam {cursor})")


def _radioml_key(key: Any) -> tuple[Any, float | None]:
    if isinstance(key, tuple) and len(key) >= 2:
        return _json_safe(key[0]), _optional_float(key[1])
    return _json_safe(key), None


def _inspect_radioml_2018(path: Path, sample_index: int) -> dict[str, Any]:
    file_path = _resolve_file(path, ("*.h5", "*.hdf5"))
    with h5py.File(file_path, "r") as handle:
        x_key = _find_h5_key(handle, ("X", "x", "samples", "data"), required=True)
        samples = handle[x_key]
        _check_index(sample_index, len(samples))
        sample = np.asarray(samples[sample_index])

        y_key = _find_h5_key(handle, ("Y", "y", "labels", "label"))
        label = None
        if y_key:
            raw_label = np.asarray(handle[y_key][sample_index])
            label_index = int(np.argmax(raw_label)) if raw_label.ndim else int(raw_label)
            classes = _load_classes(file_path.parent)
            label = {
                "index": label_index,
                "name": classes[label_index] if label_index < len(classes) else None,
            }

        z_key = _find_h5_key(handle, ("Z", "z", "snr", "snrs"))
        snr = None
        if z_key:
            raw_snr = np.asarray(handle[z_key][sample_index]).reshape(-1)
            if raw_snr.size:
                snr = _optional_float(raw_snr[0])

        sequence_id = _decode_scalar(handle.attrs.get("sequence_id", file_path.stem))

    return {
        "source": file_path,
        "sample": sample,
        "label": label,
        "snr_db": snr,
        "group_id": None,
        "sequence_id": sequence_id,
    }


def _inspect_radarscenes(path: Path, sample_index: int) -> dict[str, Any]:
    file_path = _resolve_file(path, ("radar_data.h5", "*.h5", "*.hdf5"))
    with h5py.File(file_path, "r") as handle:
        data_key = _find_h5_key(handle, ("radar_data",), required=True)
        detections = handle[data_key]
        _check_index(sample_index, len(detections))
        sample = np.asarray(detections[sample_index])

    fields = sample.dtype.names or ()
    label_id = _structured_value(sample, "label_id") if "label_id" in fields else None
    label_index = int(label_id) if label_id is not None else None
    label = (
        {"index": label_index, "name": RADARSCENES_LABELS.get(label_index)}
        if label_index is not None
        else None
    )
    group_id = _structured_value(sample, "track_id") if "track_id" in fields else None

    return {
        "source": file_path,
        "sample": sample,
        "label": label,
        "snr_db": None,
        "group_id": _empty_to_none(group_id),
        "sequence_id": file_path.parent.name,
        "snr_note": "RadarScenes açık SNR sağlamaz; rcs alanı SNR değildir.",
    }


def _inspect_npy(
    path: Path, sample_index: int, metadata_path: Path | None
) -> dict[str, Any]:
    if sample_index != 0:
        raise InspectError(
            "NPY okuyucusunda her dosya tek örnek kabul edilir; --sample-index 0 kullanın"
        )
    file_path = _resolve_file(path, ("*.npy",))
    sample = np.load(file_path, allow_pickle=False, mmap_mode="r")

    sidecar = metadata_path.expanduser() if metadata_path else file_path.with_suffix(".json")
    metadata: dict[str, Any] = {}
    if sidecar.exists():
        loaded = json.loads(sidecar.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise InspectError("NPY metadata dosyası bir JSON nesnesi olmalıdır")
        metadata = loaded
    elif metadata_path:
        raise InspectError(f"Metadata dosyası bulunamadı: {sidecar}")

    return {
        "source": file_path,
        "sample": sample,
        "label": metadata.get("label"),
        "snr_db": _optional_float(metadata.get("snr_db")),
        "group_id": metadata.get("group_id"),
        "sequence_id": metadata.get("sequence_id", file_path.parent.name),
        "metadata_source": str(sidecar.resolve()) if sidecar.exists() else None,
    }


def _resolve_file(path: Path, patterns: Iterable[str]) -> Path:
    if path.is_file():
        return path
    for pattern in patterns:
        matches = sorted(candidate for candidate in path.rglob(pattern) if candidate.is_file())
        if matches:
            return matches[0]
    expected = ", ".join(patterns)
    raise InspectError(f"{path} altında beklenen dosya bulunamadı ({expected})")


def _find_h5_key(
    handle: h5py.File, candidates: Iterable[str], required: bool = False
) -> str | None:
    for candidate in candidates:
        if candidate in handle:
            return candidate
    if required:
        raise InspectError(
            "HDF5 içinde beklenen veri alanı bulunamadı: " + ", ".join(candidates)
        )
    return None


def _load_classes(directory: Path) -> list[str]:
    classes_path = directory / "classes.txt"
    if not classes_path.exists():
        return []
    text = classes_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    return [line.strip() for line in text.splitlines() if line.strip()]


def _check_index(index: int, total: int) -> None:
    if index >= total:
        raise InspectError(f"sample-index veri seti dışında: {index} (toplam {total})")


def _describe_dtype(dtype: np.dtype[Any]) -> str | dict[str, Any]:
    if dtype.names:
        fields = dtype.fields
        assert fields is not None
        return {
            "kind": "structured",
            "fields": {
                name: str(fields[name][0])
                for name in dtype.names
            },
        }
    return str(dtype)


def _statistics(sample: Any) -> dict[str, Any]:
    array = np.asarray(sample)
    if array.dtype.names:
        fields = array.dtype.fields
        assert fields is not None
        return {
            "basis": "structured_fields",
            "fields": {
                name: _numeric_statistics(np.asarray(array[name]))
                for name in array.dtype.names
                if np.issubdtype(fields[name][0], np.number)
            },
        }
    return _numeric_statistics(array)


def _numeric_statistics(array: np.ndarray[Any, Any]) -> dict[str, Any]:
    if not (
        np.issubdtype(array.dtype, np.number)
        or np.issubdtype(array.dtype, np.bool_)
    ):
        return {"basis": "non_numeric", "count": int(array.size)}

    basis = "magnitude" if np.iscomplexobj(array) else "value"
    values = np.abs(array) if np.iscomplexobj(array) else array.astype(np.float64)
    flattened = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = flattened[np.isfinite(flattened)]
    if not finite.size:
        return {
            "basis": basis,
            "count": int(flattened.size),
            "finite_count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
        }
    return {
        "basis": basis,
        "count": int(flattened.size),
        "finite_count": int(finite.size),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
    }


def _structured_value(sample: np.ndarray[Any, Any], field: str) -> Any:
    return _json_safe(np.asarray(sample[field]).reshape(-1)[0])


def _decode_scalar(value: Any) -> Any:
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8", errors="replace")
    return _json_safe(value)


def _empty_to_none(value: Any) -> Any:
    decoded = _decode_scalar(value)
    return None if decoded in (None, "", "00000000-0000-0000-0000-000000000000") else decoded


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    numeric = float(np.asarray(value).reshape(-1)[0])
    return numeric if np.isfinite(numeric) else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value

