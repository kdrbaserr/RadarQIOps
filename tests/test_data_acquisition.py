from __future__ import annotations

import contextlib
import json
import socket
import threading
import zipfile
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from radariq.cli import main
from radariq.data.acquisition import (
    AcquisitionConfig,
    AcquisitionConfigError,
    AcquisitionError,
    AcquisitionStatus,
    SourceType,
    acquire,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_local_file_acquisition_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "incoming" / "fixture.bin"
    destination = tmp_path / "raw" / "fixture.bin"
    source.parent.mkdir()
    source.write_bytes(b"first-source-version")
    config = acquisition_config(SourceType.LOCAL_FILE, source, destination)

    first = acquire(config)
    first_mtime = destination.stat().st_mtime_ns
    source.write_bytes(b"changed-source-must-not-overwrite-raw")
    second = acquire(config)

    assert first.status is AcquisitionStatus.ACQUIRED
    assert first.attempts == 1
    assert second.status is AcquisitionStatus.REUSED
    assert second.attempts == 0
    assert destination.read_bytes() == b"first-source-version"
    assert destination.stat().st_mtime_ns == first_mtime
    assert not list(destination.parent.glob("*.part"))


def test_user_archive_is_validated_and_copied_without_extraction(tmp_path: Path) -> None:
    source = tmp_path / "dataset.zip"
    destination = tmp_path / "raw" / "dataset.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("samples/part-001.bin", b"fixture")

    result = acquire(acquisition_config(SourceType.ARCHIVE, source, destination))

    assert result.status is AcquisitionStatus.ACQUIRED
    assert destination.read_bytes() == source.read_bytes()
    assert not (destination.parent / "samples").exists()


def test_invalid_user_archive_fails_without_destination_or_partial_file(tmp_path: Path) -> None:
    source = tmp_path / "not-an-archive.zip"
    destination = tmp_path / "raw" / "dataset.zip"
    source.write_bytes(b"not really a zip or tar")

    with pytest.raises(AcquisitionConfigError, match="ZIP/TAR"):
        acquire(acquisition_config(SourceType.ARCHIVE, source, destination))

    assert not destination.exists()
    assert not list(destination.parent.glob("*.part"))


def test_interrupted_http_download_retries_and_publishes_only_complete_file(
    tmp_path: Path,
) -> None:
    payload = b"complete-http-fixture-payload"
    destination = tmp_path / "raw" / "dataset.bin"

    with http_fixture(payload, failures_before_success=1) as (url, request_count):
        config = AcquisitionConfig(
            source_type=SourceType.HTTP,
            location=url,
            destination=destination,
            max_attempts=3,
            timeout_seconds=2,
            retry_delay_seconds=0,
            chunk_size_bytes=4,
        )
        result = acquire(config)

    assert result.status is AcquisitionStatus.ACQUIRED
    assert result.attempts == 2
    assert request_count() == 2
    assert destination.read_bytes() == payload
    assert not list(destination.parent.glob("*.part"))


def test_exhausted_http_retries_leave_no_raw_or_partial_file(tmp_path: Path) -> None:
    destination = tmp_path / "raw" / "dataset.bin"

    with http_fixture(b"never-completes", failures_before_success=10) as (url, request_count):
        config = AcquisitionConfig(
            source_type=SourceType.HTTP,
            location=url,
            destination=destination,
            max_attempts=2,
            timeout_seconds=2,
            retry_delay_seconds=0,
            chunk_size_bytes=4,
        )
        with pytest.raises(AcquisitionError, match="2 denemede"):
            acquire(config)

    assert request_count() == 2
    assert not destination.exists()
    assert not list(destination.parent.glob("*.part"))


def test_acquisition_cli_resolves_paths_relative_to_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_directory = tmp_path / "configs"
    source = tmp_path / "incoming" / "fixture.bin"
    destination = tmp_path / "data" / "raw" / "fixture.bin"
    config_directory.mkdir()
    source.parent.mkdir()
    source.write_bytes(b"cli-fixture")
    config_path = config_directory / "acquire.yaml"
    config_path.write_text(
        json.dumps(
            {
                "source": {"type": "local_file", "location": "../incoming/fixture.bin"},
                "destination": "../data/raw/fixture.bin",
                "max_attempts": 1,
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["data", "acquire", "--config", str(config_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "acquired"
    assert Path(output["destination"]) == destination
    assert destination.read_bytes() == b"cli-fixture"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_attempts", 0),
        ("timeout_seconds", float("inf")),
        ("retry_delay_seconds", -1),
        ("chunk_size_bytes", False),
    ],
)
def test_invalid_numeric_config_is_rejected(field: str, value: object, tmp_path: Path) -> None:
    config: dict[str, object] = {
        "source": {"type": "local_file", "location": "source.bin"},
        "destination": "raw/source.bin",
        field: value,
    }

    with pytest.raises(AcquisitionConfigError, match=field):
        AcquisitionConfig.from_mapping(config, base_directory=tmp_path)


def test_local_source_and_destination_cannot_be_the_same_file(tmp_path: Path) -> None:
    source = tmp_path / "fixture.bin"
    source.write_bytes(b"keep-me")

    with pytest.raises(AcquisitionConfigError, match="aynı dosya"):
        acquire(acquisition_config(SourceType.LOCAL_FILE, source, source))

    assert source.read_bytes() == b"keep-me"


def acquisition_config(
    source_type: SourceType,
    source: Path,
    destination: Path,
) -> AcquisitionConfig:
    return AcquisitionConfig(
        source_type=source_type,
        location=str(source),
        destination=destination,
        max_attempts=2,
        timeout_seconds=2,
        retry_delay_seconds=0,
        chunk_size_bytes=4,
    )


@contextlib.contextmanager
def http_fixture(
    payload: bytes,
    *,
    failures_before_success: int,
) -> Iterator[tuple[str, Callable[[], int]]]:
    class FixtureHandler(BaseHTTPRequestHandler):
        requests = 0

        def do_GET(self) -> None:
            type(self).requests += 1
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if type(self).requests <= failures_before_success:
                partial_size = max(1, len(payload) // 3)
                self.wfile.write(payload[:partial_size])
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/dataset.bin", lambda: FixtureHandler.requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
