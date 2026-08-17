from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from radariq.data.contracts import (
    CURRENT_SCHEMA_VERSION,
    REGISTERED_SCHEMA_FINGERPRINTS,
    DataContractError,
    IQBatch,
    IQRepresentation,
    IQSampleMetadata,
    SchemaVersionError,
    assert_schema_version_registered,
    schema_fingerprint,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def metadata(sample_id: str = "sample-001") -> IQSampleMetadata:
    return IQSampleMetadata(
        sample_id=sample_id,
        label="BPSK",
        snr_db=-6.0,
        group_id="capture-01",
        source_version="radioml-2018.01a@sha256:fixture",
    )


def test_channels_first_batch_satisfies_contract() -> None:
    samples = np.zeros((2, 2, 128), dtype=np.float32)

    batch = IQBatch(
        samples=samples,
        metadata=(metadata("sample-001"), metadata("sample-002")),
        representation=IQRepresentation.CHANNELS_FIRST,
    )

    assert batch.schema_version == "1.0"
    assert batch.sample_count == 2
    assert batch.signal_length == 128


def test_complex64_batch_satisfies_contract_with_nullable_source_metadata() -> None:
    samples = np.zeros((1, 1024), dtype=np.complex64)
    sample_metadata = IQSampleMetadata(
        sample_id="sample-001",
        label=3,
        snr_db=None,
        group_id=None,
        source_version="field-capture@2026-08-17",
    )

    batch = IQBatch(
        samples=samples,
        metadata=(sample_metadata,),
        representation=IQRepresentation.COMPLEX,
    )

    assert batch.samples.dtype == np.complex64
    assert batch.metadata[0].snr_db is None
    assert batch.metadata[0].group_id is None


@pytest.mark.parametrize(
    ("samples", "representation", "error_code"),
    [
        (np.zeros((1, 128), dtype=np.float32), IQRepresentation.CHANNELS_FIRST, "iq.invalid_shape"),
        (
            np.zeros((1, 2, 128), dtype=np.float64),
            IQRepresentation.CHANNELS_FIRST,
            "iq.invalid_dtype",
        ),
        (np.zeros((1, 2, 128), dtype=np.complex64), IQRepresentation.COMPLEX, "iq.invalid_shape"),
        (np.zeros((1, 128), dtype=np.complex128), IQRepresentation.COMPLEX, "iq.invalid_dtype"),
        (
            np.zeros((0, 2, 128), dtype=np.float32),
            IQRepresentation.CHANNELS_FIRST,
            "iq.empty_batch_or_signal",
        ),
    ],
)
def test_invalid_iq_arrays_are_rejected(
    samples: np.ndarray,
    representation: IQRepresentation,
    error_code: str,
) -> None:
    with pytest.raises(DataContractError) as error:
        IQBatch(samples=samples, metadata=(metadata(),), representation=representation)

    assert error.value.code == error_code


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("sample_id", "", "metadata.invalid_string"),
        ("label", "", "metadata.invalid_label"),
        ("label", True, "metadata.invalid_label"),
        ("snr_db", float("nan"), "metadata.non_finite_number"),
        ("snr_db", float("inf"), "metadata.non_finite_number"),
        ("group_id", " ", "metadata.invalid_string"),
        ("source_version", "", "metadata.invalid_string"),
    ],
)
def test_invalid_sample_metadata_is_rejected(field: str, value: object, error_code: str) -> None:
    values: dict[str, object] = {
        "sample_id": "sample-001",
        "label": "BPSK",
        "snr_db": -6.0,
        "group_id": "capture-01",
        "source_version": "dataset@v1",
    }
    values[field] = value

    with pytest.raises(DataContractError) as error:
        IQSampleMetadata(**values)  # type: ignore[arg-type]

    assert error.value.code == error_code
    assert error.value.field == field


def test_metadata_count_must_match_sample_count() -> None:
    with pytest.raises(DataContractError) as error:
        IQBatch(
            samples=np.zeros((2, 2, 16), dtype=np.float32),
            metadata=(metadata(),),
            representation=IQRepresentation.CHANNELS_FIRST,
        )

    assert error.value.code == "metadata.count_mismatch"


def test_sample_ids_must_be_unique_within_batch() -> None:
    with pytest.raises(DataContractError) as error:
        IQBatch(
            samples=np.zeros((2, 2, 16), dtype=np.float32),
            metadata=(metadata("duplicate"), metadata("duplicate")),
            representation=IQRepresentation.CHANNELS_FIRST,
        )

    assert error.value.code == "metadata.duplicate_sample_id"


def test_current_schema_definition_matches_registered_fingerprint() -> None:
    assert schema_fingerprint() == REGISTERED_SCHEMA_FINGERPRINTS[CURRENT_SCHEMA_VERSION]
    assert_schema_version_registered()


def test_incompatible_schema_change_requires_explicit_version_registration() -> None:
    changed_definition = deepcopy(
        {
            "name": "radariq.iq_batch",
            "schema_version": CURRENT_SCHEMA_VERSION,
            "representations": {
                "channels_first": {"dtype": "float32", "shape": ["N", 2, "L"]},
                "complex": {"dtype": "complex64", "shape": ["N", "L"]},
            },
            "sample_metadata": {
                "sample_id": {"type": "string", "required": True, "nullable": False},
                "label": {"type": ["string", "integer"], "required": True, "nullable": False},
                "snr_db": {"type": "number", "required": True, "nullable": True},
                "group_id": {"type": "string", "required": True, "nullable": True},
                "source_version": {"type": "string", "required": True, "nullable": False},
            },
        }
    )
    changed_definition["sample_metadata"]["sensor_id"] = {
        "type": "string",
        "required": True,
        "nullable": False,
    }

    with pytest.raises(SchemaVersionError) as error:
        assert_schema_version_registered(changed_definition, version="1.0")

    assert error.value.code == "schema.version_bump_required"


def test_unknown_schema_version_is_rejected() -> None:
    with pytest.raises(SchemaVersionError) as error:
        IQBatch(
            samples=np.zeros((1, 2, 16), dtype=np.float32),
            metadata=(metadata(),),
            representation=IQRepresentation.CHANNELS_FIRST,
            schema_version="2.0",
        )

    assert error.value.code == "schema.unsupported_version"
