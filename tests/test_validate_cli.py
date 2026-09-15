from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "validate"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def write_document(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, ensure_ascii=True), encoding="utf-8")


def run_validate(
    run_ltc,
    tmp_path: Path,
    *,
    analysis: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
    rights: dict[str, Any] | None = None,
    prior_output: bytes | None = None,
):
    documents = {
        "analysis": analysis if analysis is not None else load_fixture("analysis.json"),
        "candidate": candidate if candidate is not None else load_fixture("candidate.json"),
        "review": review if review is not None else load_fixture("review.json"),
        "rights": rights if rights is not None else load_fixture("rights.json"),
    }
    paths = {name: tmp_path / f"{name}.json" for name in documents}
    for name, document in documents.items():
        write_document(paths[name], document)
    output = tmp_path / "release.json"
    if prior_output is not None:
        output.write_bytes(prior_output)
    result = run_ltc(
        "validate",
        "--analysis",
        paths["analysis"],
        "--candidate",
        paths["candidate"],
        "--review",
        paths["review"],
        "--rights",
        paths["rights"],
        "--output",
        output,
    )
    return result, output


@pytest.mark.parametrize(
    ("document_name", "mutation", "expected_violation"),
    [
        (
            "analysis",
            lambda document: document.update(extension={"nested": "\ud800"}),
            "invalid-analysis-document",
        ),
        (
            "candidate",
            lambda document: document["provenance"].update(privateNote="\ud800"),
            "invalid-candidate-document",
        ),
        (
            "review",
            lambda document: document["attribution"].update(privateNote="\ud800"),
            "invalid-review-document",
        ),
        (
            "rights",
            lambda document: document["assessments"][0].update(privateNote="\ud800"),
            "invalid-rights-document",
        ),
    ],
)
def test_validate_rejects_nested_non_utf8_encodable_json_strings(
    run_ltc,
    tmp_path: Path,
    document_name: str,
    mutation: Callable[[dict[str, Any]], None],
    expected_violation: str,
) -> None:
    document = mutate_fixture(document_name + ".json", mutation)
    prior = b"preserve existing release\n"

    result, output = run_validate(
        run_ltc,
        tmp_path,
        prior_output=prior,
        **{document_name: document},
    )

    assert result.returncode == 2
    assert stderr_error(result)["code"] == "release-validation-failed"
    assert expected_violation in stderr_error(result)["details"]["violations"]
    assert output.read_bytes() == prior


def mutate_fixture(name: str, mutation: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    document = copy.deepcopy(load_fixture(name))
    mutation(document)
    return document


def stderr_error(result) -> dict[str, Any]:
    lines = result.stderr.splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])["error"]


