from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from literary_time_corpus.candidate import candidate_record_violations
from literary_time_corpus.io import write_json_atomic
from literary_time_corpus.normalized import normalized_record_violations


RELEASE_SCHEMA_VERSION = "time-release-v1"
RELEASE_VERSION = "release-v1"
TARGET_USE_PROFILE = "zi5-public-corpus-v1"
UTC_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class ValidationInputError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "invalid-release-input"


class ReleaseValidationError(ValueError):
    def __init__(self, violations: list[str]) -> None:
        super().__init__("release candidate failed validation")
        self.code = "release-validation-failed"
        self.details = {"violations": sorted(set(violations))}


def _read_document(path: Path, kind: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationInputError(f"could not read {kind} JSON document") from error
    if not isinstance(value, dict):
        raise ValidationInputError(f"{kind} JSON document must be an object")
    return value


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _nonblank_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return value


def _nonblank_string_list(value: Any) -> list[str] | None:
    values = _string_list(value)
    if values is None or any(not item.strip() for item in values):
        return None
    return values


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str) or DATE_PATTERN.fullmatch(value) is None:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _public_https_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed_port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or (parsed_port is not None and not 1 <= parsed_port <= 65535)
    ):
        return False
    hostname = hostname.rstrip(".").lower()
    if (
        hostname == "localhost"
        or "." not in hostname
        or hostname.endswith((".localhost", ".local", ".internal", ".lan", ".home"))
    ):
        return False
    try:
        if not ipaddress.ip_address(hostname).is_global:
            return False
    except ValueError:
        pass
    return True


def _valid_provenance_url(provenance: Any) -> bool:
    if not isinstance(provenance, dict):
        return False
    url = provenance.get("sourcePageUrl")
    if not _public_https_url(url):
        return False
    if provenance.get("provider") == "Project Gutenberg":
        item_id = provenance.get("providerItemId")
        if (
            not isinstance(item_id, str)
            or not item_id.isascii()
            or not item_id.isdigit()
        ):
            return False
        return url == f"https://www.gutenberg.org/ebooks/{item_id}"
    return True


def _offsets(candidate: dict[str, Any]) -> tuple[int, int, int, int] | None:
    names = (
        "excerptStartByte",
        "matchStartByte",
        "matchEndByte",
        "excerptEndByte",
    )
    values = [candidate.get(name) for name in names]
    if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
        return None
    excerpt_start, match_start, match_end, excerpt_end = values
    if not (0 <= excerpt_start <= match_start < match_end <= excerpt_end):
        return None
    return excerpt_start, match_start, match_end, excerpt_end


def _snapshot_spans_match(
    analysis_text: str, candidate: dict[str, Any]
) -> tuple[bool, bool]:
    offsets = _offsets(candidate)
    if offsets is None:
        return False, False
    excerpt_start, match_start, match_end, excerpt_end = offsets
    analysis_bytes = analysis_text.encode("utf-8")
    if excerpt_end > len(analysis_bytes):
        return False, False
    try:
        excerpt = analysis_bytes[excerpt_start:excerpt_end].decode("utf-8")
        before = analysis_bytes[excerpt_start:match_start].decode("utf-8")
        matched = analysis_bytes[match_start:match_end].decode("utf-8")
        after = analysis_bytes[match_end:excerpt_end].decode("utf-8")
    except UnicodeDecodeError:
        return False, False
    return True, (
        excerpt == candidate.get("excerpt")
        and before == candidate.get("quoteBefore")
        and matched == candidate.get("matchedText")
        and matched == candidate.get("quoteTime")
        and after == candidate.get("quoteAfter")
    )


def _confirmed_excerpt_matches(candidate: dict[str, Any], review: dict[str, Any]) -> bool:
    confirmed = review.get("confirmedExcerpt")
    if not isinstance(confirmed, dict):
        return False
    fields = (
        "excerpt",
        "excerptStartByte",
        "excerptEndByte",
        "matchStartByte",
        "matchEndByte",
        "quoteBefore",
        "quoteTime",
        "quoteAfter",
    )
    return all(confirmed.get(field) == candidate.get(field) for field in fields)


