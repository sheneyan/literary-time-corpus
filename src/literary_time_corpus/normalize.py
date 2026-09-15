from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

from literary_time_corpus.io import write_json_atomic
from literary_time_corpus.normalized import (
    NORMALIZATION_VERSION,
    NORMALIZED_SCHEMA_VERSION,
    FULL_FILE_TRANSFORMATION_METHOD,
    MARKER_TRANSFORMATION_METHOD,
    normalized_record_violations,
)


class NormalizationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _occurs_exactly_once(source: bytes, marker: bytes) -> bool:
    first = source.find(marker)
    return first >= 0 and source.find(marker, first + 1) < 0


def normalize_bytes(
    source: bytes,
    *,
    start_marker: str | None = None,
    end_marker: str | None = None,
) -> dict[str, Any]:
    try:
        source.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise NormalizationError("invalid-utf8", "source is not valid UTF-8") from error

    if (start_marker is None) != (end_marker is None):
        raise NormalizationError(
            "invalid-markers",
            "start and end markers must be supplied together",
        )

    if start_marker is None:
        body_start = 0
        body_end = len(source)
        method = FULL_FILE_TRANSFORMATION_METHOD
    else:
        try:
            start_marker_bytes = start_marker.encode("utf-8", errors="strict")
            end_marker_bytes = end_marker.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise NormalizationError(
                "invalid-markers", "markers must be valid UTF-8 text"
            ) from error
        if not start_marker_bytes or not end_marker_bytes:
            raise NormalizationError(
                "invalid-markers", "markers must not be empty"
            )
        if (
            not _occurs_exactly_once(source, start_marker_bytes)
            or not _occurs_exactly_once(source, end_marker_bytes)
        ):
            raise NormalizationError(
                "invalid-markers",
                "each marker must occur exactly once with start before end",
            )
        start_position = source.index(start_marker_bytes)
        end_position = source.index(end_marker_bytes)
        if start_position >= end_position:
            raise NormalizationError(
                "invalid-markers",
                "each marker must occur exactly once with start before end",
            )
        body_start = start_position + len(start_marker_bytes)
        body_end = end_position
        if source[body_start : body_start + 2] == b"\r\n":
            body_start += 2
        elif source[body_start : body_start + 1] == b"\n":
            body_start += 1
        if source[body_end - 2 : body_end] == b"\r\n":
            body_end -= 2
        elif source[body_end - 1 : body_end] == b"\n":
            body_end -= 1
        if body_end <= body_start:
            raise NormalizationError(
                "invalid-markers", "markers select no body"
            )
        method = MARKER_TRANSFORMATION_METHOD

    analysis = source[body_start:body_end]
    if not analysis.decode("utf-8").strip():
        raise NormalizationError(
            "empty-body", "source body must contain non-whitespace text"
        )
    source_hash = hashlib.sha256(source).hexdigest()
    document = {
        "analysisText": analysis.decode("utf-8"),
        "analysisTextSha256": hashlib.sha256(analysis).hexdigest(),
        "bodyEndByte": body_end,
        "bodyStartByte": body_start,
        "normalizationVersion": NORMALIZATION_VERSION,
        "schemaVersion": NORMALIZED_SCHEMA_VERSION,
        "sourceId": f"local_{source_hash[:12]}",
        "sourceSha256": source_hash,
        "transformationLog": [
            {
                "inputEndByte": body_end,
                "inputStartByte": body_start,
                "method": method,
                "outputEndByte": len(analysis),
                "outputStartByte": 0,
            }
        ],
    }
    if normalized_record_violations(document):
        raise NormalizationError(
            "normalization-failed", "generated normalized record failed validation"
        )
    return document


def normalize_file(
    input_path: Path,
    output_path: Path,
    *,
    start_marker: str | None = None,
    end_marker: str | None = None,
) -> None:
    try:
        descriptor = os.open(input_path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as error:
        raise NormalizationError("input-error", "could not read source") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise NormalizationError(
                "input-error", "source must be a regular file"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as source_file:
            source = source_file.read()
    except OSError as error:
        raise NormalizationError("input-error", "could not read source") from error
    finally:
        os.close(descriptor)
    document = normalize_bytes(source, start_marker=start_marker, end_marker=end_marker)
    write_json_atomic(output_path, document)
