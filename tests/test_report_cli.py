from __future__ import annotations

import json
from pathlib import Path

import pytest


FIXTURE = Path(__file__).parent / "fixtures" / "report" / "candidates.jsonl"
FIXTURE_SHA256 = "6701450094913a5194dfd644d6b3237d0fa46b85ea675c4a26a8c3c1995c2d0e"


def first_candidate() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8").splitlines()[0])


def write_candidate(path: Path, candidate: dict[str, object]) -> None:
    path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")


def test_report_summarizes_candidate_jsonl_deterministically(run_ltc, tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    first_result = run_ltc("report", "--input", FIXTURE, "--output", first)
    second_result = run_ltc("report", "--input", FIXTURE, "--output", second)

    assert first_result.returncode == second_result.returncode == 0
    assert first.read_bytes() == second.read_bytes()
    report = json.loads(first.read_text(encoding="utf-8"))
    assert report == {
        "candidateCount": 7,
        "candidateSchemaVersion": "time-candidate-v1",
        "coverageFraction": 3 / 1440,
        "duplicateConcentration": {
            "duplicateCandidateCount": 2,
            "duplicateFraction": 0.4,
            "duplicateMinuteCount": 2,
            "maxCandidatesPerMinute": 2,
            "resolvedCandidateCount": 5,
        },
        "exclusionReasonCounts": {
            "approximate-expression": 1,
            "duplicate-source": 1,
        },
        "inputSha256": FIXTURE_SHA256,
        "precisionCounts": {
            "approximate": 1,
            "exact-minute-ambiguous": 1,
            "exact-minute-resolved": 5,
        },
        "reportVersion": "report-v1",
        "resolvedMinuteCount": 3,
        "ruleFamilyCounts": {
            "approximate-clock": 1,
            "named-time": 2,
            "numeric-12-hour": 1,
            "numeric-24-hour": 2,
            "written-minutes": 1,
        },
        "schemaVersion": "candidate-report-v1",
        "statusCounts": {
            "automatically-excluded": 2,
            "awaiting-review": 1,
            "detected": 3,
            "reviewed": 1,
        },
        "topDuplicateMinutes": [
            {"candidateCount": 2, "minute": "12:00"},
            {"candidateCount": 2, "minute": "13:15"},
        ],
        "uniqueResolvedMinutes": ["01:17", "12:00", "13:15"],
        "warningReasonCounts": {"context-note": 2, "missing-meridiem": 1},
    }
    assert "timestamp" not in first.read_text(encoding="utf-8").lower()


def test_report_accepts_deterministic_empty_no_match_extraction(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "no-time.txt"
    source.write_text(
        "Synthetic metadata\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK NO TIME ***\n"
        "The synthetic room stayed quiet throughout the scene.\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK NO TIME ***\n",
        encoding="utf-8",
    )
    normalized = tmp_path / "normalized.json"
    candidates = tmp_path / "candidates.jsonl"
    first = tmp_path / "first-report.json"
    second = tmp_path / "second-report.json"

    assert run_ltc("normalize", "--input", source, "--output", normalized).returncode == 0
    extract_result = run_ltc("extract", "--input", normalized, "--output", candidates)
    assert extract_result.returncode == 0, extract_result.stderr
    assert candidates.read_bytes() == b""

    first_result = run_ltc("report", "--input", candidates, "--output", first)
    second_result = run_ltc("report", "--input", candidates, "--output", second)

    assert first_result.returncode == second_result.returncode == 0
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text(encoding="utf-8")) == {
        "candidateCount": 0,
        "candidateSchemaVersion": "time-candidate-v1",
        "coverageFraction": 0.0,
        "duplicateConcentration": {
            "duplicateCandidateCount": 0,
            "duplicateFraction": 0.0,
            "duplicateMinuteCount": 0,
            "maxCandidatesPerMinute": 0,
            "resolvedCandidateCount": 0,
        },
        "exclusionReasonCounts": {},
        "inputSha256": (
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
        "precisionCounts": {},
        "reportVersion": "report-v1",
        "resolvedMinuteCount": 0,
        "ruleFamilyCounts": {},
        "schemaVersion": "candidate-report-v1",
        "statusCounts": {},
        "topDuplicateMinutes": [],
        "uniqueResolvedMinutes": [],
        "warningReasonCounts": {},
    }
    assert "timestamp" not in first.read_text(encoding="utf-8").lower()


def test_report_reordered_rows_keep_metrics_but_change_input_hash(run_ltc, tmp_path: Path) -> None:
    rows = FIXTURE.read_bytes().splitlines(keepends=True)
    reordered_input = tmp_path / "reordered.jsonl"
    reordered_input.write_bytes(b"".join(reversed(rows)))
    original_output = tmp_path / "original.json"
    reordered_output = tmp_path / "reordered.json"

    assert run_ltc("report", "--input", FIXTURE, "--output", original_output).returncode == 0
    assert run_ltc("report", "--input", reordered_input, "--output", reordered_output).returncode == 0

    original = json.loads(original_output.read_text(encoding="utf-8"))
    reordered = json.loads(reordered_output.read_text(encoding="utf-8"))
    assert original.pop("inputSha256") != reordered.pop("inputSha256")
    assert original == reordered


def test_report_malformed_jsonl_preserves_existing_output(run_ltc, tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_bytes(FIXTURE.read_bytes().splitlines(keepends=True)[0] + b"not-json\n")
    output = tmp_path / "report.json"
    output.write_bytes(b"keep this exact output\n")

    result = run_ltc("report", "--input", malformed, "--output", output)

    assert result.returncode == 2
    error = json.loads(result.stderr)
    assert error["error"]["code"] == "invalid-candidate-jsonl"
    assert error["error"]["details"] == {"line": 2}
    assert output.read_bytes() == b"keep this exact output\n"


@pytest.mark.parametrize(
    "shape", ["missing-parent", "non-directory-parent", "symlink-loop-parent"]
)
def test_report_invalid_output_path_is_structured_and_preserves_existing_data(
    run_ltc, tmp_path: Path, shape: str
) -> None:
    preserved = tmp_path / "preserved.json"
    preserved.write_bytes(b"keep this exact output\n")
    if shape == "missing-parent":
        output = tmp_path / "missing" / "report.json"
    elif shape == "non-directory-parent":
        parent = tmp_path / "not-a-directory"
        parent.write_bytes(b"keep this parent file\n")
        output = parent / "report.json"
    else:
        parent = tmp_path / "loop"
        parent.symlink_to(parent)
        output = parent / "report.json"

    result = run_ltc("report", "--input", FIXTURE, "--output", output)

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == {
        "code": "invalid-output-path",
        "message": "could not write output path",
    }
    assert preserved.read_bytes() == b"keep this exact output\n"
    assert not output.exists()
    if shape == "non-directory-parent":
        assert output.parent.read_bytes() == b"keep this parent file\n"
    elif shape == "symlink-loop-parent":
        assert output.parent.is_symlink()


def test_report_rejects_inconsistent_schema_versions_without_overwriting(
    run_ltc, tmp_path: Path
) -> None:
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
    rows[-1]["schemaVersion"] = "time-candidate-v2"
    inconsistent = tmp_path / "inconsistent.jsonl"
    inconsistent.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    output = tmp_path / "report.json"
    output.write_bytes(b"existing\n")

    result = run_ltc("report", "--input", inconsistent, "--output", output)

    assert result.returncode == 2
    error = json.loads(result.stderr)
    assert error["error"]["code"] == "inconsistent-candidate-schema"
    assert error["error"]["details"] == {
        "actual": "time-candidate-v2",
        "expected": "time-candidate-v1",
        "line": 7,
    }
    assert output.read_bytes() == b"existing\n"


def test_report_rejects_invalid_candidate_shape_without_output(run_ltc, tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text(
        json.dumps(
            {
                "schemaVersion": "time-candidate-v1",
                "status": "invented",
                "precision": "exact-minute-resolved",
                "ruleFamily": "numeric-24-hour",
                "normalizedTimes": ["25:00"],
                "exclusionReasonCodes": [],
                "warningReasonCodes": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    result = run_ltc("report", "--input", invalid, "--output", output)

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "invalid-candidate-jsonl"
    assert not output.exists()


@pytest.mark.parametrize("rule_family", ["numeric-24-hour", "named-time"])
def test_report_rejects_coherent_partial_resolution_evidence_spoof(
    run_ltc, tmp_path: Path, rule_family: str
) -> None:
    candidates = [
        json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()
    ]
    candidate = next(row for row in candidates if row["ruleFamily"] == rule_family)
    resolution = candidate["contextualResolution"]
    resolution["evidenceText"] = resolution["evidenceText"][:-1]
    resolution["evidenceEndByte"] -= 1
    input_path = tmp_path / "spoof.jsonl"
    write_candidate(input_path, candidate)
    output = tmp_path / "report.json"

    result = run_ltc("report", "--input", input_path, "--output", output)

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "invalid-candidate-jsonl"
    assert not output.exists()


@pytest.mark.parametrize(
    "corruption",
    [
        "missing-candidate-id",
        "invalid-source-hash",
        "invalid-analysis-hash",
        "missing-normalization-version",
        "missing-extraction-version",
        "missing-rule-id",
        "matched-text-mismatch",
        "context-mismatch",
        "invalid-offset",
        "segmentation-mismatch",
        "invalid-source-hash-status",
        "duplicate-reason",
        "ambiguous-without-alternatives",
        "approximate-with-normalized-time",
    ],
)
def test_report_rejects_truncated_or_corrupt_candidate_artifacts(
    run_ltc, tmp_path: Path, corruption: str
) -> None:
    candidate = first_candidate()
    if corruption == "missing-candidate-id":
        del candidate["candidateId"]
    elif corruption == "invalid-source-hash":
        candidate["sourceSha256"] = "bad"
    elif corruption == "invalid-analysis-hash":
        candidate["analysisTextSha256"] = "bad"
    elif corruption == "missing-normalization-version":
        candidate["normalizationVersion"] = ""
    elif corruption == "missing-extraction-version":
        candidate["extractionVersion"] = ""
    elif corruption == "missing-rule-id":
        del candidate["ruleId"]
    elif corruption == "matched-text-mismatch":
        candidate["matchedText"] = "01:18"
    elif corruption == "context-mismatch":
        candidate["context"] = "different"
    elif corruption == "invalid-offset":
        candidate["matchStartByte"] = -1
    elif corruption == "segmentation-mismatch":
        candidate["quoteAfter"] = "!"
    elif corruption == "invalid-source-hash-status":
        candidate["sourceHashStatus"] = "unverified"
    elif corruption == "duplicate-reason":
        candidate["warningReasonCodes"] = ["same", "same"]
    elif corruption == "ambiguous-without-alternatives":
        candidate["precision"] = "exact-minute-ambiguous"
        candidate["normalizedTimes"] = []
    elif corruption == "approximate-with-normalized-time":
        candidate["precision"] = "approximate"

    input_path = tmp_path / "corrupt.jsonl"
    write_candidate(input_path, candidate)
    output = tmp_path / "report.json"
    output.write_bytes(b"preserve\n")

    result = run_ltc("report", "--input", input_path, "--output", output)

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == {
        "code": "invalid-candidate-jsonl",
        "details": {"line": 1},
        "message": "candidate row does not satisfy time-candidate-v1",
    }
    assert output.read_bytes() == b"preserve\n"


@pytest.mark.parametrize(
    "field", ["unrecognizedField", "schemaVersion", "sourceId", "warningReasonCodes"]
)
def test_report_rejects_non_utf8_encodable_json_strings_without_overwriting(
    run_ltc, tmp_path: Path, field: str
) -> None:
    candidate = first_candidate()
    candidate[field] = ["\ud800"] if field == "warningReasonCodes" else "\ud800"
    input_path = tmp_path / "surrogate.jsonl"
    expected_line = 2 if field == "schemaVersion" else 1
    if field == "schemaVersion":
        input_path.write_text(
            json.dumps(first_candidate()) + "\n" + json.dumps(candidate) + "\n",
            encoding="utf-8",
        )
    else:
        write_candidate(input_path, candidate)
    output = tmp_path / "report.json"
    output.write_bytes(b"preserve\n")

    result = run_ltc("report", "--input", input_path, "--output", output)

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == {
        "code": "invalid-candidate-jsonl",
        "details": {"line": expected_line},
        "message": "candidate row does not satisfy time-candidate-v1",
    }
    assert output.read_bytes() == b"preserve\n"


def test_report_rejects_nested_non_utf8_encodable_candidate_with_line_detail(
    run_ltc, tmp_path: Path
) -> None:
    input_path = tmp_path / "surrogate.jsonl"
    input_path.write_text(
        json.dumps(first_candidate())
        + "\n"
        + json.dumps({**first_candidate(), "extension": {"nested": "\ud800"}})
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    prior = b"preserve\n"
    output.write_bytes(prior)

    result = run_ltc("report", "--input", input_path, "--output", output)

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == {
        "code": "invalid-candidate-jsonl",
        "details": {"line": 2},
        "message": "candidate row does not satisfy time-candidate-v1",
    }
    assert output.read_bytes() == prior