def _rights_assessments(
    rights: dict[str, Any], violations: list[str]
) -> list[dict[str, Any]]:
    assessments = rights.get("assessments")
    if not isinstance(assessments, list):
        violations.append("missing-jurisdiction")
        return []
    valid_objects = [item for item in assessments if isinstance(item, dict)]
    if len(valid_objects) != len(assessments):
        violations.append("incomplete-jurisdiction-assessment")
    by_jurisdiction: dict[str, list[dict[str, Any]]] = {}
    for assessment in valid_objects:
        jurisdiction = assessment.get("jurisdiction")
        if isinstance(jurisdiction, str):
            by_jurisdiction.setdefault(jurisdiction, []).append(assessment)
    if set(by_jurisdiction) - {"US", "CN-mainland"}:
        violations.append("unexpected-jurisdiction")

    for jurisdiction in ("US", "CN-mainland"):
        matching = by_jurisdiction.get(jurisdiction, [])
        if len(matching) == 0:
            violations.append("missing-jurisdiction")
            continue
        if len(matching) != 1:
            violations.append("duplicate-jurisdiction")
        assessment = matching[0]
        if assessment.get("workStatus") != "not-restricted":
            violations.append("work-status-not-eligible")
        if assessment.get("editionStatus") != "eligible":
            violations.append("edition-status-not-eligible")
        required_evidence = (
            _nonblank_string_list(assessment.get("basisReasonCodes")),
            _nonblank_string_list(assessment.get("evidenceReferences")),
        )
        if (
            any(not values for values in required_evidence)
            or not _nonblank_string(assessment.get("reviewer"))
            or not _nonblank_string(assessment.get("decisionDate"))
        ):
            violations.append("incomplete-jurisdiction-assessment")
        if not _valid_date(assessment.get("decisionDate")):
            violations.append("invalid-rights-date")
    return valid_objects


def _collect_violations(
    analysis: dict[str, Any],
    candidate: dict[str, Any],
    review: dict[str, Any],
    rights: dict[str, Any],
) -> list[str]:
    violations: list[str] = []

    candidate_violations = set(candidate_record_violations(candidate))
    if candidate_violations:
        violations.append("invalid-candidate-document")

    analysis_text = _string(analysis.get("analysisText"))
    try:
        actual_analysis_hash = (
            hashlib.sha256(analysis_text.encode("utf-8")).hexdigest()
            if analysis_text is not None
            else None
        )
    except UnicodeEncodeError:
        actual_analysis_hash = None
    if normalized_record_violations(analysis):
        violations.append("invalid-analysis-document")

    if review.get("schemaVersion") != "time-review-v1":
        violations.append("invalid-review-document")
    if rights.get("schemaVersion") != "rights-decision-v1":
        violations.append("invalid-rights-document")

    if candidate.get("precision") != "exact-minute-resolved":
        violations.append("precision-not-resolved")
    normalized_times = _string_list(candidate.get("normalizedTimes"))
    if normalized_times is None or len(normalized_times) != 1:
        violations.append("normalized-time-count")
    elif "invalid-normalizedTimes" in candidate_violations:
        violations.append("invalid-normalized-time")

    if "invalid-text-segmentation" in candidate_violations:
        violations.append("quote-segmentation-inconsistent")
        violations.append("source-span-mismatch")
    if "offset-text-mismatch" in candidate_violations:
        violations.append("source-span-mismatch")

    if candidate.get("analysisTextSha256") != actual_analysis_hash:
        violations.append("analysis-hash-mismatch")
    if (
        candidate.get("sourceId") != analysis.get("sourceId")
        or candidate.get("sourceSha256") != analysis.get("sourceSha256")
        or candidate.get("normalizationVersion") != analysis.get("normalizationVersion")
    ):
        violations.append("source-identity-mismatch")
    if analysis_text is not None:
        valid_offsets, spans_match = _snapshot_spans_match(analysis_text, candidate)
        if not valid_offsets:
            violations.append("invalid-offsets")
        elif not spans_match:
            violations.append("invalid-offsets")
            violations.append("source-span-mismatch")

    if candidate_violations & {"invalid-sourceSha256", "invalid-analysisTextSha256"}:
        violations.append("invalid-hash")
    if candidate_violations & {"invalid-offsets", "offset-text-mismatch"}:
        violations.append("invalid-offsets")
    if "candidate-identity-mismatch" in candidate_violations:
        violations.append("candidate-identity-mismatch")

    candidate_id = candidate.get("candidateId")
    if review.get("candidateId") != candidate_id:
        violations.append("candidate-review-identity-mismatch")
    if rights.get("candidateId") != candidate_id:
        violations.append("candidate-rights-identity-mismatch")
    if review.get("rightsDecisionId") != rights.get("decisionId"):
        violations.append("review-rights-identity-mismatch")

    if review.get("decision") != "accepted":
        violations.append("review-not-accepted")
    if not _valid_utc_timestamp(review.get("reviewedAt")):
        violations.append("invalid-review-timestamp")
    if (
        review.get("confirmedPrecision") != candidate.get("precision")
        or review.get("confirmedNormalizedTimes") != candidate.get("normalizedTimes")
    ):
        violations.append("review-confirmed-time-mismatch")
    if not _confirmed_excerpt_matches(candidate, review):
        violations.append("review-confirmed-excerpt-mismatch")

    candidate_warnings = candidate.get("warningReasonCodes")
    review_warnings = _nonblank_string_list(review.get("unresolvedWarningReasonCodes"))
    if candidate_warnings or review_warnings:
        violations.append("unresolved-warnings")
    if review.get("supersedingRejectionIds"):
        violations.append("superseding-rejection")
    if candidate.get("exclusionReasonCodes") or candidate.get("status") == "automatically-excluded":
        violations.append("candidate-excluded")

    _rights_assessments(rights, violations)
    if rights.get("decision") != "eligible":
        violations.append("rights-decision-not-eligible")
    if rights.get("targetUseProfile") != TARGET_USE_PROFILE:
        violations.append("target-use-profile-mismatch")
    if rights.get("policyVersion") != "rights-policy-v1":
        violations.append("rights-policy-version-mismatch")
    if not _valid_date(rights.get("decisionDate")):
        violations.append("invalid-rights-date")

    required_review_strings = ("reviewId", "reviewer", "reviewedAt")
    review_reason_fields = (
        _nonblank_string_list(review.get("reasonCodes")),
        review_warnings,
        _nonblank_string_list(review.get("supersedingRejectionIds")),
    )
    if (
        any(not _nonblank_string(review.get(field)) for field in required_review_strings)
        or not _nonblank_string(review.get("decision"))
        or any(values is None for values in review_reason_fields)
        or not isinstance(review.get("attribution"), dict)
    ):
        violations.append("invalid-review-document")
    required_rights_strings = ("decisionId", "reviewer", "decisionDate")
    if any(not _nonblank_string(rights.get(field)) for field in required_rights_strings):
        violations.append("invalid-rights-document")
    provenance = candidate.get("provenance")
    if not isinstance(provenance, dict) or any(
        not _nonblank_string(provenance.get(field))
        for field in ("provider", "providerItemId", "sourcePageUrl")
    ):
        violations.append("invalid-candidate-document")
    if not _valid_provenance_url(provenance):
        violations.append("invalid-provenance-url")
    attribution = review.get("attribution")
    if not isinstance(attribution, dict) or any(
        not _nonblank_string(attribution.get(field))
        for field in ("workId", "title", "author")
    ):
        violations.append("invalid-review-document")

    return sorted(set(violations))