def test_validate_projects_one_deterministic_release_record(run_ltc, tmp_path: Path) -> None:
    result, output = run_validate(run_ltc, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""

    release = json.loads(output.read_text(encoding="utf-8"))
    candidate = load_fixture("candidate.json")
    review = load_fixture("review.json")
    rights = load_fixture("rights.json")
    assert release == {
        "analysisTextSha256": candidate["analysisTextSha256"],
        "attribution": review["attribution"],
        "candidateId": candidate["candidateId"],
        "excerpt": candidate["excerpt"],
        "excerptEndByte": candidate["excerptEndByte"],
        "excerptStartByte": candidate["excerptStartByte"],
        "extractionVersion": "extract-v2",
        "matchEndByte": candidate["matchEndByte"],
        "matchStartByte": candidate["matchStartByte"],
        "matchedText": candidate["matchedText"],
        "normalizationVersion": "normalize-v1",
        "normalizedTime": "01:17",
        "provenance": candidate["provenance"],
        "quoteAfter": candidate["quoteAfter"],
        "quoteBefore": candidate["quoteBefore"],
        "quoteTime": candidate["quoteTime"],
        "releaseVersion": "release-v1",
        "review": {
            "reviewId": review["reviewId"],
            "reviewedAt": review["reviewedAt"],
            "reviewer": review["reviewer"],
        },
        "rights": {
            "assessments": rights["assessments"],
            "decision": "eligible",
            "decisionDate": rights["decisionDate"],
            "decisionId": rights["decisionId"],
            "policyVersion": "rights-policy-v1",
            "reviewer": rights["reviewer"],
            "targetUseProfile": "zi5-public-corpus-v1",
        },
        "schemaVersion": "time-release-v1",
        "sourceId": candidate["sourceId"],
        "sourceSha256": candidate["sourceSha256"],
    }

    second_output = tmp_path / "second-release.json"
    candidate_path = tmp_path / "candidate.json"
    review_path = tmp_path / "review.json"
    rights_path = tmp_path / "rights.json"
    second = run_ltc(
        "validate",
        "--analysis",
        tmp_path / "analysis.json",
        "--candidate",
        candidate_path,
        "--review",
        review_path,
        "--rights",
        rights_path,
        "--output",
        second_output,
    )
    assert second.returncode == 0, second.stderr
    assert output.read_bytes() == second_output.read_bytes()


def test_validate_detects_same_length_analysis_tampering(run_ltc, tmp_path: Path) -> None:
    analysis = load_fixture("analysis.json")
    analysis["analysisText"] = analysis["analysisText"].replace("1:17", "1:18")
    analysis["analysisTextSha256"] = hashlib.sha256(
        analysis["analysisText"].encode("utf-8")
    ).hexdigest()

    result, output = run_validate(run_ltc, tmp_path, analysis=analysis)

    assert result.returncode == 2
    assert not output.exists()
    violations = stderr_error(result)["details"]["violations"]
    assert "analysis-hash-mismatch" in violations
    assert "source-span-mismatch" in violations


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("transformationLog", "missing"),
        ("normalizationVersion", "normalize-v999"),
        ("transformationLog.0.outputEndByte", 1),
        ("bodyEndByte", 138),
    ],
)
def test_validate_requires_complete_exact_normalized_analysis_record(
    run_ltc, tmp_path: Path, path: str, value: Any
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        if path == "transformationLog" and value == "missing":
            document.pop(path)
        else:
            set_path(document, path, value)

    analysis = mutate_fixture("analysis.json", mutate)

    result, output = run_validate(run_ltc, tmp_path, analysis=analysis)

    assert result.returncode == 2
    assert not output.exists()
    assert "invalid-analysis-document" in stderr_error(result)["details"]["violations"]


def test_validate_rejects_shifted_full_file_bounds(run_ltc, tmp_path: Path) -> None:
    analysis = load_fixture("analysis.json")
    analysis["bodyStartByte"] = 1
    analysis["bodyEndByte"] += 1
    analysis["transformationLog"][0]["inputStartByte"] = 1
    analysis["transformationLog"][0]["inputEndByte"] += 1

    result, output = run_validate(run_ltc, tmp_path, analysis=analysis)

    assert result.returncode == 2
    assert "invalid-analysis-document" in stderr_error(result)["details"]["violations"]
    assert not output.exists()


@pytest.mark.parametrize("method", [[], {}])
def test_validate_rejects_non_string_transformation_method(
    run_ltc, tmp_path: Path, method: object
) -> None:
    analysis = load_fixture("analysis.json")
    analysis["transformationLog"][0]["method"] = method

    result, output = run_validate(run_ltc, tmp_path, analysis=analysis)

    assert result.returncode == 2
    error = stderr_error(result)
    assert error["code"] == "release-validation-failed"
    assert "invalid-analysis-document" in error["details"]["violations"]
    assert not output.exists()


def set_path(document: dict[str, Any], path: str, value: Any) -> None:
    parent: Any = document
    parts = path.split(".")
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    final = parts[-1]
    if value is _DELETE:
        if isinstance(parent, list):
            del parent[int(final)]
        else:
            del parent[final]
    elif isinstance(parent, list):
        parent[int(final)] = value
    else:
        parent[final] = value


_DELETE = object()


NEGATIVE_CASES = [
    ("candidate", "precision", "exact-minute-ambiguous", "precision-not-resolved"),
    ("candidate", "normalizedTimes", [], "normalized-time-count"),
    ("candidate", "normalizedTimes", ["01:17", "13:17"], "normalized-time-count"),
    ("candidate", "normalizedTimes", ["1:17"], "invalid-normalized-time"),
    ("candidate", "normalizedTimes", ["24:00"], "invalid-normalized-time"),
    ("review", "candidateId", "d" * 64, "candidate-review-identity-mismatch"),
    ("rights", "candidateId", "d" * 64, "candidate-rights-identity-mismatch"),
    ("review", "decision", "rejected-context-insufficient", "review-not-accepted"),
    ("review", "confirmedNormalizedTimes", ["01:18"], "review-confirmed-time-mismatch"),
    ("review", "confirmedPrecision", "approximate", "review-confirmed-time-mismatch"),
    ("review", "confirmedExcerpt.quoteAfter", ", she stayed.", "review-confirmed-excerpt-mismatch"),
    ("candidate", "quoteBefore", "At ", "quote-segmentation-inconsistent"),
    ("candidate", "quoteTime", "1:17 am", "source-span-mismatch"),
    ("candidate", "matchStartByte", 119, "invalid-offsets"),
    ("candidate", "excerptEndByte", 138, "invalid-offsets"),
    ("candidate", "sourceSha256", _DELETE, "invalid-hash"),
    ("candidate", "analysisTextSha256", "not-a-sha", "invalid-hash"),
    ("rights", "assessments.0", _DELETE, "missing-jurisdiction"),
    ("rights", "assessments.1", _DELETE, "missing-jurisdiction"),
    ("rights", "assessments.0.workStatus", "restricted", "work-status-not-eligible"),
    ("rights", "assessments.1.workStatus", "uncertain", "work-status-not-eligible"),
    ("rights", "assessments.0.editionStatus", "contains-protected-material", "edition-status-not-eligible"),
    ("rights", "assessments.1.editionStatus", "uncertain", "edition-status-not-eligible"),
    ("rights", "decision", "analysis-only", "rights-decision-not-eligible"),
    ("candidate", "warningReasonCodes", ["missing-meridiem"], "unresolved-warnings"),
    ("review", "unresolvedWarningReasonCodes", ["attribution-question"], "unresolved-warnings"),
    ("review", "supersedingRejectionIds", ["review-rejection-v2"], "superseding-rejection"),
    ("rights", "targetUseProfile", "private-research-v1", "target-use-profile-mismatch"),
]


REQUIRED_FIELD_CASES = [
    ("candidate", "ruleFamily", _DELETE, "invalid-candidate-document"),
    ("candidate", "ruleId", _DELETE, "invalid-candidate-document"),
    ("candidate", "context", _DELETE, "invalid-candidate-document"),
    ("candidate", "sourceHashStatus", _DELETE, "invalid-candidate-document"),
    ("candidate", "contextualResolution", _DELETE, "invalid-candidate-document"),
    ("candidate", "status", _DELETE, "invalid-candidate-document"),
    ("candidate", "status", "", "invalid-candidate-document"),
    ("candidate", "exclusionReasonCodes", _DELETE, "invalid-candidate-document"),
    ("candidate", "exclusionReasonCodes", "", "invalid-candidate-document"),
    ("candidate", "exclusionReasonCodes", [""], "invalid-candidate-document"),
    ("candidate", "warningReasonCodes", _DELETE, "invalid-candidate-document"),
    ("candidate", "warningReasonCodes", "", "invalid-candidate-document"),
    ("candidate", "warningReasonCodes", [""], "invalid-candidate-document"),
    ("review", "decision", _DELETE, "invalid-review-document"),
    ("review", "decision", "", "invalid-review-document"),
    ("review", "reasonCodes", _DELETE, "invalid-review-document"),
    ("review", "reasonCodes", "", "invalid-review-document"),
    ("review", "reasonCodes", [""], "invalid-review-document"),
    ("review", "unresolvedWarningReasonCodes", _DELETE, "invalid-review-document"),
    ("review", "unresolvedWarningReasonCodes", "", "invalid-review-document"),
    ("review", "unresolvedWarningReasonCodes", [""], "invalid-review-document"),
    ("candidate", "provenance.provider", _DELETE, "invalid-candidate-document"),
    ("candidate", "provenance.provider", "", "invalid-candidate-document"),
    ("candidate", "provenance.providerItemId", _DELETE, "invalid-candidate-document"),
    ("candidate", "provenance.providerItemId", "", "invalid-candidate-document"),
    ("candidate", "provenance.sourcePageUrl", _DELETE, "invalid-candidate-document"),
    ("candidate", "provenance.sourcePageUrl", "", "invalid-candidate-document"),
    ("review", "attribution.workId", _DELETE, "invalid-review-document"),
    ("review", "attribution.workId", "", "invalid-review-document"),
    ("review", "attribution.title", _DELETE, "invalid-review-document"),
    ("review", "attribution.title", "", "invalid-review-document"),
    ("review", "attribution.author", _DELETE, "invalid-review-document"),
    ("review", "attribution.author", "", "invalid-review-document"),
    ("rights", "assessments.0.basisReasonCodes", _DELETE, "incomplete-jurisdiction-assessment"),
    ("rights", "assessments.0.basisReasonCodes", [], "incomplete-jurisdiction-assessment"),
    ("rights", "assessments.0.basisReasonCodes", [""], "incomplete-jurisdiction-assessment"),
    ("rights", "assessments.1.evidenceReferences", _DELETE, "incomplete-jurisdiction-assessment"),
    ("rights", "assessments.1.evidenceReferences", [], "incomplete-jurisdiction-assessment"),
    ("rights", "assessments.1.evidenceReferences", [""], "incomplete-jurisdiction-assessment"),
    ("rights", "assessments.0.reviewer", "", "incomplete-jurisdiction-assessment"),
    ("rights", "assessments.1.decisionDate", "", "incomplete-jurisdiction-assessment"),
]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("normalizationVersion", "normalize-v999"),
        ("extractionVersion", "extract-v999"),
        ("ruleFamily", ""),
        ("ruleId", ""),
        ("context", "spoofed context"),
        ("sourceHashStatus", "verified-from-source"),
        ("contextualResolution.method", "named-time"),
        ("contextualResolution.evidenceText", "p.m."),
    ],
)
def test_validate_reuses_complete_candidate_shape_validation(
    run_ltc, tmp_path: Path, path: str, value: Any
) -> None:
    candidate = mutate_fixture(
        "candidate.json", lambda document: set_path(document, path, value)
    )

    result, output = run_validate(run_ltc, tmp_path, candidate=candidate)

    assert result.returncode == 2
    assert not output.exists()
    assert "invalid-candidate-document" in stderr_error(result)["details"]["violations"]


