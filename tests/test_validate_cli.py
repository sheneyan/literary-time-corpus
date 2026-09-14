from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "validate"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def write_document(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def run_validate(
    run_ltc,
    tmp_path: Path,
    *,
    candidate: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
    rights: dict[str, Any] | None = None,
):
    documents = {
        "candidate": candidate or load_fixture("candidate.json"),
        "review": review or load_fixture("review.json"),
        "rights": rights or load_fixture("rights.json"),
    }
    paths = {name: tmp_path / f"{name}.json" for name in documents}
    for name, document in documents.items():
        write_document(paths[name], document)
    output = tmp_path / "release.json"
    result = run_ltc(
        "validate",
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
        "extractionVersion": "extract-v1",
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


def test_validate_reports_all_violations_in_stable_sorted_order(run_ltc, tmp_path: Path) -> None:
    candidate = load_fixture("candidate.json")
    candidate["precision"] = "approximate"
    candidate["normalizedTimes"] = []
    candidate["warningReasonCodes"] = ["approximation"]

    result, output = run_validate(run_ltc, tmp_path, candidate=candidate)

    assert result.returncode == 2
    assert not output.exists()
    assert stderr_error(result)["details"]["violations"] == [
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


def test_validate_removes_existing_regular_output_on_failure(run_ltc, tmp_path: Path) -> None:
    candidate = mutate_fixture(
        "candidate.json", lambda document: document.update(precision="approximate")
    )
    result, output = run_validate(run_ltc, tmp_path, candidate=candidate)
    assert result.returncode == 2
    assert not output.exists()

    output.write_text("stale release", encoding="utf-8")
    result = run_ltc(
        "validate",
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
    assert not output.exists()


def test_validate_rejects_output_aliases_without_damaging_inputs(run_ltc, tmp_path: Path) -> None:
    candidate = load_fixture("candidate.json")
    candidate_path = tmp_path / "candidate.json"
    review_path = tmp_path / "review.json"
    rights_path = tmp_path / "rights.json"
    write_document(candidate_path, candidate)
    write_document(review_path, load_fixture("review.json"))
    write_document(rights_path, load_fixture("rights.json"))
    before = candidate_path.read_bytes()

    result = run_ltc(
        "validate",
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