def _project_release(
    candidate: dict[str, Any], review: dict[str, Any], rights: dict[str, Any]
) -> dict[str, Any]:
    return {
        "analysisTextSha256": candidate["analysisTextSha256"],
        "attribution": {
            field: review["attribution"][field]
            for field in ("workId", "title", "author")
        },
        "candidateId": candidate["candidateId"],
        "excerpt": candidate["excerpt"],
        "excerptEndByte": candidate["excerptEndByte"],
        "excerptStartByte": candidate["excerptStartByte"],
        "extractionVersion": candidate["extractionVersion"],
        "matchEndByte": candidate["matchEndByte"],
        "matchStartByte": candidate["matchStartByte"],
        "matchedText": candidate["matchedText"],
        "normalizationVersion": candidate["normalizationVersion"],
        "normalizedTime": candidate["normalizedTimes"][0],
        "provenance": {
            field: candidate["provenance"][field]
            for field in ("provider", "providerItemId", "sourcePageUrl")
        },
        "quoteAfter": candidate["quoteAfter"],
        "quoteBefore": candidate["quoteBefore"],
        "quoteTime": candidate["quoteTime"],
        "releaseVersion": RELEASE_VERSION,
        "review": {
            "reviewId": review["reviewId"],
            "reviewedAt": review["reviewedAt"],
            "reviewer": review["reviewer"],
        },
        "rights": {
            "assessments": [
                {
                    field: assessment[field]
                    for field in (
                        "jurisdiction",
                        "workStatus",
                        "editionStatus",
                        "basisReasonCodes",
                        "evidenceReferences",
                        "reviewer",
                        "decisionDate",
                    )
                }
                for assessment in sorted(
                    rights["assessments"],
                    key=lambda item: {"US": 0, "CN-mainland": 1}[
                        item["jurisdiction"]
                    ],
                )
            ],
            "decision": rights["decision"],
            "decisionDate": rights["decisionDate"],
            "decisionId": rights["decisionId"],
            "policyVersion": rights["policyVersion"],
            "reviewer": rights["reviewer"],
            "targetUseProfile": rights["targetUseProfile"],
        },
        "schemaVersion": RELEASE_SCHEMA_VERSION,
        "sourceId": candidate["sourceId"],
        "sourceSha256": candidate["sourceSha256"],
    }


def validate_file(
    analysis_path: Path,
    candidate_path: Path,
    review_path: Path,
    rights_path: Path,
    output_path: Path,
) -> None:
    analysis = _read_document(analysis_path, "analysis")
    candidate = _read_document(candidate_path, "candidate")
    review = _read_document(review_path, "review")
    rights = _read_document(rights_path, "rights")
    violations = _collect_violations(analysis, candidate, review, rights)
    if violations:
        raise ReleaseValidationError(violations)
    write_json_atomic(output_path, _project_release(candidate, review, rights))
