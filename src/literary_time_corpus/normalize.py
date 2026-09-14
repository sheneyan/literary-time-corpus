from __future__ import annotations

import hashlib
import re
from pathlib import Path

from literary_time_corpus.io import write_json_atomic
from literary_time_corpus.normalized import (
    NORMALIZATION_VERSION,
    NORMALIZED_SCHEMA_VERSION,
    TRANSFORMATION_METHOD,
)


START_MARKER = re.compile(
    rb"^\*\*\* START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\r\n]*\*\*\*\r?$",
    re.MULTILINE,
)
END_MARKER = re.compile(
    rb"^\*\*\* END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\r\n]*\*\*\*\r?$",
    re.MULTILINE,
)


class NormalizationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_file(input_path: Path, output_path: Path) -> None:
    try:
        source = input_path.read_bytes()
    except OSError as error:
        raise NormalizationError("input-error", f"could not read source: {error}") from error

    try:
        source.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise NormalizationError("invalid-utf8", "source is not valid UTF-8") from error

    starts = list(START_MARKER.finditer(source))
    ends = list(END_MARKER.finditer(source))
    if len(starts) != 1 or len(ends) != 1:
        raise NormalizationError(
            "invalid-markers",
            "source must contain exactly one complete START/END marker pair",
        )

    start = starts[0]
    end = ends[0]
    body_start = start.end()
    if body_start >= len(source) or source[body_start : body_start + 1] != b"\n":
        raise NormalizationError(
            "invalid-markers",
            "source must contain exactly one complete START/END marker pair",
        )
    body_start += 1

    body_end = end.start()
    if body_end <= body_start or source[body_end - 1 : body_end] != b"\n":
        raise NormalizationError(
            "invalid-markers",
            "source must contain exactly one complete START/END marker pair",
        )
    body_end -= 1
    if body_end > body_start and source[body_end - 1 : body_end] == b"\r":
        body_end -= 1

    analysis = source[body_start:body_end]
    source_hash = hashlib.sha256(source).hexdigest()
    document = {
        "analysisText": analysis.decode("utf-8"),
        "analysisTextSha256": hashlib.sha256(analysis).hexdigest(),
        "bodyEndByte": body_end,
        "bodyStartByte": body_start,
        "normalizationVersion": NORMALIZATION_VERSION,
        "schemaVersion": NORMALIZED_SCHEMA_VERSION,
        "sourceId": f"synthetic_{source_hash[:12]}",
        "sourceSha256": source_hash,
        "transformationLog": [
            {
                "inputEndByte": body_end,
                "inputStartByte": body_start,
                "method": TRANSFORMATION_METHOD,
                "outputEndByte": len(analysis),
                "outputStartByte": 0,
            }
        ],
    }
    write_json_atomic(output_path, document)