def test_validate_rejects_coherent_non_meridiem_evidence_spoof(
    run_ltc, tmp_path: Path
) -> None:
    candidate = load_fixture("candidate.json")
    candidate["contextualResolution"] = {
        "evidenceEndByte": 122,
        "evidenceStartByte": 118,
        "evidenceText": "1:17",
        "method": "explicit-meridiem",
    }

    result, output = run_validate(run_ltc, tmp_path, candidate=candidate)

    assert result.returncode == 2
    assert not output.exists()
    assert "invalid-candidate-document" in stderr_error(result)["details"]["violations"]


@pytest.mark.parametrize(
    ("document_name", "path", "value", "expected_violation"),
    NEGATIVE_CASES,
    ids=[f"{name}-{path}-{expected}" for name, path, _value, expected in NEGATIVE_CASES],
)
def test_validate_fails_closed_for_each_release_invariant(
    run_ltc,
    tmp_path: Path,
    document_name: str,
    path: str,
    value: Any,
    expected_violation: str,
) -> None:
    changed = mutate_fixture(document_name + ".json", lambda document: set_path(document, path, value))
    inputs = {document_name: changed}
    result, output = run_validate(run_ltc, tmp_path, **inputs)

    assert result.returncode == 2
    assert not output.exists()
    error = stderr_error(result)
    assert error["code"] == "release-validation-failed"
    assert expected_violation in error["details"]["violations"]
    assert error["details"]["violations"] == sorted(set(error["details"]["violations"]))


