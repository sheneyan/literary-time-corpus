from __future__ import annotations

import hashlib
import re
from typing import Any


CANDIDATE_SCHEMA_VERSION = "time-candidate-v1"
TIME_PATTERN = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
STATUSES = {"detected", "automatically-excluded", "awaiting-review", "reviewed"}
PRECISIONS = {
    "exact-minute-resolved",
    "exact-minute-ambiguous",
    "approximate",
}


def _is_nonblank_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _all_strings_encode_utf8(value: Any) -> bool:
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return False
        return True
    if isinstance(value, list):
        return all(_all_strings_encode_utf8(item) for item in value)
    if isinstance(value, dict):
        return all(
            _all_strings_encode_utf8(key) and _all_strings_encode_utf8(item)
            for key, item in value.items()
        )
    return True


def _valid_reason_codes(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(_is_nonblank_string(item) for item in value)
        and len(set(value)) == len(value)
    )


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


def candidate_record_violations(candidate: Any) -> list[str]:
    if not isinstance(candidate, dict):
        return ["not-an-object"]

    violations: list[str] = []
    strings_encode_utf8 = _all_strings_encode_utf8(candidate)
    if not strings_encode_utf8:
        violations.append("non-utf8-string")
    if candidate.get("schemaVersion") != CANDIDATE_SCHEMA_VERSION:
        violations.append("invalid-schema-version")

    for field in (
        "sourceId",
        "normalizationVersion",
        "extractionVersion",
        "ruleFamily",
        "ruleId",
        "matchedText",
    ):
        if not _is_nonblank_string(candidate.get(field)):
            violations.append(f"invalid-{field}")

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
