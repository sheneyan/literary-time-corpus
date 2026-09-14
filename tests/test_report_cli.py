from __future__ import annotations

import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "report" / "candidates.jsonl"
FIXTURE_SHA256 = "020947ce7a90a02a4e5a38ba8bc5140a758f78b0ea03dfcc09c63bbe3624a02d"


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
            {"candidateCount": 2, "minute": "01:17"},
            {"candidateCount": 2, "minute": "13:15"},
        ],
        "uniqueResolvedMinutes": ["01:17", "12:00", "13:15"],
        "warningReasonCounts": {"context-note": 2, "missing-meridiem": 1},
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
