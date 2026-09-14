from __future__ import annotations

import hashlib
import re
from typing import Any


NORMALIZED_SCHEMA_VERSION = "normalized-source-v1"
NORMALIZATION_VERSION = "normalize-v1"
TRANSFORMATION_METHOD = "project-gutenberg-marker-body-selection"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
TRANSFORMATION_FIELDS = {
    "inputEndByte",
    "inputStartByte",
    "method",
    "outputEndByte",
    "outputStartByte",
}


def _byte_offset(value: Any) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def normalized_record_violations(document: Any) -> list[str]:
    if not isinstance(document, dict):
        return ["not-an-object"]

    violations: list[str] = []
    analysis_text = document.get("analysisText")
    try:
        analysis_bytes = analysis_text.encode("utf-8")
    except (AttributeError, UnicodeEncodeError):
        analysis_bytes = None
        violations.append("invalid-analysisText")

    source_hash = document.get("sourceSha256")
    analysis_hash = document.get("analysisTextSha256")
    if document.get("schemaVersion") != NORMALIZED_SCHEMA_VERSION:
        violations.append("invalid-schemaVersion")
    if document.get("normalizationVersion") != NORMALIZATION_VERSION:
        violations.append("invalid-normalizationVersion")
    if not isinstance(source_hash, str) or SHA256_PATTERN.fullmatch(source_hash) is None:
        violations.append("invalid-sourceSha256")
    if not isinstance(analysis_hash, str) or SHA256_PATTERN.fullmatch(analysis_hash) is None:
        violations.append("invalid-analysisTextSha256")
    elif analysis_bytes is not None and hashlib.sha256(analysis_bytes).hexdigest() != analysis_hash:
        violations.append("analysis-hash-mismatch")
    if (
        not isinstance(source_hash, str)
        or SHA256_PATTERN.fullmatch(source_hash) is None
        or document.get("sourceId") != f"synthetic_{source_hash[:12]}"
    ):
        violations.append("source-identity-mismatch")

    body_start = _byte_offset(document.get("bodyStartByte"))
    body_end = _byte_offset(document.get("bodyEndByte"))
    if (
        body_start is None
        or body_end is None
        or body_end <= body_start
        or analysis_bytes is None
        or body_end - body_start != len(analysis_bytes)
    ):
        violations.append("invalid-body-bounds")

    log = document.get("transformationLog")
    if not isinstance(log, list) or len(log) != 1 or not isinstance(log[0], dict):
        violations.append("invalid-transformationLog")
    else:
        entry = log[0]
        offsets = {
            field: _byte_offset(entry.get(field))
            for field in (
                "inputStartByte",
                "inputEndByte",
                "outputStartByte",
                "outputEndByte",
            )
        }
        if (
            set(entry) != TRANSFORMATION_FIELDS
            or entry.get("method") != TRANSFORMATION_METHOD
            or any(value is None for value in offsets.values())
            or offsets["inputStartByte"] != body_start
            or offsets["inputEndByte"] != body_end
            or offsets["outputStartByte"] != 0
            or analysis_bytes is None
            or offsets["outputEndByte"] != len(analysis_bytes)
        ):
            violations.append("invalid-transformationLog")

    return sorted(set(violations))
