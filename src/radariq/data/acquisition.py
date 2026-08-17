"""Configurable, atomic acquisition adapters for raw dataset files."""

from __future__ import annotations

import hashlib
import math
import os
import tarfile
import tempfile
import time
import zipfile
from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from enum import StrEnum
from http.client import HTTPException
from pathlib import Path
from typing import Any, BinaryIO, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from radariq.configs import load_config

DEFAULT_CHUNK_SIZE_BYTES = 1024 * 1024
SHA256_HEX_LENGTH = 64


class SourceType(StrEnum):
    """Acquisition source implementations supported by the local pipeline."""

    HTTP = "http"
    LOCAL_FILE = "local_file"
    ARCHIVE = "archive"


class AcquisitionStatus(StrEnum):
    """Whether acquisition created or reused the immutable destination."""

    ACQUIRED = "acquired"
    REUSED = "reused"


class AcquisitionError(RuntimeError):
    """Raised when acquisition cannot produce a complete destination file."""


class AcquisitionConfigError(AcquisitionError):
    """Raised before transfer when acquisition configuration is invalid."""


class ChecksumMismatchError(AcquisitionError):
    """Raised before publication when content differs from its expected SHA-256."""


class _ReadableStream(Protocol):
    def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True, slots=True)
class OpenedSource:
    """A readable source plus its expected byte size when known."""

    stream: _ReadableStream
    expected_size: int | None


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    """Validated settings shared by every acquisition adapter."""

    source_type: SourceType
    location: str
    destination: Path
    expected_sha256: str | None = None
    max_attempts: int = 3
    timeout_seconds: float = 30.0
    retry_delay_seconds: float = 0.25
    chunk_size_bytes: int = DEFAULT_CHUNK_SIZE_BYTES

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        base_directory: Path,
    ) -> AcquisitionConfig:
        source = value.get("source")
        if not isinstance(source, Mapping):
            raise AcquisitionConfigError("source bir config nesnesi olmalıdır")

        raw_source_type = source.get("type")
        if not isinstance(raw_source_type, str):
            choices = ", ".join(SourceType)
            raise AcquisitionConfigError(f"source.type desteklenmiyor; seçenekler: {choices}")
        try:
            source_type = SourceType(raw_source_type)
        except (TypeError, ValueError) as exc:
            choices = ", ".join(SourceType)
            raise AcquisitionConfigError(
                f"source.type desteklenmiyor; seçenekler: {choices}"
            ) from exc

        location = source.get("location")
        if not isinstance(location, str) or not location.strip():
            raise AcquisitionConfigError("source.location boş olmayan string olmalıdır")

        destination_value = value.get("destination")
        if not isinstance(destination_value, str) or not destination_value.strip():
            raise AcquisitionConfigError("destination boş olmayan string olmalıdır")

        max_attempts = _positive_int(value.get("max_attempts", 3), "max_attempts")
        timeout_seconds = _positive_float(value.get("timeout_seconds", 30.0), "timeout_seconds")
        retry_delay_seconds = _non_negative_float(
            value.get("retry_delay_seconds", 0.25), "retry_delay_seconds"
        )
        chunk_size_bytes = _positive_int(
            value.get("chunk_size_bytes", DEFAULT_CHUNK_SIZE_BYTES), "chunk_size_bytes"
        )
        expected_sha256 = _optional_sha256(value.get("expected_sha256"))

        resolved_location = location.strip()
        if source_type is not SourceType.HTTP:
            resolved_location = str(_resolve_config_path(base_directory, resolved_location))

        return cls(
            source_type=source_type,
            location=resolved_location,
            destination=_resolve_config_path(base_directory, destination_value.strip()),
            expected_sha256=expected_sha256,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
            retry_delay_seconds=retry_delay_seconds,
            chunk_size_bytes=chunk_size_bytes,
        )


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    """Machine-readable outcome emitted by the acquisition CLI."""

    status: AcquisitionStatus
    source_type: SourceType
    destination: Path
    size_bytes: int
    sha256: str
    attempts: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "status": self.status.value,
            "source_type": self.source_type.value,
            "destination": str(self.destination),
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "attempts": self.attempts,
        }


