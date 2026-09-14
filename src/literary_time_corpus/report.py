from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from literary_time_corpus.candidate import (
    CANDIDATE_SCHEMA_VERSION,
    candidate_record_violations,
)
from literary_time_corpus.io import write_json_atomic


REPORT_SCHEMA_VERSION = "candidate-report-v1"
REPORT_VERSION = "report-v1"
EXPECTED_CANDIDATE_SCHEMA = CANDIDATE_SCHEMA_VERSION
MINUTES_PER_DAY = 24 * 60


class ReportError(ValueError):
    def __init__(
        self, code: str, message: str, *, details: dict[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


def _invalid(line_number: int, message: str) -> ReportError:
    return ReportError(
        "invalid-candidate-jsonl", message, details={"line": line_number}
    )


def _sorted_counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def build_report(input_path: Path) -> dict[str, Any]:
    input_hash = hashlib.sha256()
    candidate_count = 0
    candidate_schema: str | None = None
    status_counts: Counter[str] = Counter()
    precision_counts: Counter[str] = Counter()
    rule_family_counts: Counter[str] = Counter()
    exclusion_reason_counts: Counter[str] = Counter()
    warning_reason_counts: Counter[str] = Counter()
    minute_counts: Counter[str] = Counter()

    try:
        with input_path.open("rb") as source:
            for line_number, raw_line in enumerate(source, start=1):
                input_hash.update(raw_line)
                try:
                    decoded_line = raw_line.decode("utf-8")
                    if not decoded_line.strip():
                        raise ValueError("blank JSONL row")
                    candidate = json.loads(decoded_line)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                    raise _invalid(line_number, "candidate row is not valid UTF-8 JSON") from error

                violations = candidate_record_violations(candidate)
                row_schema = (
                    candidate.get("schemaVersion")
                    if isinstance(candidate, dict)
                    else None
                )
                if violations:
                    if (
                        violations == ["invalid-schema-version"]
                        and candidate_schema is not None
                        and isinstance(row_schema, str)
                    ):
                        raise ReportError(
                            "inconsistent-candidate-schema",
                            "candidate rows use inconsistent schema versions",
                            details={
                                "actual": row_schema,
                                "expected": candidate_schema,
                                "line": line_number,
                            },
                        )
                    raise _invalid(
                        line_number,
                        "candidate row does not satisfy time-candidate-v1",
                    )

                if candidate_schema is None:
                    candidate_schema = row_schema
                candidate_count += 1
                status_counts[candidate["status"]] += 1
                precision_counts[candidate["precision"]] += 1
                rule_family_counts[candidate["ruleFamily"]] += 1
                exclusion_reason_counts.update(candidate["exclusionReasonCodes"])
                warning_reason_counts.update(candidate["warningReasonCodes"])
                if candidate["precision"] == "exact-minute-resolved":
                    minute_counts[candidate["normalizedTimes"][0]] += 1
    except ReportError:
        raise
    except OSError as error:
        raise ReportError(
            "invalid-candidate-jsonl", "could not read candidate JSONL"
        ) from error

    if candidate_count == 0:
        raise ReportError("invalid-candidate-jsonl", "candidate JSONL must not be empty")

    unique_minutes = sorted(minute_counts)
    resolved_candidate_count = sum(minute_counts.values())
    duplicate_candidate_count = resolved_candidate_count - len(unique_minutes)
    top_duplicate_minutes = [
        {"candidateCount": count, "minute": minute}
        for minute, count in sorted(minute_counts.items(), key=lambda item: (-item[1], item[0]))
        if count > 1
    ][:10]

    return {
        "candidateCount": candidate_count,
        "candidateSchemaVersion": candidate_schema,
        "coverageFraction": len(unique_minutes) / MINUTES_PER_DAY,
        "duplicateConcentration": {
            "duplicateCandidateCount": duplicate_candidate_count,
            "duplicateFraction": (
                duplicate_candidate_count / resolved_candidate_count
                if resolved_candidate_count
                else 0.0
            ),
            "duplicateMinuteCount": sum(count > 1 for count in minute_counts.values()),
            "maxCandidatesPerMinute": max(minute_counts.values(), default=0),
            "resolvedCandidateCount": resolved_candidate_count,
        },
        "exclusionReasonCounts": _sorted_counts(exclusion_reason_counts),
        "inputSha256": input_hash.hexdigest(),
        "precisionCounts": _sorted_counts(precision_counts),
        "reportVersion": REPORT_VERSION,
        "resolvedMinuteCount": len(unique_minutes),
        "ruleFamilyCounts": _sorted_counts(rule_family_counts),
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "statusCounts": _sorted_counts(status_counts),
        "topDuplicateMinutes": top_duplicate_minutes,
        "uniqueResolvedMinutes": unique_minutes,
        "warningReasonCounts": _sorted_counts(warning_reason_counts),
    }


def report_file(input_path: Path, output_path: Path) -> None:
    report = build_report(input_path)
    write_json_atomic(output_path, report)