@pytest.mark.parametrize(
    ("document_name", "path", "value", "expected_violation"),
    REQUIRED_FIELD_CASES,
    ids=[f"{name}-{path}" for name, path, _value, _expected in REQUIRED_FIELD_CASES],
)
def test_validate_rejects_missing_or_blank_required_fields(
    run_ltc,
    tmp_path: Path,
    document_name: str,
    path: str,
    value: Any,
    expected_violation: str,
) -> None:
    changed = mutate_fixture(
        document_name + ".json", lambda document: set_path(document, path, value)
    )
    result, output = run_validate(run_ltc, tmp_path, **{document_name: changed})

    assert result.returncode == 2
    assert not output.exists()
    assert expected_violation in stderr_error(result)["details"]["violations"]


def test_validate_reports_all_violations_in_stable_sorted_order(run_ltc, tmp_path: Path) -> None:
    candidate = load_fixture("candidate.json")
    candidate["precision"] = "approximate"
    candidate["normalizedTimes"] = []
    candidate["warningReasonCodes"] = ["approximation"]

    result, output = run_validate(run_ltc, tmp_path, candidate=candidate)

    assert result.returncode == 2
    assert not output.exists()
    assert stderr_error(result)["details"]["violations"] == [
        "invalid-candidate-document",
        "normalized-time-count",
        "precision-not-resolved",
        "review-confirmed-time-mismatch",
        "unresolved-warnings",
    ]


