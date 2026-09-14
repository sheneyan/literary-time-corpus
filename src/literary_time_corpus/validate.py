from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from literary_time_corpus.io import write_json_atomic


RELEASE_SCHEMA_VERSION = "time-release-v1"
RELEASE_VERSION = "release-v1"
TARGET_USE_PROFILE = "zi5-public-corpus-v1"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
TIME_PATTERN = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")


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


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return value


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
    if not (0 <= excerpt_start <= match_start < match_end <= excerpt_end):
        return False

    excerpt = _string(candidate.get("excerpt"))
    before = _string(candidate.get("quoteBefore"))
    time = _string(candidate.get("quoteTime"))
    after = _string(candidate.get("quoteAfter"))
    if None in (excerpt, before, time, after):
        return False
    return (
        excerpt_end - excerpt_start == len(excerpt.encode("utf-8"))
        and match_start - excerpt_start == len(before.encode("utf-8"))
        and match_end - match_start == len(time.encode("utf-8"))
        and excerpt_end - match_end == len(after.encode("utf-8"))
    )


def _candidate_identity(candidate: dict[str, Any]) -> str | None:
    source_id = _string(candidate.get("sourceId"))
    analysis_hash = _string(candidate.get("analysisTextSha256"))
    match_start = candidate.get("matchStartByte")
    match_end = candidate.get("matchEndByte")
    if (
        source_id is None
        or analysis_hash is None
        or not isinstance(match_start, int)
        or isinstance(match_start, bool)
        or not isinstance(match_end, int)
        or isinstance(match_end, bool)
    ):
        return None
    identity = "\0".join((source_id, analysis_hash, str(match_start), str(match_end)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


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
            _string_list(assessment.get("basisReasonCodes")),
            _string_list(assessment.get("evidenceReferences")),
        )
        if (
            any(not values for values in required_evidence)
            or not _string(assessment.get("reviewer"))
            or not _string(assessment.get("decisionDate"))
        ):
            violations.append("incomplete-jurisdiction-assessment")
    return valid_objects


def _collect_violations(
    candidate: dict[str, Any], review: dict[str, Any], rights: dict[str, Any]
) -> list[str]:
    violations: list[str] = []

    if candidate.get("schemaVersion") != "time-candidate-v1":
        violations.append("invalid-candidate-document")
    if review.get("schemaVersion") != "time-review-v1":
        violations.append("invalid-review-document")
    if rights.get("schemaVersion") != "rights-decision-v1":
        violations.append("invalid-rights-document")

    if candidate.get("precision") != "exact-minute-resolved":
        violations.append("precision-not-resolved")
    normalized_times = _string_list(candidate.get("normalizedTimes"))
    if normalized_times is None or len(normalized_times) != 1:
        violations.append("normalized-time-count")
    elif TIME_PATTERN.fullmatch(normalized_times[0]) is None:
        violations.append("invalid-normalized-time")

    excerpt = _string(candidate.get("excerpt"))
    before = _string(candidate.get("quoteBefore"))
    quote_time = _string(candidate.get("quoteTime"))
    after = _string(candidate.get("quoteAfter"))
    if (
        None in (excerpt, before, quote_time, after)
        or before + quote_time + after != excerpt
    ):
        violations.append("quote-segmentation-inconsistent")
    if quote_time is None or quote_time != candidate.get("matchedText"):
        violations.append("source-span-mismatch")

    source_hash = _string(candidate.get("sourceSha256"))
    analysis_hash = _string(candidate.get("analysisTextSha256"))
    if (
        source_hash is None
        or SHA256_PATTERN.fullmatch(source_hash) is None
        or analysis_hash is None
        or SHA256_PATTERN.fullmatch(analysis_hash) is None
    ):
        violations.append("invalid-hash")
    if not _valid_offsets(candidate):
        violations.append("invalid-offsets")
    if candidate.get("candidateId") != _candidate_identity(candidate):
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
    if (
        review.get("confirmedPrecision") != candidate.get("precision")
        or review.get("confirmedNormalizedTimes") != candidate.get("normalizedTimes")
    ):
        violations.append("review-confirmed-time-mismatch")
    if not _confirmed_excerpt_matches(candidate, review):
        violations.append("review-confirmed-excerpt-mismatch")

    if candidate.get("warningReasonCodes") or review.get("unresolvedWarningReasonCodes"):
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

    required_candidate_strings = (
        "candidateId",
        "sourceId",
        "normalizationVersion",
        "extractionVersion",
        "matchedText",
    )
    if any(not _string(candidate.get(field)) for field in required_candidate_strings):
        violations.append("invalid-candidate-document")
    required_review_strings = ("reviewId", "reviewer", "reviewedAt")
    if (
        any(not _string(review.get(field)) for field in required_review_strings)
        or not isinstance(review.get("attribution"), dict)
    ):
        violations.append("invalid-review-document")
    required_rights_strings = ("decisionId", "reviewer", "decisionDate")
    if any(not _string(rights.get(field)) for field in required_rights_strings):
        violations.append("invalid-rights-document")
    if not isinstance(candidate.get("provenance"), dict):
        violations.append("invalid-candidate-document")

    return sorted(set(violations))


def _project_release(
    candidate: dict[str, Any], review: dict[str, Any], rights: dict[str, Any]
) -> dict[str, Any]:
    return {
        "analysisTextSha256": candidate["analysisTextSha256"],
        "attribution": review["attribution"],
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
        "provenance": candidate["provenance"],
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
            "assessments": sorted(
                rights["assessments"],
                key=lambda assessment: {"US": 0, "CN-mainland": 1}[
                    assessment["jurisdiction"]
                ],
            ),
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
    candidate_path: Path, review_path: Path, rights_path: Path, output_path: Path
) -> None:
    candidate = _read_document(candidate_path, "candidate")
    review = _read_document(review_path, "review")
    rights = _read_document(rights_path, "rights")
    violations = _collect_violations(candidate, review, rights)
    if violations:
        raise ReleaseValidationError(violations)
    write_json_atomic(output_path, _project_release(candidate, review, rights))
