from __future__ import annotations

import hashlib
import re
from typing import Any

from literary_time_corpus.encoding import all_strings_encode_utf8
from literary_time_corpus.normalized import NORMALIZATION_VERSION


CANDIDATE_SCHEMA_VERSION = "time-candidate-v1"
EXTRACTION_VERSION = "extract-v1"
WORK_METADATA_SCHEMA_VERSION = "scan-work-metadata-v1"
TIME_PATTERN = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
STATUSES = {"detected", "automatically-excluded", "awaiting-review", "reviewed"}
PRECISIONS = {
    "exact-minute-resolved",
    "exact-minute-ambiguous",
    "approximate",
}
CONTEXTUAL_RESOLUTION_METHODS = {
    "explicit-meridiem",
    "explicit-24-hour-clock",
    "named-time",
}
RESOLUTION_METHOD_BY_RULE_FAMILY = {
    "numeric-12-hour": "explicit-meridiem",
    "numeric-24-hour": "explicit-24-hour-clock",
    "named-time": "named-time",
}


def _is_nonblank_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_reason_codes(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(_is_nonblank_string(item) for item in value)
        and len(set(value)) == len(value)
    )


def work_metadata_violations(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["not-an-object"]

    violations: list[str] = []
    if set(value) != {
        "schemaVersion",
        "title",
        "author",
        "sourceUrl",
        "metadataComplete",
    }:
        violations.append("invalid-fields")
    if value.get("schemaVersion") != WORK_METADATA_SCHEMA_VERSION:
        violations.append("invalid-schema-version")
    for field in ("title", "author"):
        if not _is_nonblank_string(value.get(field)):
            violations.append(f"invalid-{field}")
    source_url = value.get("sourceUrl")
    if source_url is not None and not isinstance(source_url, str):
        violations.append("invalid-sourceUrl")
    if not isinstance(value.get("metadataComplete"), bool):
        violations.append("invalid-metadataComplete")
    if not all_strings_encode_utf8(value):
        violations.append("non-utf8-string")
    return sorted(set(violations))


def _valid_offsets(candidate: dict[str, Any]) -> bool:
    names = (
        "excerptStartByte",
        "matchStartByte",
        "matchEndByte",
        "excerptEndByte",
    )
    values = [candidate.get(name) for name in names]
    if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
        return False
    excerpt_start, match_start, match_end, excerpt_end = values
    return 0 <= excerpt_start <= match_start < match_end <= excerpt_end


def _valid_contextual_resolution(candidate: dict[str, Any]) -> bool:
    resolution = candidate.get("contextualResolution")
    if candidate.get("precision") != "exact-minute-resolved":
        return resolution is None
    if not isinstance(resolution, dict) or set(resolution) != {
        "method",
        "evidenceStartByte",
        "evidenceEndByte",
        "evidenceText",
    }:
        return False
    method = resolution.get("method")
    evidence_start = resolution.get("evidenceStartByte")
    evidence_end = resolution.get("evidenceEndByte")
    evidence_text = resolution.get("evidenceText")
    match_start = candidate.get("matchStartByte")
    match_end = candidate.get("matchEndByte")
    if (
        method not in CONTEXTUAL_RESOLUTION_METHODS
        or method != RESOLUTION_METHOD_BY_RULE_FAMILY.get(candidate.get("ruleFamily"))
        or not isinstance(evidence_start, int)
        or isinstance(evidence_start, bool)
        or not isinstance(evidence_end, int)
        or isinstance(evidence_end, bool)
        or not _is_nonblank_string(evidence_text)
        or not isinstance(match_start, int)
        or isinstance(match_start, bool)
        or not isinstance(match_end, int)
        or isinstance(match_end, bool)
        or not match_start <= evidence_start < evidence_end <= match_end
    ):
        return False
    excerpt = candidate.get("excerpt")
    excerpt_start = candidate.get("excerptStartByte")
    if not isinstance(excerpt, str) or not isinstance(excerpt_start, int):
        return False
    relative_start = evidence_start - excerpt_start
    relative_end = evidence_end - excerpt_start
    try:
        excerpt_bytes = excerpt.encode("utf-8")
        evidence_matches_span = (
            excerpt_bytes[relative_start:relative_end].decode("utf-8") == evidence_text
            and len(evidence_text.encode("utf-8")) == evidence_end - evidence_start
        )
    except (UnicodeDecodeError, UnicodeEncodeError):
        return False
    if not evidence_matches_span:
        return False

    matched_text = candidate.get("matchedText")
    normalized_times = candidate.get("normalizedTimes")
    if not isinstance(matched_text, str) or not isinstance(normalized_times, list):
        return False
    if method == "explicit-meridiem":
        match = re.fullmatch(
            r"((?:0?[1-9]|1[0-2])):([0-5][0-9])\s*([ap]\.?m\.?)",
            matched_text,
            re.IGNORECASE,
        )
        if match is None:
            return False
        expected_text = match.group(3)
        expected_start = match_start + len(matched_text[: match.start(3)].encode("utf-8"))
        hour = int(match.group(1)) % 12 + (12 if expected_text[0].lower() == "p" else 0)
        return (
            evidence_text == expected_text
            and evidence_start == expected_start
            and evidence_end == match_end
            and normalized_times == [f"{hour:02d}:{int(match.group(2)):02d}"]
        )
    if method == "explicit-24-hour-clock":
        match = re.fullmatch(r"([0-2][0-9]):([0-5][0-9])", matched_text)
        if match is None:
            return False
        hour = int(match.group(1))
        return (
            hour <= 23
            and (hour == 0 or hour >= 13 or match.group(1).startswith("0"))
            and evidence_text == matched_text
            and evidence_start == match_start
            and evidence_end == match_end
            and normalized_times == [matched_text]
        )
    if method == "named-time":
        lowered = matched_text.lower()
        return (
            lowered in {"noon", "midnight"}
            and evidence_text == matched_text
            and evidence_start == match_start
            and evidence_end == match_end
            and normalized_times == (["12:00"] if lowered == "noon" else ["00:00"])
        )
    return False


def candidate_record_violations(candidate: Any) -> list[str]:
    if not isinstance(candidate, dict):
        return ["not-an-object"]

    violations: list[str] = []
    strings_encode_utf8 = all_strings_encode_utf8(candidate)
    if not strings_encode_utf8:
        violations.append("non-utf8-string")
    if candidate.get("schemaVersion") != CANDIDATE_SCHEMA_VERSION:
        violations.append("invalid-schema-version")
    if "workMetadata" in candidate and work_metadata_violations(
        candidate["workMetadata"]
    ):
        violations.append("invalid-workMetadata")

    for field in (
        "sourceId",
        "ruleFamily",
        "ruleId",
        "matchedText",
    ):
        if not _is_nonblank_string(candidate.get(field)):
            violations.append(f"invalid-{field}")

    if candidate.get("normalizationVersion") != NORMALIZATION_VERSION:
        violations.append("invalid-normalizationVersion")
    if candidate.get("extractionVersion") != EXTRACTION_VERSION:
        violations.append("invalid-extractionVersion")

    for field in ("candidateId", "sourceSha256", "analysisTextSha256"):
        value = candidate.get(field)
        if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
            violations.append(f"invalid-{field}")

    if candidate.get("sourceHashStatus") != "carried-from-normalization":
        violations.append("invalid-sourceHashStatus")
    if candidate.get("status") not in STATUSES:
        violations.append("invalid-status")
    precision = candidate.get("precision")
    if precision not in PRECISIONS:
        violations.append("invalid-precision")

    normalized_times = candidate.get("normalizedTimes")
    if (
        not isinstance(normalized_times, list)
        or any(
            not isinstance(value, str) or TIME_PATTERN.fullmatch(value) is None
            for value in normalized_times
        )
        or len(set(normalized_times)) != len(normalized_times)
    ):
        violations.append("invalid-normalizedTimes")
    elif (
        (precision == "exact-minute-resolved" and len(normalized_times) != 1)
        or (precision == "exact-minute-ambiguous" and len(normalized_times) <= 1)
        or (precision == "approximate" and normalized_times)
    ):
        violations.append("precision-cardinality-mismatch")

    for field in ("exclusionReasonCodes", "warningReasonCodes"):
        if not _valid_reason_codes(candidate.get(field)):
            violations.append(f"invalid-{field}")

    text_fields = (
        "context",
        "excerpt",
        "quoteBefore",
        "quoteTime",
        "quoteAfter",
    )
    if any(not isinstance(candidate.get(field), str) for field in text_fields):
        violations.append("invalid-text-segmentation")
    else:
        excerpt = candidate["excerpt"]
        before = candidate["quoteBefore"]
        quote_time = candidate["quoteTime"]
        after = candidate["quoteAfter"]
        if (
            candidate["context"] != excerpt
            or before + quote_time + after != excerpt
            or quote_time != candidate.get("matchedText")
        ):
            violations.append("invalid-text-segmentation")

    if not _valid_offsets(candidate):
        violations.append("invalid-offsets")
    elif all(isinstance(candidate.get(field), str) for field in text_fields):
        excerpt_start = candidate["excerptStartByte"]
        match_start = candidate["matchStartByte"]
        match_end = candidate["matchEndByte"]
        excerpt_end = candidate["excerptEndByte"]
        try:
            byte_lengths_match = (
                len(candidate["excerpt"].encode("utf-8")) == excerpt_end - excerpt_start
                and len(candidate["quoteBefore"].encode("utf-8"))
                == match_start - excerpt_start
                and len(candidate["quoteTime"].encode("utf-8")) == match_end - match_start
                and len(candidate["quoteAfter"].encode("utf-8")) == excerpt_end - match_end
            )
        except UnicodeEncodeError:
            byte_lengths_match = False
        if not byte_lengths_match:
            violations.append("offset-text-mismatch")

    if not _valid_contextual_resolution(candidate):
        violations.append("invalid-contextualResolution")

    identity_fields = (
        candidate.get("sourceId"),
        candidate.get("analysisTextSha256"),
        candidate.get("matchStartByte"),
        candidate.get("matchEndByte"),
    )
    if (
        strings_encode_utf8
        and isinstance(identity_fields[0], str)
        and isinstance(identity_fields[1], str)
        and isinstance(identity_fields[2], int)
        and not isinstance(identity_fields[2], bool)
        and isinstance(identity_fields[3], int)
        and not isinstance(identity_fields[3], bool)
    ):
        identity = "\0".join(str(value) for value in identity_fields)
        expected_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        if candidate.get("candidateId") != expected_id:
            violations.append("candidate-identity-mismatch")

    return sorted(set(violations))