def test_validate_canonicalizes_required_jurisdiction_order(run_ltc, tmp_path: Path) -> None:
    first, output = run_validate(run_ltc, tmp_path)
    assert first.returncode == 0, first.stderr
    expected = output.read_bytes()

    rights = load_fixture("rights.json")
    rights["assessments"].reverse()
    rights_path = tmp_path / "rights.json"
    write_document(rights_path, rights)
    second_output = tmp_path / "release-reordered-rights.json"
    second = run_ltc(
        "validate",
        "--analysis",
        tmp_path / "analysis.json",
        "--candidate",
        tmp_path / "candidate.json",
        "--review",
        tmp_path / "review.json",
        "--rights",
        rights_path,
        "--output",
        second_output,
    )

    assert second.returncode == 0, second.stderr
    assert second_output.read_bytes() == expected


def test_validate_rejects_assessments_outside_the_profile(run_ltc, tmp_path: Path) -> None:
    rights = load_fixture("rights.json")
    extra = copy.deepcopy(rights["assessments"][0])
    extra["jurisdiction"] = "GB"
    rights["assessments"].append(extra)

    result, output = run_validate(run_ltc, tmp_path, rights=rights)

    assert result.returncode == 2
    assert not output.exists()
    assert "unexpected-jurisdiction" in stderr_error(result)["details"]["violations"]


def test_validate_release_uses_nested_allowlists(run_ltc, tmp_path: Path) -> None:
    candidate = load_fixture("candidate.json")
    review = load_fixture("review.json")
    rights = load_fixture("rights.json")
    candidate["exactFileUrl"] = "SECRET exact file URL"
    candidate["privateNote"] = "SECRET candidate note"
    candidate["provenance"]["privateNote"] = "SECRET provenance note"
    candidate["provenance"]["exactFileUrl"] = "SECRET nested exact file URL"
    review["privateReviewerNote"] = "SECRET reviewer note"
    review["attribution"]["privateNote"] = "SECRET attribution note"
    rights["privateNote"] = "SECRET rights note"
    rights["assessments"][0]["privateNote"] = "SECRET assessment note"

    result, output = run_validate(
        run_ltc, tmp_path, candidate=candidate, review=review, rights=rights
    )

    assert result.returncode == 0, result.stderr
    release_text = output.read_text(encoding="utf-8")
    assert "SECRET" not in release_text
    assert "analysisText" not in json.loads(release_text)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.gutenberg.org/ebooks/117",
        "https://user:password@www.gutenberg.org/ebooks/117",
        "https://localhost/ebooks/117",
        "https://catalog.internal/ebooks/117",
        "https://192.168.1.8/ebooks/117",
        "file:///srv/private/117.txt",
        "https://www.gutenberg.org/ebooks/118",
        "https://www.gutenberg.org/ebooks/117?token=secret",
    ],
)
def test_validate_rejects_unsafe_or_noncanonical_provenance_urls(
    run_ltc, tmp_path: Path, url: str
) -> None:
    candidate = load_fixture("candidate.json")
    candidate["provenance"]["sourcePageUrl"] = url

    result, output = run_validate(run_ltc, tmp_path, candidate=candidate)

    assert result.returncode == 2
    assert not output.exists()
    assert "invalid-provenance-url" in stderr_error(result)["details"]["violations"]