class AcquisitionAdapter(ABC):
    """Source-specific stream opener used by the shared atomic writer."""

    @abstractmethod
    def open(self, timeout_seconds: float) -> AbstractContextManager[OpenedSource]:
        """Open the source without choosing how the destination is written."""


@dataclass(frozen=True, slots=True)
class LocalFileAdapter(AcquisitionAdapter):
    location: Path

    @contextmanager
    def open(self, timeout_seconds: float) -> Any:
        del timeout_seconds
        if not self.location.is_file():
            raise OSError(f"yerel kaynak dosyası bulunamadı: {self.location}")
        with self.location.open("rb") as stream:
            yield OpenedSource(stream=stream, expected_size=self.location.stat().st_size)


@dataclass(frozen=True, slots=True)
class UserArchiveAdapter(LocalFileAdapter):
    """Acquire a user-supplied ZIP or TAR archive without extracting it."""

    @contextmanager
    def open(self, timeout_seconds: float) -> Any:
        if not self.location.is_file():
            raise OSError(f"kullanıcı arşivi bulunamadı: {self.location}")
        if not (zipfile.is_zipfile(self.location) or tarfile.is_tarfile(self.location)):
            raise AcquisitionConfigError(f"desteklenen ZIP/TAR arşivi bekleniyor: {self.location}")
        with LocalFileAdapter.open(self, timeout_seconds) as opened:
            yield opened


@dataclass(frozen=True, slots=True)
class HttpAdapter(AcquisitionAdapter):
    location: str

    def __post_init__(self) -> None:
        _require_http_url(self.location)

    @contextmanager
    def open(self, timeout_seconds: float) -> Any:
        request = Request(self.location, headers={"User-Agent": "RadarIQops/0.1"})
        with urlopen(request, timeout=timeout_seconds) as response:
            final_url = response.geturl()
            _require_http_url(final_url)
            expected_size = _content_length(response.headers.get("Content-Length"))
            yield OpenedSource(stream=response, expected_size=expected_size)


def acquire_from_config(config_path: str | Path) -> AcquisitionResult:
    """Load a JSON-compatible YAML config and acquire its raw source."""

    path = Path(config_path).expanduser().resolve()
    config = AcquisitionConfig.from_mapping(load_config(path), base_directory=path.parent)
    return acquire(config)


def acquire(config: AcquisitionConfig) -> AcquisitionResult:
    """Acquire a source atomically and never replace an existing destination."""

    adapter = _adapter_for(config)
    destination = config.destination.expanduser().resolve()
    _reject_same_local_source(adapter, destination)

    if destination.exists():
        if not destination.is_file():
            raise AcquisitionConfigError(f"destination bir dosya olmalıdır: {destination}")
        digest = sha256_file(destination, chunk_size_bytes=config.chunk_size_bytes)
        _require_checksum_match(config.expected_sha256, digest)
        return _result(config, AcquisitionStatus.REUSED, destination, digest, attempts=0)

    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            digest = _transfer_once(
                adapter,
                destination,
                expected_sha256=config.expected_sha256,
                timeout_seconds=config.timeout_seconds,
                chunk_size_bytes=config.chunk_size_bytes,
            )
            return _result(
                config,
                AcquisitionStatus.ACQUIRED,
                destination,
                digest,
                attempts=attempt,
            )
        except AcquisitionConfigError:
            raise
        except (HTTPException, OSError) as exc:
            last_error = exc
            if attempt < config.max_attempts and config.retry_delay_seconds:
                time.sleep(config.retry_delay_seconds)

    raise AcquisitionError(
        f"acquisition {config.max_attempts} denemede tamamlanamadı: {last_error}"
    ) from last_error


