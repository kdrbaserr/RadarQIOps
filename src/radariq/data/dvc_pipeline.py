"""DVC stage entry points and small export-manifest verification for the data pipeline."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from radariq.configs import load_config
from radariq.data.contracts import IQRepresentation
from radariq.data.leakage import (
    DuplicatePolicy,
    ExplicitGroupIdAdapter,
    LeakageCandidate,
    analyze_duplicates_and_leakage,
)
from radariq.data.preprocessing import preprocess_from_config
from radariq.data.quarantine import (
    QualityLineage,
    QuarantinePolicy,
    build_quarantine_decision,
    write_quarantine_artifacts,
)
from radariq.data.splitting import split_from_config
from radariq.data.validation import SampleCandidate, ValidationPolicy, validate_samples

PIPELINE_EXPORT_SCHEMA_VERSION = "1.0"
PIPELINE_STAGE_ORDER = ("validate", "split", "preprocess", "report")


class DataPipelineError(RuntimeError):
    """Raised when a DVC stage cannot produce a trustworthy artifact chain."""


def run_validation_stage(params_path: str | Path) -> dict[str, Any]:
    params_file, params = _load_params(params_path)
    pipeline = _required_mapping(params, "pipeline")
    validation_value = _required_mapping(params, "validation")
    leakage_value = _required_mapping(params, "leakage")
    input_path = _param_path(params_file, pipeline, "raw_input")
    output_directory = _param_path(params_file, pipeline, "validation_output")
    source_revision = _required_string(pipeline, "source_revision")
    representation = _representation(validation_value)
    arrays = _load_pipeline_input(input_path, representation)
    policy = ValidationPolicy.from_mapping(validation_value)
    duplicate_policy = DuplicatePolicy.from_mapping(leakage_value)
    if duplicate_policy.representation is not representation:
        raise DataPipelineError("validation ve leakage representation aynı olmalıdır")

    candidates = [
        SampleCandidate(
            sample_id=str(arrays["sample_ids"][index]),
            signal=arrays["samples"][index],
            label=_json_scalar(arrays["labels"][index]),
            snr_db=_optional_snr(arrays["snr_db"][index]),
        )
        for index in range(len(arrays["sample_ids"]))
    ]
    validation_report = validate_samples(candidates, policy)
    valid_ids = set(validation_report.valid_sample_ids)
    leakage_candidates = [
        LeakageCandidate(
            sample_id=str(arrays["sample_ids"][index]),
            signal=arrays["samples"][index],
            label=_json_scalar(arrays["labels"][index]),
            group_id=str(arrays["group_ids"][index]),
            source_version=source_revision,
        )
        for index in range(len(arrays["sample_ids"]))
        if str(arrays["sample_ids"][index]) in valid_ids
    ]
    leakage_report = analyze_duplicates_and_leakage(
        leakage_candidates,
        duplicate_policy,
        ExplicitGroupIdAdapter(),
    )
    raw_sha256 = _file_sha256(input_path)
    validation_policy_sha256 = _canonical_sha256(validation_value)
    leakage_policy_sha256 = _canonical_sha256(leakage_value)
    decision = build_quarantine_decision(
        validation_report,
        leakage_report,
        QuarantinePolicy(),
        QualityLineage(
            raw_manifest_sha256=raw_sha256,
            validation_policy_sha256=validation_policy_sha256,
            leakage_policy_sha256=leakage_policy_sha256,
        ),
    )
    accepted_ids = set(decision.accepted_sample_ids)
    accepted_indices = [
        index
        for index, sample_id in enumerate(arrays["sample_ids"])
        if str(sample_id) in accepted_ids
    ]
    if not accepted_indices:
        raise DataPipelineError("validation sonrasında kabul edilen örnek kalmadı")
    accepted_arrays = {name: values[accepted_indices] for name, values in arrays.items()}
    accepted_payload = _deterministic_npz(accepted_arrays)

    temporary = _temporary_sibling(output_directory)
    try:
        quality_result = write_quarantine_artifacts(decision, temporary / "quality")
        accepted_path = temporary / "accepted_iq.npz"
        _write_bytes(accepted_path, accepted_payload)
        stage_manifest = {
            "schema_version": PIPELINE_EXPORT_SCHEMA_VERSION,
            "stage": "validate",
            "source_revision": source_revision,
            "raw_input_sha256": raw_sha256,
            "validation_policy_sha256": validation_policy_sha256,
            "leakage_policy_sha256": leakage_policy_sha256,
            "decision_sha256": quality_result.decision_sha256,
            "accepted_iq_sha256": hashlib.sha256(accepted_payload).hexdigest(),
            "total_count": decision.total_count,
            "accepted_count": decision.accepted_count,
            "quarantine_count": decision.quarantine_count,
        }
        _write_json(temporary / "validation_stage.json", stage_manifest)
        _publish_tree(temporary, output_directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return stage_manifest


def run_split_stage(params_path: str | Path) -> dict[str, Any]:
    params_file, params = _load_params(params_path)
    pipeline = _required_mapping(params, "pipeline")
    split_policy = _required_mapping(params, "split")
    input_path = _param_path(params_file, pipeline, "validation_output") / "accepted_iq.npz"
    output_directory = _param_path(params_file, pipeline, "split_output")
    config = {
        "input_path": str(input_path.resolve()),
        "output_dir": str(output_directory.resolve()),
        "source_revision": _required_string(pipeline, "source_revision"),
        "split": split_policy,
    }
    result = _invoke_with_config(split_from_config, config, output_directory.parent)
    return result.as_dict()


def run_preprocessing_stage(params_path: str | Path) -> dict[str, Any]:
    params_file, params = _load_params(params_path)
    pipeline = _required_mapping(params, "pipeline")
    preprocessing_policy = _required_mapping(params, "preprocessing")
    validation_directory = _param_path(params_file, pipeline, "validation_output")
    split_directory = _param_path(params_file, pipeline, "split_output")
    output_directory = _param_path(params_file, pipeline, "preprocessing_output")
    config = {
        "input_path": str((validation_directory / "accepted_iq.npz").resolve()),
        "train_indices_path": str((split_directory / "train_indices.npy").resolve()),
        "output_dir": str(output_directory.resolve()),
        "source_revision": _required_string(pipeline, "source_revision"),
        "preprocessing": preprocessing_policy,
    }
    result = _invoke_with_config(preprocess_from_config, config, output_directory.parent)
    return result.as_dict()


def run_report_stage(params_path: str | Path) -> dict[str, Any]:
    params_file, params = _load_params(params_path)
    pipeline = _required_mapping(params, "pipeline")
    validation_directory = _param_path(params_file, pipeline, "validation_output")
    split_directory = _param_path(params_file, pipeline, "split_output")
    preprocessing_directory = _param_path(params_file, pipeline, "preprocessing_output")
    output_directory = _param_path(params_file, pipeline, "report_output")

    validation = _load_json(validation_directory / "validation_stage.json")
    split_manifest = _load_json(split_directory / "split_manifest.json")
    test_lock = _load_json(split_directory / "test_lock.json")
    preprocessor = _load_json(preprocessing_directory / "preprocessor.json")
    preprocessing_manifest = _load_json(preprocessing_directory / "preprocessing_artifacts.json")
    accepted_sha256 = _file_sha256(validation_directory / "accepted_iq.npz")
    if split_manifest.get("input_sha256") != accepted_sha256:
        raise DataPipelineError("split input hash validation accepted_iq hash'iyle eşleşmiyor")
    fit_lineage = _required_mapping(preprocessor, "fit_lineage")
    if fit_lineage.get("input_sha256") != accepted_sha256:
        raise DataPipelineError(
            "preprocessing input hash validation accepted_iq hash'iyle eşleşmiyor"
        )
    train_sha256 = _file_sha256(split_directory / "train_indices.npy")
    if fit_lineage.get("train_indices_sha256") != train_sha256:
        raise DataPipelineError("preprocessing train indeks hash'i split çıktısıyla eşleşmiyor")
    split_plan_sha256 = _canonical_sha256(split_manifest)
    if test_lock.get("split_plan_sha256") != split_plan_sha256:
        raise DataPipelineError("test lock split manifest kimliğiyle eşleşmiyor")
    split_details = _required_mapping(split_manifest, "splits")
    actual_index_sha256: dict[str, str] = {}
    for split_name in ("train", "validation", "test"):
        detail = _required_mapping(split_details, split_name)
        actual = _file_sha256(split_directory / f"{split_name}_indices.npy")
        if detail.get("indices_sha256") != actual:
            raise DataPipelineError(f"{split_name} indeks hash'i split manifest ile eşleşmiyor")
        actual_index_sha256[split_name] = actual
    test_reference = _required_mapping(test_lock, "test_indices")
    if test_reference.get("sha256") != actual_index_sha256["test"]:
        raise DataPipelineError("test lock indeks hash'i test split çıktısıyla eşleşmiyor")
    preprocessor_sha256 = _canonical_sha256(preprocessor)
    if preprocessing_manifest.get("preprocessor_sha256") != preprocessor_sha256:
        raise DataPipelineError("preprocessor hash preprocessing manifest ile eşleşmiyor")
    preprocessing_files = _required_mapping(preprocessing_manifest, "files")
    processed_iq_sha256 = _file_sha256(preprocessing_directory / "processed_iq.npz")
    if preprocessing_files.get("processed_iq.npz") != processed_iq_sha256:
        raise DataPipelineError("processed IQ hash preprocessing manifest ile eşleşmiyor")

    execution = _execution_evidence(pipeline)
    body = {
        "schema_version": PIPELINE_EXPORT_SCHEMA_VERSION,
        "pipeline": {
            "stage_order": list(PIPELINE_STAGE_ORDER),
            "params_sha256": _canonical_sha256(params),
            "source_revision": _required_string(pipeline, "source_revision"),
        },
        "execution": execution,
        "validation": {
            "raw_input_sha256": validation.get("raw_input_sha256"),
            "accepted_iq_sha256": accepted_sha256,
            "decision_sha256": validation.get("decision_sha256"),
            "accepted_count": validation.get("accepted_count"),
            "quarantine_count": validation.get("quarantine_count"),
        },
        "split": {
            "split_plan_sha256": split_plan_sha256,
            "seed": split_manifest.get("seed"),
            "train_indices_sha256": actual_index_sha256["train"],
            "validation_indices_sha256": actual_index_sha256["validation"],
            "test_indices_sha256": actual_index_sha256["test"],
            "test_lock_sha256": _file_sha256(split_directory / "test_lock.json"),
        },
        "preprocessing": {
            "preprocessor_sha256": preprocessor_sha256,
            "processed_iq_sha256": processed_iq_sha256,
            "fit_split": fit_lineage.get("fit_split"),
            "train_indices_sha256": fit_lineage.get("train_indices_sha256"),
        },
    }
    manifest = {**body, "manifest_sha256": _canonical_sha256(body)}
    errors = validate_pipeline_export_manifest(manifest)
    if errors:
        raise DataPipelineError("pipeline export manifest geçersiz: " + "; ".join(errors))
    payload = _json_bytes(manifest)
    _publish_files(output_directory, {"pipeline_export_manifest.json": payload})
    return manifest


def validate_pipeline_export_manifest(
    manifest: Mapping[str, Any], expected_split_sha256: str | None = None
) -> list[str]:
    """Validate only the small export manifest; never open dataset/model artifacts."""

    errors: list[str] = []
    if manifest.get("schema_version") != PIPELINE_EXPORT_SCHEMA_VERSION:
        errors.append("schema_version 1.0 olmalıdır")
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != _canonical_sha256(body):
        errors.append("manifest_sha256 içerikle eşleşmiyor")
    pipeline = manifest.get("pipeline")
    if not isinstance(pipeline, Mapping):
        errors.append("pipeline nesnesi zorunludur")
    else:
        if pipeline.get("stage_order") != list(PIPELINE_STAGE_ORDER):
            errors.append("pipeline.stage_order güvenli sırayla eşleşmiyor")
        _append_sha_error(errors, pipeline, "params_sha256", "pipeline")
        if not _nonempty_string(pipeline.get("source_revision")):
            errors.append("pipeline.source_revision zorunludur")
    execution = manifest.get("execution")
    if not isinstance(execution, Mapping):
        errors.append("execution nesnesi zorunludur")
    else:
        profile = execution.get("profile")
        if profile not in {"fixture", "colab"}:
            errors.append("execution.profile fixture veya colab olmalıdır")
        if profile == "colab":
            if execution.get("dvc_pull_status") != "verified":
                errors.append("Colab manifestinde DVC pull verified olmalıdır")
            _append_sha_error(errors, execution, "dvc_pull_log_sha256", "execution")
            _append_sha_error(errors, execution, "runtime_manifest_sha256", "execution")
        if not _nonempty_string(execution.get("dvc_remote")):
            errors.append("execution.dvc_remote zorunludur")
    for section_name, fields in {
        "validation": ("raw_input_sha256", "accepted_iq_sha256", "decision_sha256"),
        "split": (
            "split_plan_sha256",
            "train_indices_sha256",
            "validation_indices_sha256",
            "test_indices_sha256",
            "test_lock_sha256",
        ),
        "preprocessing": ("preprocessor_sha256", "processed_iq_sha256", "train_indices_sha256"),
    }.items():
        section = manifest.get(section_name)
        if not isinstance(section, Mapping):
            errors.append(f"{section_name} nesnesi zorunludur")
            continue
        for field in fields:
            _append_sha_error(errors, section, field, section_name)
    split = manifest.get("split")
    preprocessing = manifest.get("preprocessing")
    if isinstance(split, Mapping) and isinstance(preprocessing, Mapping):
        if split.get("train_indices_sha256") != preprocessing.get("train_indices_sha256"):
            errors.append("split ve preprocessing train indeks hash'leri eşleşmiyor")
        if expected_split_sha256 is not None:
            if not _is_sha256(expected_split_sha256):
                errors.append("beklenen split SHA-256 biçimi geçersiz")
            elif split.get("split_plan_sha256") != expected_split_sha256:
                errors.append("split_plan_sha256 beklenen değerle eşleşmiyor")
    if isinstance(preprocessing, Mapping) and preprocessing.get("fit_split") != "train":
        errors.append("preprocessing.fit_split train olmalıdır")
    return errors


def _execution_evidence(pipeline: Mapping[str, Any]) -> dict[str, Any]:
    profile = pipeline.get("execution_profile", "fixture")
    if profile not in {"fixture", "colab"}:
        raise DataPipelineError("execution_profile fixture veya colab olmalıdır")
    result = {
        "profile": profile,
        "dvc_remote": _required_string(pipeline, "dvc_remote"),
        "dvc_pull_status": pipeline.get("dvc_pull_status", "fixture"),
    }
    if profile == "colab":
        result["dvc_pull_log_sha256"] = _required_sha256(pipeline, "dvc_pull_log_sha256")
        result["runtime_manifest_sha256"] = _required_sha256(pipeline, "runtime_manifest_sha256")
    return result


def _load_pipeline_input(
    path: Path, representation: IQRepresentation
) -> dict[str, np.ndarray[Any, Any]]:
    if path.suffix.casefold() == ".json":
        value = _load_json(path)
        metadata = value.get("metadata")
        if not isinstance(metadata, list):
            raise DataPipelineError("fixture JSON metadata listesi içermelidir")
        samples = np.asarray(value.get("samples"))
        dtype = np.float32 if representation is IQRepresentation.CHANNELS_FIRST else np.complex64
        samples = samples.astype(dtype)
        arrays = {
            "samples": samples,
            "sample_ids": np.asarray([item.get("sample_id") for item in metadata]),
            "labels": np.asarray([item.get("label") for item in metadata]),
            "snr_db": np.asarray(
                [np.nan if item.get("snr_db") is None else item.get("snr_db") for item in metadata],
                dtype=np.float64,
            ),
            "group_ids": np.asarray([item.get("group_id") for item in metadata]),
        }
    else:
        try:
            with np.load(path, allow_pickle=False) as payload:
                arrays = {name: np.asarray(payload[name]) for name in payload.files}
        except (OSError, TypeError, ValueError) as exc:
            raise DataPipelineError(f"pipeline NPZ okunamadı: {path}: {exc}") from exc
    required = {"samples", "sample_ids", "labels", "snr_db", "group_ids"}
    missing = sorted(required.difference(arrays))
    if missing:
        raise DataPipelineError("pipeline input alanları eksik: " + ", ".join(missing))
    sample_count = len(arrays["samples"])
    if any(len(arrays[name]) != sample_count for name in required):
        raise DataPipelineError("pipeline input alanlarının örnek sayıları eşit olmalıdır")
    return arrays


def _representation(value: Mapping[str, Any]) -> IQRepresentation:
    raw = value.get("representation")
    if not isinstance(raw, str):
        raise DataPipelineError("validation representation zorunludur")
    try:
        return IQRepresentation(raw)
    except ValueError as exc:
        raise DataPipelineError("validation representation desteklenmiyor") from exc


def _invoke_with_config(function: Any, config: Mapping[str, Any], directory: Path) -> Any:
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix="pipeline-stage-", suffix=".json", dir=directory)
    os.close(descriptor)
    path = Path(raw_path)
    try:
        path.write_bytes(_json_bytes(config))
        return function(path)
    finally:
        path.unlink(missing_ok=True)


def _load_params(params_path: str | Path) -> tuple[Path, dict[str, Any]]:
    path = Path(params_path)
    return path, load_config(path)


def _param_path(params_file: Path, value: Mapping[str, Any], field: str) -> Path:
    raw = _required_string(value, field)
    path = Path(raw)
    return path if path.is_absolute() else params_file.parent / path


def _required_mapping(value: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    result = value.get(field)
    if not isinstance(result, Mapping):
        raise DataPipelineError(f"{field} config nesnesi zorunludur")
    return result


def _required_string(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise DataPipelineError(f"{field} boş olmayan string olmalıdır")
    return result.strip()


def _required_sha256(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not _is_sha256(result):
        raise DataPipelineError(f"{field} geçerli küçük harf SHA-256 olmalıdır")
    assert isinstance(result, str)
    return result


def _append_sha_error(errors: list[str], value: Mapping[str, Any], field: str, prefix: str) -> None:
    if not _is_sha256(value.get(field)):
        errors.append(f"{prefix}.{field} geçerli SHA-256 olmalıdır")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _optional_snr(value: Any) -> float | None:
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _json_scalar(value: Any) -> Any:
    return value.item() if isinstance(value, np.generic) else value


def _temporary_sibling(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    return Path(
        tempfile.mkdtemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".part")
    )


def _publish_tree(temporary: Path, destination: Path) -> None:
    if destination.exists():
        if _tree_hashes(destination) != _tree_hashes(temporary):
            raise DataPipelineError(
                "pipeline stage artifact farklı içerikle yerinde değiştirilemez"
            )
        return
    temporary.rename(destination)


def _publish_files(destination: Path, payloads: Mapping[str, bytes]) -> None:
    if destination.exists():
        if not destination.is_dir() or {path.name for path in destination.iterdir()} != set(
            payloads
        ):
            raise DataPipelineError("pipeline report artifact dosya kümesi farklı")
        if any((destination / name).read_bytes() != payload for name, payload in payloads.items()):
            raise DataPipelineError("pipeline report farklı içerikle yerinde değiştirilemez")
        return
    temporary = _temporary_sibling(destination)
    try:
        for name, payload in payloads.items():
            _write_bytes(temporary / name, payload)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _tree_hashes(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        raise DataPipelineError("pipeline artifact hedefi dizin olmalıdır")
    return {
        path.relative_to(directory).as_posix(): _file_sha256(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


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


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _json_bytes(value: Any) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    return (payload + "\n").encode()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataPipelineError(f"JSON okunamadı: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DataPipelineError(f"JSON nesne olmalıdır: {path}")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DataPipelineError(f"dosya okunamadı: {path}: {exc}") from exc
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    _write_bytes(path, _json_bytes(value))


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m radariq.data.dvc_pipeline")
    parser.add_argument("stage", choices=PIPELINE_STAGE_ORDER)
    parser.add_argument("--params", type=Path, default=Path("params.yaml"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    functions = {
        "validate": run_validation_stage,
        "split": run_split_stage,
        "preprocess": run_preprocessing_stage,
        "report": run_report_stage,
    }
    try:
        result = functions[args.stage](args.params)
    except (DataPipelineError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