@pytest.mark.parametrize(
    "reviewed_at",
    [
        "2026-09-14T08:00:00+00:00",
        "2026-09-14T08:00:00.000Z",
        "2026-02-30T08:00:00Z",
        "2026-09-14 08:00:00Z",
        "",
    ],
)
def test_validate_requires_canonical_utc_review_timestamp(
    run_ltc, tmp_path: Path, reviewed_at: str
) -> None:
    review = load_fixture("review.json")
    review["reviewedAt"] = reviewed_at

    result, output = run_validate(run_ltc, tmp_path, review=review)

    assert result.returncode == 2
    assert not output.exists()
    assert "invalid-review-timestamp" in stderr_error(result)["details"]["violations"]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("decisionDate", "2026-02-30"),
        ("decisionDate", "2026-9-14"),
        ("decisionDate", "2026-09-14T00:00:00Z"),
        ("assessments.0.decisionDate", "2025-02-29"),
        ("assessments.1.decisionDate", ""),
    ],
)
def test_validate_requires_real_iso_rights_dates(
    run_ltc, tmp_path: Path, path: str, value: str
) -> None:
    rights = mutate_fixture(
        "rights.json", lambda document: set_path(document, path, value)
    )

    result, output = run_validate(run_ltc, tmp_path, rights=rights)

    assert result.returncode == 2
    assert not output.exists()
    assert "invalid-rights-date" in stderr_error(result)["details"]["violations"]


def test_validate_preserves_existing_regular_output_on_failure(run_ltc, tmp_path: Path) -> None:
    candidate = mutate_fixture(
        "candidate.json", lambda document: document.update(precision="approximate")
    )
    result, output = run_validate(run_ltc, tmp_path, candidate=candidate)
    assert result.returncode == 2
    assert not output.exists()

    prior_release = b'{"prior":"approved release"}\n'
    output.write_bytes(prior_release)
    result = run_ltc(
        "validate",
        "--analysis",
        tmp_path / "analysis.json",
        "--candidate",
        tmp_path / "candidate.json",
        "--review",
        tmp_path / "review.json",
        "--rights",
        tmp_path / "rights.json",
        "--output",
        output,
    )
    assert result.returncode == 2
    assert output.read_bytes() == prior_release


def test_validate_rejects_output_aliases_without_damaging_inputs(run_ltc, tmp_path: Path) -> None:
    candidate = load_fixture("candidate.json")
    candidate_path = tmp_path / "candidate.json"
    analysis_path = tmp_path / "analysis.json"
    review_path = tmp_path / "review.json"
    rights_path = tmp_path / "rights.json"
    write_document(candidate_path, candidate)
    write_document(analysis_path, load_fixture("analysis.json"))
    write_document(review_path, load_fixture("review.json"))
    write_document(rights_path, load_fixture("rights.json"))
    before = candidate_path.read_bytes()

    result = run_ltc(
        "validate",
        "--analysis",
        analysis_path,
        "--candidate",
        candidate_path,
        "--review",
        review_path,
        "--rights",
        rights_path,
        "--output",
        candidate_path,
    )
    assert result.returncode == 2
    assert stderr_error(result)["code"] == "unsafe-output-path"
    assert candidate_path.read_bytes() == before

    target = tmp_path / "target.json"
    target.write_text("do not overwrite", encoding="utf-8")
    link = tmp_path / "release-link.json"
    link.symlink_to(target)
    result = run_ltc(
        "validate",
        "--analysis",
        analysis_path,
        "--candidate",
        candidate_path,
        "--review",
        review_path,
        "--rights",
        rights_path,
        "--output",
        link,
    )
    assert result.returncode == 2
    assert stderr_error(result)["code"] == "unsafe-output-path"
    assert target.read_text(encoding="utf-8") == "do not overwrite"