def _transfer_once(
    adapter: AcquisitionAdapter,
    destination: Path,
    *,
    expected_sha256: str | None,
    timeout_seconds: float,
    chunk_size_bytes: int,
) -> str:
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".part",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as output:
            with adapter.open(timeout_seconds) as opened:
                copied_bytes, digest = _copy_stream(opened.stream, output, chunk_size_bytes)
                if opened.expected_size is not None and copied_bytes != opened.expected_size:
                    raise OSError(
                        "kaynak tamamlanmadan kapandı: "
                        f"beklenen={opened.expected_size}, alınan={copied_bytes}"
                    )
                _require_checksum_match(expected_sha256, digest)
            output.flush()
            os.fsync(output.fileno())

        if destination.exists():
            existing_digest = sha256_file(destination, chunk_size_bytes=chunk_size_bytes)
            _require_checksum_match(expected_sha256, existing_digest)
            return existing_digest
        os.replace(temporary_path, destination)
        return digest
    finally:
        temporary_path.unlink(missing_ok=True)


def _copy_stream(
    source: _ReadableStream, output: BinaryIO, chunk_size_bytes: int
) -> tuple[int, str]:
    copied_bytes = 0
    digest = hashlib.sha256()
    while chunk := source.read(chunk_size_bytes):
        output.write(chunk)
        digest.update(chunk)
        copied_bytes += len(chunk)
    return copied_bytes, digest.hexdigest()


def sha256_file(path: Path, *, chunk_size_bytes: int = DEFAULT_CHUNK_SIZE_BYTES) -> str:
    """Calculate a file SHA-256 without loading the whole file into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def _adapter_for(config: AcquisitionConfig) -> AcquisitionAdapter:
    if config.source_type is SourceType.HTTP:
        return HttpAdapter(config.location)
    if config.source_type is SourceType.ARCHIVE:
        return UserArchiveAdapter(Path(config.location))
    return LocalFileAdapter(Path(config.location))


def _reject_same_local_source(adapter: AcquisitionAdapter, destination: Path) -> None:
    if isinstance(adapter, LocalFileAdapter) and adapter.location.resolve() == destination:
        raise AcquisitionConfigError("yerel source ve destination aynı dosya olamaz")


def _result(
    config: AcquisitionConfig,
    status: AcquisitionStatus,
    destination: Path,
    digest: str,
    *,
    attempts: int,
) -> AcquisitionResult:
    return AcquisitionResult(
        status=status,
        source_type=config.source_type,
        destination=destination,
        size_bytes=destination.stat().st_size,
        sha256=digest,
        attempts=attempts,
    )


def _resolve_config_path(base_directory: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (base_directory / path).resolve() if not path.is_absolute() else path.resolve()


def _require_http_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AcquisitionConfigError(f"geçerli HTTP(S) URL bekleniyor: {value}")


def _content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        size = int(value)
    except ValueError as exc:
        raise OSError(f"geçersiz Content-Length: {value}") from exc
    if size < 0:
        raise OSError(f"geçersiz Content-Length: {value}")
    return size


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AcquisitionConfigError(f"{field} pozitif integer olmalıdır")
    return value


def _positive_float(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise AcquisitionConfigError(f"{field} pozitif sayı olmalıdır")
    return float(value)


def _non_negative_float(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise AcquisitionConfigError(f"{field} sıfır veya pozitif sayı olmalıdır")
    return float(value)


def _optional_sha256(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AcquisitionConfigError("expected_sha256 64 karakterli hexadecimal string olmalıdır")
    normalized = value.strip().lower()
    if len(normalized) != SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise AcquisitionConfigError("expected_sha256 64 karakterli hexadecimal string olmalıdır")
    return normalized


def _require_checksum_match(expected: str | None, actual: str) -> None:
    if expected is not None and actual != expected:
        raise ChecksumMismatchError(
            f"SHA-256 uyuşmazlığı: beklenen={expected}, hesaplanan={actual}"
        )
