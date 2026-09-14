from __future__ import annotations

import hashlib
import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "extract" / "times.txt"


def normalized_fixture(run_ltc, tmp_path: Path) -> Path:
    normalized = tmp_path / "normalized.json"
    result = run_ltc("normalize", "--input", FIXTURE, "--output", normalized)
    assert result.returncode == 0, result.stderr
    return normalized


def extract_fixture(run_ltc, tmp_path: Path) -> tuple[dict[str, object], list[dict[str, object]], bytes]:
    normalized = normalized_fixture(run_ltc, tmp_path)
    output = tmp_path / "candidates.jsonl"
    result = run_ltc("extract", "--input", normalized, "--output", output)
    assert result.returncode == 0, result.stderr
    document = json.loads(normalized.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    return document, rows, output.read_bytes()


def candidate_by_text(rows: list[dict[str, object]], text: str) -> dict[str, object]:
    matches = [row for row in rows if row["matchedText"] == text]
    assert len(matches) == 1, (text, matches)
    return matches[0]


def expected_candidate_id(candidate: dict[str, object]) -> str:
    identity = "\0".join(
        [
            str(candidate["sourceId"]),
            str(candidate["analysisTextSha256"]),
            str(candidate["matchStartByte"]),
            str(candidate["matchEndByte"]),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def test_extract_resolves_initial_exact_time_rule_families(run_ltc, tmp_path: Path) -> None:
    _document, rows, _output = extract_fixture(run_ltc, tmp_path)

    expected = {
        "1:17 a.m.": ("numeric-12-hour", ["01:17"]),
        "09:03 P.M.": ("numeric-12-hour", ["21:03"]),
        "noon": ("named-time", ["12:00"]),
        "midnight": ("named-time", ["00:00"]),
    }
    for matched_text, (family, times) in expected.items():
        candidate = candidate_by_text(rows, matched_text)
        assert candidate["ruleFamily"] == family
        assert candidate["normalizedTimes"] == times
        assert candidate["precision"] == "exact-minute-resolved"
        assert candidate["status"] == "detected"
        assert candidate["exclusionReasonCodes"] == []
        assert candidate["warningReasonCodes"] == []
    assert not [row for row in rows if row["matchedText"] == "09:03"]

    ambiguous_written = {
        "twenty minutes past four": ("written-minutes", ["04:20", "16:20"]),
        "quarter past six": ("written-fraction", ["06:15", "18:15"]),
        "a quarter to eight": ("written-fraction", ["07:45", "19:45"]),
        "Half past nine": ("written-fraction", ["09:30", "21:30"]),
    }
    for matched_text, (family, times) in ambiguous_written.items():
        candidate = candidate_by_text(rows, matched_text)
        assert candidate["ruleFamily"] == family
        assert candidate["normalizedTimes"] == times
        assert candidate["precision"] == "exact-minute-ambiguous"
        assert candidate["status"] == "detected"
        assert candidate["warningReasonCodes"] == ["missing-meridiem"]


def test_extract_marks_bare_clock_ambiguous_and_approximation_non_releaseable(
    run_ltc, tmp_path: Path
) -> None:
    _document, rows, _output = extract_fixture(run_ltc, tmp_path)

    bare = candidate_by_text(rows, "5:42")
    assert bare["normalizedTimes"] == ["05:42", "17:42"]
    assert bare["precision"] == "exact-minute-ambiguous"
    assert bare["status"] == "detected"
    assert bare["warningReasonCodes"] == ["missing-meridiem"]

    approximate = candidate_by_text(rows, "about five o'clock")
    assert approximate["normalizedTimes"] == []
    assert approximate["precision"] == "approximate"
    assert approximate["status"] == "automatically-excluded"
    assert approximate["exclusionReasonCodes"] == ["approximate-expression"]

    for text in ("about 13:15", "approximately 14:20"):
        numeric_approximation = candidate_by_text(rows, text)
        assert numeric_approximation["normalizedTimes"] == []
        assert numeric_approximation["precision"] == "approximate"
        assert numeric_approximation["status"] == "automatically-excluded"
        assert numeric_approximation["exclusionReasonCodes"] == [
            "approximate-expression"
        ]


def test_extract_does_not_release_false_positive_numeric_shapes(run_ltc, tmp_path: Path) -> None:
    document, rows, _output = extract_fixture(run_ltc, tmp_path)

    analysis = document["analysisText"]
    false_positive_shapes = (
        "2026-09-14",
        "$1:30",
        "$ 2:40",
        "€3:50",
        "£ 4:10",
        "¥5:20",
        "John 3:16",
        "Romans 13:15",
        "Rom. 17:33",
        "romans 18:34",
        "chapter 12:10",
        "13:15:42",
        "1:30 hours",
    )
    for shape in false_positive_shapes:
        character_start = analysis.index(shape)
        start = len(analysis[:character_start].encode("utf-8"))
        end = start + len(shape.encode("utf-8"))
        overlapping = [
            row
            for row in rows
            if row["matchStartByte"] < end and row["matchEndByte"] > start
        ]
        assert all(row["status"] == "automatically-excluded" for row in overlapping), (
            shape,
            overlapping,
        )


def test_extract_keeps_sentence_initial_numeric_24_hour_time(run_ltc, tmp_path: Path) -> None:
    document, rows, _output = extract_fixture(run_ltc, tmp_path)

    analysis = document["analysisText"]
    character_start = analysis.index("At 13:15") + len("At ")
    expected_start = len(analysis[:character_start].encode("utf-8"))
    matching = [
        row
        for row in rows
        if row["matchedText"] == "13:15" and row["matchStartByte"] == expected_start
    ]
    assert len(matching) == 1
    candidate = matching[0]

    assert candidate["normalizedTimes"] == ["13:15"]
    assert candidate["precision"] == "exact-minute-resolved"
    assert candidate["status"] == "detected"


def test_extract_supports_zero_padded_24_hour_times(run_ltc, tmp_path: Path) -> None:
    _document, rows, _output = extract_fixture(run_ltc, tmp_path)

    nine = candidate_by_text(rows, "09:05")
    midnight = candidate_by_text(rows, "00:07")

    assert nine["normalizedTimes"] == ["09:05"]
    assert nine["precision"] == "exact-minute-resolved"
    assert nine["ruleFamily"] == "numeric-24-hour"
    assert midnight["normalizedTimes"] == ["00:07"]
    assert midnight["precision"] == "exact-minute-resolved"
    assert midnight["ruleFamily"] == "numeric-24-hour"


def test_extract_keeps_narrative_title_case_time_introducers(run_ltc, tmp_path: Path) -> None:
    _document, rows, _output = extract_fixture(run_ltc, tmp_path)

    by_time = candidate_by_text(rows, "15:31")
    after_time = candidate_by_text(rows, "16:32")

    assert by_time["normalizedTimes"] == ["15:31"]
    assert by_time["precision"] == "exact-minute-resolved"
    assert after_time["normalizedTimes"] == ["16:32"]
    assert after_time["precision"] == "exact-minute-resolved"


def test_extract_emits_exact_utf8_offsets_ids_context_and_segmentation(
    run_ltc, tmp_path: Path
) -> None:
    document, rows, _output = extract_fixture(run_ltc, tmp_path)
    analysis = document["analysisText"]
    analysis_bytes = analysis.encode("utf-8")

    assert rows == sorted(
        rows,
        key=lambda row: (row["matchStartByte"], row["matchEndByte"], row["candidateId"]),
    )
    for candidate in rows:
        start = candidate["matchStartByte"]
        end = candidate["matchEndByte"]
        assert analysis_bytes[start:end].decode("utf-8") == candidate["matchedText"]
        assert candidate["candidateId"] == expected_candidate_id(candidate)
        assert candidate["sourceId"] == document["sourceId"]
        assert candidate["sourceSha256"] == document["sourceSha256"]
        assert candidate["sourceHashStatus"] == "carried-from-normalization"
        assert candidate["analysisTextSha256"] == document["analysisTextSha256"]
        assert candidate["normalizationVersion"] == document["normalizationVersion"]
        assert candidate["schemaVersion"] == "time-candidate-v1"
        assert candidate["extractionVersion"] == "extract-v1"
        assert candidate["ruleId"]
        assert candidate["context"] == candidate["excerpt"]
        assert candidate["quoteBefore"] + candidate["quoteTime"] + candidate["quoteAfter"] == candidate["excerpt"]
        assert candidate["quoteTime"] == candidate["matchedText"]
        excerpt_bytes = candidate["excerpt"].encode("utf-8")
        assert analysis_bytes[candidate["excerptStartByte"] : candidate["excerptEndByte"]] == excerpt_bytes
        match_within_excerpt = start - candidate["excerptStartByte"]
        assert len(candidate["quoteBefore"].encode("utf-8")) == match_within_excerpt


def test_extract_is_byte_deterministic(run_ltc, tmp_path: Path) -> None:
    normalized = normalized_fixture(run_ltc, tmp_path)
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"

    first_result = run_ltc("extract", "--input", normalized, "--output", first)
    second_result = run_ltc("extract", "--input", normalized, "--output", second)

    assert first_result.returncode == second_result.returncode == 0
    assert first.read_bytes() == second.read_bytes()


def test_extract_rejects_tampered_normalized_hash_without_output(run_ltc, tmp_path: Path) -> None:
    normalized = normalized_fixture(run_ltc, tmp_path)
    document = json.loads(normalized.read_text(encoding="utf-8"))
    document["analysisText"] += "tampered"
    normalized.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "candidates.jsonl"

    result = run_ltc("extract", "--input", normalized, "--output", output)

    assert result.returncode == 2
    assert json.loads(result.stderr) == {
        "error": {
            "code": "invalid-normalized-source",
            "message": "analysis text hash does not match its content",
        }
    }
    assert not output.exists()


def test_extract_rejects_source_hash_inconsistent_with_source_identity(run_ltc, tmp_path: Path) -> None:
    normalized = normalized_fixture(run_ltc, tmp_path)
    document = json.loads(normalized.read_text(encoding="utf-8"))
    document["sourceSha256"] = "0" * 64
    normalized.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "candidates.jsonl"

    result = run_ltc("extract", "--input", normalized, "--output", output)

    assert result.returncode == 2
    assert json.loads(result.stderr) == {
        "error": {
            "code": "invalid-normalized-source",
            "message": "source identity is inconsistent with carried source hash",
        }
    }
    assert not output.exists()
